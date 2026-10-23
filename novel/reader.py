"""Read-only chapter reader. Never initializes or mutates the writing controller."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .engine import EngineError, canonical, checked_path, digest, identifier

ASSETS = Path(__file__).with_name("reader_assets")
REVISION = re.compile(r"[0-9a-f]{64}\Z")
CHAPTER = re.compile(r"manuscript/(\d+)[^/]*\.(?:md|txt)\Z")


def chapters(files):
    result = []
    for path, text in files.items():
        match = CHAPTER.fullmatch(path)
        if not match:
            continue
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        number = int(match.group(1))
        title = (re.sub(r"^#{1,6}\s+", "", first)
                 if re.match(r"^#{1,6}\s+|^第[一二三四五六七八九十百零〇\d]+章", first)
                 else f"第{number}章")
        result.append({"id": path, "number": number,
                       "title": title or f"第{number}章", "characters": len(text),
                       "sha256": digest(text)})
    result.sort(key=lambda item: (item["number"], item["id"]))
    if len({item["number"] for item in result}) != len(result):
        raise EngineError("Duplicate chapter numbers; cannot identify the reading order")
    return result


class RootSource:
    """Resolve current revision from a read-only database; pin all chapter reads."""
    def __init__(self, root, book_id):
        self.root = Path(root).absolute()
        self.book_id = identifier(book_id)

    def _version(self, revision=None):
        database = checked_path(self.root, "runtime/novel.sqlite3")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            row = db.execute("SELECT b.id,b.title,b.current_revision,r.status,r.created_at "
                             "FROM books b JOIN revisions r ON r.id=b.current_revision "
                             "AND r.book_id=b.id WHERE b.id=?", (self.book_id,)).fetchone()
            if row is None:
                raise EngineError("Book is not available")
            book = dict(row)
            selected = revision or book["current_revision"]
            if not isinstance(selected, str) or not REVISION.fullmatch(selected):
                raise EngineError("Invalid revision")
            if not db.execute("SELECT 1 FROM revisions WHERE id=? AND book_id=?",
                              (selected, self.book_id)).fetchone():
                raise EngineError("Revision does not belong to this book")
        base = checked_path(self.root, f"books/{self.book_id}/versions/{selected}")
        manifest = json.loads(checked_path(base, "manifest.json").read_text(encoding="utf-8"))
        if digest(canonical(manifest)) != selected or manifest.get("book_id") != self.book_id:
            raise EngineError("Snapshot manifest integrity check failed")
        return book, selected, base, manifest

    @staticmethod
    def _text(base, path, expected):
        raw = checked_path(base, path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise EngineError("Chapter integrity check failed")
        return raw.decode("utf-8")

    def catalog(self):
        book, revision, base, manifest = self._version()
        files = {p: self._text(base, p, sha) for p, sha in manifest["hashes"].items()
                 if CHAPTER.fullmatch(p)}
        return {"book": book, "revision": revision, "chapters": chapters(files),
                "source_mode": "live", "checked_at": datetime.now(timezone.utc).isoformat()}

    def chapter(self, revision, path):
        if not isinstance(path, str) or not CHAPTER.fullmatch(path):
            raise EngineError("Unknown chapter")
        _, _, base, manifest = self._version(revision)
        expected = manifest["hashes"].get(path)
        if expected is None:
            raise EngineError("Chapter is not in this revision")
        return {"revision": revision, "id": path, "sha256": expected,
                "text": self._text(base, path, expected)}


class ExportSource:
    """A verified private read copy, explicitly distinguished from a live root."""
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (value.get("schema") != "novel-reader-export-v1"
                or not REVISION.fullmatch(value.get("revision", ""))
                or value["book"]["current_revision"] != value["revision"]):
            raise EngineError("Invalid reader export")
        for item in value["documents"]:
            if (not CHAPTER.fullmatch(item["path"])
                    or digest(item["text"]) != item["sha256"]
                    or len(item["text"]) != item["characters"]):
                raise EngineError("Reader export integrity check failed")
        paths = [item["path"] for item in value["documents"]]
        if len(set(paths)) != len(paths):
            raise EngineError("Duplicate chapter paths")
        return value

    def catalog(self):
        value = self._load()
        return {"book": value["book"], "revision": value["revision"],
                "source_mode": "verified_copy", "checked_at": value["checked_at"],
                "chapters": chapters({d["path"]: d["text"] for d in value["documents"]})}

    def chapter(self, revision, path):
        value = self._load()
        if revision != value["revision"]:
            raise EngineError("Reading copy updated; refresh the catalog")
        for item in value["documents"]:
            if item["path"] == path:
                return {"revision": revision, "id": path, "text": item["text"],
                        "sha256": item["sha256"]}
        raise EngineError("Unknown chapter")


def make_handler(source):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not log private chapter paths or browser requests.

        def reply(self, status, data, mime):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                             "style-src 'self'; connect-src 'self'; img-src 'self'; "
                             "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            # Loopback binding plus Host validation prevents DNS-rebinding reads.
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}",
                       f"localhost:{self.server.server_port}"}
            if host not in allowed or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.reply(403, b"Forbidden", "text/plain; charset=utf-8")
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/api/book":
                    value = source.catalog()
                elif parsed.path == "/api/chapter":
                    params = parse_qs(parsed.query, strict_parsing=True)
                    if set(params) != {"revision", "id"} or any(len(v) != 1 for v in params.values()):
                        raise EngineError("Invalid chapter query")
                    value = source.chapter(params["revision"][0], params["id"][0])
                elif parsed.path in {"/", "/index.html", "/reader.css", "/reader.js"}:
                    name = "index.html" if parsed.path == "/" else parsed.path[1:]
                    mime = {"html": "text/html", "css": "text/css", "js": "text/javascript"}[name.rsplit(".", 1)[1]]
                    self.reply(200, (ASSETS / name).read_bytes(), mime + "; charset=utf-8")
                    return
                else:
                    self.reply(404, b"Not found", "text/plain; charset=utf-8")
                    return
                self.reply(200, canonical(value).encode("utf-8"), "application/json; charset=utf-8")
            except (EngineError, OSError, ValueError, KeyError, sqlite3.Error):
                self.reply(409, canonical({"error": "正文暂时无法读取，请刷新目录重试；若仍失败，请检查资料完整性。"}).encode("utf-8"),
                           "application/json; charset=utf-8")
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private read-only Novel chapter reader")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--root", type=Path, help="Live formal data root; never defaults to an old checkout")
    inputs.add_argument("--snapshot", type=Path, help="Verified reader export; displays its verification time")
    parser.add_argument("--book", default="shizhi-zhicheng")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    source = RootSource(args.root, args.book) if args.root else ExportSource(args.snapshot)
    source.catalog()  # Fail before listening if the chosen source is invalid.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(source))
    print(f"Novel reader: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
