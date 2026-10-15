"""Versioned reference library: discover, acquire, audit, read all, synthesize.

This store is separate from fiction Canon. Model notes are evidence-bearing
interpretations, never a certificate of completeness or reader acceptance.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import os
from pathlib import Path
import re
import time
import uuid

from .engine import canonical, checked_path, identifier, now
from .reference_io import MAX_BYTES, download, extract, sha
from . import reference_model

UNIT_CHARS = 100_000
VERSION = 1


def units(text, size=UNIT_CHARS):
    """Disjoint, contiguous, lossless coverage, including appendices/front matter."""
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        yield {"id": f"chars-{start}-{end}", "start": start, "end": end, "text": text[start:end]}
        start = end


def _validate(value, schema):
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("Invalid reference result enum")
    kind = schema.get("type")
    if isinstance(kind, list):
        if value is None and "null" in kind:
            return
        kind = next(x for x in kind if x != "null")
    types = {"object": dict, "array": list, "string": str, "integer": int}
    if kind in types and type(value) is not types[kind]:
        raise ValueError("Invalid reference result type: " + kind)
    if kind == "object":
        if set(value) != set(schema["properties"]):
            raise ValueError("Invalid reference result fields")
        for key, child in schema["properties"].items():
            _validate(value[key], child)
    elif kind == "array":
        if len(value) > 2000:
            raise ValueError("Excessive reference result items")
        for child in value:
            _validate(child, schema["items"])


def validate_result(mode, result, packet):
    from urllib.parse import urlsplit
    _validate(result, reference_model.SCHEMAS[mode])
    if mode == "read":
        if result["unit_id"] != packet["unit_id"] or not result["summary"].strip() or not result["findings"]:
            raise ValueError("Reading needs the exact unit id, summary and evidence")
        for finding in result["findings"]:
            if not finding["claim"].strip() or not finding["quote"].strip() or finding["quote"] not in packet["text"]:
                raise ValueError("Reading evidence is not an exact source substring")
            if len(finding["quote"]) > 1200:
                raise ValueError("Reference evidence must be a short quote")
    elif mode == "discover":
        seen = set()
        for work in result["works"]:
            identifier(work["id"])
            if work["id"] in seen or not work["title"].strip() or not work["author"].strip() or not work["sources"]:
                raise ValueError("Catalogue requires unique ids and source-backed identity")
            seen.add(work["id"])
            for key in ("expected_chapters", "expected_words"):
                if work[key] is not None and work[key] <= 0:
                    raise ValueError("Expected counts must be positive or unknown")
            for source in work["sources"]:
                parsed = urlsplit(source["url"])
                if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Invalid bibliographic URL")
                if not source["title"].strip():
                    raise ValueError("Source title required")
                date.fromisoformat(source["accessed"])
            for candidate in work["downloads"]:
                if urlsplit(candidate["url"]).scheme != "https":
                    raise ValueError("Download candidates must use HTTPS")
    else:
        ids = {entry["id"] for entry in packet["evidence"]}
        if not result["summary"].strip():
            raise ValueError("Synthesis summary required")
        for conclusion in result["conclusions"] + result["revisions"]:
            if not conclusion["evidence_ids"] or not set(conclusion["evidence_ids"]) <= ids:
                raise ValueError("Synthesis cites absent evidence")
    return result


def _normal(value):
    return re.sub(r"[^\w]", "", value.casefold())


class ReferenceLibrary:
    def __init__(self, root, reference_id):
        self.root = Path(root).resolve()
        self.id = identifier(reference_id)
        self.base = checked_path(self.root, "runtime/references/library/" + self.id)

    def path(self, relative):
        return checked_path(self.root, "runtime/references/library/" + self.id + "/" + relative)

    @contextmanager
    def lock(self):
        self.base.mkdir(parents=True, exist_ok=True)
        with self.path("writer.lock").open("a+b") as stream:
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("Reference library already has an active writer") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def load(self):
        data = json.loads(self.path("state.json").read_text(encoding="utf-8"))
        if data.get("schema_version") != VERSION or data.get("id") != self.id:
            raise ValueError("Unsupported reference state")
        return data

    def save(self, state):
        temp = self.path("state-" + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            for attempt in range(4):
                try:
                    os.replace(temp, self.path("state.json"))
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == 3:
                        raise
                    time.sleep(0.05 * (2 ** attempt))
        finally:
            temp.unlink(missing_ok=True)

    def artifact(self, relative, data):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Immutable reference artifact changed: " + relative)
        else:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        return {"path": relative, "sha256": sha(data)}

    def read_artifact(self, record):
        data = self.path(record["path"]).read_bytes()
        if sha(data) != record["sha256"]:
            raise ValueError("Reference artifact hash mismatch: " + record["path"])
        return data

    @staticmethod
    def work(work_id, title, author, language="unknown", kind="volume"):
        return {"id": identifier(work_id), "title": title, "author": author, "kind": kind,
                "language": language, "edition": "unknown", "order": "unknown", "sources": [],
                "expected_chapters": None, "expected_words": None, "downloads": []}

    def add(self, file, title, author, *, work_id=None, language="unknown", kind="volume", original=None):
        if not title.strip() or not author.strip():
            raise ValueError("Reference title and author are required")
        if kind not in ("volume", "extra", "appendix", "standalone"):
            raise ValueError("Invalid reference work kind")
        file = Path(file)
        if file.stat().st_size > MAX_BYTES or (original and Path(original).stat().st_size > MAX_BYTES):
            raise ValueError("Reference exceeds 32 MiB")
        data = file.read_bytes()
        with self.lock():
            if self.path("state.json").exists():
                state = self.load()
            else:
                state = {"schema_version": VERSION, "id": self.id, "seed": {"title": title, "author": author},
                         "series": title, "works": {}, "editions": [], "jobs": {}, "downloads": {},
                         "discovery_generation": 0, "discovery_history": [], "discovery_gaps": ["尚未联网核对系列、番外和附录"],
                         "authorized_urls": {}, "stop": None, "resumptions": [], "bindings": [], "series_reports": []}
            wid = identifier(work_id or self.id)
            existing = state["works"].get(wid)
            if existing and (_normal(existing["title"]), _normal(existing["author"])) != (_normal(title), _normal(author)):
                raise ValueError("Work id already names a different title/author")
            state["works"].setdefault(wid, self.work(wid, title, author, language, kind))
            self._ingest(state, wid, data, file.suffix, {"kind": "user_file", "name": file.name, "scope": "unknown"}, original)
            state["report_stale"] = True
            state["active_series_job"] = None
            state["cycle_open"] = False
            self.save(state)
        return self.status()

    def _ingest(self, state, wid, data, suffix, provenance, original=None):
        suffix = suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        digest = sha(data)
        eid = wid + ":" + digest
        if any(e["id"] == eid for e in state["editions"]):
            return
        source = self.artifact(f"sources/{digest}{suffix}", data)
        edition = {"id": eid, "work_id": wid, "source": source, "provenance": provenance, "imported_at": now(),
                   "text": None, "integrity": None, "analysis_jobs": [], "reports": [], "error": None}
        if original:
            raw = Path(original).read_bytes()
            raw_suffix = Path(original).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,10}", raw_suffix):
                raw_suffix = ".bin"
            edition["original"] = self.artifact(f"sources/{sha(raw)}{raw_suffix}", raw)
        try:
            text, integrity = extract(data, suffix)
            work = state["works"][wid]
            titles = integrity["metadata"].get("title", [])
            if titles and not any(_normal(work["title"]) in _normal(t) for t in titles):
                raise ValueError("identity_mismatch: embedded title differs from the requested work")
            authors = integrity["metadata"].get("creator", [])
            expected_author = set(re.findall(r"\w+", work["author"].casefold()))
            if authors and not any(expected_author <= set(re.findall(r"\w+", a.casefold())) for a in authors):
                integrity["issues"].append("author_identity_unverified")
            languages = integrity["metadata"].get("language", [])
            if work["language"] != "unknown" and languages and not any(x.split("-")[0] == work["language"].split("-")[0] for x in languages):
                integrity["issues"].append("original_language_mismatch")
            if provenance["kind"] == "download" and not titles and _normal(work["title"]) not in _normal(text[:8000]):
                raise ValueError("identity_unverified: downloaded text does not identify the requested title")
            edition["text"] = self.artifact(f"texts/{sha(text.encode('utf-8'))}.txt", text.encode("utf-8"))
            edition["integrity"] = integrity
        except Exception as exc:
            # Extraction failure is a preserved gap, not a reason to discard the original.
            # Parser exceptions vary by optional format; no executable format is run.
            edition["error"] = f"{type(exc).__name__}: {exc}"
        state["editions"].append(edition)

    def allow_source(self, url, basis, evidence_url, note):
        from urllib.parse import urlsplit
        if basis not in ("author_publication", "open_license", "owned_access") or not note.strip():
            raise ValueError("An explicit rights basis and evidence note are required")
        for value in (url, evidence_url):
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Authorized source must be an HTTPS URL without credentials")
        with self.lock():
            state = self.load()
            state["authorized_urls"][url] = {"basis": basis, "evidence_url": evidence_url, "note": note, "registered_at": now()}
            self.save(state)
        return {"url": url, "registered": True}

    def _job(self, state, mode, packet, runner, budget, timeout):
        # A new date alone must not reset a failed bibliography attempt budget.
        # Successful refreshes already advance discovery_generation explicitly.
        identity_packet = {k: v for k, v in packet.items() if k != "as_of"} if mode == "discover" else packet
        key = sha(canonical({"version": VERSION, "mode": mode, "packet": identity_packet}).encode())
        job = state["jobs"].get(key)
        if job and job["status"] == "completed":
            result = json.loads(self.read_artifact(job["result"]))
            validate_result(mode, result, packet)
            return key, result
        if job and job["status"] == "blocked":
            return key, None
        if state["stop"] or budget[0] <= 0:
            return key, None
        if job and job["status"] == "running":
            state["stop"] = {"reason": "interrupted", "job": key, "detail": "Previous attempt did not finish; explicit resume note required"}
            self.save(state)
            return key, None
        if job and job["attempts"] >= 3:
            state["stop"] = {"reason": "attempt_limit", "job": key, "detail": "Three cumulative attempts exhausted; inspect inputs and logs"}
            self.save(state)
            return key, None
        job = state["jobs"].setdefault(key, {"mode": mode, "attempts": 0, "status": "pending"})
        job.update(attempts=job["attempts"] + 1, status="running")
        self.save(state)
        directory = self.path(f"jobs/{key}/attempt-{job['attempts']}")
        budget[0] -= 1
        try:
            result = runner(mode, packet, directory, timeout)
            validate_result(mode, result, packet)
            record = self.artifact(f"jobs/{key}/accepted.json", (canonical(result) + "\n").encode("utf-8"))
            job.update(status="completed", result=record, completed_at=now())
            self.save(state)
            return key, result
        except (Exception, KeyboardInterrupt) as exc:
            job.update(status="blocked", error=f"{type(exc).__name__}: {exc}")
            state["stop"] = {"reason": getattr(exc, "reason", "tool_failure"), "job": key, "detail": job["error"]}
            self.save(state)
            if isinstance(exc, KeyboardInterrupt):
                raise
            return key, None

    def _catalogue(self, state, result, job_id):
        for item in result["works"]:
            # Stable local ids survive a discovery model choosing a different slug.
            same = next((w for w in state["works"].values() if (_normal(w["title"]), _normal(w["author"])) == (_normal(item["title"]), _normal(item["author"]))), None)
            wid = same["id"] if same else item["id"]
            if wid in state["works"] and not same:
                raise ValueError("Discovered id collides with an existing work")
            state["works"][wid] = {**item, "id": wid}
        state["series"] = result["series"]
        state["discovery_gaps"] = result["gaps"]
        state["discovery_history"].append({"job": job_id, "at": now()})
        state["discovery_generation"] += 1
        self.save(state)

    def _acquire(self, state, fetcher, resume):
        for work in state["works"].values():
            # Local structural readability does not establish that all edition
            # supplements are present. Inspect newly discovered full candidates
            # even when the supplied copy parses cleanly; retain both versions.
            for candidate in work["downloads"]:
                url = candidate["url"]
                if candidate["scope"] != "full":
                    continue
                previous = state["downloads"].get(url)
                if previous and (previous["status"] == "acquired" or previous["attempts"] >= 3 or not resume):
                    continue
                record = {"work_id": work["id"], "status": "attempting", "attempts": (previous or {}).get("attempts", 0) + 1, "at": now()}
                state["downloads"][url] = record
                self.save(state)
                try:
                    data, suffix, receipt = fetcher(url, tuple(state["authorized_urls"]))
                    self._ingest(state, work["id"], data, suffix, {"kind": "download", "scope": "full", **receipt})
                    added = next(e for e in state["editions"] if e["id"] == work["id"] + ":" + sha(data))
                    record.update(status="acquired" if added["text"] and not added["error"] else "unreadable", edition=added["id"], error=added["error"])
                except Exception as exc:
                    record.update(status="unavailable", error=f"{type(exc).__name__}: {exc}")
                self.save(state)
                if record["status"] == "acquired":
                    break

    @staticmethod
    def _edition_gaps(work, edition):
        if edition["error"] or not edition["integrity"]:
            return [edition["error"] or "No readable text"]
        report = edition["integrity"]
        gaps = list(report["issues"])
        heading_count = len(set(report["headings"]))
        if work["expected_chapters"] is not None and heading_count != work["expected_chapters"]:
            gaps.append(f"chapter_count_mismatch: {heading_count} / {work['expected_chapters']} (heading detector is heuristic)")
        english_count = work["language"].lower() in ("en", "eng", "english") or work["language"].lower().startswith("en-")
        if work["expected_words"] and english_count and report["word_count"] < work["expected_words"] * .85:
            gaps.append(f"word_count_shortfall: {report['word_count']} / approximately {work['expected_words']}")
        elif work["expected_words"] and not english_count:
            gaps.append("count_units_unverified: 未将英文词元计数与其他语言的字数/词数直接比较")
        return gaps

    def run(self, *, max_calls=24, timeout=600, resume_note=None, runner=None, fetcher=None):
        if type(max_calls) is not int or not 0 <= max_calls <= 100:
            raise ValueError("max_calls must be 0-100")
        if resume_note is not None and not resume_note.strip():
            raise ValueError("Explicit nonempty resume note required")
        runner = runner or reference_model.run
        fetcher = fetcher or download
        budget = [max_calls]
        with self.lock():
            state = self.load()
            if resume_note:
                state["resumptions"].append({"at": now(), "note": resume_note, "previous_stop": state["stop"]})
                for job in state["jobs"].values():
                    if job["status"] in ("running", "blocked"):
                        job["status"] = "interrupted"
                state.pop("discovery_blocked", None)
                state["stop"] = None
                self.save(state)
            unfinished = next((key for key, job in state["jobs"].items() if job["status"] == "running"), None)
            if unfinished and not state["stop"]:
                state["stop"] = {"reason": "interrupted", "job": unfinished, "detail": "Previous attempt did not finish; explicit resume note required"}
                self.save(state)
            if state["stop"]:
                result = self.status()
                result["last_run"] = {"at": now(), "model_calls": 0, "call_limit": max_calls, "budget_exhausted": False}
                return result
            # Never send manuscript, source text or past private analysis to search.
            packet = {"seed": state["seed"], "known_works": list(state["works"].values()),
                      "refresh": state["discovery_generation"], "as_of": now()[:10]}
            continuing = state.get("cycle_open", state.get("last_run", {}).get("budget_exhausted", False)) and state["discovery_history"] and not state.get("discovery_blocked")
            if continuing:
                # Continue a budget-paused reading cycle without paying for the
                # same completed bibliography search again.
                catalog = None
                self._acquire(state, fetcher, bool(resume_note))
            else:
                job_id, catalog = (None, None) if state.get("discovery_blocked") else self._job(state, "discover", packet, runner, budget, timeout)
                if catalog is not None:
                    self._catalogue(state, catalog, job_id)
                    self._acquire(state, fetcher, bool(resume_note))
            if catalog is None and state["stop"] and state["stop"]["reason"] == "tool_failure":
                # Bibliography/search outages do not prevent reading already held
                # material. Quota/authentication stops still apply to all calls.
                state["discovery_blocked"] = state["stop"]
                state["discovery_gaps"] = ["本次书目查询失败，需明确接续后重试: " + state["stop"]["detail"]]
                state["stop"] = None
                self.save(state)
            evidence = []
            state["active_series_job"] = None
            for edition in state["editions"]:
                edition["active_report"] = None
                work = state["works"][edition["work_id"]]
                try:
                    self.read_artifact(edition["source"])
                    if edition.get("original"):
                        self.read_artifact(edition["original"])
                    if not edition["text"]:
                        continue
                    text = self.read_artifact(edition["text"]).decode("utf-8")
                except (OSError, ValueError) as exc:
                    edition["verification_error"] = str(exc)
                    self.save(state)
                    continue
                edition.pop("verification_error", None)
                reading = []
                for unit in units(text):
                    packet = {"work": {k: work[k] for k in ("id", "title", "author")},
                              "source_sha256": edition["source"]["sha256"], "text_sha256": edition["text"]["sha256"],
                              "unit_id": unit["id"], "start": unit["start"], "end": unit["end"],
                              "text": unit["text"]}
                    key, result = self._job(state, "read", packet, runner, budget, timeout)
                    if key not in edition["analysis_jobs"]:
                        edition["analysis_jobs"].append(key)
                    if result is not None:
                        reading.append({"id": key, "unit_id": unit["id"], "start": unit["start"], "end": unit["end"], "analysis": result})
                    self.save(state)
                if not reading:
                    continue
                previous = self._previous(state, edition["reports"])
                packet = {"scope": "edition", "work": work, "source_sha256": edition["source"]["sha256"],
                          "evidence": reading, "coverage": {"total_chars": len(text), "covered_chars": sum(r["end"] - r["start"] for r in reading)},
                          "known_gaps": self._edition_gaps(work, edition) + ["未与出版社完整正文逐字核对"],
                          "previous_report": previous}
                # Prior report is supplied only when evidence changes, to keep cache keys stable.
                signature = sha(canonical({k: v for k, v in packet.items() if k != "previous_report"}).encode())
                cached = next((r for r in edition["reports"] if r["signature"] == signature), None)
                if cached:
                    key = cached["job"]
                    result = json.loads(self.read_artifact(state["jobs"][key]["result"]))
                else:
                    key, result = self._job(state, "synthesize", packet, runner, budget, timeout)
                    if result is not None:
                        edition["reports"].append({"signature": signature, "job": key, "at": now()})
                if result is not None:
                    edition["active_report"] = key
                    evidence.append({"id": key, "work_id": work["id"], "title": work["title"], "edition": edition["id"], "analysis": result})
                self.save(state)
            if evidence:
                packet = {"scope": "series", "series": state["series"], "evidence": evidence,
                          "known_gaps": self._gaps(state), "previous_report": self._previous(state, state["series_reports"])}
                signature = sha(canonical({k: v for k, v in packet.items() if k != "previous_report"}).encode())
                cached = next((r for r in state["series_reports"] if r["signature"] == signature), None)
                if cached:
                    self.read_artifact(state["jobs"][cached["job"]]["result"])
                    state["active_series_job"] = cached["job"]
                else:
                    key, result = self._job(state, "synthesize", packet, runner, budget, timeout)
                    if result is not None:
                        state["series_reports"].append({"signature": signature, "job": key, "at": now()})
                        state["active_series_job"] = key
            state["last_run"] = {"at": now(), "model_calls": max_calls - budget[0], "call_limit": max_calls,
                                 "budget_exhausted": budget[0] == 0}
            state["cycle_open"] = any(e["text"] and not e.get("active_report") for e in state["editions"]) or (bool(evidence) and not state.get("active_series_job"))
            self.save(state)
            report = self.render(state)
            artifact = self.artifact("reports/" + sha(report.encode()) + ".md", report.encode("utf-8"))
            state["latest_report"] = artifact
            state["report_stale"] = False
            self.save(state)
        return self.status()

    def _previous(self, state, reports):
        if not reports:
            return None
        return json.loads(self.read_artifact(state["jobs"][reports[-1]["job"]]["result"]))

    def _coverage(self, state, edition):
        if not edition["text"] or edition.get("verification_error"):
            return 0, 0
        text = self.read_artifact(edition["text"]).decode("utf-8")
        done = set()
        for key in edition["analysis_jobs"]:
            job = state["jobs"].get(key)
            if job and job["status"] == "completed":
                result = json.loads(self.read_artifact(job["result"]))
                done.add(result["unit_id"])
        all_units = list(units(text))
        return sum(len(u["text"]) for u in all_units if u["id"] in done), len(text)

    def _gaps(self, state):
        gaps = list(state["discovery_gaps"])
        if not state["discovery_history"]:
            gaps.append("系列书目、番外和附录尚未完成联网核验")
        for work in state["works"].values():
            editions = [e for e in state["editions"] if e["work_id"] == work["id"]]
            if not editions:
                gaps.append(work["title"] + ": 缺全文；只有书目，不能据此分析内容")
            for edition in editions:
                gaps.extend(work["title"] + ": " + g for g in self._edition_gaps(work, edition))
                if edition.get("verification_error"):
                    gaps.append(work["title"] + ": " + edition["verification_error"])
                    continue
                try:
                    done, total = self._coverage(state, edition)
                    if total and done < total:
                        gaps.append(f"{work['title']}: 阅读覆盖 {done}/{total} 字符，尚未读完")
                    if total and not edition.get("active_report"):
                        gaps.append(work["title"] + ": 全书综合尚未完成")
                except (ValueError, OSError) as exc:
                    gaps.append(work["title"] + ": " + str(exc))
        gaps.extend("获取失败 " + url + ": " + record.get("error", record["status"])
                    for url, record in state["downloads"].items() if record["status"] != "acquired")
        if state["stop"]:
            gaps.append("执行停止: " + state["stop"]["detail"])
        return list(dict.fromkeys(gaps))

    def status(self):
        state = self.load()
        editions = []
        for e in state["editions"]:
            errors = []
            try:
                self.read_artifact(e["source"])
                if e.get("original"):
                    self.read_artifact(e["original"])
                done, total = self._coverage(state, e)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
                done, total = 0, 0
            editions.append({"id": e["id"], "title": state["works"][e["work_id"]]["title"],
                             "read_chars": done, "total_chars": total, "all_units_analyzed": bool(total and done == total and not errors),
                             "synthesis_available": bool(e["reports"]), "integrity": e["integrity"],
                             "synthesis_current": bool(e.get("active_report")) and not errors,
                             "errors": errors + ([e["error"]] if e["error"] else [])})
        return {"id": self.id, "series": state["series"], "catalogued_works": len(state["works"]),
                "editions": editions, "gaps": self._gaps(state), "stop": state["stop"],
                "series_analysis_available": bool(state["series_reports"]),
                "series_analysis_current": bool(state.get("active_series_job")) and not state.get("report_stale", True),
                "all_acquired_content_analyzed": bool(editions) and all(e["all_units_analyzed"] and e["synthesis_current"] for e in editions),
                "report": str(self.path(state["latest_report"]["path"])) if state.get("latest_report") else None,
                "last_run": state.get("last_run"), "completeness": "not_certified",
                "reading_evidence": "all text units delivered to model with validated exact quotes; not proof of comprehension"}

    def render(self, state=None):
        state = state or self.load()
        lines = [f"# 参考系列：{state['series']}", "", f"资料库：{self.id}", "",
                 "分析是模型解释；完整性未获出版社全文逐字认证。未取得材料不参与内容结论，参考资料不自动进入 Canon。", "", "## 书目与来源", ""]
        for w in state["works"].values():
            lines.append(f"- {w['title']} / {w['author']} / {w['kind']} / {w['language']} / {w['edition']}")
            for s in w["sources"]:
                lines.append(f"  - [{s['title']}]({s['url']})（{s['accessed']}）")
        lines.extend(["", "## 缺口", ""] + ["- " + g for g in self._gaps(state)])
        for e in state["editions"]:
            lines.extend(["", "## " + state["works"][e["work_id"]]["title"], "", "底本 SHA-256：" + e["source"]["sha256"], ""])
            report = (json.loads(self.read_artifact(state["jobs"][e["active_report"]]["result"]))
                      if e.get("active_report") else self._previous(state, e["reports"]))
            if report:
                if not e.get("active_report"):
                    lines.append("以下是历史分析，当前版本/覆盖尚未重新综合。\n")
                lines.append(report["summary"])
                for c in report["conclusions"]:
                    lines.append("\n- " + c["claim"] + "（证据：" + ", ".join(c["evidence_ids"]) + "）")
                for r in report["revisions"]:
                    lines.append("\n- 修订：" + r["previous_claim"] + " → " + r["revised_claim"] + "（证据：" + ", ".join(r["evidence_ids"]) + "）")
                lines.extend("\n- 分析限制：" + g for g in report["gaps"])
        report = (json.loads(self.read_artifact(state["jobs"][state["active_series_job"]]["result"]))
                  if state.get("active_series_job") else self._previous(state, state["series_reports"]))
        if report:
            heading = "## 系列综合" if state.get("active_series_job") else "## 历史系列综合（当前尚未完成复核）"
            lines.extend(["", heading, "", report["summary"]])
            lines.extend("\n- " + c["claim"] + "（证据：" + ", ".join(c["evidence_ids"]) + "）" for c in report["conclusions"])
            lines.extend("\n- 修订：" + r["previous_claim"] + " → " + r["revised_claim"] for r in report["revisions"])
            lines.extend("\n- 分析限制：" + g for g in report["gaps"])
        return "\n".join(lines) + "\n"

    def bind(self, engine, book):
        """Append a version-bound report without replacing history or importing Canon."""
        with self.lock():
            state = self.load()
            report = self.render(state)
            text = f"<!-- novel-reference:{self.id} report:{sha(report.encode())} -->\n" + report
            files = engine.files(book)
            if text not in files.values():
                result = engine.reference(book, text)
            else:
                result = {"book_id": book, "unchanged": True}
            if book not in state["bindings"]:
                state["bindings"].append(book)
            self.save(state)
            return result


def refresh_bound(engine, book, *, max_calls=24, timeout=600):
    """CLI task creation refreshes previously attached libraries before pinning input."""
    ids = set()
    for path, content in engine.files(book).items():
        if path.startswith("reference/"):
            ids.update(re.findall(r"<!-- novel-reference:([a-z0-9_-]+) report:[0-9a-f]{64} -->", content))
    if ids and any(t["status"] in ("running", "submitted") for t in engine.tasks(book)):
        raise ValueError("Finish or cancel executing tasks before refreshing bound references")
    results = []
    remaining = max_calls
    for ref_id in sorted(ids):
        library = ReferenceLibrary(engine.root, ref_id)
        result = library.run(max_calls=remaining, timeout=timeout)
        results.append(result)
        remaining -= result.get("last_run", {}).get("model_calls", 0)
        library.bind(engine, book)
    return results
