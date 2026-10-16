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
    tasks, books, artifacts, feedback, history = {}, {}, {}, {}, {}
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
            history[task_id] = [dict(event) for event in db.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,))]
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
    return {"tasks": tasks, "books": books, "artifacts": artifacts, "feedback": feedback, "task_events": history,
            "control_hash": engine._controls(),
            "controller_hash": _sha({p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                                     for p in sorted(Path(__file__).parent.glob("*.py"))})}


def _state(capture):
    return {**({"task_events": _sha(capture["task_events"])} if "task_events" in capture else {}),
            "tasks": {k: _sha(v) if v is not None else None for k, v in capture["tasks"].items()},
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
    if record["schema_version"] not in (1, 2) or package["id"] != _sha(record):
        raise EngineError("Bundle identity/integrity mismatch")
    _spec(record["spec"])
    capture = record["capture"]
    capture_keys = ("tasks", "books", "artifacts", "feedback", "control_hash", "controller_hash")
    if record["schema_version"] == 2:
        capture_keys += ("task_events",)
    evaluation._exact(capture, capture_keys, "capture")
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
    if record["schema_version"] == 2:
        history = capture["task_events"]
        if not isinstance(history, dict) or set(history) != set(capture["tasks"]):
            raise EngineError("Task event history selection mismatch")
        for tid, events in history.items():
            if not isinstance(events, list):
                raise EngineError("Invalid task event history")
            for event in events:
                evaluation._exact(event, ("id", "task_id", "book_id", "event", "payload", "created_at"), "peer event")
                if event["task_id"] != tid or event["book_id"] != capture["tasks"][tid]["task"]["book_id"]:
                    raise EngineError("Peer event task mismatch")
                if not isinstance(event["payload"], str):
                    raise EngineError("Invalid peer event payload")
                _json(event["payload"], "peer event")
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
    record = {"schema_version": 2, "created_at": now(), "spec": spec,
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


def guard_claim(engine, db, task, *, applying_bundle=None):
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
        if package["id"] == applying_bundle:
            continue  # Only the explicit atomic adoption path may consume this result.
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


def apply(engine, path, task_id, baseline, expected_base, expected_target):
    """Explicitly adopt one completed write/revise task as a draft, atomically.

    No generic file copying, foreign task creation, review acceptance, or merging.
    A local queued task and the exact shared baseline must already exist.
    """
    from .engine import digest
    from .records import validate_result
    package, known = _read(path), _read(baseline)
    record = package["record"]
    spec = record["spec"]
    if record["schema_version"] != 2 or spec["task_ids"] != [task_id] or spec["artifacts"]:
        raise EngineError("Apply requires a v2 single-task bundle without extra artifacts")
    if record["baseline"] != {"id": known["id"], "state": known["record"]["state"]}:
        raise EngineError("Apply baseline mismatch")
    received = checked_path(engine.root, f"runtime/exchange/inbox/{spec['origin']}/{spec['operation_id']}.json")
    if _read(received) != package:
        raise EngineError("Apply requires the exact received bundle")
    peer = record["capture"]["tasks"][task_id]["task"]
    if peer["kind"] not in ("write", "revise") or peer["status"] != "completed":
        raise EngineError("Apply supports completed write/revise tasks only")
    if peer["input_revision"] != expected_base or peer["result_revision"] != expected_target:
        raise EngineError("Explicit input/target revision mismatch")
    if record["capture"]["books"].get(peer["book_id"]) != expected_target:
        raise EngineError("Peer has advanced beyond the selected result")
    with engine._db(True) as db:
        local = engine._row(db, "tasks", task_id)
        for row in db.execute("SELECT payload FROM events WHERE task_id=? AND event='exchange.applied'", (task_id,)):
            applied = json.loads(row["payload"])
            if applied["bundle_id"] == package["id"]:
                if local["result_hash"] != peer["result_hash"] or local["result_revision"] != expected_target:
                    raise EngineError("Applied task has changed")
                return {"bundle_id": package["id"], "revision": expected_target, "duplicate": True}
        if local["status"] != "queued" or local["result"] is not None:
            raise EngineError("Local task must be queued with no result; never replace active/stopped work")
        if _state(_capture(engine, spec, required=True)) != known["record"]["state"]:
            raise EngineError("Local state diverged from shared baseline")
        for field in ("id", "book_id", "kind", "instruction", "input_revision", "control_hash", "created_at"):
            if local[field] != peer[field]:
                raise EngineError("Task identity or instruction mismatch")
        if any(peer[k] < local[k] for k in ("attempts", "no_progress")):
            raise EngineError("Cannot reset cumulative counters")
        limits = engine.limits()
        if not 1 <= peer["attempts"] <= limits["max_attempts"] or peer["no_progress"] >= limits["max_no_progress"]:
            raise EngineError("Peer counters exceed local stop limits")
        guard_claim(engine, db, local, applying_bundle=package["id"])
        files = engine._fresh(db, local)
        result = peer["result"]
        encoded = canonical(result)
        if len(encoded.encode('utf-8')) > limits["max_result_bytes"]:
            raise EngineError("Result exceeds configured size limit")
        validate_result(result, local, files)
        engine._check_changes(files, result)
        engine._check_adoption(files, result)
        if not any(files.get(c["path"]) != c["content"] for c in result["changes"]):
            raise EngineError("No effective change")
        merged = {**files, **{c["path"]: c["content"] for c in result["changes"]}}
        hashes = {p: digest(content) for p, content in sorted(merged.items())}
        target = digest(canonical({"book_id": local["book_id"], "parent": expected_base,
                                   "task_id": task_id, "hashes": hashes}))
        if target != expected_target or hashes != record["capture"]["tasks"][task_id]["output_hashes"]:
            raise EngineError("Result does not reproduce the expected target snapshot")
        db.execute("UPDATE tasks SET result=?,result_hash=?,attempts=?,no_progress=?,status='submitted',updated_at=? WHERE id=?",
                   (encoded, digest(encoded), peer["attempts"], peer["no_progress"], now(), task_id))
        engine._publish_locked(db, engine._row(db, "tasks", task_id))
        for event in record["capture"]["task_events"][task_id]:
            engine._event(db, "exchange.peer_event", {"bundle_id": package["id"], "source_event": event}, task_id, local["book_id"])
        engine._event(db, "exchange.applied", {"bundle_id": package["id"], "baseline_id": known["id"],
                      "input_revision": expected_base, "target_revision": expected_target,
                      "scope": "draft result only; peer feedback stays in received evidence"}, task_id, local["book_id"])
        # Acknowledges this exact imported evidence, not unknown later peer work.
        engine._event(db, "exchange.baseline_checked", {"bundle_id": package["id"],
                      "selected_state_hash": _sha(record["state"]), "scope": "explicit draft adoption"}, task_id, local["book_id"])
    return {"bundle_id": package["id"], "revision": expected_target, "duplicate": False}
