"""Local, explicit handoff bundles. No transport, live import, or auto-merge.

Only selected UTF-8 artifacts travel. Task state comes from the controller;
verification notes remain operator declarations. Inbox copies never alter books.
"""
import hashlib
import json
from pathlib import Path
import re

from .engine import EngineError, canonical, checked_path, identifier, now
from . import evaluation
from .records import _json

MAX_BYTES = 16 * 1024 * 1024
SPEC_KEYS = ("origin", "operation_id", "task_ids", "artifacts", "verification", "unresolved", "next_step", "excluded")
PREFIXES = ("books/", "runtime/inputs/", "runtime/feedback/", "evaluations/experiments/")


def _sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _path(value):
    if not isinstance(value, str) or not value.startswith(PREFIXES):
        raise EngineError("Only explicitly selected book/input/feedback/evaluation artifacts are supported")
    if any(not re.fullmatch(r"[A-Za-z0-9_\-.]+", part) or part in (".", "..")
           or part.endswith((".", " ")) or part.split('.')[0].upper() in
           {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}
           for part in value.split("/")):
        raise EngineError("Unsafe or nonportable artifact path")
    if not value.endswith((".json", ".txt", ".md")):
        raise EngineError("Only UTF-8 JSON/text/Markdown artifacts are supported")
    return value


def _spec(spec):
    evaluation._exact(spec, SPEC_KEYS, "handoff spec")
    for field in ("origin", "operation_id"):
        identifier(spec[field])
    for field in ("task_ids", "artifacts", "unresolved", "excluded"):
        if not isinstance(spec[field], list) or any(not isinstance(v, str) or not v.strip() for v in spec[field]):
            raise EngineError(f"{field} must be a string list")
        if len(spec[field]) != len(set(spec[field])):
            raise EngineError(f"Duplicate {field}")
    if len({p.casefold() for p in spec["artifacts"]}) != len(spec["artifacts"]):
        raise EngineError("Artifact case collision")
    for task in spec["task_ids"]:
        identifier(task)
    for path in spec["artifacts"]:
        _path(path)
    for field in ("verification", "next_step"):
        evaluation._text(spec[field], field)
    if not spec["task_ids"] and not spec["artifacts"]:
        raise EngineError("Select at least one task or artifact")


def _capture(engine, spec, *, required):
    tasks, books, artifacts, feedback = {}, {}, {}, {}
    with engine._db() as db:
        for task_id in spec["task_ids"]:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                if required:
                    raise EngineError("Unknown export task")
                tasks[task_id] = None
                continue
            # Handoff verifies snapshots and stored result hashes.
            tasks[task_id] = engine.handoff(task_id)
            books[row["book_id"]] = tasks[task_id]["current_revision"]
        for book_id in books:
            feedback[book_id] = [dict(row) for row in db.execute(
                "SELECT * FROM feedback WHERE book_id=? ORDER BY id", (book_id,))]
    total_bytes = 0
    for relative in spec["artifacts"]:
        path = checked_path(engine.root, relative)
        if not path.is_file():
            if required:
                raise EngineError(f"Missing artifact: {relative}")
            artifacts[relative] = None
        else:
            if path.stat().st_size > MAX_BYTES:
                raise EngineError("Artifact exceeds bundle size limit")
            with path.open("rb") as stream:
                data = stream.read(MAX_BYTES + 1)
            total_bytes += len(data)
            if total_bytes > MAX_BYTES:
                raise EngineError("Selected artifacts exceed bundle size limit")
            artifacts[relative] = data.decode("utf-8")
    return {"tasks": tasks, "books": books, "artifacts": artifacts, "feedback": feedback,
            "control_hash": engine._controls(),
            "controller_hash": _sha({p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                                     for p in sorted(Path(__file__).parent.glob("*.py"))})}


def _state(capture):
    return {"tasks": {k: _sha(v) if v is not None else None for k, v in capture["tasks"].items()},
            "books": capture["books"], "feedback": _sha(capture["feedback"]),
            "control_hash": capture["control_hash"], "controller_hash": capture["controller_hash"],
            "artifacts": {k: hashlib.sha256(v.encode("utf-8")).hexdigest() if v is not None else None for k, v in capture["artifacts"].items()}}


def _read(path):
    path = Path(path).absolute()
    checked_path(path.parent, path.name)
    if path.stat().st_size > MAX_BYTES:
        raise EngineError("Bundle exceeds size limit")
    package = _json(path.read_text(encoding="utf-8"), "handoff bundle")
    evaluation._exact(package, ("id", "record"), "bundle")
    record = package["record"]
    evaluation._exact(record, ("schema_version", "created_at", "spec", "baseline", "capture", "state"), "bundle record")
    if record["schema_version"] != 1 or package["id"] != _sha(record):
        raise EngineError("Bundle identity/integrity mismatch")
    _spec(record["spec"])
    capture = record["capture"]
    evaluation._exact(capture, ("tasks", "books", "artifacts", "feedback", "control_hash", "controller_hash"), "capture")
    if (not isinstance(capture["tasks"], dict) or not isinstance(capture["artifacts"], dict)
            or not isinstance(capture["books"], dict)
            or set(capture["tasks"]) != set(record["spec"]["task_ids"])
            or set(capture["artifacts"]) != set(record["spec"]["artifacts"])):
        raise EngineError("Bundle selection mismatch")
    if any(not isinstance(v, str) for v in capture["artifacts"].values()):
        raise EngineError("Bundle artifact must contain UTF-8 text")
    for field in ("control_hash", "controller_hash"):
        if not isinstance(capture[field], str) or not re.fullmatch("[0-9a-f]{64}", capture[field]):
            raise EngineError("Invalid controller/control hash")
    if not isinstance(capture["feedback"], dict):
        raise EngineError("Invalid feedback capture")
    for task_id, handoff in capture["tasks"].items():
        if not isinstance(handoff, dict) or not isinstance(handoff.get("task"), dict):
            raise EngineError("Invalid task handoff")
        task = handoff["task"]
        if task.get("id") != task_id or task.get("status") not in (
                "queued", "running", "submitted", "completed", "blocked", "exhausted", "cancelled"):
            raise EngineError("Invalid task identity/status")
        for field in ("attempts", "no_progress"):
            if type(task.get(field)) is not int or task[field] < 0:
                raise EngineError("Invalid task counters")
        if task.get("book_id") not in capture["books"]:
            raise EngineError("Missing task book state")
        if task.get("result") is not None and _sha(task["result"]) != task.get("result_hash"):
            raise EngineError("Task result hash mismatch")
        if task["status"] == "completed" and (task.get("result") is None or not task.get("result_revision")):
            raise EngineError("Completed task lacks result")
    if _state(capture) != record["state"]:
        raise EngineError("Bundle state mismatch")
    baseline = record["baseline"]
    if baseline is not None:
        evaluation._exact(baseline, ("id", "state"), "baseline")
        if not isinstance(baseline["id"], str) or not re.fullmatch('[0-9a-f]{64}', baseline['id']):
            raise EngineError("Invalid baseline id")
    return package


def create(engine, spec, output, baseline=None):
    _spec(spec)
    base = _read(baseline) if baseline else None
    if base and any(set(base["record"]["spec"][key]) != set(spec[key]) for key in ("task_ids", "artifacts")):
        raise EngineError("Selection changed; establish a new baseline explicitly")
    capture = _capture(engine, spec, required=True)
    record = {"schema_version": 1, "created_at": now(), "spec": spec,
              "baseline": {"id": base["id"], "state": base["record"]["state"]} if base else None,
              "capture": capture, "state": _state(capture)}
    package = {"id": _sha(record), "record": record}
    encoded = canonical(package) + "\n"
    if len(encoded.encode('utf-8')) > MAX_BYTES:
        raise EngineError("Bundle exceeds size limit")
    if _capture(engine, spec, required=True) != capture:
        raise EngineError("Source changed during capture; stop writers before exporting")
    output = Path(output).absolute()
    checked_path(output.parent, output.name)
    engine._new_file(output, encoded)
    return {"id": package["id"], "path": str(output), "status": "created_not_transferred"}


def check(engine, path, baseline=None):
    return _check_package(engine, _read(path), baseline)


def _check_package(engine, package, baseline):
    record = package["record"]
    local = _state(_capture(engine, record["spec"], required=False))
    remote = record["state"]
    base = record["baseline"]
    baseline_verified = False
    if baseline:
        known = _read(baseline)
        if base is None or base != {"id": known["id"], "state": known["record"]["state"]}:
            raise EngineError("Provided baseline does not match bundle")
        baseline_verified = True
    if local == remote:
        status = "same_selected_state"
    elif not baseline_verified:
        status = "unknown_baseline"
    elif local == base["state"]:
        status = "incoming_ahead"
    elif remote == base["state"]:
        status = "local_ahead"
    else:
        status = "diverged"
    completed = [tid for tid, handoff in record["capture"]["tasks"].items()
                 if isinstance(handoff, dict) and handoff.get("task", {}).get("status") == "completed"]
    stopped = [tid for tid, handoff in record["capture"]["tasks"].items()
               if isinstance(handoff, dict) and handoff.get("task", {}).get("status") in ("blocked", "exhausted")]
    blockers = ([] if status == "same_selected_state" else ["Reconcile peer state before executing selected work"])
    if completed:
        blockers.append("Do not rerun incoming completed task ids")
    if stopped:
        blockers.append("Preserve and explicitly resolve incoming stop conditions")
    return {"bundle_id": package["id"], "status": status, "work_blockers": blockers,
            "incoming_stopped_tasks": stopped, "baseline_verified": baseline_verified,
            "incoming_completed_tasks": completed, "local_state": local, "incoming_state": remote,
            "unresolved": record["spec"]["unresolved"], "next_step": record["spec"]["next_step"],
            "verification_declaration": record["spec"]["verification"], "excluded": record["spec"]["excluded"],
            "live_import_performed": False, "peer_latest_known": False,
            "action": "Compare selected evidence before work; do not repeat completed tasks. No live import or automatic permission to execute."}


def receive(engine, path, baseline=None):
    # Serialize inbox publication with claim's BEGIN IMMEDIATE transaction.
    with engine._db(True):
        return _receive(engine, path, baseline)


def _receive(engine, path, baseline=None):
    package = _read(path)
    report = _check_package(engine, package, baseline)
    spec = package["record"]["spec"]
    # Stable operation identity rejects reuse with a different payload. The inbox
    # is a retained peer copy, never a replacement of live files or SQLite.
    relative = f"runtime/exchange/inbox/{spec['origin']}/{spec['operation_id']}.json"
    target = checked_path(engine.root, relative)
    if target.exists():
        if _read(target) != package:
            raise EngineError("Operation id already received with different content")
        duplicate = True
    else:
        engine._new_file(target, canonical(package) + "\n")
        duplicate = False
    return {"receipt": {"bundle_id": package["id"], "origin": spec["origin"],
                        "operation_id": spec["operation_id"], "status": "received_copy_only",
                        "duplicate": duplicate, "path": relative}, "preflight": report}


def guard_claim(engine, db, task):
    """Fail closed on unprocessed peer evidence; called inside claim transaction.

    A matching selected baseline is acknowledged in the same transaction as the
    claim. Later local progress must not be mistaken for an unresolved old fork.
    New peer packages are new evidence and must be checked again.
    """
    inbox = checked_path(engine.root, "runtime/exchange/inbox")
    if not inbox.exists():
        return
    acknowledged = set()
    for row in db.execute("SELECT payload FROM events WHERE event='exchange.baseline_checked' AND book_id=?",
                          (task["book_id"],)):
        acknowledged.add(json.loads(row["payload"])["bundle_id"])
    packages = []
    for origin in sorted(inbox.iterdir()):
        identifier(origin.name)
        directory = checked_path(engine.root, f"runtime/exchange/inbox/{origin.name}")
        if not directory.is_dir():
            raise EngineError("Invalid exchange inbox directory")
        for item in sorted(directory.iterdir()):
            if item.suffix != ".json":
                raise EngineError("Unexpected exchange inbox file")
            identifier(item.stem)
            path = checked_path(engine.root, f"runtime/exchange/inbox/{origin.name}/{item.name}")
            package = _read(path)
            record = package["record"]
            if record["spec"]["origin"] != origin.name or record["spec"]["operation_id"] != item.stem:
                raise EngineError("Exchange inbox identity mismatch")
            books = record["capture"]["books"]
            if books and task["book_id"] not in books:
                continue
            packages.append(package)
    superseded = set()
    known = {p["id"]: p for p in packages}
    for package in packages:
        record = package["record"]
        base = record["baseline"]
        if base and base["id"] in known:
            older = known[base["id"]]["record"]
            if (base["state"] != older["state"] or
                    any(set(record["spec"][k]) != set(older["spec"][k]) for k in ("task_ids", "artifacts"))):
                raise EngineError("Received baseline chain mismatch")
            for tid, handoff in record["capture"]["tasks"].items():
                previous = older["capture"]["tasks"][tid]["task"]
                if any(handoff["task"][k] < previous[k] for k in ("attempts", "no_progress")):
                    raise EngineError("Peer handoff resets cumulative counters")
            superseded.add(base["id"])
    for package in packages:
        record = package["record"]
        peers = [h["task"] for h in record["capture"]["tasks"].values()
                 if h["task"]["book_id"] == task["book_id"]]
        for peer in peers:
            if peer["id"] == task["id"] and peer["status"] in ("completed", "cancelled"):
                raise EngineError(f"Peer already finished task {task['id']}; do not repeat it")
        if package["id"] in acknowledged or package["id"] in superseded:
            continue
        if any(p["status"] in ("running", "submitted", "blocked", "exhausted") for p in peers):
            raise EngineError("Peer has active/stopped work; reconcile it before claiming")
        report = _check_package(engine, package, None)
        if report["status"] != "same_selected_state":
            raise EngineError(f"Unreconciled peer bundle {package['id']}: selected state differs or baseline is unknown; run bundle-check")
        engine._event(db, "exchange.baseline_checked", {"bundle_id": package["id"],
                      "selected_state_hash": _sha(report["local_state"]),
                      "scope": "selected evidence only; peer latest state is unknown"}, task["id"], task["book_id"])
