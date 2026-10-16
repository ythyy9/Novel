"""Append-only diagnostic notes linked to original feedback and visible evidence.

Notes are operator-supplied hypotheses, never authenticated model introspection or
automatic method decisions. Reuse the evaluation envelope integrity contract.
"""
import uuid

from . import evaluation
from .engine import EngineError, checked_path, digest, identifier, now


FIELDS = ("evidence", "hypothesis", "prevention", "scope", "validation_plan",
          "actual_result", "experiment_id")


def _original(engine, feedback_id):
    identifier(feedback_id)
    with engine._db() as db:
        original = engine._row(db, "feedback", feedback_id)
    engine.files(original["book_id"], original["revision"])
    return original


def _evidence(engine, book_id, entries):
    if not isinstance(entries, list):
        raise EngineError("evidence must be a list; use [] when inputs are missing")
    verified = []
    for entry in entries:
        evaluation._exact(entry, ("revision", "path", "quote"), "feedback evidence")
        for field in ("revision", "path", "quote"):
            evaluation._text(entry[field], field)
        files = engine.files(book_id, entry["revision"])
        if entry["path"] not in files or entry["quote"] not in files[entry["path"]]:
            raise EngineError("Feedback evidence quote is absent from the specified snapshot")
        verified.append({**entry, "source_hash": digest(files[entry["path"]])})
    return verified


def append(engine, feedback_id, spec):
    original = _original(engine, feedback_id)
    evaluation._exact(spec, FIELDS, "feedback diagnosis")
    for field in ("hypothesis", "prevention", "scope", "validation_plan"):
        evaluation._text(spec[field], field)
    if spec["actual_result"] is not None:
        evaluation._text(spec["actual_result"], "actual_result")
    evidence = _evidence(engine, original["book_id"], spec["evidence"])
    experiment = None
    if spec["experiment_id"] is not None:
        _, _, checksum = evaluation._load(engine.root, spec["experiment_id"])
        experiment = {"manifest_sha256": checksum,
                      "summary_at_recording": evaluation.summarize(engine.root, spec["experiment_id"])}
    record = {"schema_version": 1, "id": uuid.uuid4().hex, "feedback_id": feedback_id,
              "feedback_sha256": evaluation._hash(original), "created_at": now(),
              "analysis_source": "operator_supplied", "spec": spec,
              "verified_evidence": evidence, "experiment": experiment}
    path = checked_path(engine.root, f"runtime/feedback/{feedback_id}/{record['id']}.json")
    evaluation._write(path, record)
    return record


def show(engine, feedback_id):
    original = _original(engine, feedback_id)
    folder = checked_path(engine.root, f"runtime/feedback/{feedback_id}")
    notes = []
    if folder.exists():
        for item in folder.iterdir():
            path = checked_path(engine.root, f"runtime/feedback/{feedback_id}/{item.name}")
            if not path.is_file() or path.suffix != ".json":
                raise EngineError("Unexpected feedback diagnostic file")
            record, _ = evaluation._read(path)
            if (record.get("schema_version") != 1 or record.get("id") != path.stem
                    or record.get("feedback_id") != feedback_id
                    or record.get("feedback_sha256") != evaluation._hash(original)):
                raise EngineError("Feedback diagnosis identity/evidence mismatch")
            spec = record["spec"]
            evaluation._exact(spec, FIELDS, "feedback diagnosis")
            if _evidence(engine, original["book_id"], spec["evidence"]) != record["verified_evidence"]:
                raise EngineError("Feedback evidence integrity mismatch")
            if spec["experiment_id"] is not None:
                _, _, checksum = evaluation._load(engine.root, spec["experiment_id"])
                if checksum != record["experiment"]["manifest_sha256"]:
                    raise EngineError("Feedback experiment binding mismatch")
            notes.append(record)
    return {"feedback": original, "diagnoses": sorted(notes, key=lambda r: (r["created_at"], r["id"])),
            "scope": "Quotes verified against snapshots; causes and outcomes are operator claims, not model introspection. No automatic resolution or method promotion. Experiment summaries are frozen at recording time."}
