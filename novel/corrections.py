"""Evidence-backed record corrections, without changing manuscript or history."""
from copy import deepcopy

FORMAT = "novel-record-correction-v1"
GUIDE = """# Record correction task
Use kind=correct_records only for correcting existing records or appending an
explanation to an existing revision note. Do not change manuscript, decisions,
reference material, information kind, holder, names, or stable record identities.
Add exactly one new revisions/correction-<unique-id>.json:
{"format":"novel-record-correction-v1","reason":"why","records":[],"annotations":[]}.
Each records item has section, id, before, after, reason, evidence. before/after
are complete records; only statement and sources may change. Keep old sources.
evidence is a nonempty list of exact {path,quote} references into the INPUT.
Each annotations item has path, quote, correction, evidence; path must name an
existing revisions file and quote must match its original content. Preserve it.
At least one record or annotation is required. For record changes also submit
canon/state.json (or a normal context state_delta) exactly matching those changes.
List every changed file and annotated original file in affected_paths.
Read the full fixed packet and preserve checkpoints as for other tasks.
Submission and publication do not constitute acceptance: the new version still
needs a separate independent review. Do not relabel or replace any existing task.
"""


def validate_corrections(result, files, changes):
    from .records import ValidationError, _json, _object, _sources, _text, validate_state

    def require(ok, message):
        if not ok:
            raise ValidationError("Record correction: " + message)

    notes = [p for p in changes if p.startswith("revisions/correction-") and p.endswith(".json")]
    require(len(notes) == 1, "add exactly one structured correction note")
    note_path = notes[0]
    require(note_path not in files, "correction notes are append-only")
    require(set(changes) <= {note_path, "canon/state.json"}, "only correction note and state may change")
    note = _json(changes[note_path], note_path)
    _object(note, "correction", {"format", "reason", "records", "annotations"})
    require(note["format"] == FORMAT, "unknown correction format")
    _text(note["reason"], "correction.reason")
    require(isinstance(note["records"], list) and isinstance(note["annotations"], list),
            "records and annotations must be arrays")
    require(bool(note["records"] or note["annotations"]), "empty correction")
    require(set(changes) <= set(result["affected_paths"]), "declare every changed path")
    _text(result["state_notes"], "result.state_notes")
    previous = _json(files["canon/state.json"], "input state")
    expected = deepcopy(previous)
    seen = set()
    for change in note["records"]:
        _object(change, "record correction", {"section", "id", "before", "after", "reason", "evidence"})
        section, record_id = change["section"], change["id"]
        require(isinstance(section, str) and section in previous, "unknown state section")
        _text(record_id, "record correction.id")
        require((section, record_id) not in seen, "duplicate record correction")
        seen.add((section, record_id))
        indexes = [i for i, r in enumerate(previous[section]) if r["id"] == record_id]
        require(len(indexes) == 1, "target record must already exist")
        old = previous[section][indexes[0]]
        new = change["after"]
        require(change["before"] == old, "before record does not match fixed input")
        require(isinstance(new, dict) and set(new) == set(old), "record fields must be preserved")
        require(all(new[k] == old[k] for k in old if k not in {"statement", "sources"}),
                "record identity, kind, holder and name cannot change")
        require(new != old, "record change has no effect")
        require(isinstance(new["sources"], list) and all(s in new["sources"] for s in old["sources"]),
                "retain original sources")
        _text(change["reason"], "record correction.reason")
        _sources(change["evidence"], files, "record correction.evidence")
        # Evidence must predate this correction; new notes cannot prove themselves.
        _sources(new["sources"], files, "corrected record.sources")
        require(all(s in new["sources"] for s in change["evidence"]), "include correction evidence in sources")
        expected[section][indexes[0]] = new
    for annotation in note["annotations"]:
        _object(annotation, "annotation", {"path", "quote", "correction", "evidence"})
        path = annotation["path"]
        require(isinstance(path, str) and path.startswith("revisions/") and path in files,
                "annotation must target an existing revision note")
        _text(annotation["quote"], "annotation.quote")
        require(annotation["quote"] in files[path], "original quote is absent")
        _text(annotation["correction"], "annotation.correction")
        _sources(annotation["evidence"], files, "annotation.evidence")
        require(path in result["affected_paths"], "declare the annotated original path")
    if note["records"]:
        require("canon/state.json" in changes, "state changes require the complete resulting state")
        updated = _json(changes["canon/state.json"], "corrected state")
        require(updated == expected, "state differs from the explicitly recorded corrections")
        validate_state(updated, {**files, **changes})
    else:
        require("canon/state.json" not in changes, "annotation-only corrections must not rewrite state")
