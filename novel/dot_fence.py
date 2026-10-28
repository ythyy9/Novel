"""Operator-installed continuation fence; no automatic takeover or model calls.

The authorized continuation carries a private 32-hex prefix in request_id,
followed by '_' and its unique request suffix. Existing MCP argument schemas and
immutable task packets stay unchanged. Only a trusted operator installs the
configuration; the creative API never creates, rotates or removes it.
"""
from __future__ import annotations

import hmac
import json
import re

from .engine import EngineError, canonical, checked_path, digest, identifier

FORMAT = "novel-continuation-fence-v1"
FILE = "continuation-fence-{book_id}.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
PREFIX = re.compile(r"([0-9a-f]{32})_(.+)\Z")


def load(workspace):
    path = checked_path(workspace.base, FILE.format(book_id=workspace.book_id))
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        required = {"format", "book_id", "task_id", "attempt", "input_revision",
                    "generation", "request_prefix_sha256", "evidence", "created_at"}
        if not isinstance(config, dict) or set(config) != required or config["format"] != FORMAT:
            raise ValueError("Invalid fence shape")
        for key in ("book_id", "task_id", "generation"):
            identifier(config[key])
        if config["book_id"] != workspace.book_id:
            raise ValueError("Fence belongs to another book")
        if type(config["attempt"]) is not int or config["attempt"] < 1:
            raise ValueError("Invalid fenced attempt")
        if any(not isinstance(config[k], str) or not HEX.fullmatch(config[k])
               for k in ("input_revision", "request_prefix_sha256")):
            raise ValueError("Invalid fence hash")
        if not isinstance(config["created_at"], str) or not config["created_at"]:
            raise ValueError("Missing operator timestamp")
        evidence = config["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 8:
            raise ValueError("Invalid evidence allowlist")
        seen = set()
        for row in evidence:
            if not isinstance(row, dict) or set(row) != {"task_id", "result_sha256"}:
                raise ValueError("Invalid evidence record")
            identifier(row["task_id"])
            if row["task_id"] in seen or not isinstance(row["result_sha256"], str) or not HEX.fullmatch(row["result_sha256"]):
                raise ValueError("Invalid evidence identity")
            seen.add(row["task_id"])
        task = workspace.engine.task(config["task_id"])
        if (task["book_id"] != config["book_id"] or task["attempts"] != config["attempt"]
                or task["input_revision"] != config["input_revision"]):
            raise ValueError("Fenced task identity changed")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise EngineError("Invalid continuation fence; operator inspection required") from exc
    return config


def _prefix(value, config):
    match = PREFIX.fullmatch(value) if isinstance(value, str) else None
    if match and hmac.compare_digest(digest(match[1]), config["request_prefix_sha256"]):
        return match
    return None


def guard(workspace, request_id, action, arguments):
    config = load(workspace)
    if config is None:
        return
    protected = arguments.get("task_id") == config["task_id"]
    if action in {"open", "accept"}:
        # An obsolete coordinator cannot open a parallel task or advance the
        # stage while the protected review is running/submitted.
        protected = workspace.engine.task(config["task_id"])["status"] in {"running", "submitted"}
    if not protected:
        return
    match = _prefix(request_id, config)
    if match is None:
        raise EngineError("Execution fenced: authorized continuation request prefix required")
    if match[1] in canonical(arguments):
        raise EngineError("Keep the private continuation prefix out of stored task content")


def public(config):
    return {key: config[key] for key in ("format", "task_id", "attempt", "input_revision", "generation", "created_at")}


def status(workspace, value):
    config = load(workspace)
    if config is None:
        return value
    def redact(item):
        if isinstance(item, str):
            match = _prefix(item, config)
            return "continuation-request_" + match[2] if match else item
        if isinstance(item, list):
            return [redact(v) for v in item]
        if isinstance(item, dict):
            return {k: redact(v) for k, v in item.items()}
        return item
    result = redact(value)
    result["continuation"] = {**public(config), "guide": "continuation-guide.json",
        "request_id_redaction": "Authorized request prefixes are omitted; the continuation holder can reconstruct its original IDs."}
    return result


def _evidence(workspace, config, task_id):
    allowed = next((row for row in config["evidence"] if row["task_id"] == task_id), None)
    if allowed is None:
        raise EngineError("Original review is not in the operator-approved evidence allowlist")
    task = workspace.engine.task(task_id)
    if (task["book_id"] != workspace.book_id or task["kind"] != "review"
            or task["status"] != "completed" or not isinstance(task["result"], dict)
            or task["result_hash"] != allowed["result_sha256"]
            or digest(canonical(task["result"])) != allowed["result_sha256"]
            or task["result"]["task_id"] != task_id):
        raise EngineError("Original review evidence identity or hash mismatch")
    return task


def read(workspace, task_id, document):
    config = load(workspace)
    if config is None or config["task_id"] != task_id:
        raise EngineError("No operator-approved continuation evidence for this task")
    if document == "continuation-guide.json":
        sources = []
        for row in config["evidence"]:
            task = _evidence(workspace, config, row["task_id"])
            sources.append({**{k: task[k] for k in ("id", "book_id", "kind", "status", "attempts",
                "input_revision", "result_revision", "result_hash", "created_at", "updated_at")},
                "document": "continuation-evidence/" + task["id"] + ".json"})
        return canonical({**public(config), "evidence": sources,
            "source": "Exact immutable results in this book's original task database; explicitly allowlisted by the operator.",
            "instructions": "Continue the original task and attempt. Prefix each NEW mutating request_id with the privately supplied 32-hex prefix and '_'; total ID length remains 64. Do not put the prefix in upload IDs, context refs, results, notes, logs or screenshots. Original packets, checkpoints, unresolved issues, literary review and acceptance gates are unchanged. Read each evidence document fully; retrieval is not proof of comprehension or resolution."})
    match = re.fullmatch(r"continuation-evidence/([a-z0-9][a-z0-9_-]{0,63})\.json", document)
    if not match:
        raise EngineError("Invalid continuation evidence document")
    return canonical(_evidence(workspace, config, match[1])["result"])
