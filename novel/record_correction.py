"""One explicitly authorized record correction; not a state-only revise mode.

The appendix pin identifies the supplied content-level handoff, NOT recovered
upload bytes. Before deployment a separately authorized operator must read-only
assemble the retained upload and verify its binding and exact appendix bytes.
Any mismatch requires review; do not normalize or silently accept a newline.
Existing context, engine, review and acceptance checks remain in force.
"""
from hashlib import sha256

TASK_ID = "9ed5c2c9c279495ca041820f471d58a2"
BOOK_ID = "shizhi-zhicheng"
INPUT_REVISION = "d1982968db808ef0800ce6e55c4c2624b67fde0fa053d480c6f6746e9d4c92a7"
CONTROL_HASH = "fac04df69e037eef05a4e67e06838befacb47e0ab313964dde22dddbc68ec3b9"
STATE = "canon/state.json"
PATH = "revisions/056-chapter33-record-correction.md"
OLD_APPENDIX = "revisions/051-chapter31-scope.md"
STATE_SHA256 = "f6cb6e817dee7450cebf5eda6d8f506b23b72a99e758f2665ba854a833bfdb1f"
APPENDIX_SHA256 = "cfb980503d7c4bf01c5504eb34a4af88ca425ce6625eebdfff8dbc8b149032a9"
INPUT_PINS = {
    STATE: STATE_SHA256,
    OLD_APPENDIX: "207ff995017164a78f050a155c66edca00a6e8661663ea68bd65d669128e08eb",
    "manuscript/025.md": "a632a9ad9bf303cc0266e54b1a9a0dc5c8e8e4a209aa7edd90500022eafd6da2",
    "manuscript/031.md": "1d1d0dcba8e984b63e62f7a7a660958cda536d8491807f87d842a44d1c1f4a0f",
}
RECORD_ID = "ch25-repairer-and-recipient"
# Semantic pin independently checked against the retained completed result.
# Keep private manuscript spans in the book history, never in public source.
UPDATED_STATE_SHA256 = "ff8694228ebe6254aec7a27e9f9e2b619de2e40084b0a7e250f8d1fb1fc13846"


def validate_record_correction(result, task, files, changes):
    """Return False for unrelated tasks; fail closed for every pinned-task deviation."""
    from .records import ValidationError, _json

    if task.get("id", task.get("task_id")) != TASK_ID:
        return False

    def require(condition, message):
        if not condition:
            raise ValidationError("Record correction recovery: " + message)

    require(task.get("book_id") == BOOK_ID and task.get("kind") == "revise"
            and type(task.get("attempts")) is int and task["attempts"] == 1
            and task.get("input_revision") == INPUT_REVISION
            and task.get("control_hash") == CONTROL_HASH,
            "task binding mismatch")
    require(set(changes) == {STATE, PATH}, "only the state and new correction appendix may change")
    require(result["review"] is None, "cannot attach a review")
    require({STATE, PATH}.issubset(result["affected_paths"]), "changed paths must be declared")
    require(not any(p.casefold() == PATH.casefold() for p in files), "appendix already exists")
    for path, checksum in INPUT_PINS.items():
        require(path in files and sha256(files[path].encode("utf-8")).hexdigest() == checksum,
                "input file mismatch: " + path)
    require(sha256(changes[PATH].encode("utf-8")).hexdigest() == APPENDIX_SHA256,
            "appendix differs from the content-level handoff pin")

    from .engine import canonical, digest
    previous = _json(files[STATE], STATE)
    updated = _json(changes[STATE], STATE)
    require(digest(canonical(updated)) == UPDATED_STATE_SHA256,
            "state must preserve every field, record, order and source except the authorized correction")
    old_statement = next(r["statement"] for r in previous["knowledge"] if r["id"] == RECORD_ID)
    record = next(r for r in updated["knowledge"] if r["id"] == RECORD_ID)
    require(old_statement in changes[PATH] and record["statement"] in changes[PATH],
            "appendix must retain the original error and corrected statement")
    return True
