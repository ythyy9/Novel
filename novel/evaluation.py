"""Small append-only method comparisons; never edits methods or policies.

A/B labels are randomized independently per case. ``reviewer`` is the source
declared by the operator entering feedback, not an authenticated identity. Agent
feedback stays separate from author/reader feedback. Hashes detect damaged or
changed records; they are not signatures or an OS permission boundary.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import uuid

from .engine import Engine, EngineError, canonical, checked_path, identifier, now


SPLITS = ("development", "holdout")
REVIEWERS = ("author", "target_reader", "agent")
CHOICES = ("A", "B", "tie", "inconclusive")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise EngineError(f"{label} must be a nonempty string")
    return value


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise EngineError(f"Invalid fields in {label}")


def _base(root, experiment_id):
    identifier(experiment_id)
    return checked_path(Path(root).absolute(), f"evaluations/experiments/{experiment_id}")


def _hash(record):
    return hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()


def _write(path, record):
    # Exclusive creation also prevents an uncertain write from being overwritten.
    Engine._new_file(path, canonical({"record": record, "sha256": _hash(record)}) + "\n")


def _read(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise EngineError(f"Duplicate JSON key in {path.name}")
            value[key] = item
        return value

    try:
        envelope = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        _exact(envelope, ("record", "sha256"), path.name)
        if not isinstance(envelope["record"], dict) or _hash(envelope["record"]) != envelope["sha256"]:
            raise EngineError(f"Record integrity failure: {path.name}")
        return envelope["record"], envelope["sha256"]
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise EngineError(f"Cannot verify evaluation record {path.name}: {exc}") from exc


def _load(root, experiment_id):
    base = _base(root, experiment_id)
    manifest, checksum = _read(checked_path(base, "manifest.json"))
    _exact(manifest, ("schema_version", "id", "hypothesis", "baseline_method", "candidate_method", "cases"), "manifest")
    if manifest["schema_version"] != 1 or manifest["id"] != experiment_id:
        raise EngineError("Evaluation manifest identity/version mismatch")
    for field in ("hypothesis", "baseline_method", "candidate_method"):
        _text(manifest[field], field)
    if not isinstance(manifest["cases"], list) or not manifest["cases"]:
        raise EngineError("Evaluation requires cases")
    ids, splits = set(), set()
    for case in manifest["cases"]:
        _exact(case, ("id", "split", "input", "A", "B", "mapping"), "case")
        identifier(case["id"])
        if case["id"] in ids or case["split"] not in SPLITS:
            raise EngineError("Invalid case identity/split")
        ids.add(case["id"])
        splits.add(case["split"])
        for field in ("input", "A", "B"):
            _text(case[field], field)
        _exact(case["mapping"], ("A", "B"), "blind mapping")
        if sorted(case["mapping"].values()) != ["baseline", "candidate"]:
            raise EngineError("Invalid blind mapping")
    if splits != set(SPLITS):
        raise EngineError("Both development and holdout cases are required")
    return base, manifest, checksum


def create(root, spec) -> dict:
    """Save an immutable comparison with actual supplied baseline/candidate outputs."""
    _exact(spec, ("id", "hypothesis", "baseline_method", "candidate_method", "cases"), "experiment")
    identifier(spec["id"])
    for field in ("hypothesis", "baseline_method", "candidate_method"):
        _text(spec[field], field)
    if not isinstance(spec["cases"], list) or not spec["cases"]:
        raise EngineError("At least one development and one holdout case are required")
    cases, ids, splits = [], set(), set()
    for case in spec["cases"]:
        _exact(case, ("id", "split", "input", "baseline_output", "candidate_output"), "case")
        identifier(case["id"])
        if case["id"] in ids or case["split"] not in SPLITS:
            raise EngineError("Duplicate case id or invalid split")
        ids.add(case["id"])
        splits.add(case["split"])
        for field in ("input", "baseline_output", "candidate_output"):
            _text(case[field], field)
        order = ("baseline", "candidate") if secrets.randbelow(2) else ("candidate", "baseline")
        cases.append({"id": case["id"], "split": case["split"], "input": case["input"],
                      "A": case[f"{order[0]}_output"], "B": case[f"{order[1]}_output"],
                      "mapping": dict(zip(("A", "B"), order))})
    if splits != set(SPLITS):
        raise EngineError("Both development and holdout cases are required")
    manifest = {key: spec[key] for key in ("id", "hypothesis", "baseline_method", "candidate_method")}
    manifest.update(schema_version=1, cases=cases)
    base = _base(root, spec["id"])
    try:
        base.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise EngineError("Experiment already exists; create a new id instead of replacing evidence") from exc
    _write(checked_path(base, "manifest.json"), manifest)
    return {"id": spec["id"], "hypothesis": spec["hypothesis"], "case_count": len(cases), "status": "created"}


def blind(root, experiment_id) -> dict:
    """Display the same persisted blind ordering on every read, without method labels."""
    _, manifest, _ = _load(root, experiment_id)
    return {"hypothesis": manifest["hypothesis"],
            "cases": [{key: case[key] for key in ("id", "split", "input", "A", "B")} for case in manifest["cases"]]}


def judge(root, experiment_id, case_id, choice, rationale, reviewer) -> dict:
    """Append the operator-provided feedback verbatim; no identity is authenticated."""
    base, manifest, checksum = _load(root, experiment_id)
    if case_id not in {case["id"] for case in manifest["cases"]}:
        raise EngineError("Unknown evaluation case")
    if choice not in CHOICES or reviewer not in REVIEWERS:
        raise EngineError("Invalid choice or reviewer source")
    _text(rationale, "rationale")
    record = {"id": uuid.uuid4().hex, "experiment_id": experiment_id, "manifest_sha256": checksum,
              "case_id": case_id, "choice": choice, "rationale": rationale, "reviewer": reviewer, "created_at": now()}
    _write(checked_path(base, f"judgments/{record['id']}.json"), record)
    return record


def _records(base, folder, experiment_id, checksum):
    path = checked_path(base, folder)
    records = []
    if not path.exists():
        return records
    for item in path.iterdir():
        verified = checked_path(base, f"{folder}/{item.name}")
        if not verified.is_file() or verified.suffix != ".json":
            raise EngineError(f"Unexpected item in {folder}")
        record, _ = _read(verified)
        if record.get("experiment_id") != experiment_id or record.get("manifest_sha256") != checksum or record.get("id") != verified.stem:
            raise EngineError(f"Evaluation record is bound to different evidence: {item.name}")
        records.append(record)
    return sorted(records, key=lambda record: (record["created_at"], record["id"]))


def summarize(root, experiment_id) -> dict:
    """Expose evidence by split, case and reviewer; do not collapse it to one score."""
    base, manifest, checksum = _load(root, experiment_id)
    judgments = _records(base, "judgments", experiment_id, checksum)
    decisions = _records(base, "decisions", experiment_id, checksum)
    cases = {case["id"]: case for case in manifest["cases"]}
    for record in judgments:
        _exact(record, ("id", "experiment_id", "manifest_sha256", "case_id", "choice", "rationale", "reviewer", "created_at"), "judgment")
        if record["case_id"] not in cases or record["choice"] not in CHOICES or record["reviewer"] not in REVIEWERS:
            raise EngineError("Invalid stored judgment")
        _text(record["rationale"], "rationale")
    groups, blockers, human_holdout_wins = {}, [], 0
    for split in SPLITS:
        grouped_cases = []
        counts = {reviewer: {verdict: 0 for verdict in ("baseline", "candidate", "tie", "inconclusive")} for reviewer in REVIEWERS}
        for case in manifest["cases"]:
            if case["split"] != split:
                continue
            evidence = []
            for record in judgments:
                if record["case_id"] != case["id"]:
                    continue
                verdict = case["mapping"].get(record["choice"], record["choice"])
                counts[record["reviewer"]][verdict] += 1
                evidence.append({**record, "verdict": verdict})
            if not evidence:
                blockers.append(f"Case {case['id']} has no judgment")
            if split == "holdout":
                human = [item for item in evidence if item["reviewer"] != "agent"]
                if not human:
                    blockers.append(f"Holdout {case['id']} has no recorded author/target_reader judgment")
                human_holdout_wins += sum(item["verdict"] == "candidate" for item in human)
                if any(item["verdict"] == "baseline" for item in evidence):
                    blockers.append(f"Holdout {case['id']} contains a candidate loss")
            grouped_cases.append({"id": case["id"], "input": case["input"], "judgments": evidence})
        groups[split] = {"cases": grouped_cases, "counts_by_reviewer": counts}
    if not human_holdout_wins:
        blockers.append("No candidate win recorded from an author/target_reader on holdout cases")
    for decision in decisions:
        _exact(decision, ("id", "experiment_id", "manifest_sha256", "action", "note", "judgment_ids", "created_at"), "decision")
        if decision["action"] not in ("trial", "retain", "rollback"):
            raise EngineError("Invalid stored decision")
        _text(decision["note"], "decision note")
        if not isinstance(decision["judgment_ids"], list) or any(value not in {item["id"] for item in judgments} for value in decision["judgment_ids"]):
            raise EngineError("Decision refers to missing feedback")
    return {"id": experiment_id, "hypothesis": manifest["hypothesis"],
            "baseline_method": manifest["baseline_method"], "candidate_method": manifest["candidate_method"],
            "groups": groups, "retain_eligible": not blockers, "retain_blockers": blockers,
            "decisions": decisions, "latest_decision": decisions[-1] if decisions else None,
            "evidence_note": "Reviewer sources are operator-declared. Agent feedback is not human feedback; no identity authentication is provided. Decisions never modify methods/policies automatically."}


def decide(root, experiment_id, action, note) -> dict:
    """Append an explicit decision bound to the feedback present at this time."""
    if action not in ("trial", "retain", "rollback"):
        raise EngineError("Decision must be trial, retain or rollback")
    _text(note, "decision note")
    summary = summarize(root, experiment_id)
    if action == "retain" and not summary["retain_eligible"]:
        raise EngineError("Cannot retain: " + "; ".join(summary["retain_blockers"]))
    base, _, checksum = _load(root, experiment_id)
    judgment_ids = sorted(item["id"] for group in summary["groups"].values()
                          for case in group["cases"] for item in case["judgments"])
    record = {"id": uuid.uuid4().hex, "experiment_id": experiment_id, "manifest_sha256": checksum,
              "action": action, "note": note, "judgment_ids": judgment_ids, "created_at": now()}
    _write(checked_path(base, f"decisions/{record['id']}.json"), record)
    return record
