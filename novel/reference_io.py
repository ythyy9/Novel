"""Reference extraction and bounded downloads. No DRM removal or executable imports."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import io
import ipaddress
from pathlib import Path
import posixpath
import re
import socket
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET
import zipfile

MAX_BYTES = 32 * 1024 * 1024
MAX_EXPANDED = 96 * 1024 * 1024
PUBLIC_HOSTS = {"www.gutenberg.org", "gutenberg.org", "standardebooks.org"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if not self.skip and tag in ("p", "div", "br", "h1", "h2", "h3", "li", "section"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if not self.skip and tag in ("p", "div", "h1", "h2", "h3", "li", "section"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        return re.sub(r"\n[ \t]*\n+", "\n\n", "".join(self.parts)).strip()


def html_text(value):
    parser = TextHTML()
    parser.feed(value)
    return parser.text()


def _xml(data):
    if b"<!ENTITY" in data.upper() or b"<!DOCTYPE" in data.upper():
        # EPUB XHTML commonly has a simple HTML doctype, but no entity expansion.
        if b"<!ENTITY" in data.upper() or b"[" in data.split(b">", 1)[0]:
            raise ValueError("XML entity declarations are unsupported")
    return ET.fromstring(data)


def _member(base, href):
    url = urlsplit(href)
    if url.scheme or url.netloc or "\\" in href:
        raise ValueError("External EPUB resource")
    name = posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(url.path))) if url.path else base
    if name.startswith(("/", "../")) or name == "..":
        raise ValueError("EPUB resource escapes archive")
    return name, unquote(url.fragment)


def extract(data: bytes, suffix: str):
    """Return all readable text, metadata and structural findings; never certify completeness."""
    if len(data) > MAX_BYTES:
        raise ValueError("Reference exceeds 32 MiB")
    suffix = suffix.lower()
    metadata, issues, sections, toc = {}, [], [], []
    if suffix in (".txt", ".md"):
        text = data.decode("utf-8-sig")
        sections = [{"label": "text", "text": text}]
    elif suffix in (".html", ".htm", ".xhtml"):
        sections = [{"label": "document", "text": html_text(data.decode("utf-8-sig"))}]
        issues.append("html_scope_unverified: 页面可能包含导航或只是一篇节选")
    elif suffix == ".epub":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > 10000:
                raise ValueError("Duplicate or excessive EPUB members")
            if sum(x.file_size for x in archive.infolist()) > MAX_EXPANDED:
                raise ValueError("EPUB expanded size exceeds limit")
            if archive.testzip() is not None:
                raise ValueError("EPUB CRC failure")
            container = _xml(archive.read("META-INF/container.xml"))
            opf = next(x.attrib["full-path"] for x in container.iter() if x.tag.endswith("}rootfile"))
            opf, _ = _member("", opf)
            package = _xml(archive.read(opf))
            for element in package.iter():
                local = element.tag.rsplit("}", 1)[-1]
                if local in ("title", "creator", "language", "identifier", "description") and element.text:
                    metadata.setdefault(local, []).append(element.text.strip())
            manifest = {x.attrib["id"]: x.attrib for x in package.iter() if x.tag.endswith("}item")}
            for item in manifest.values():
                try:
                    name, _ = _member(opf, item["href"])
                    if name not in names:
                        issues.append("missing_resource: " + name)
                except ValueError:
                    issues.append("external_resource: " + item["href"])
            seen = set()
            for item in package.iter():
                if not item.tag.endswith("}itemref"):
                    continue
                entry = manifest.get(item.attrib.get("idref"))
                if entry is None:
                    issues.append("missing_spine_id: " + str(item.attrib.get("idref")))
                    continue
                name, _ = _member(opf, entry["href"])
                if name in seen:
                    issues.append("duplicate_spine: " + name)
                    continue
                seen.add(name)
                if name not in names:
                    continue
                if entry.get("media-type") not in ("application/xhtml+xml", "text/html"):
                    issues.append("unreadable_spine_resource: " + name)
                    continue
                content = html_text(archive.read(name).decode("utf-8-sig"))
                if not content.strip():
                    issues.append("empty_spine_text: " + name)
                sections.append({"label": name, "text": content})
            for entry in manifest.values():
                is_ncx = entry.get("media-type") == "application/x-dtbncx+xml"
                is_nav = "nav" in entry.get("properties", "").split()
                if not (is_ncx or is_nav):
                    continue
                name, _ = _member(opf, entry["href"])
                if name not in names:
                    continue
                tree = _xml(archive.read(name))
                for element in tree.iter():
                    local = element.tag.rsplit("}", 1)[-1]
                    href = element.attrib.get("src") if is_ncx and local == "content" else element.attrib.get("href") if is_nav and local == "a" else None
                    if not href:
                        continue
                    try:
                        target, anchor = _member(name, href)
                        if target not in names:
                            issues.append("broken_toc: " + href)
                        elif anchor:
                            doc = _xml(archive.read(target))
                            if not any(anchor in (x.attrib.get("id"), x.attrib.get("name"), x.attrib.get("{http://www.w3.org/XML/1998/namespace}id")) for x in doc.iter()):
                                issues.append("broken_toc_anchor: " + href)
                        toc.append(href)
                    except ValueError:
                        issues.append("external_toc: " + href)
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF extraction needs optional pypdf; original retained, supply EPUB/TXT or install pypdf") from exc
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF requires an accessible copy; no DRM removal")
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            sections.append({"label": f"page-{number}", "text": text})
            if not text.strip():
                issues.append(f"unreadable_page: {number}; OCR required")
        issues.append("pdf_reading_order_unverified")
    else:
        raise ValueError("Unsupported format; original retained, supply UTF-8 TXT, EPUB, HTML or optional text PDF")
    text = "\n\n".join(x["text"] for x in sections)
    if not text.strip():
        raise ValueError("No readable text; OCR or an accessible edition is required")
    labels = re.findall(r"(?im)^\s*(?:chapter\s+[\w -]+|第[一二三四五六七八九十百零〇\d]+[章回节])\s*$", text)
    headings = list(dict.fromkeys(x.strip() for x in labels))
    numbers = list(dict.fromkeys(int(x) for x in re.findall(r"(?im)^\s*chapter\s+(\d+)\s*$", text)))
    if numbers and numbers != list(range(1, max(numbers) + 1)):
        issues.append("chapter_number_gap_or_order")
    if "\ufffd" in text:
        issues.append("replacement_characters")
    if any(re.search(r"\b(sample|abridged|excerpt)\b", value, re.I) for value in metadata.get("title", [])):
        issues.append("sample_or_abridgment_in_title")
    return text, {"metadata": metadata, "section_count": len(sections), "headings": headings, "heading_occurrences": len(labels),
                  "toc_targets": len(toc), "word_count": len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", text)),
                  "word_count_unit": "ASCII English word tokens; not Chinese character count",
                  "characters": len(text), "issues": sorted(set(issues)),
                  "status": "suspect" if issues else "structurally_readable_completeness_unverified",
                  "publisher_full_text_collated": False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS URLs without credentials are supported")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError("Non-public download address")
    return parsed


def download(url, allowed_urls=()):
    """Only known public-domain hosts or exact operator-registered authorized URLs.

    Redirects repeat all checks. No cookies, login automation or paid API. This
    is application validation, not a network sandbox against hostile DNS/proxies.
    """
    from urllib.error import HTTPError
    opener = build_opener(NoRedirect())
    original = url
    for _ in range(6):
        parsed = public_url(url)
        if parsed.hostname not in PUBLIC_HOSTS and url not in allowed_urls:
            raise ValueError("rights_unverified: download source is not registered as authorized")
        request = Request(url, headers={"User-Agent": "NovelReference/1.0", "Accept-Encoding": "identity"})
        try:
            response = opener.open(request, timeout=30)
        except HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                target = urlsplit(urljoin(url, exc.headers["Location"]))
                # Some public-domain endpoints advertise HTTP canonical links.
                # Request their HTTPS equivalent; never send a plaintext request.
                if target.scheme == "http" and target.hostname == parsed.hostname and parsed.hostname in PUBLIC_HOSTS:
                    target = target._replace(scheme="https")
                url = urlunsplit(target)
                exc.close()
                continue
            raise
        with response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("Download exceeds 32 MiB")
            content_type = response.headers.get_content_type()
            suffix = Path(unquote(parsed.path)).suffix.lower()
            if content_type == "application/epub+zip" or data.startswith(b"PK\x03\x04"):
                suffix = ".epub"
            elif data.startswith(b"%PDF-"):
                suffix = ".pdf"
            elif content_type == "text/plain":
                suffix = ".txt"
            elif content_type in ("text/html", "application/xhtml+xml"):
                suffix = ".html"
            if suffix not in (".epub", ".txt", ".html", ".htm", ".pdf", ".xhtml"):
                raise ValueError("Download is not a supported book format")
            return data, suffix, {"requested_url": original, "final_url": url, "content_type": content_type}
    raise ValueError("Too many redirects")
