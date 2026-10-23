"""Strict, dependency-free validation for the Novel task exchange protocol.

The authoritative six-way information distinction lives in ``knowledge``.
Each knowledge item has ``id, kind, statement, holder, sources``. Character
knowledge/belief requires a named holder; other kinds may use null. Supporting
``characters``, ``world`` and ``offstage`` entries have ``id, statement, sources``;
characters may also include ``name``. These descriptive indexes do not themselves
adopt a candidate as a world fact. Record adopted facts explicitly in knowledge.

Every source is an exact, nonempty ``{path, quote}`` reference into the supplied
file snapshot. The state file cannot cite itself. Validation establishes shape,
referential integrity and provenance boundaries; it cannot establish that quoted
prose logically proves a claim or that a remote source is accurate.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit


class ValidationError(ValueError):
    """An untrusted record does not satisfy the exchange contract."""


PREFIXES = frozenset({"manuscript", "canon", "possibilities", "research", "reference", "decisions", "revisions"})
KNOWLEDGE_KINDS = frozenset({"world_fact", "character_knowledge", "character_belief", "reader_knowledge", "undecided", "candidate"})
REVIEW_DIMENSIONS = frozenset({"continuity", "character", "world", "reading"})
_WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.IGNORECASE)


def _fail(message: str) -> None:
    raise ValidationError(message)


def _object(value: object, label: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    if set(value) - required - (optional or set()) or required - set(value):
        _fail(f"{label} has missing or unknown fields")
    return value


def _text(value: object, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        _fail(f"{label} must be {'a nonempty' if nonempty else 'a'} string")
    # Surrogate code points cannot be represented in UTF-8 files or JSON output.
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _fail(f"{label} contains an invalid Unicode surrogate")
    return value


def _list(value: object, label: str, *, nonempty: bool = False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(f"{label} must be {'a nonempty' if nonempty else 'a'} list")
    return value


def _strings(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    result = _list(value, label, nonempty=nonempty)
    for item in result:
        _text(item, label)
    return result


def validate_path(path: str) -> str:
    """Return a canonical relative book path, or reject unsafe/ambiguous names.

    Paths are POSIX relative paths with an allowed root and .md/.json suffix.
    No normalizing or silent repair is performed. Case collisions between valid
    paths are checked by the controller against its complete file inventory.
    """
    _text(path, "path")
    if unicodedata.normalize("NFC", path) != path:
        _fail("path must use NFC Unicode normalization")
    if "\\" in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        _fail("path contains a backslash or control character")
    components = path.split("/")
    if len(components) < 2 or components[0] not in PREFIXES:
        _fail("path must be relative to an allowed book directory")
    for component in components:
        if (not component or component.startswith(".") or component.endswith((".", " "))
                or any(c in '<>:"|?*' for c in component)
                or _WINDOWS_RESERVED.match(component)):
            _fail("path contains an unsafe or noncanonical component")
    if not path.endswith((".md", ".json")):
        _fail("path extension must be .md or .json")
    return path


def _paths(value: object, label: str, files: dict[str, str], *, nonempty: bool = False) -> list[str]:
    paths = _strings(value, label, nonempty=nonempty)
    if len(paths) != len(set(paths)):
        _fail(f"{label} contains duplicate paths")
    for path in paths:
        validate_path(path)
        if path not in files:
            _fail(f"{label} references a missing file: {path}")
    return paths


def _sources(value: object, files: dict[str, str], label: str) -> list[dict]:
    sources = _list(value, label, nonempty=True)
    for source in sources:
        _object(source, label, {"path", "quote"})
        path = validate_path(source["path"])
        quote = _text(source["quote"], f"{label}.quote")
        if path == "canon/state.json":
            _fail("state cannot cite itself")
        if path not in files or not isinstance(files[path], str) or quote not in files[path]:
            _fail(f"{label} quote is absent from its source: {path}")
    return sources


def validate_state(data: dict, files: dict[str, str]) -> None:
    """Validate canon/state.json against the resulting complete file snapshot."""
    _object(data, "state", {"knowledge", "characters", "world", "offstage"})
    for section in ("knowledge", "characters", "world", "offstage"):
        records = _list(data[section], f"state.{section}")
        ids: set[str] = set()
        for entry in records:
            required = {"id", "statement", "sources"}
            if section == "knowledge":
                required |= {"kind", "holder"}
            _object(entry, f"state.{section} entry", required, {"name"} if section == "characters" else None)
            identifier = _text(entry["id"], f"state.{section}.id")
            if identifier in ids:
                _fail(f"state.{section} contains duplicate id: {identifier}")
            ids.add(identifier)
            _text(entry["statement"], f"state.{section}.statement")
            if "name" in entry:
                _text(entry["name"], "character.name")
            sources = _sources(entry["sources"], files, f"state.{section}.sources")
            if section == "knowledge":
                kind = _text(entry["kind"], "knowledge.kind")
                if kind not in KNOWLEDGE_KINDS:
                    _fail("knowledge.kind is not one of the six information kinds")
                if kind in {"character_knowledge", "character_belief"} or entry["holder"] is not None:
                    _text(entry["holder"], "knowledge.holder")
                if kind == "world_fact" and all(s["path"].split("/")[0] in {"possibilities", "reference"} for s in sources):
                    _fail("world_fact cannot rely solely on possibilities or reference material")


def _json(content: str, label: str) -> dict:
    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        _fail(f"{label} contains nonstandard JSON constant {value}")

    try:
        return json.loads(content, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError(f"{label} is not valid JSON") from exc


def _research(data: dict, files: dict[str, str]) -> None:
    _object(data, "research", {"question", "sources", "conclusion", "conditions", "uncertainties", "affected_paths", "claims"})
    _text(data["question"], "research.question")
    _text(data["conclusion"], "research.conclusion")
    _strings(data["conditions"], "research.conditions", nonempty=True)
    _strings(data["uncertainties"], "research.uncertainties", nonempty=True)
    _paths(data["affected_paths"], "research.affected_paths", files)
    sources = _list(data["sources"], "research.sources")
    for source in sources:
        _object(source, "research source", {"url", "title", "accessed"})
        url = _text(source["url"], "research source.url")
        _text(source["title"], "research source.title")
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url)):
                _fail("research source.url must be an absolute HTTP(S) URL without credentials")
            # Accessing .port also checks malformed or out-of-range port numbers.
            parsed.port
            accessed = _text(source["accessed"], "research source.accessed")
            if date.fromisoformat(accessed).isoformat() != accessed:
                _fail("research source.accessed must be YYYY-MM-DD")
        except ValueError as exc:
            raise ValidationError("research source URL or access date is invalid") from exc
    for claim in _list(data["claims"], "research.claims", nonempty=True):
        _object(claim, "research claim", {"kind", "text", "source_indexes"})
        kind = _text(claim["kind"], "research claim.kind")
        if kind not in {"external_fact", "inference", "fiction_rule"}:
            _fail("research claim.kind is invalid")
        _text(claim["text"], "research claim.text")
        indexes = _list(claim["source_indexes"], "research claim.source_indexes", nonempty=kind == "external_fact")
        for index in indexes:
            if type(index) is not int or index < 0 or index >= len(sources):
                _fail("research claim has an invalid source index")
        if len(indexes) != len(set(indexes)):
            _fail("research claim contains duplicate source indexes")


def _review(review: dict, files: dict[str, str]) -> None:
    _object(review, "review", {"coverage", "dimensions", "findings"})
    coverage = _paths(review["coverage"], "review.coverage", files, nonempty=True)
    dimensions = _strings(review["dimensions"], "review.dimensions")
    if len(dimensions) != len(REVIEW_DIMENSIONS) or set(dimensions) != REVIEW_DIMENSIONS:
        _fail("review must cover all four dimensions exactly once")
    ids: set[str] = set()
    for finding in _list(review["findings"], "review.findings"):
        _object(finding, "review finding", {"id", "category", "confirmed", "severity", "path", "quote", "explanation", "suggestion", "affected_paths", "status"})
        identifier = _text(finding["id"], "finding.id")
        if identifier in ids:
            _fail("review contains duplicate finding ids")
        ids.add(identifier)
        category = _text(finding["category"], "finding.category")
        severity = _text(finding["severity"], "finding.severity")
        if category not in {"error", "concern", "experience"} or severity not in {"major", "minor"}:
            _fail("finding category or severity is invalid")
        if type(finding["confirmed"]) is not bool:
            _fail("finding.confirmed must be a boolean")
        if finding["status"] != "open":
            _fail("a newly submitted finding must have status open")
        path = validate_path(finding["path"])
        quote = _text(finding["quote"], "finding.quote")
        if path not in coverage or quote not in files[path]:
            _fail("finding must cite an exact quote in a covered input file")
        _text(finding["explanation"], "finding.explanation")
        _text(finding["suggestion"], "finding.suggestion")
        _paths(finding["affected_paths"], "finding.affected_paths", files)


def validate_result(result: dict, task: dict, files: dict[str, str]) -> None:
    """Validate a task result, using ``files`` as its unchanged input snapshot.

    The validator overlays changes before checking state and research sources.
    Revision hashes, cross-version adoption, locks, case collisions, review
    acceptance and atomic publication remain controller responsibilities.
    """
    _object(result, "result", {"task_id", "input_revision", "completed_steps", "next_step", "unresolved", "changes", "review", "affected_paths", "state_notes"})
    _text(result["task_id"], "result.task_id")
    _text(result["input_revision"], "result.input_revision")
    if result["task_id"] != task.get("id", task.get("task_id")) or result["input_revision"] != task.get("input_revision"):
        _fail("result does not match the task id and input revision")
    _strings(result["completed_steps"], "result.completed_steps", nonempty=True)
    _text(result["next_step"], "result.next_step")
    _strings(result["unresolved"], "result.unresolved")
    _text(result["state_notes"], "result.state_notes", nonempty=False)
    kind = _text(task.get("kind"), "task.kind")
    if kind not in {"write", "revise", "research", "review", "correct_records"}:
        _fail("task kind is invalid")
    changes: dict[str, str] = {}
    for change in _list(result["changes"], "result.changes"):
        _object(change, "change", {"path", "content"})
        path = validate_path(change["path"])
        if path in changes:
            _fail("result contains duplicate change paths")
        changes[path] = _text(change["content"], "change.content")
    merged = {**files, **changes}
    affected = _paths(result["affected_paths"], "result.affected_paths", merged)
    from .scope_correction import validate_scope_correction
    if validate_scope_correction(result, task, files, changes):
        _text(result["state_notes"], "result.state_notes")
        validate_state(_json(files["canon/state.json"], "canon/state.json"), merged)
        return
    from .record_correction import validate_record_correction
    if validate_record_correction(result, task, files, changes):
        _text(result["state_notes"], "result.state_notes")
        validate_state(_json(changes["canon/state.json"], "canon/state.json"), merged)
        return
    if kind == "review":
        if changes:
            _fail("review tasks cannot change book files")
        _review(result["review"], files)
        return
    if result["review"] is not None:
        _fail("only review tasks may submit review records")
    if kind == "correct_records":
        from .corrections import validate_corrections
        validate_corrections(result, files, changes)
        return
    from .naming_append import validate_naming_append
    if validate_naming_append(result, task, files, changes):
        return
    if kind in {"write", "revise"}:
        if any(path.startswith("research/") for path in changes):
            _fail("write/revise cannot bypass the research record protocol")
        if any(path.startswith("canon/") and path != "canon/state.json" for path in changes):
            _fail("structured state belongs in canon/state.json")
        manuscripts = {path for path in changes if path.startswith("manuscript/") and path.endswith(".md")}
        if not manuscripts or "canon/state.json" not in changes:
            _fail("write/revise must change manuscript Markdown and canon/state.json together")
        if not manuscripts.issubset(affected):
            _fail("affected_paths must include all changed manuscripts")
        _text(result["state_notes"], "result.state_notes")
        validate_state(_json(changes["canon/state.json"], "canon/state.json"), merged)
    else:
        if not changes:
            _fail("research tasks must add a research record")
        for path, content in changes.items():
            if not path.startswith("research/") or not path.endswith(".json") or path in files:
                _fail("research tasks may only add new research/*.json records")
            research = _json(content, path)
            _research(research, merged)
            if not set(research["affected_paths"]).issubset(affected):
                _fail("result affected_paths must include the research record's declared impact")
