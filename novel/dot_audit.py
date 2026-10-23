"""Read-only recovery checks for a quiescent Dot backup; never initializes a gateway."""
from collections import defaultdict
from contextlib import closing
import re
import sqlite3

from .context import book_files, build_plan, validate_checkpoint, verify_packet
from .engine import EngineError, canonical, checked_path, digest
from .records import _json


def audit_dot(engine):
    base = checked_path(engine.root, "runtime/dot")
    database = checked_path(base, "gateway.sqlite3")
    if not database.is_file():
        raise EngineError("Dot recovery audit: gateway database is missing")
    for suffix in ("-wal", "-shm", "-journal"):
        checked_path(base, "gateway.sqlite3" + suffix)
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise EngineError("Dot gateway integrity check failed")
            rows = {table: [dict(row) for row in db.execute("SELECT * FROM " + table)]
                    for table in ("tasks", "requests", "parts", "context_reads", "context_checkpoints")}
    except sqlite3.Error as exc:
        raise EngineError("Dot recovery audit: cannot read the complete gateway") from exc

    registered = {row["id"]: row for row in rows["tasks"]}
    tasks = {task_id: engine.task(task_id) for task_id in registered}
    by_task = {name: defaultdict(list) for name in ("parts", "context_reads", "context_checkpoints")}
    for table, grouped in by_task.items():
        for row in rows[table]:
            if row["task_id"] not in registered:
                raise EngineError("Dot recovery audit: orphan " + table)
            if not 1 <= row["attempt"] <= tasks[row["task_id"]]["attempts"]:
                raise EngineError("Dot recovery audit: invalid attempt in " + table)
            grouped[row["task_id"]].append(row)

    checkpoint_hashes, complete_uploads, chunks = set(), set(), set()
    for task_id, task in tasks.items():
        packet_path = checked_path(base, "packets/" + task_id + ".json")
        if not packet_path.is_file():
            raise EngineError("Dot recovery audit: missing fixed packet for " + task_id)
        try:
            packet = _json(packet_path.read_text(encoding="utf-8"), "Dot packet")
            verify_packet(packet)
            for key in ("id", "book_id", "input_revision", "control_hash", "attempts", "kind", "instruction"):
                if packet["task"].get(key) != task[key]:
                    raise EngineError("Dot recovery audit: packet task identity mismatch")
            if (registered[task_id]["kind"] != task["kind"]
                    or registered[task_id]["context_ref"] != packet["context_ref"]):
                raise EngineError("Dot recovery audit: task registration mismatch")
            if book_files(packet) != engine.files(task["book_id"], task["input_revision"]):
                raise EngineError("Dot recovery audit: packet differs from its input snapshot")
            plan, views = build_plan(packet)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise EngineError("Dot recovery audit: invalid fixed packet for " + task_id + ": " + str(exc)) from exc
        batches = {b["document"]: b for b in plan["batches"]}
        ranges = defaultdict(list)
        for row in by_task["context_reads"][task_id]:
            batch = batches.get(row["document"])
            if (batch is None or row["plan_hash"] != plan["plan_sha256"]
                    or row["attempt"] != task["attempts"]
                    or not 0 <= row["start"] <= row["end"] <= batch["characters"]):
                raise EngineError("Dot recovery audit: invalid delivered range")
            ranges[row["document"]].append((row["start"], row["end"]))
        for row in by_task["context_checkpoints"][task_id]:
            if digest(row["payload"]) != row["hash"] or row["plan_hash"] != plan["plan_sha256"]:
                raise EngineError("Dot recovery audit: checkpoint hash mismatch")
            payload = _json(row["payload"], "checkpoint")
            if payload["batch_id"] != row["batch_id"] or payload["attempt"] != row["attempt"]:
                raise EngineError("Dot recovery audit: checkpoint row identity mismatch")
            batch = validate_checkpoint(payload, task, packet, plan, views)
            position = 0
            for start, end in sorted(ranges[batch["document"]]):
                if start > position:
                    break
                position = max(position, end)
            if position != batch["characters"]:
                raise EngineError("Dot recovery audit: checkpoint lacks complete delivery evidence")
            checkpoint_hashes.add((task_id, row["attempt"], row["hash"]))
        uploads = defaultdict(list)
        for row in by_task["parts"][task_id]:
            if (not 1 <= row["total"] <= 256 or not 0 <= row["part"] < row["total"]
                    or not isinstance(row["content"], str) or not 1 <= len(row["content"]) <= 6000):
                raise EngineError("Dot recovery audit: invalid upload part")
            uploads[(row["attempt"], row["upload_id"])].append(row)
            args = {key: row[key] for key in ("task_id", "attempt", "upload_id", "part", "total", "content")}
            chunks.add((task_id, row["upload_id"], row["part"], digest(row["content"]),
                        digest(canonical(["chunk", args]))))
        for (attempt, upload_id), parts in uploads.items():
            parts.sort(key=lambda row: row["part"])
            if len({row["total"] for row in parts}) != 1:
                raise EngineError("Dot recovery audit: inconsistent upload totals")
            # Partial uploads are valid durable progress, not a completed result.
            if [row["part"] for row in parts] == list(range(parts[0]["total"])):
                complete_uploads.add((task_id, attempt, digest("".join(row["content"] for row in parts))))

    for row in rows["requests"]:
        if row["state"] not in {"pending", "error", "done"} or not re.fullmatch(r"[0-9a-f]{64}", row["signature"]):
            raise EngineError("Dot recovery audit: invalid request record")
        if row["state"] == "pending":
            continue
        receipt = _json(row["receipt"], "request receipt")
        if row["state"] == "error":
            if not isinstance(receipt.get("error"), str):
                raise EngineError("Dot recovery audit: missing original error")
            continue
        if {"task_id", "upload_id", "part", "sha256"} <= receipt.keys():
            key = (receipt["task_id"], receipt["upload_id"], receipt["part"], receipt["sha256"], row["signature"])
            if key not in chunks:
                raise EngineError("Dot recovery audit: saved chunk receipt has no matching upload part")
        if "checkpoint_sha256" in receipt:
            task = receipt["task"]
            if (task["id"], task["attempts"], receipt["checkpoint_sha256"]) not in checkpoint_hashes:
                raise EngineError("Dot recovery audit: saved receipt has no matching checkpoint")
        if "upload_sha256" in receipt:
            task = receipt["task"]
            if (task["id"], task["attempts"], receipt["upload_sha256"]) not in complete_uploads:
                raise EngineError("Dot recovery audit: finished upload is incomplete or changed")
        if "recovered_request_id" in receipt:
            originals = [r for r in rows["requests"] if r["id"] == receipt["recovered_request_id"]]
            if len(originals) != 1 or digest(originals[0]["receipt"] or "") != receipt["original_receipt_sha256"]:
                raise EngineError("Dot recovery audit: original recovery evidence changed")
    return {"database": "ok", "tasks_verified": len(tasks), "requests_verified": len(rows["requests"]),
            "uploads_verified": len(complete_uploads), "checkpoints_verified": len(checkpoint_hashes),
            "scope": "quiescent backup; partial uploads and original errors retained"}
