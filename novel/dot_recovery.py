"""Operator-only completion of interrupted task opening, with original receipts retained."""
from .engine import EngineError, canonical, digest, identifier
from .records import _json


def unresolved_requests(db, book_id):
    recovered = set()
    for row in db.execute("SELECT receipt FROM requests WHERE state='done' AND receipt LIKE ?",
                          ('%"recovered_request_id":%',)):
        recovered.add(_json(row[0], "recovery receipt")["recovered_request_id"])
    pending, recoverable = [], []
    for row in db.execute("SELECT id,state,receipt FROM requests WHERE state IN ('pending','error') ORDER BY rowid"):
        if row["id"] in recovered:
            continue
        receipt = _json(row["receipt"], "request receipt") if row["receipt"] else {}
        if receipt.get("book_id", book_id) != book_id:
            continue
        if row["state"] == "pending":
            pending.append(row["id"])
        if receipt.get("operation") == "open":
            recoverable.append({"request_id": row["id"], "task_id": receipt["task_id"],
                                "state": row["state"], "error": receipt.get("error")})
    return pending, recoverable


def recover_open_task(workspace, *, request_id, failed_request_id, task_id,
                      expected_attempt, expected_revision, context_ref, note):
    """Finish only the bound queued/running task; never resume, reset or recreate it.

    A new request records the recovery. The original pending/error receipt remains
    byte-for-byte intact. Legacy requests require an existing Dot registration;
    new requests also carry the task identity durably before enqueue begins.
    """
    from .dot import _integer, _text
    identifier(failed_request_id)
    identifier(task_id)
    _integer(expected_attempt, "expected_attempt", 0, 10000)
    _text(context_ref, "context_ref", 240)
    _text(note, "recovery note")
    if request_id == failed_request_id:
        raise EngineError("Recovery requires a new request ID; retain the original receipt")
    arguments = dict(failed_request_id=failed_request_id, task_id=task_id,
                     expected_attempt=expected_attempt, expected_revision=expected_revision,
                     context_ref=context_ref, note=note)

    def operation():
        with workspace._db() as db:
            failed = db.execute("SELECT * FROM requests WHERE id=?", (failed_request_id,)).fetchone()
            known = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if failed is None or failed["state"] not in {"pending", "error"}:
            raise EngineError("Recovery requires an interrupted or failed original open request")
        task = workspace.engine.task(task_id)
        if (task["book_id"] != workspace.book_id or task["status"] not in {"queued", "running"}
                or task["attempts"] != expected_attempt or task["result"] is not None
                or task["input_revision"] != expected_revision):
            raise EngineError("Recovery must bind the exact unfinished original task and attempt")
        original_args = dict(kind=task["kind"], instruction=task["instruction"],
                             expected_revision=expected_revision, context_ref=context_ref)
        if failed["signature"] != digest(canonical(["open", original_args])):
            raise EngineError("Original open request arguments do not match this task")
        intent = _json(failed["receipt"], "original request") if failed["receipt"] else {}
        if "operation" in intent:
            if (intent.get("operation") != "open" or intent.get("task_id") != task_id
                    or intent.get("book_id") != workspace.book_id or intent.get("arguments") != original_args):
                raise EngineError("Original open intent does not match this task")
        elif known is None:
            raise EngineError("Legacy open lacks a verified task registration; operator inspection required")
        if known and (known["context_ref"] != context_ref or known["kind"] != task["kind"]):
            raise EngineError("Original task registration differs")
        if any(t["id"] != task_id and t["status"] in {"queued", "running", "submitted", "blocked", "exhausted"}
               for t in workspace.engine.tasks(workspace.book_id)):
            raise EngineError("Other outstanding work prevents open recovery")
        with workspace.engine._db() as db:
            workspace.engine._fresh(db, task)
        packet_path = workspace.base / "packets" / (task_id + ".json")
        with workspace._db() as db:
            if not packet_path.exists() and any(db.execute(
                    f"SELECT 1 FROM {table} WHERE task_id=? LIMIT 1", (task_id,)).fetchone()
                    for table in ("parts", "context_reads", "context_checkpoints")):
                raise EngineError("Missing packet has existing execution evidence; restore the original backup")
            if known is None:
                db.execute("INSERT INTO tasks VALUES (?,?,?)", (task_id, context_ref, task["kind"]))
        if task["status"] == "queued":
            if expected_attempt != 0:
                raise EngineError("Recovery cannot reclaim a previously attempted task")
            task = workspace.engine.claim(task_id, expected_attempt=1)
        else:
            workspace.engine.execution_inputs(task_id, expected_attempt=expected_attempt)
        receipt = workspace._save_packet(task, context_ref)
        return {**receipt, "recovered_request_id": failed_request_id,
                "original_receipt_sha256": digest(failed["receipt"] or ""), "recovery_note": note}

    return workspace._change(request_id, "recover_open", arguments, operation)
