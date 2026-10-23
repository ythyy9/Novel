"""One authorized chapter 34 appendix; no general appendix-only revise mode.

The content pin matches the supplied retained candidate, including its final LF.
Production must independently verify the original stored upload before deployment.
Existing workspace, context, review and acceptance gates remain in force.
"""
from hashlib import sha256

TASK_ID = "c669130d983d46fdaca1506d35fae6f6"
BOOK_ID = "shizhi-zhicheng"
INPUT_REVISION = "45241dd4205d7d0c9a4b8abbf1253718d3ddeb330eb14389ae5f098483908754"
CONTROL_HASH = "fac04df69e037eef05a4e67e06838befacb47e0ab313964dde22dddbc68ec3b9"
PATH = "revisions/058-chapter34-scope-correction.md"
APPENDIX_SHA256 = "29ec6cbbabd78a43d5c1810475d9bb796926b0d2eaad82691f6733d9d12f5aef"
INPUT_PINS = {
    "canon/state.json": "c39a28674e4a1b2b5f4315e8d10e9e45d27659955f41a818a064a634f7f6abc0",
    "manuscript/011.md": "ca55eea3b255d6c1a4d4696a0cbfb532d63cd3869836b0c220067dd5e1e81bbe",
    "manuscript/028.md": "51531d2b2c766d7d8914ed84af5f42bc581a0ea68004533822b6cf76c7751406",
    "revisions/022-chapter11-scope.md": "71c3c72641b4c6d9be61ee1a7bb99192060e24063914f99b4357957d2f7b2e12",
    "revisions/048-chapter28-scope.md": "8817a502c1c4f6d22163462219d76958549b5f495d56055ea583520545926577",
}


def validate_scope_correction(result, task, files, changes):
    from .records import ValidationError

    if task.get("id", task.get("task_id")) != TASK_ID:
        return False

    def require(condition, message):
        if not condition:
            raise ValidationError("Chapter 34 scope correction: " + message)

    require(task.get("book_id") == BOOK_ID and task.get("kind") == "revise"
            and type(task.get("attempts")) is int and task["attempts"] == 1
            and task.get("input_revision") == INPUT_REVISION
            and task.get("control_hash") == CONTROL_HASH, "task binding mismatch")
    require(set(changes) == {PATH}, "only the new correction appendix may change")
    require(result["review"] is None, "cannot attach review")
    require(PATH in result["affected_paths"], "appendix must be declared")
    require(not any(p.casefold() == PATH.casefold() for p in files), "appendix already exists")
    for path, checksum in INPUT_PINS.items():
        require(path in files and sha256(files[path].encode("utf-8")).hexdigest() == checksum,
                "input file mismatch: " + path)
    require(APPENDIX_SHA256 is not None, "original appendix bytes have not been verified")
    require(sha256(changes[PATH].encode("utf-8")).hexdigest() == APPENDIX_SHA256,
            "appendix content mismatch")
    return True
