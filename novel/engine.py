"""Durable controller: SQLite is the authority, immutable snapshots carry content.

Files are flushed before a transaction publishes their pointer. A crash may leave
an unreferenced snapshot, but cannot publish a partial version. This is a local
integrity contract, not an OS security boundary against the same user account.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from .records import ValidationError, validate_path, validate_result


class EngineError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise EngineError("Identifier must contain 1-64 lowercase letters, digits, '-' or '_'")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        raise EngineError("Reserved identifier")
    return value


def checked_path(root: Path, relative: str) -> Path:
    """Reject junctions/symlinks as well as lexical escapes, on every access."""
    if not relative or "\\" in relative or ":" in relative:
        raise EngineError("Unsafe local path")
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise EngineError("Unsafe local path")
    path = root
    for part in (None, *parts):
        if part is not None:
            path = path / part
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise EngineError(f"Reparse points are not supported: {path}")
    def comparison_path(value):
        resolved = str(value.resolve())
        # On Windows, realpath may retain \\?\ when a missing parent is created
        # during resolution (ERROR_PATH_NOT_FOUND becomes ERROR_FILE_NOT_FOUND).
        # Compare the same drive/UNC namespace without changing the opened path
        # or skipping any of the reparse-point checks above.
        if os.name == "nt":
            if resolved.upper().startswith("\\\\?\\UNC\\"):
                resolved = "\\\\" + resolved[8:]
            elif re.match(r"^\\\\\?\\[A-Za-z]:\\", resolved):
                resolved = resolved[4:]
        return Path(resolved)

    if not comparison_path(path).is_relative_to(comparison_path(root)):
        raise EngineError("Path escapes project")
    return path


DEFAULT_LIMITS = {"schema_version": 1, "billing": "chatgpt_subscription", "max_attempts": 3,
                  "max_no_progress": 2, "max_result_bytes": 2_000_000}
EMPTY_STATE = {"knowledge": [], "characters": [], "world": [], "offstage": []}
STOP_REASONS = {"decision", "quota", "no_progress", "tool_failure", "authorization"}
KINDS = {"write", "revise", "research", "review"}
ACTIVE = ("running", "submitted", "blocked", "exhausted")

DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS books(id TEXT PRIMARY KEY, title TEXT NOT NULL, current_revision TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(
 id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id), parent TEXT,
 status TEXT NOT NULL, task_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id), kind TEXT NOT NULL,
 instruction TEXT NOT NULL, input_revision TEXT NOT NULL, control_hash TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, no_progress INTEGER NOT NULL DEFAULT 0,
 stop_reason TEXT, detail TEXT, result TEXT, result_hash TEXT, result_revision TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_writer ON tasks(book_id)
 WHERE kind != 'review' AND status IN ('running','submitted','blocked','exhausted');
CREATE TABLE IF NOT EXISTS reviews(task_id TEXT PRIMARY KEY REFERENCES tasks(id),
 book_id TEXT NOT NULL, revision TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
 book_id TEXT, event TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
 revision TEXT NOT NULL, source TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
"""


class Engine:
    def __init__(self, root):
        raw_root = Path(root).absolute()
        if raw_root.is_symlink():
            raise EngineError("Project root cannot be a symlink")
        self.root = raw_root.resolve()
        self.db_path = checked_path(self.root, "runtime/novel.sqlite3")
        if not self.db_path.is_file():
            raise EngineError("Project is not initialized; run init first")
        self.limits()
        with self._db() as db:
            version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if not version or version[0] != "1":
                raise EngineError("Unsupported database schema")

    @classmethod
    def initialize(cls, root):
        root = Path(root).absolute()
        if root.is_symlink():
            raise EngineError("Project root cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        for folder in ("runtime", "books", "policies", "methods"):
            checked_path(root, folder).mkdir(exist_ok=True)
        limits = checked_path(root, "policies/limits.json")
        if not limits.exists():
            cls._new_file(limits, json.dumps(DEFAULT_LIMITS, indent=2) + "\n")
        template_root = Path(__file__).resolve().parent.parent
        for relative in ("policies/principles.md", "methods/writing.md", "methods/review.md", "methods/research.md"):
            source = template_root / relative
            target = checked_path(root, relative)
            if source.is_file() and not target.exists():
                cls._new_file(target, source.read_text(encoding="utf-8"))
        db_path = checked_path(root, "runtime/novel.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            checked_path(root, "runtime/novel.sqlite3" + suffix)
        db = sqlite3.connect(db_path, timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(DDL)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', '1')")
            db.commit()
        finally:
            db.close()
        return cls(root)

    @staticmethod
    def _new_file(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())

    @contextmanager
    def _db(self, write=False):
        checked_path(self.root, "runtime/novel.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            checked_path(self.root, "runtime/novel.sqlite3" + suffix)
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise EngineError(f"Conflicting state: {exc}") from exc
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def limits(self):
        path = checked_path(self.root, "policies/limits.json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise EngineError("Cannot read limits policy") from exc
        if set(data) != set(DEFAULT_LIMITS) or data["schema_version"] != 1 or data["billing"] != "chatgpt_subscription":
            raise EngineError("Unsupported limits policy or billing path")
        for field in ("max_attempts", "max_no_progress", "max_result_bytes"):
            if type(data[field]) is not int or data[field] <= 0:
                raise EngineError(f"Invalid limit: {field}")
        return data

    def _controls(self):
        self.limits()
        files = {}
        for folder in ("policies", "methods"):
            base = checked_path(self.root, folder)
            for path in sorted(base.rglob("*")):
                relative = path.relative_to(self.root).as_posix()
                checked_path(self.root, relative)
                if path.is_file():
                    files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest(canonical(files))

    def control_documents(self):
        """Export the actual versioned policies and methods used by a task."""
        documents = {}
        for folder in ("policies", "methods"):
            for path in checked_path(self.root, folder).rglob("*"):
                relative = path.relative_to(self.root).as_posix()
                checked_path(self.root, relative)
                if path.is_file():
                    documents[relative] = path.read_text(encoding="utf-8")
        return documents

    @staticmethod
    def _row(db, table, key):
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise EngineError(f"Unknown {table}: {key}")
        return dict(row)

    @staticmethod
    def _event(db, event, payload, task_id=None, book_id=None):
        db.execute("INSERT INTO events(task_id,book_id,event,payload,created_at) VALUES (?,?,?,?,?)",
                   (task_id, book_id, event, canonical(payload), now()))

    def _snapshot(self, book_id, files, parent, task_id):
        paths = list(files)
        if len({p.casefold() for p in paths}) != len(paths):
            raise EngineError("Case-insensitive file collision")
        for path in paths:
            validate_path(path)
            if any(other.startswith(path + "/") for other in paths):
                raise EngineError("File/directory collision")
        hashes = {p: digest(content) for p, content in sorted(files.items())}
        manifest = {"book_id": book_id, "parent": parent, "task_id": task_id, "hashes": hashes}
        revision = digest(canonical(manifest))
        base = checked_path(self.root, f"books/{book_id}/versions/{revision}")
        if base.exists():
            # Only a fully written identical orphan can be reused after a crash.
            self._read_snapshot(book_id, revision)
            return revision
        staging = checked_path(self.root, f"books/{book_id}/versions/.staging-{uuid.uuid4().hex}")
        staging.mkdir(parents=True)
        for relative, content in files.items():
            self._new_file(checked_path(staging, relative), content)
        self._new_file(staging / "manifest.json", canonical(manifest) + "\n")
        staging.rename(base)
        return revision

    def _read_snapshot(self, book_id, revision):
        identifier(book_id)
        if not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise EngineError("Invalid revision")
        base = checked_path(self.root, f"books/{book_id}/versions/{revision}")
        manifest_path = checked_path(base, "manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if digest(canonical(manifest)) != revision or manifest["book_id"] != book_id:
                raise EngineError("Snapshot manifest has changed")
            result = {}
            for relative, expected in manifest["hashes"].items():
                validate_path(relative)
                data = checked_path(base, relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise EngineError(f"Snapshot content has changed: {relative}")
                result[relative] = data.decode("utf-8")
            actual = set()
            for path in base.rglob("*"):
                checked_path(base, path.relative_to(base).as_posix())
                if path.is_file():
                    actual.add(path.relative_to(base).as_posix())
            if actual != {*manifest["hashes"], "manifest.json"}:
                raise EngineError("Unexpected files in snapshot")
            return result
        except (OSError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise EngineError(f"Cannot verify snapshot {revision}: {exc}") from exc

    def create_book(self, book_id, title):
        identifier(book_id)
        if not isinstance(title, str) or not title.strip():
            raise EngineError("Book title is required")
        with self._db(True) as db:
            if db.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                raise EngineError("Book already exists")
            revision = self._snapshot(book_id, {"canon/state.json": canonical(EMPTY_STATE) + "\n"}, None, None)
            db.execute("INSERT INTO books VALUES (?,?,?)", (book_id, title, revision))
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (revision, book_id, None, "accepted", None, now()))
            self._event(db, "book.created", {"title": title, "revision": revision}, book_id=book_id)
        return self.book(book_id)

    def book(self, book_id):
        with self._db() as db:
            book = self._row(db, "books", book_id)
            book["status"] = self._row(db, "revisions", book["current_revision"])["status"]
            return book

    def list_books(self):
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT b.*,r.status FROM books b JOIN revisions r ON b.current_revision=r.id ORDER BY b.id")]

    def files(self, book_id, revision=None):
        with self._db() as db:
            book = self._row(db, "books", book_id)
            revision = revision or book["current_revision"]
            version = self._row(db, "revisions", revision)
            if version["book_id"] != book_id:
                raise EngineError("Revision belongs to another book")
            return self._read_snapshot(book_id, revision)

    def task(self, task_id):
        with self._db() as db:
            result = self._row(db, "tasks", task_id)
            if result["result"] is not None:
                result["result"] = json.loads(result["result"])
            return result

    def tasks(self, book_id=None):
        with self._db() as db:
            rows = db.execute("SELECT id FROM tasks WHERE (? IS NULL OR book_id=?) ORDER BY created_at", (book_id, book_id)).fetchall()
        return [self.task(row[0]) for row in rows]

    def enqueue(self, book_id, kind, instruction):
        if kind not in KINDS or not isinstance(instruction, str) or not instruction.strip():
            raise EngineError("Valid task kind and instruction required")
        with self._db(True) as db:
            book = self._row(db, "books", book_id)
            version = self._row(db, "revisions", book["current_revision"])
            self._read_snapshot(book_id, version["id"])
            if kind == "write" and version["status"] != "accepted":
                raise EngineError("Accept the current chapter/version before writing the next; use revise for repairs")
            task_id = uuid.uuid4().hex
            timestamp = now()
            db.execute("""INSERT INTO tasks(id,book_id,kind,instruction,input_revision,control_hash,status,created_at,updated_at)
                          VALUES (?,?,?,?,?,?,'queued',?,?)""", (task_id, book_id, kind, instruction, version["id"], self._controls(), timestamp, timestamp))
            self._event(db, "task.enqueued", {"kind": kind, "input_revision": version["id"]}, task_id, book_id)
        return self.task(task_id)

    def _fresh(self, db, task):
        if task["control_hash"] != self._controls():
            raise EngineError("Policies or methods changed since this task was created")
        if self._row(db, "books", task["book_id"])["current_revision"] != task["input_revision"]:
            raise EngineError("Stale input revision; create a new task using the current version")
        self._not_stopped(db, task["book_id"], task["id"])
        if task["kind"] == "write" and self._row(db, "revisions", task["input_revision"])["status"] != "accepted":
            raise EngineError("The input version is no longer accepted; use a fresh revision task")
        return self._read_snapshot(task["book_id"], task["input_revision"])

    @staticmethod
    def _not_stopped(db, book_id, except_task=None):
        stopped = db.execute("SELECT id FROM tasks WHERE book_id=? AND status IN ('blocked','exhausted') AND id!=?",
                             (book_id, except_task or "")).fetchone()
        if stopped:
            raise EngineError(f"Book has a stopped task {stopped[0]}; explicitly resolve or cancel it first")

    def claim(self, task_id):
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if task["status"] != "queued":
                raise EngineError("Only queued tasks can be claimed")
            self._fresh(db, task)
            if task["attempts"] >= self.limits()["max_attempts"]:
                raise EngineError("Cumulative attempt limit exhausted")
            db.execute("UPDATE tasks SET status='running',attempts=attempts+1,updated_at=? WHERE id=?", (now(), task_id))
            self._event(db, "task.claimed", {"attempt": task["attempts"] + 1}, task_id, task["book_id"])
        return self.task(task_id)

    def submit(self, task_id, result, *, expected_attempt=None):
        encoded = canonical(result)
        if len(encoded.encode("utf-8")) > self.limits()["max_result_bytes"]:
            raise EngineError("Result exceeds configured size limit")
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if expected_attempt is not None and task["attempts"] != expected_attempt:
                raise EngineError("Result belongs to a superseded execution attempt")
            if task["result_hash"]:
                if task["result_hash"] == digest(encoded) and task["status"] in ("submitted", "completed"):
                    return self.task(task_id)
                raise EngineError("A different result already exists for this task")
            if task["status"] != "running":
                raise EngineError("Only running tasks accept results")
            files = self._fresh(db, task)
            validate_result(result, task, files)
            self._check_changes(files, result)
            if task["kind"] != "review" and not any(files.get(c["path"]) != c["content"] for c in result["changes"]):
                raise EngineError("No effective change; record no_progress instead of publishing")
            self._check_adoption(files, result)
            db.execute("UPDATE tasks SET result=?,result_hash=?,status='submitted',updated_at=? WHERE id=?", (encoded, digest(encoded), now(), task_id))
            self._event(db, "task.submitted", {"result_hash": digest(encoded)}, task_id, task["book_id"])
        return self.task(task_id)

    @staticmethod
    def _check_changes(files, result):
        changes = {c["path"]: c["content"] for c in result["changes"]}
        paths = {*files, *changes}
        if len({p.casefold() for p in paths}) != len(paths):
            raise EngineError("Case-insensitive file collision")
        for path in changes:
            if path.startswith(("decisions/", "reference/")):
                raise EngineError("Author decisions and original reference material require the explicit operator import command")
            if result["review"] is None and path.startswith("research/") and path in files:
                raise EngineError("Research evidence is append-only; add a new record")
            if path.startswith("revisions/") and path in files:
                raise EngineError("Revision reasons are append-only")
        if "canon/state.json" in changes:
            previous = json.loads(files["canon/state.json"])
            updated = json.loads(changes["canon/state.json"])
            old_ids = {r["id"] for r in previous["knowledge"]}
            new_ids = {r["id"] for r in updated["knowledge"]}
            if not old_ids <= new_ids:
                raise EngineError("Keep stable knowledge IDs and history; correct existing records rather than deleting their identity")

    @staticmethod
    def _check_adoption(files, result):
        new_state = next((c["content"] for c in result["changes"] if c["path"] == "canon/state.json"), None)
        if new_state is None:
            return
        prior = {r["id"]: r for r in json.loads(files["canon/state.json"])["knowledge"]}
        merged = {**files, **{c["path"]: c["content"] for c in result["changes"]}}

        def explicit_selection(record, old_record):
            for source in record["sources"]:
                path = source["path"]
                if path.startswith("decisions/") and path in files:
                    return True
                # Ordinary reversible candidates may be selected autonomously,
                # with an explicit agent-origin rationale, never an author claim.
                if old_record["kind"] == "candidate" and path.startswith("revisions/") and path.endswith(".json") and path in merged:
                    try:
                        note = json.loads(merged[path])
                    except ValueError:
                        continue
                    if (isinstance(note, dict) and set(note) == {"kind", "candidate_ids", "reason", "scope"}
                            and note["kind"] == "agent_selection" and note["scope"] == "ordinary_reversible"
                            and isinstance(note["candidate_ids"], list) and old_record["id"] in note["candidate_ids"]
                            and isinstance(note["reason"], str) and note["reason"].strip()
                            and any(s["path"].startswith("manuscript/") for s in record["sources"])):
                        return True
            return False

        for record in json.loads(new_state)["knowledge"]:
            old = prior.get(record["id"])
            if old and old["kind"] in ("candidate", "undecided") and record["kind"] == "world_fact":
                if not explicit_selection(record, old):
                    raise EngineError("Adoption requires an existing author decision, or an explicit ordinary candidate selection with manuscript evidence")
            if record["kind"] == "world_fact":
                for old_record in prior.values():
                    if old_record["statement"] == record["statement"] and old_record["kind"] in ("candidate", "undecided") and not explicit_selection(record, old_record):
                        raise EngineError("A known candidate cannot be adopted under a new identity without explicit selection")

    def publish(self, task_id):
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if task["status"] == "completed":
                return self.task(task_id)
            if task["status"] != "submitted":
                raise EngineError("Submit a validated result before publishing")
            files = self._fresh(db, task)
            result = json.loads(task["result"])
            if digest(canonical(result)) != task["result_hash"]:
                raise EngineError("Stored result hash mismatch")
            validate_result(result, task, files)
            self._check_changes(files, result)
            if task["kind"] == "review":
                revision = task["input_revision"]
                db.execute("INSERT INTO reviews VALUES (?,?,?,?)", (task_id, task["book_id"], revision, task["result"]))
                # New evidence always reopens the stage, including an accepted version.
                db.execute("UPDATE revisions SET status='draft' WHERE id=?", (revision,))
            else:
                self._check_adoption(files, result)
                files.update({c["path"]: c["content"] for c in result["changes"]})
                revision = self._snapshot(task["book_id"], files, task["input_revision"], task_id)
                db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (revision, task["book_id"], task["input_revision"], "draft", task_id, now()))
                db.execute("UPDATE books SET current_revision=? WHERE id=?", (revision, task["book_id"]))
            db.execute("UPDATE tasks SET status='completed',result_revision=?,updated_at=? WHERE id=?", (revision, now(), task_id))
            self._event(db, "task.published", {"revision": revision}, task_id, task["book_id"])
        return self.task(task_id)

    def assessment(self, book_id):
        with self._db() as db:
            book = self._row(db, "books", book_id)
            return self._assessment(db, book)

    def _assessment(self, db, book):
        revision = book["current_revision"]
        files = self._read_snapshot(book["id"], revision)
        required = {p for p in files if p.startswith("manuscript/")}
        covered, blockers, review_ids = set(), [], []
        rows = db.execute("SELECT * FROM reviews WHERE book_id=? AND revision=?", (book["id"], revision)).fetchall()
        for row in rows:
            task = self._row(db, "tasks", row["task_id"])
            self._verify_review(row, task)
            if task["control_hash"] != self._controls():
                blockers.append(f"Review {task['id']} used obsolete policies/methods")
                continue
            result = json.loads(task["result"])
            review = result["review"]
            covered.update(review["coverage"])
            review_ids.append(row["task_id"])
            blockers.extend(result["unresolved"])
            for finding in review["findings"]:
                if finding["status"] == "open" and ((finding["category"] == "error" and finding["confirmed"]) or (finding["category"] == "concern" and finding["severity"] == "major")):
                    blockers.append(f"{row['task_id']}:{finding['id']}: {finding['explanation']}")
        if not rows:
            blockers.append("No independent review of this revision")
        if required - covered:
            blockers.append("Unreviewed manuscript: " + ", ".join(sorted(required - covered)))
        writer = db.execute("SELECT result FROM tasks WHERE result_revision=? AND kind!='review' AND status='completed'", (revision,)).fetchone()
        if writer:
            blockers.extend(json.loads(writer[0])["unresolved"])
        return {"revision": revision, "review_tasks": review_ids, "covered": sorted(covered), "blockers": blockers, "can_accept": not blockers}

    @staticmethod
    def _verify_review(row, task):
        if (task["kind"] != "review" or task["status"] != "completed" or task["book_id"] != row["book_id"]
                or task["input_revision"] != row["revision"] or task["result_revision"] != row["revision"]
                or task["result"] != row["result"] or digest(task["result"]) != task["result_hash"]):
            raise EngineError("Review evidence integrity mismatch")

    def accept(self, book_id):
        with self._db(True) as db:
            book = self._row(db, "books", book_id)
            self._not_stopped(db, book_id)
            assessment = self._assessment(db, book)
            if not assessment["can_accept"]:
                raise EngineError("Cannot accept: " + "; ".join(assessment["blockers"]))
            if db.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('running','submitted','blocked','exhausted')", (book_id,)).fetchone():
                raise EngineError("Finish or explicitly cancel outstanding tasks before acceptance")
            db.execute("UPDATE revisions SET status='accepted' WHERE id=?", (book["current_revision"],))
            self._event(db, "revision.accepted", assessment, book_id=book_id)
        return self.book(book_id)

    def block(self, task_id, reason, detail):
        if reason not in STOP_REASONS or not isinstance(detail, str) or not detail.strip():
            raise EngineError("Valid stop reason and explanation required")
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if task["status"] not in ("queued", "running", "blocked"):
                raise EngineError("Task cannot be blocked in its current state")
            no_progress = task["no_progress"] + (1 if reason == "no_progress" else 0)
            limits = self.limits()
            status = "exhausted" if task["attempts"] >= limits["max_attempts"] or no_progress >= limits["max_no_progress"] else "blocked"
            db.execute("UPDATE tasks SET status=?,stop_reason=?,detail=?,no_progress=?,updated_at=? WHERE id=?", (status, reason, detail, no_progress, now(), task_id))
            self._event(db, "task.stopped", {"reason": reason, "detail": detail, "attempts": task["attempts"], "no_progress": no_progress}, task_id, task["book_id"])
        return self.task(task_id)

    def resume(self, task_id, note):
        if not isinstance(note, str) or not note.strip():
            raise EngineError("Explain how the stopping condition was resolved")
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if task["status"] != "blocked":
                raise EngineError("Only blocked, non-exhausted tasks can resume")
            self._fresh(db, task)
            db.execute("UPDATE tasks SET status='queued',stop_reason=NULL,detail=NULL,updated_at=? WHERE id=?", (now(), task_id))
            self._event(db, "task.resumed", {"resolution": note, "attempts": task["attempts"]}, task_id, task["book_id"])
        return self.task(task_id)

    def recover(self, task_id, note):
        task = self.task(task_id)
        if task["status"] != "running":
            raise EngineError("Recovery applies only to an interrupted running task")
        return self.block(task_id, "tool_failure", note)

    def cancel(self, task_id, note):
        if not isinstance(note, str) or not note.strip():
            raise EngineError("Cancellation reason required")
        with self._db(True) as db:
            task = self._row(db, "tasks", task_id)
            if task["status"] in ("completed", "cancelled"):
                raise EngineError("Task is already terminal")
            db.execute("UPDATE tasks SET status='cancelled',detail=?,updated_at=? WHERE id=?", (note, now(), task_id))
            self._event(db, "task.cancelled", {"reason": note}, task_id, task["book_id"])
        return self.task(task_id)

    def rollback(self, book_id, revision, note):
        if not isinstance(note, str) or not note.strip():
            raise EngineError("Rollback reason required")
        files = self.files(book_id, revision)
        with self._db(True) as db:
            book = self._row(db, "books", book_id)
            current_version = self._row(db, "revisions", book["current_revision"])
            if current_version["book_id"] != book_id:
                raise EngineError("Current revision belongs to another book")
            self._read_snapshot(book_id, book["current_revision"])
            self._not_stopped(db, book_id)
            if db.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('running','submitted','blocked','exhausted')", (book_id,)).fetchone():
                raise EngineError("Cancel or finish active tasks before rollback")
            new_revision = self._snapshot(book_id, files, book["current_revision"], "rollback-" + uuid.uuid4().hex)
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (new_revision, book_id, book["current_revision"], "draft", None, now()))
            db.execute("UPDATE books SET current_revision=? WHERE id=?", (new_revision, book_id))
            self._event(db, "revision.rolled_back", {"source_revision": revision, "new_revision": new_revision, "reason": note}, book_id=book_id)
        return self.book(book_id)

    def handoff(self, task_id):
        task = self.task(task_id)
        files = self.files(task["book_id"], task["input_revision"])
        current = self.book(task["book_id"])["current_revision"]
        result = task["result"]
        if result and digest(canonical(result)) != task["result_hash"]:
            raise EngineError("Task result has changed")
        output = self.files(task["book_id"], task["result_revision"]) if task["result_revision"] else None
        return {"task": task, "input_verified": True, "current_revision": current,
                "input_is_current": current == task["input_revision"], "controls_match": task["control_hash"] == self._controls(),
                "input_hashes": {p: digest(v) for p, v in files.items()},
                "output_verified": output is not None,
                "output_hashes": {p: digest(v) for p, v in output.items()} if output is not None else {},
                "completed_steps": result["completed_steps"] if result else [],
                "changed_files": [c["path"] for c in result["changes"]] if result else [],
                "unresolved": result["unresolved"] if result else [],
                "next_step": result["next_step"] if result else "Continue the persisted task; resolve any stop before claiming again"}

    def search(self, book_id, query, revision=None):
        if not query.strip():
            raise EngineError("Search query cannot be empty")
        return [{"path": path, "line": i, "text": line} for path, content in self.files(book_id, revision).items()
                for i, line in enumerate(content.splitlines(), 1) if query.casefold() in line.casefold()]

    def impact(self, book_id, path, revision=None):
        """Report explicit evidence within one revision, not inferred causality."""
        from .records import _json, _research, validate_state

        validate_path(path)
        revision = revision or self.book(book_id)["current_revision"]
        files = self.files(book_id, revision)
        if path not in files:
            raise EngineError("File is absent from this version")
        state = _json(files["canon/state.json"], "canon/state.json")
        validate_state(state, files)
        references = []
        for section in ("knowledge", "characters", "world", "offstage"):
            for entry in state[section]:
                sources = [source for source in entry["sources"] if source["path"] == path]
                if sources:
                    references.append({"section": section, "id": entry["id"],
                                       "statement": entry["statement"],
                                       "kind": entry.get("kind"), "holder": entry.get("holder"),
                                       "sources": sources})
        research = []
        for research_path, content in sorted(files.items()):
            if research_path.startswith("research/") and research_path.endswith(".json"):
                record = _json(content, research_path)
                _research(record, files)
                if path in record["affected_paths"]:
                    research.append({"path": research_path, "content_hash": digest(content),
                                     "record": record})
        reviews = []
        with self._db() as db:
            controls = self._controls()
            rows = db.execute("SELECT * FROM reviews WHERE book_id=? AND revision=? ORDER BY task_id",
                              (book_id, revision)).fetchall()
            for row in rows:
                task = self._row(db, "tasks", row["task_id"])
                self._verify_review(row, task)
                result = json.loads(task["result"])
                report = result["review"]
                if path in report["coverage"]:
                    reviews.append({"task_id": task["id"], "revision": row["revision"],
                                    "controls_match": task["control_hash"] == controls,
                                    "result_hash": task["result_hash"], "review": report,
                                    "unresolved": result["unresolved"]})
        return {"book_id": book_id, "revision": revision, "path": path,
                "source_hash": digest(files[path]), "references": references,
                "research": research, "reviews": reviews,
                "scope": "explicit state citations, declared research impact and same-revision review coverage; not acceptance or semantic proof"}

    def feedback(self, book_id, text, source="author"):
        if source not in ("author", "target_reader") or not text.strip():
            raise EngineError("Feedback needs exact text and author/target_reader source")
        with self._db(True) as db:
            book = self._row(db, "books", book_id)
            feedback_id = uuid.uuid4().hex
            db.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?)", (feedback_id, book_id, book["current_revision"], source, text, now()))
            self._event(db, "feedback.recorded", {"feedback_id": feedback_id, "source": source}, book_id=book_id)
        return {"id": feedback_id, "revision": book["current_revision"], "source": source, "text": text}

    def decision(self, book_id, text):
        """Trusted operator ingress, not exposed in the model result protocol.

        The caller must have the author's explicit statement/authorization.
        This local command is not an authenticated human identity proof.
        """
        return self._operator_append(book_id, "decisions", text, "author.decision")

    def reference(self, book_id, text):
        """Preserve explicitly supplied reference text; never import it as Canon."""
        return self._operator_append(book_id, "reference", text, "reference.imported")

    def _operator_append(self, book_id, folder, text, event):
        if not isinstance(text, str) or not text.strip():
            raise EngineError("Exact source text is required")
        with self._db(True) as db:
            book = self._row(db, "books", book_id)
            self._row(db, "revisions", book["current_revision"])
            if db.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('running','submitted')", (book_id,)).fetchone():
                raise EngineError("Finish or cancel executing tasks before recording a decision")
            files = self._read_snapshot(book_id, book["current_revision"])
            decision_id = uuid.uuid4().hex
            path = f"{folder}/{decision_id}.md"
            files[path] = text
            revision = self._snapshot(book_id, files, book["current_revision"], "decision-" + decision_id)
            status = "draft" if any(p.startswith("manuscript/") for p in files) else "accepted"
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (revision, book_id, book["current_revision"], status, None, now()))
            db.execute("UPDATE books SET current_revision=? WHERE id=?", (revision, book_id))
            self._event(db, event, {"path": path, "revision": revision}, book_id=book_id)
        return {"path": path, "revision": revision, "status": status, "text": text}

    def audit(self):
        with self._db() as db:
            check = db.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise EngineError("SQLite integrity check failed: " + check)
            versions = db.execute("SELECT * FROM revisions").fetchall()
            for version in versions:
                self._read_snapshot(version["book_id"], version["id"])
                manifest = json.loads(checked_path(self.root, f"books/{version['book_id']}/versions/{version['id']}/manifest.json").read_text(encoding="utf-8"))
                if manifest["parent"] != version["parent"]:
                    raise EngineError("Revision parent differs from its immutable manifest")
                if version["parent"] is not None:
                    parent = self._row(db, "revisions", version["parent"])
                    if parent["book_id"] != version["book_id"]:
                        raise EngineError("Parent revision belongs to another book")
                if version["task_id"] is not None and manifest["task_id"] != version["task_id"]:
                    raise EngineError("Revision task differs from manifest")
            for book in db.execute("SELECT * FROM books"):
                current = self._row(db, "revisions", book["current_revision"])
                if current["book_id"] != book["id"]:
                    raise EngineError("Invalid current revision pointer")
            for review in db.execute("SELECT * FROM reviews"):
                self._verify_review(review, self._row(db, "tasks", review["task_id"]))
            for task in db.execute("SELECT * FROM tasks WHERE result IS NOT NULL"):
                if digest(task["result"]) != task["result_hash"]:
                    raise EngineError("Stored task result integrity failure")
            events = db.execute("SELECT count(*) FROM events").fetchone()[0]
        return {"database": "ok", "snapshots_verified": len(versions), "events": events,
                "protection": "validated controller operations; not OS isolation"}
