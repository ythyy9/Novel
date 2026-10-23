"""Model-free, bounded operations for a remote Dot executor.

The embedding transport must authenticate the owner and grant the separate
``agenthub.novel.runtime`` scope. A configured workspace is the only accessible
root. Context references are executor declarations, not identity attestation.
This module never starts a model, shell, reference refresh, or scheduler.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import threading
import uuid

from .engine import Engine, EngineError, NoProgressError, canonical, checked_path, digest, identifier, now
from .records import _json

CHUNK_CHARS = 6000
MAX_PARTS = 256
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()

DDL = """
CREATE TABLE IF NOT EXISTS requests(
 id TEXT PRIMARY KEY, signature TEXT NOT NULL, state TEXT NOT NULL,
 receipt TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
 id TEXT PRIMARY KEY, context_ref TEXT NOT NULL, kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parts(
 task_id TEXT NOT NULL, attempt INTEGER NOT NULL, upload_id TEXT NOT NULL,
 part INTEGER NOT NULL, total INTEGER NOT NULL, content TEXT NOT NULL,
 PRIMARY KEY(task_id, attempt, upload_id, part));
CREATE TABLE IF NOT EXISTS context_reads(
 task_id TEXT NOT NULL, attempt INTEGER NOT NULL, plan_hash TEXT NOT NULL,
 document TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
 PRIMARY KEY(task_id, attempt, plan_hash, document, start, end));
CREATE TABLE IF NOT EXISTS context_checkpoints(
 task_id TEXT NOT NULL, attempt INTEGER NOT NULL, plan_hash TEXT NOT NULL,
 batch_id TEXT NOT NULL, hash TEXT NOT NULL, payload TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(task_id, attempt, plan_hash, hash));
"""


def _text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise EngineError(f"Invalid {name}")
    return value


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise EngineError(f"Invalid {name}")
    return value


class DotWorkspace:
    def __init__(self, root, book_id):
        self.engine = Engine(root)
        self.book_id = identifier(book_id)
        self.engine.book(book_id)
        self.base = checked_path(self.engine.root, "runtime/dot")
        self.base.mkdir(exist_ok=True)
        self.db_path = checked_path(self.base, "gateway.sqlite3")
        with self._db() as db:
            db.executescript(DDL)
        with _LOCKS_GUARD:
            self.lock = _LOCKS.setdefault(str(self.base), threading.RLock())

    @contextmanager
    def _db(self):
        checked_path(self.base, "gateway.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            checked_path(self.base, "gateway.sqlite3" + suffix)
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @contextmanager
    def _exclusive(self):
        # Serialize across threads and processes without a second controller.
        with self.lock:
            with checked_path(self.base, "operation.lock").open("a+b") as handle:
                if __import__("os").name == "nt":
                    import msvcrt
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if __import__("os").name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle, fcntl.LOCK_UN)

    def _change(self, request_id, action, arguments, operation, *, intent=None):
        identifier(request_id)
        signature = digest(canonical([action, arguments]))
        with self._exclusive():
            with self._db() as db:
                previous = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
                if previous:
                    if previous["signature"] != signature:
                        raise EngineError("Request ID was already used with different arguments")
                    if previous["state"] == "pending":
                        raise EngineError("Uncertain prior operation: inspect persisted state before recovery")
                    receipt = json.loads(previous["receipt"])
                    if previous["state"] == "error":
                        raise EngineError(receipt["error"])
                    return {**receipt, "replayed": True}
                db.execute("INSERT INTO requests VALUES (?,?,'pending',?,?)",
                           (request_id, signature, canonical(intent) if intent else None, now()))
            try:
                receipt = operation()
            except (ValueError, OSError) as exc:
                with self._db() as db:
                    db.execute("UPDATE requests SET state='error',receipt=? WHERE id=?",
                               (canonical({**(intent or {}), "error": str(exc)}), request_id))
                raise
            with self._db() as db:
                db.execute("UPDATE requests SET state='done',receipt=? WHERE id=?", (canonical(receipt), request_id))
            return {**receipt, "replayed": False}

    def _task(self, task_id):
        identifier(task_id)
        with self._db() as db:
            known = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if known is None:
            raise EngineError("Task is not registered in this Dot workspace")
        task = self.engine.task(task_id)
        if task["book_id"] != self.book_id:
            raise EngineError("Task belongs to another book")
        return task, dict(known)

    @staticmethod
    def _summary(task):
        return {key: value for key, value in task.items() if key != "result"}

    def status(self, *, history_limit=10, before=None, include_instructions=False):
        from .dot_recovery import unresolved_requests
        _integer(history_limit, "history_limit", 1, 100)
        if before is not None:
            _integer(before, "before", 1, 2**63 - 1)
        if type(include_instructions) is not bool:
            raise EngineError("Invalid include_instructions")
        with self._db() as db:
            task_rows = [dict(row) for row in db.execute("SELECT rowid AS position,* FROM tasks ORDER BY rowid")]
            pending, recoverable = unresolved_requests(db, self.book_id)
        with self.engine._db() as db:
            states = dict(db.execute("SELECT id,status FROM tasks WHERE book_id=?", (self.book_id,)))
            task_rows = [row for row in task_rows if row["id"] in states]
            active = [row for row in task_rows if states[row["id"]] not in {"completed", "cancelled"}]
            history = [row for row in reversed(task_rows) if states[row["id"]] in {"completed", "cancelled"}
                       and (before is None or row["position"] < before)]
            page = history[:history_limit]
            selected = active + page
            # Fetch only selected metadata in one query; do not load/decode saved results.
            columns = "id,book_id,kind,input_revision,control_hash,status,attempts,no_progress,stop_reason,detail,result_hash,result_revision,created_at,updated_at"
            if include_instructions:
                columns += ",instruction"
            summaries = {row["id"]: dict(row) for row in db.execute(
                "SELECT " + columns + " FROM tasks WHERE id IN (" + ",".join("?" for _ in selected) + ")",
                [row["id"] for row in selected])} if selected else {}
        recoverable = [row for row in recoverable if row["task_id"] in states]
        tasks = [{**summaries[row["id"]], "context_ref": row["context_ref"],
                  "packet_index": "packet-index.json", "task_document": "task-info.json"} for row in selected]
        return {"book": self.engine.book(self.book_id), "assessment": self.engine.assessment(self.book_id),
                "tasks": tasks, "task_count": len(task_rows), "active_task_count": len(active),
                "tasks_complete": before is None and len(history) <= history_limit,
                "next_before": page[-1]["position"] if len(history) > history_limit else None,
                "next_history_document": ("status-history/" + str(page[-1]["position"]) + ".json"
                                          if len(history) > history_limit else None),
                "history_limit": history_limit,
                "task_listing": "All active tasks plus a bounded history page; full instructions via task-info.json",
                "uncertain_requests": pending, "recoverable_open_requests": recoverable,
                "model_execution": "external_dot_only",
                "reference_refresh": "not_performed", "notification_delivery": "not_attested",
                "context_provenance": "executor_declared_requires_independent_live_verification"}

    def open_task(self, *, request_id, kind, instruction, expected_revision, context_ref):
        _text(instruction, "instruction", 12000)
        _text(context_ref, "context_ref", 240)
        args = dict(kind=kind, instruction=instruction, expected_revision=expected_revision, context_ref=context_ref)
        intent = {"operation": "open", "book_id": self.book_id,
                  "task_id": uuid.uuid4().hex, "arguments": args}
        def operation():
            if self.engine.book(self.book_id)["current_revision"] != expected_revision:
                raise EngineError("Stale expected revision")
            if any(t["status"] in {"queued", "running", "submitted", "blocked", "exhausted"}
                   for t in self.engine.tasks(self.book_id)):
                raise EngineError("Resolve outstanding work before opening another task")
            if kind == "review":
                writers = [t for t in self.engine.tasks(self.book_id)
                           if t["result_revision"] == expected_revision and t["kind"] != "review"]
                with self._db() as db:
                    for writer in writers:
                        previous = db.execute("SELECT context_ref FROM tasks WHERE id=?", (writer["id"],)).fetchone()
                        if previous and previous[0] == context_ref:
                            raise EngineError("Review must use a different execution context from its writer")
            task = self.engine.enqueue(self.book_id, kind, instruction, task_id=intent["task_id"])
            with self._db() as db:
                db.execute("INSERT INTO tasks VALUES (?,?,?)", (task["id"], context_ref, kind))
            task = self.engine.claim(task["id"])
            return self._save_packet(task, context_ref)
        return self._change(request_id, "open", args, operation, intent=intent)

    def recover_open_task(self, **arguments):
        """Explicit operator recovery; never exposed as a creative MCP tool."""
        from .dot_recovery import recover_open_task
        return recover_open_task(self, **arguments)

    def _save_packet(self, task, context_ref, supplemental_documents=None):
        task, files, controls = self.engine.execution_inputs(task["id"], expected_attempt=task["attempts"])
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/result.schema.json").read_text(encoding="utf-8"))
        documents = {**files, **controls, "result.schema.json": canonical(schema)}
        if task["kind"] == "correct_records":
            from .corrections import GUIDE
            documents["record-correction-guide.md"] = GUIDE
        documents.update(supplemental_documents or {})
        packet = {"task": self._summary(task), "context_ref": context_ref,
                  "documents": documents, "sha256": {p: digest(v) for p, v in documents.items()}}
        path = checked_path(self.base, "packets/" + task["id"] + ".json")
        if path.exists():
            # A successful save followed by a lost receipt must preserve bytes.
            existing = self._packet(task)
            if existing["context_ref"] != context_ref or existing["documents"] != documents:
                raise EngineError("Existing fixed packet differs; inspect original evidence")
        else:
            temporary = checked_path(self.base, "packets/.pending-" + uuid.uuid4().hex)
            try:
                self.engine._new_file(temporary, canonical(packet))
                if os.name == "nt":
                    temporary.rename(path)  # Windows rename refuses an existing destination.
                else:
                    os.link(temporary, path)  # Atomic publication without replacement.
            finally:
                if temporary.exists():
                    temporary.unlink()
        return {"task": self._summary(task), "documents": [
            {"path": p, "characters": len(v), "sha256": digest(v)} for p, v in documents.items()],
            "context_guide": "context-guide.md", "context_plan": "context-plan.json",
            "instructions": "Start with context-guide.md and context-plan.json for bounded, lossless reading. "
                "Preserve batch checkpoints across native contexts; all input must still be covered. "
                "Read the fixed input documents and result schema. Generate the result in Dot. "
                "Do not invoke Codex, Work or a paid API. Upload JSON chunks then finish and publish. "
                "Reference documents are fixed snapshots; no automatic refresh was performed. "
                "Context IDs are declarations; retain native independent review evidence."}

    def adopt_running_task(self, *, request_id, task_id, expected_attempt, expected_revision, context_ref,
                           supplemental_documents=None):
        """Trusted operator handoff only; deliberately absent from MCP tools.

        The operator must first verify source freeze and an intact backup. This
        registers an existing running attempt, never claims/retries/resets it.
        The receipt does not attest that another executor has actually stopped.
        """
        identifier(task_id)
        _integer(expected_attempt, "expected_attempt", 1, 10000)
        _text(context_ref, "context_ref", 240)
        if supplemental_documents is None:
            supplemental_documents = {}
        if not isinstance(supplemental_documents, dict) or len(supplemental_documents) > 16:
            raise EngineError("Invalid handoff documents")
        for path, content in supplemental_documents.items():
            if (not isinstance(path, str) or not path.startswith("handoff/") or "\\" in path
                    or ":" in path or any(part in {"", ".", ".."} for part in path.split("/"))
                    or PurePosixPath(path).suffix not in {".md", ".json"}):
                raise EngineError("Handoff documents must stay in the fixed handoff directory")
            _text(content, "handoff document", 100000)
        args = dict(task_id=task_id, expected_attempt=expected_attempt,
                    expected_revision=expected_revision, context_ref=context_ref,
                    supplemental_documents=supplemental_documents)
        def operation():
            task = self.engine.task(task_id)
            if task["book_id"] != self.book_id:
                raise EngineError("Task belongs to another book")
            if task["status"] != "running" or task["attempts"] != expected_attempt:
                raise EngineError("Only the exact running attempt can be adopted")
            if task["input_revision"] != expected_revision or self.engine.book(self.book_id)["current_revision"] != expected_revision:
                raise EngineError("Stale expected revision")
            if any(t["id"] != task_id and t["status"] in {"queued", "running", "submitted", "blocked", "exhausted"}
                   for t in self.engine.tasks(self.book_id)):
                raise EngineError("Resolve other outstanding work before adoption")
            with self._db() as db:
                if db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                    raise EngineError("Task is already registered; use the original receipt")
            receipt = self._save_packet(task, context_ref, supplemental_documents)
            if self.engine.task(task_id) != task:
                raise EngineError("Task changed during adoption; inspect before recovery")
            with self._db() as db:
                db.execute("INSERT INTO tasks VALUES (?,?,?)", (task_id, context_ref, task["kind"]))
            return {**receipt, "adopted_existing_attempt": True, "task_record_unchanged": True,
                    "source_freeze": "requires_operator_verification"}
        return self._change(request_id, "adopt_running", args, operation)

    def _packet(self, task):
        from .context import verify_packet
        packet = _json(checked_path(self.base, "packets/" + task["id"] + ".json").read_text(encoding="utf-8"), "Dot packet")
        verify_packet(packet)
        for key in ("id", "book_id", "input_revision", "control_hash", "attempts", "kind", "instruction"):
            if packet["task"].get(key) != task[key]:
                raise EngineError("Fixed packet task identity mismatch")
        return packet

    def _checkpoints(self, task, plan):
        from .context import validate_identity
        with self._db() as db:
            rows = db.execute("SELECT * FROM context_checkpoints WHERE task_id=? AND attempt=? AND plan_hash=? ORDER BY rowid",
                              (task["id"], task["attempts"], plan["plan_sha256"])).fetchall()
        checkpoints = []
        for row in rows:
            if digest(row["payload"]) != row["hash"]:
                raise EngineError("Context checkpoint integrity mismatch")
            checkpoint = _json(row["payload"], "checkpoint")
            validate_identity(checkpoint, task, plan)
            if checkpoint["batch_id"] != row["batch_id"]:
                raise EngineError("Context checkpoint batch mismatch")
            checkpoints.append(checkpoint)
        return checkpoints

    def _context_view(self, task, packet, document):
        from .context import cached_plan
        plan, views = cached_plan(packet)
        if document == "context-progress.json" or document.startswith("context/checkpoints/"):
            checkpoints = self._checkpoints(task, plan)
            if document == "context-progress.json":
                completed = {c["batch_id"] for c in checkpoints}
                return canonical({"task_id": task["id"], "attempt": task["attempts"],
                    "plan_sha256": plan["plan_sha256"], "completed_batches": sorted(completed),
                    "missing_batches": [b["id"] for b in plan["batches"] if b["id"] not in completed],
                    "checkpoints": [{"batch_id": c["batch_id"], "context_ref": c["context_ref"],
                        "document": "context/checkpoints/" + digest(canonical(c)) + ".json",
                        "notes_preview": c["notes"][:160], "unresolved": c["unresolved"]} for c in checkpoints],
                    "evidence_scope": "delivered bytes and executor declarations; not proof of comprehension"}), plan
            for checkpoint in checkpoints:
                if document == "context/checkpoints/" + digest(canonical(checkpoint)) + ".json":
                    return canonical(checkpoint), plan
        if document not in views:
            raise EngineError("Document is not in the fixed context plan")
        return views[document], plan

    def read(self, *, task_id, document, offset=0):
        task, _ = self._task(task_id)
        _integer(offset, "offset", 0, 10_000_000)
        plan = None
        if document.startswith("status-history/"):
            cursor = document.removeprefix("status-history/").removesuffix(".json")
            if not cursor.isascii() or not cursor.isdecimal() or document != "status-history/" + cursor + ".json":
                raise EngineError("Invalid status history document")
            content = canonical(self.status(before=int(cursor)))
        elif document == "task-info.json":
            content = canonical(self._summary(task))
        elif document == "candidate-amend-guide.json":
            from .candidate import GUIDE
            content = canonical(GUIDE)
        elif document == "candidate-history.json" or document.startswith("candidates/"):
            from .candidate import read_history
            content = read_history(self, task_id, document)
        elif document == "result.json" and task.get("result") is not None:
            content = canonical(task["result"])
            if digest(content) != task["result_hash"]:
                raise EngineError("Stored result hash mismatch")
        else:
            packet = self._packet(task)
            if document == "packet-index.json":
                content = canonical({"task": packet["task"], "context_ref": packet["context_ref"],
                    "context_guide": "context-guide.md", "context_plan": "context-plan.json",
                    "documents": [{"path": path, "characters": len(value), "sha256": packet["sha256"][path]}
                                  for path, value in packet["documents"].items()]})
            elif document.startswith("context/") or document in {"context-guide.md", "context-plan.json", "context-progress.json"}:
                content, plan = self._context_view(task, packet, document)
            elif document not in packet["documents"]:
                raise EngineError("Document is not in the fixed task packet")
            else:
                content = packet["documents"][document]
                if digest(content) != packet["sha256"][document]:
                    raise EngineError("Task packet hash mismatch")
        if offset > len(content):
            raise EngineError("Offset exceeds document length")
        end = min(len(content), offset + CHUNK_CHARS)
        if plan and document.startswith("context/batches/"):
            with self._db() as db:
                db.execute("INSERT OR IGNORE INTO context_reads VALUES (?,?,?,?,?,?)",
                           (task_id, task["attempts"], plan["plan_sha256"], document, offset, end))
        return {"task_id": task_id, "input_revision": task["input_revision"], "document": document,
                "sha256": digest(content), "offset": offset, "end_offset": end,
                "total_characters": len(content), "text": content[offset:end],
                "complete": end == len(content), "next_offset": end if end < len(content) else None}

    def chunk(self, *, request_id, task_id, attempt, upload_id, part, total, content):
        identifier(upload_id)
        _integer(attempt, "attempt", 1, 10000)
        _integer(total, "total", 1, MAX_PARTS)
        _integer(part, "part", 0, total - 1)
        _text(content, "content", CHUNK_CHARS)
        args = dict(task_id=task_id, attempt=attempt, upload_id=upload_id, part=part, total=total, content=content)
        def operation():
            task, _ = self._task(task_id)
            if (task["attempts"] != attempt or not (task["status"] == "running" or
                    (task["status"] == "submitted" and task["kind"] in {"write", "revise"}
                     and task["result_revision"] is None))):
                raise EngineError("Chunk belongs to an inactive or superseded attempt")
            with self._db() as db:
                rows = db.execute("SELECT * FROM parts WHERE task_id=? AND attempt=? AND upload_id=?",
                                  (task_id, attempt, upload_id)).fetchall()
                if any(row["total"] != total for row in rows):
                    raise EngineError("Upload part count changed")
                existing = next((row for row in rows if row["part"] == part), None)
                if existing and existing["content"] != content:
                    raise EngineError("Cannot replace an existing upload part")
                size = sum(len(row["content"].encode("utf-8")) for row in rows)
                if not existing:
                    size += len(content.encode("utf-8"))
                if size > self.engine.limits()["max_result_bytes"]:
                    raise EngineError("Upload exceeds result size limit")
                db.execute("INSERT OR IGNORE INTO parts VALUES (?,?,?,?,?,?)", (task_id, attempt, upload_id, part, total, content))
            return {"task_id": task_id, "upload_id": upload_id, "part": part, "sha256": digest(content), "stored_bytes": size}
        return self._change(request_id, "chunk", args, operation)

    def finish(self, *, request_id, task_id, attempt, upload_id):
        identifier(upload_id)
        _integer(attempt, "attempt", 1, 10000)
        args = dict(task_id=task_id, attempt=attempt, upload_id=upload_id)
        def operation():
            task, _ = self._task(task_id)
            with self._db() as db:
                rows = db.execute("SELECT * FROM parts WHERE task_id=? AND attempt=? AND upload_id=? ORDER BY part",
                                  (task_id, attempt, upload_id)).fetchall()
            if not rows or len(rows) != rows[0]["total"] or [r["part"] for r in rows] != list(range(len(rows))):
                raise EngineError("Upload is incomplete")
            raw = "".join(row["content"] for row in rows)
            result = _json(raw, "Dot result")
            from .candidate import FORMAT, amend
            if isinstance(result, dict) and result.get("format") == FORMAT:
                if result.get("task_id") != task_id:
                    raise EngineError("Candidate amendment task mismatch")
                return amend(self, result, request_id, upload_id, raw, attempt)
            from .context import CHECKPOINT, RESULT, assemble_result, cached_plan, validate_checkpoint
            if isinstance(result, dict) and result.get("format") in {CHECKPOINT, RESULT}:
                self.engine.execution_inputs(task_id, expected_attempt=attempt)
                packet = self._packet(task)
                plan, views = cached_plan(packet)
                if result["format"] == CHECKPOINT:
                    batch = validate_checkpoint(result, task, packet, plan, views)
                    if task["kind"] == "review":
                        writers = [t["id"] for t in self.engine.tasks(self.book_id)
                                   if t["result_revision"] == task["input_revision"] and t["kind"] != "review"]
                        with self._db() as db:
                            for writer in writers:
                                registered = db.execute("SELECT context_ref FROM tasks WHERE id=?", (writer,)).fetchone()
                                writer_contexts = {registered[0]} if registered else set()
                                for row in db.execute("SELECT payload FROM context_checkpoints WHERE task_id=?", (writer,)):
                                    writer_contexts.add(_json(row[0], "writer checkpoint")["context_ref"])
                                if result["context_ref"] in writer_contexts:
                                    raise EngineError("Review checkpoint must use a different context from its writer")
                    with self._db() as db:
                        ranges = db.execute("SELECT start,end FROM context_reads WHERE task_id=? AND attempt=? AND plan_hash=? AND document=? ORDER BY start,end",
                            (task_id, attempt, plan["plan_sha256"], batch["document"])).fetchall()
                        position = 0
                        for start, end in ranges:
                            if start > position:
                                break
                            position = max(position, end)
                        if position != batch["characters"]:
                            raise EngineError("Batch bytes have not all been delivered; continue reading")
                        encoded = canonical(result)
                        checksum = digest(encoded)
                        db.execute("INSERT OR IGNORE INTO context_checkpoints VALUES (?,?,?,?,?,?,?)",
                            (task_id, attempt, plan["plan_sha256"], batch["id"], checksum, encoded, now()))
                    return {"task": self._summary(task), "checkpoint_sha256": checksum,
                            "batch_id": batch["id"], "submitted": False, "published": False,
                            "evidence_scope": "bytes delivered; notes are executor claims"}
                result = assemble_result(result, task, packet, plan, self._checkpoints(task, plan))
            else:
                with self._db() as db:
                    started = db.execute("SELECT 1 FROM context_checkpoints WHERE task_id=? AND attempt=? LIMIT 1",
                                         (task_id, attempt)).fetchone()
                if started:
                    raise EngineError("Staged reading started; use novel-context-result-v1 and complete all batches")
            try:
                task = self.engine.submit(task_id, result, expected_attempt=attempt)
            except NoProgressError as exc:
                self.engine.block(task_id, "no_progress", str(exc), expected_attempt=attempt)
                raise
            return {"task": self._summary(task), "upload_sha256": digest(raw), "published": False}
        return self._change(request_id, "finish", args, operation)

    def publish(self, *, request_id, task_id, expected_revision):
        args = dict(task_id=task_id, expected_revision=expected_revision)
        def operation():
            task, _ = self._task(task_id)
            if task["input_revision"] != expected_revision:
                raise EngineError("Expected revision does not match task input")
            task = self.engine.publish(task_id)
            return {"task": self._summary(task), "book": self.engine.book(self.book_id),
                    "assessment": self.engine.assessment(self.book_id), "external_publication": False}
        return self._change(request_id, "publish", args, operation)

    def accept(self, *, request_id, expected_revision):
        def operation():
            if self.engine.book(self.book_id)["current_revision"] != expected_revision:
                raise EngineError("Stale expected revision")
            assessment = self.engine.assessment(self.book_id)
            with self._db() as db:
                for task_id in assessment["review_tasks"]:
                    if db.execute("SELECT 1 FROM tasks WHERE id=? AND kind='review'", (task_id,)).fetchone() is None:
                        raise EngineError("Acceptance requires Dot review provenance for this revision")
            return {"book": self.engine.accept(self.book_id), "assessment": assessment,
                    "literary_acceptance": "not_author_or_reader_approval", "notification_delivery": "not_attested"}
        return self._change(request_id, "accept", dict(expected_revision=expected_revision), operation)
