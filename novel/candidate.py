"""Bounded amendment of unpublished candidates; no schema or book writes."""
from .engine import EngineError, NoProgressError, canonical, digest, now
from .records import validate_result
from .context import RESULT, exact, assemble_result, cached_plan

FORMAT = "novel-candidate-amend-v1"
GUIDE = {"format": FORMAT, "fields": ["format", "task_id", "attempt", "input_revision",
    "expected_result_hash", "reason", "candidate"],
    "candidate": "Complete novel-context-result-v1 envelope using the unchanged fixed plan and checkpoints",
    "upload": "Use a new upload_id with novel_work_chunk; then novel_work_finish. Never overwrite old uploads.",
    "read": "result.json is current; candidate-history.json lists immutable candidates/<sha256>.json documents.",
    "scope": "Only submitted, unpublished write/revise tasks. No publishing, reset or counter changes."}


def amend(workspace, payload, request_id, upload_id, raw, attempt):
    exact(payload, GUIDE["fields"], "candidate amendment")
    if (payload["format"] != FORMAT or type(payload["attempt"]) is not int
            or payload["attempt"] != attempt):
        raise EngineError("Candidate amendment attempt mismatch")
    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
        raise EngineError("Candidate amendment requires a bounded reason")
    engine = workspace.engine
    with engine._db(True) as db:
        task = engine._row(db, "tasks", payload["task_id"])
        if (task["book_id"] != workspace.book_id or task["status"] != "submitted"
                or task["kind"] not in {"write", "revise"} or task["result_revision"] is not None):
            raise EngineError("Only unpublished submitted write/revise candidates can be amended")
        if (task["attempts"] != attempt or task["input_revision"] != payload["input_revision"]
                or task["result_hash"] != payload["expected_result_hash"]):
            raise EngineError("Stale candidate hash, revision or attempt")
        if not task["result"] or digest(task["result"]) != task["result_hash"]:
            raise EngineError("Stored candidate integrity mismatch")
        files = engine._fresh(db, task)
        from .exchange import guard_claim
        guard_claim(engine, db, task)
        packet = workspace._packet(task)
        plan, _ = cached_plan(packet)
        candidate = payload["candidate"]
        if not isinstance(candidate, dict) or candidate.get("format") != RESULT:
            raise EngineError("Amendment requires complete novel-context-result-v1 coverage")
        result = assemble_result(candidate, task, packet, plan, workspace._checkpoints(task, plan))
        encoded = canonical(result)
        if len(encoded.encode("utf-8")) > engine.limits()["max_result_bytes"]:
            raise EngineError("Result exceeds configured size limit")
        validate_result(result, task, files)
        engine._check_changes(files, result)
        engine._check_adoption(files, result)
        if not any(files.get(c["path"]) != c["content"] for c in result["changes"]):
            raise NoProgressError("No effective change; candidate preserved")
        if digest(encoded) == task["result_hash"]:
            raise EngineError("Amendment does not change candidate")
        # Archive exact saved candidate text in the same transaction as replacement.
        engine._event(db, "task.candidate_amended", {"request_id": request_id,
            "attempt": attempt, "input_revision": task["input_revision"], "reason": reason,
            "old_result": task["result"], "old_result_hash": task["result_hash"],
            "new_result": encoded, "new_result_hash": digest(encoded),
            "upload_id": upload_id, "upload_sha256": digest(raw)}, task["id"], task["book_id"])
        db.execute("UPDATE tasks SET result=?,result_hash=?,updated_at=? WHERE id=?",
                   (encoded, digest(encoded), now(), task["id"]))
        updated = engine._row(db, "tasks", task["id"])
    return {"task": workspace._summary(updated), "previous_result_hash": task["result_hash"],
            "upload_sha256": digest(raw), "amended": True, "published": False,
            "history_document": "candidate-history.json"}


def read_history(workspace, task_id, document):
    with workspace.engine._db() as db:
        task = workspace.engine._row(db, "tasks", task_id)
        rows = db.execute("SELECT payload,created_at FROM events WHERE task_id=? AND event=? ORDER BY id",
                          (task_id, "task.candidate_amended")).fetchall()
    candidates, amendments = {}, []
    if task["result"] is not None:
        candidates[task["result_hash"]] = task["result"]
    for row in rows:
        import json
        event = json.loads(row["payload"])
        for prefix in ("old", "new"):
            candidates[event[prefix + "_result_hash"]] = event[prefix + "_result"]
        amendments.append({k: v for k, v in event.items() if k not in {"old_result", "new_result"}})
        amendments[-1]["created_at"] = row["created_at"]
    if any(digest(value) != key for key, value in candidates.items()):
        raise EngineError("Candidate history integrity mismatch")
    if document == "candidate-history.json":
        return canonical({"task_id": task_id, "current_result_hash": task["result_hash"],
            "candidates": [{"sha256": key, "document": "candidates/" + key + ".json"}
                           for key in candidates], "amendments": amendments})
    for key, value in candidates.items():
        if document == "candidates/" + key + ".json":
            return value
    raise EngineError("Unknown candidate history document")
