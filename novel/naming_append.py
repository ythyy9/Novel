"""One authorized recovery, not a general revisions-only task capability.

The original candidate bytes are not in the source bundle. Keep the content pin
closed until its UTF-8 SHA-256 and book id are independently supplied and checked
against the retained upload. These are code-review inputs, never result fields.
"""
from hashlib import sha256

TASK_ID = "4dac7f5d0ce24a51b85a001e7c11fb26"
INPUT_REVISION = "fe487995bb16fcb7363e1537abe32f44e1cbcf100a7ff8de0189a18255cad7cf"
CONTROL_HASH = "fac04df69e037eef05a4e67e06838befacb47e0ab313964dde22dddbc68ec3b9"
PATH = "revisions/naming-provisional-title-current-20261017.md"
BOOK_ID = "shizhi-zhicheng"
CONTENT_SHA256 = "5bd7efb8583cf9ce0fdff2913d011d95db9a92c6e168b72af995b7ffe4abf09d"


def validate_naming_append(result, task, files, changes):
    """Return False for unrelated tasks; reject any deviation for the pinned task."""
    from .records import ValidationError

    if task.get("id") != TASK_ID:
        return False

    def require(condition, detail):
        if not condition:
            raise ValidationError("Naming append recovery: " + detail)

    require(isinstance(BOOK_ID, str) and bool(BOOK_ID)
            and isinstance(CONTENT_SHA256, str) and len(CONTENT_SHA256) == 64
            and set(CONTENT_SHA256) <= set("0123456789abcdef"),
            "original candidate content hash and book binding are not verified")
    require(task.get("book_id") == BOOK_ID and task.get("kind") == "revise"
            and type(task.get("attempts")) is int and task["attempts"] == 1
            and task.get("input_revision") == INPUT_REVISION
            and task.get("control_hash") == CONTROL_HASH,
            "task binding mismatch")
    require(set(changes) == {PATH}, "only the authorized naming record may be added")
    require(not any(p.casefold() == PATH.casefold() for p in files), "record already exists")
    require(sha256(changes[PATH].encode("utf-8")).hexdigest() == CONTENT_SHA256,
            "original candidate bytes changed")
    require(result["review"] is None, "cannot attach a review")
    return True
