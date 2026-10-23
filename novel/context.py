"""Lossless views and staged results for an immutable external-executor packet.

No summarizer, model, network, task retry, or source mutation lives here.
Checkpoints attest delivered bytes and executor claims, never comprehension.
"""
from __future__ import annotations

from copy import deepcopy
from collections import OrderedDict
import json
import sys
import threading
from types import MappingProxyType

from .engine import EngineError, canonical, digest
from .records import _json, validate_result

VERSION = 1
BATCH_CHARS = 12000
FRAGMENT_CHARS = 3000
SECTIONS = ("knowledge", "characters", "world", "offstage")
CHECKPOINT = "novel-context-checkpoint-v1"
RESULT = "novel-context-result-v1"
_PLAN_CACHE = OrderedDict()
_PLAN_CACHE_LOCK = threading.RLock()
_PLAN_CACHE_BYTES = 32 * 1024 * 1024
_PLAN_CACHE_ITEMS = 8


def cached_plan(packet):
    """Bounded process-local derived cache; exact input bytes are verified on every read.

    No persisted format/hash changes: old packets and checkpoints retain their
    plans across deployments. Mutable plans are copied; cached views are immutable.
    """
    verify_packet(packet)
    key = digest(canonical(packet))
    with _PLAN_CACHE_LOCK:
        if key in _PLAN_CACHE:
            _PLAN_CACHE.move_to_end(key)
            plan, views, _ = _PLAN_CACHE[key]
            return deepcopy(plan), MappingProxyType(views)
        plan, views = build_plan(packet)
        size = sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in views.items()) + sys.getsizeof(canonical(plan))
        if size <= _PLAN_CACHE_BYTES:
            while _PLAN_CACHE and (len(_PLAN_CACHE) >= _PLAN_CACHE_ITEMS
                    or sum(item[2] for item in _PLAN_CACHE.values()) + size > _PLAN_CACHE_BYTES):
                _PLAN_CACHE.popitem(last=False)
            _PLAN_CACHE[key] = (deepcopy(plan), views, size)
        return plan, MappingProxyType(views)


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise EngineError(f"Invalid {label} fields")


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise EngineError(f"Invalid {label}")


def verify_packet(packet):
    documents = packet["documents"]
    if (not isinstance(documents, dict) or set(documents) != set(packet["sha256"])
            or any(not isinstance(v, str) or digest(v) != packet["sha256"][p] for p, v in documents.items())):
        raise EngineError("Task packet hash mismatch")
    if any(p.startswith("context/") or p in {"context-plan.json", "context-progress.json", "context-guide.md"}
           for p in documents):
        raise EngineError("Packet collides with reserved context view names")


def factor_state(text):
    """Deduplicate exact sources, preserving record/array order and multiplicity."""
    state = _json(text, "canon/state.json")
    exact(state, SECTIONS, "state")
    pool, source_ids, records = [], {}, []
    for section in SECTIONS:
        for index, original in enumerate(state[section]):
            record = deepcopy(original)
            refs = []
            for source in record["sources"]:
                key = canonical(source)
                if key not in source_ids:
                    source_ids[key] = f"s{len(pool) + 1:05d}"
                    pool.append({"id": source_ids[key], "source": source})
                refs.append(source_ids[key])
            record["sources"] = refs
            records.append({"section": section, "index": index, "record_sha256": digest(canonical(original)),
                            "record": record})
    if restore_state(records, pool) != state:
        raise EngineError("Lossless state view reconstruction failed")
    return records, pool


def restore_state(records, sources):
    pool = {row["id"]: row["source"] for row in sources}
    state = {section: [] for section in SECTIONS}
    for row in records:
        record = deepcopy(row["record"])
        record["sources"] = [deepcopy(pool[key]) for key in record["sources"]]
        if digest(canonical(record)) != row["record_sha256"] or row["index"] != len(state[row["section"]]):
            raise EngineError("State view integrity mismatch")
        state[row["section"]].append(record)
    return state


GUIDE = """# 固定资料包的分批读取 v1

原 packet-index.json、原文件和全部历史保持可读。先读 context-plan.json、
context-progress.json。计划绑定同一 task、attempt、input_revision、control_hash 和原包哈希。
这些视图只改变表示和读取顺序，不改变任务要求或审核标准，不恢复程序内模型调用。

每个批次 context/batches/NNNN.json 最多12000字符，按 next_offset 完整读到末尾。
批次内 fragments 给出原文/无损视图的 document、哈希、字符起止和精确 text。
全部非状态文件均完整覆盖；canon/state.json 以 context/state-records.jsonl 和
context/state-sources.jsonl 无损表达。sources 中 sNNNNN 指向共用证据表；不可把它们
写回 Canon。记录有稳定 section/id 和 record_sha256，正文、作者决定与 Unknown 不省略。

每个新上下文先读计划中的 task_instruction 和 mandatory_documents 原件（规则、
方法、作者决定与结果Schema）；不能只凭上一位执行者的摘要恢复这些约束。
一个原生上下文默认处理1至2批，按实际容量减少，保留解释、六类信息边界、命名依据、
跨章节牵连、未决项与准确引文，再通过现有 chunk/finish 保存 checkpoint。
notes 建议约1000字符；暂待后续批次回查的线索放 notes。unresolved 记录最终仍需
解决的实质缺口，会保留到提交门禁；历史 Unknown 依原规则区分，不自动升级为阻断。
context/state-current.jsonl 是逐字保留当前陈述的导航，record_document 可直达该条
完整原始记录及引文；共用证据 sNNNNN 可通过 context/sources/sNNNNN.json 直读。
这些导航不计作额外阅读批次，也不替代完整记录和证据表的覆盖。
新上下文先读进度和已有 checkpoint，然后接尚未完成的批次；不要重领、重试或清零任务。
所有批次都有 checkpoint 后，执行者综合各批笔记，并原文回查关联章节、状态和引文。
摘要只是导航，不替代分批全文阅读；服务端只验证字节送达和引用，不证明理解正确。
若跨批联系仍不清楚，继续回查或报告缺口，不声称全读/全审。

checkpoint 格式（通过现有 chunk/finish 上传；这一步不提交作品）：
{"format":"novel-context-checkpoint-v1","task_id":"...","attempt":1,
 "plan_sha256":"...","batch_id":"0001","context_ref":"真实原生上下文",
 "notes":"本批理解及下一批需回查的关系，不能只有已读二字",
 "evidence":[{"document":"批次中的document","quote":"该批精确非空引文"}],
 "unresolved":[],"review":null}
审核任务的 review 必须是原协议的四维审核对象（coverage/dimensions/findings），
coverage 至少包含本批涉及的全部作品文件；跨批问题可扩大覆盖。所有发现与未决项
都会并入最终结果，不能被后续空白意见覆盖。写作批次 review=null。
同批可追加 checkpoint，不能覆盖旧记录；context_ref 是声明，独立性仍须原生平台核实。

最终格式：
{"format":"novel-context-result-v1","task_id":"...","attempt":1,
 "plan_sha256":"...","result":{原协议九个字段},"state_delta":null}
write/revise 可令 result.changes 不含 canon/state.json，改用 state_delta：
{"base_sha256":"原state文件哈希","operations":[{"section":"knowledge",
 "id":"稳定ID","before_sha256":"原record_sha256，新记录填null",
 "set":{"statement":"实际更新的陈述"},"append_sources":[{"path":"...","quote":"..."}]}]}
不得删除记录或改ID。已有字段省略表示原样保留；set.sources 可明确整体更正引用，
此时 append_sources 必须为空。未改记录及来源由程序保留。新增记录需完整必要字段。
最终由控制器展开成原九字段完整结果，再校验所有引用、采用授权、影响范围、大小上限
及版本/attempt。审核仍须四维、全部正文、命名和跨章一致性，不是只审核新增章节。

开始保存 checkpoint 后必须用最终封装提交，不能改用旧格式跳过未完成批次。
旧协议仍可读和处理历史任务；不改变旧任务记录、审核发现或正式作品版本。
"""


def build_plan(packet):
    verify_packet(packet)
    records, sources = factor_state(packet["documents"]["canon/state.json"])
    views = {
        "context/state-records.jsonl": "".join(canonical(r) + "\n" for r in records),
        "context/state-sources.jsonl": "".join(canonical(r) + "\n" for r in sources),
    }
    current = []
    source_pool = {source["id"]: source["source"] for source in sources}
    for row in records:
        document = f"context/records/{row['section']}/{row['index']:04d}.json"
        record = deepcopy(row["record"])
        source_ids = record.pop("sources")
        current.append({**record, "section": row["section"], "record_sha256": row["record_sha256"],
                        "record_document": document, "source_count": len(source_ids)})
        # Per-record readback includes the original sources, not inferred prose.
        original = restore_state_fragment(row, sources, source_pool=source_pool)
        views[document] = canonical({"section": row["section"], "record_sha256": row["record_sha256"],
                                     "record": original})
    views["context/state-current.jsonl"] = "".join(canonical(r) + "\n" for r in current)
    for source in sources:
        views[f"context/sources/{source['id']}.json"] = canonical(source)
    readable = {p: v for p, v in packet["documents"].items() if p != "canon/state.json"}
    readable.update({p: views[p] for p in ("context/state-records.jsonl", "context/state-sources.jsonl")})

    def order(path):
        # Mandatory rules/decisions before evidence and prose; no relevance filter.
        rank = 0 if path.startswith(("policies/", "methods/", "decisions/")) or path == "result.schema.json" else 1
        return rank, path

    batches, pending = [], []

    def flush():
        if not pending:
            return
        batch_id = f"{len(batches) + 1:04d}"
        document = f"context/batches/{batch_id}.json"
        text = canonical({"fragments": pending})
        views[document] = text
        paths = sorted({f["document"] for f in pending})
        source_paths = sorted({"canon/state.json" if p.startswith("context/state-") else p for p in paths})
        batches.append({"id": batch_id, "document": document, "characters": len(text),
                        "sha256": digest(text), "source_paths": source_paths})
        pending.clear()

    for path in sorted(readable, key=order):
        content = readable[path]
        checksum = digest(content)
        for start in range(0, max(1, len(content)), FRAGMENT_CHARS):
            end = min(len(content), start + FRAGMENT_CHARS)
            item = {"document": path, "sha256": checksum, "start": start,
                    "end": end, "text": content[start:end]}
            if len(canonical({"fragments": [*pending, item]})) > BATCH_CHARS:
                flush()
            if len(canonical({"fragments": [item]})) > BATCH_CHARS:
                # Escapes may expand unusual source text; split further without loss.
                for offset in range(start, end, 500):
                    piece = {**item, "start": offset, "end": min(end, offset + 500),
                             "text": content[offset:min(end, offset + 500)]}
                    pending.append(piece)
                    flush()
            else:
                pending.append(item)
    flush()
    task = packet["task"]
    plan = {"version": VERSION, "task_id": task["id"], "attempt": task["attempts"],
            "input_revision": task["input_revision"], "control_hash": task["control_hash"],
            "task_instruction": task.get("instruction", ""),
            "mandatory_documents": [p for p in sorted(readable) if order(p)[0] == 0],
            "packet_sha256": digest(canonical(packet)), "batches": batches,
            "state_sha256": packet["sha256"]["canon/state.json"],
            "state_records": len(records), "unique_sources": len(sources),
            "original_characters": sum(map(len, packet["documents"].values())),
            "reading_characters": sum(map(len, readable.values())),
            "state_view_characters": sum(len(views[p]) for p in
                                         ("context/state-records.jsonl", "context/state-sources.jsonl")),
            "evidence_scope": "complete lossless input coverage; delivery and claims are not proof of comprehension"}
    plan["plan_sha256"] = digest(canonical(plan))
    views["context-plan.json"] = canonical(plan)
    views["context-guide.md"] = GUIDE
    return plan, views


def apply_delta(original, delta):
    exact(delta, ("base_sha256", "operations"), "state_delta")
    if delta["base_sha256"] != digest(original) or not isinstance(delta["operations"], list):
        raise EngineError("State delta base hash mismatch or invalid operations")
    state = _json(original, "canon/state.json")
    previous = deepcopy(state)
    seen = set()
    for operation in delta["operations"]:
        exact(operation, ("section", "id", "before_sha256", "set", "append_sources"), "state operation")
        section, record_id = operation["section"], operation["id"]
        if section not in SECTIONS or not isinstance(record_id, str) or not record_id.strip():
            raise EngineError("Invalid state record identity")
        if (section, record_id) in seen:
            raise EngineError("Duplicate state operation")
        seen.add((section, record_id))
        fields, extra = operation["set"], operation["append_sources"]
        if not isinstance(fields, dict) or "id" in fields or not isinstance(extra, list):
            raise EngineError("Cannot change record identity; invalid state fields/sources")
        if "sources" in fields and extra:
            raise EngineError("Cannot replace and append sources in one operation")
        prior = next((r for r in state[section] if r["id"] == record_id), None)
        expected = digest(canonical(prior)) if prior is not None else None
        if operation["before_sha256"] != expected:
            raise EngineError("State record compare-and-swap hash mismatch")
        if prior is None:
            record = {"id": record_id, **deepcopy(fields)}
            state[section].append(record)
        else:
            record = prior
            record.update(deepcopy(fields))
        if extra:
            record.setdefault("sources", []).extend(deepcopy(extra))
    # Preserve bytes on a no-op, so formatting cannot disguise no progress.
    return original if state == previous else canonical(state)


def restore_state_fragment(row, sources, *, source_pool=None):
    pool = source_pool if source_pool is not None else {source["id"]: source["source"] for source in sources}
    record = deepcopy(row["record"])
    record["sources"] = [pool[key] for key in record["sources"]]
    if digest(canonical(record)) != row["record_sha256"]:
        raise EngineError("State record integrity mismatch")
    return record


def validate_checkpoint(payload, task, packet, plan, views):
    exact(payload, ("format", "task_id", "attempt", "plan_sha256", "batch_id", "context_ref",
                    "notes", "evidence", "unresolved", "review"), "checkpoint")
    validate_identity(payload, task, plan)
    batch = next((b for b in plan["batches"] if b["id"] == payload["batch_id"]), None)
    if batch is None:
        raise EngineError("Unknown context batch")
    for key, limit in (("context_ref", 240), ("notes", 4000)):
        value = payload[key]
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise EngineError(f"Invalid checkpoint {key}")
    strings(payload["unresolved"], "checkpoint unresolved")
    fragments = json.loads(views[batch["document"]])["fragments"]
    evidence = payload["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise EngineError("Checkpoint requires exact batch evidence")
    for item in evidence:
        exact(item, ("document", "quote"), "checkpoint evidence")
        if (not isinstance(item["quote"], str) or not item["quote"].strip()
                or not any(f["document"] == item["document"] and item["quote"] in f["text"] for f in fragments)):
            raise EngineError("Checkpoint evidence is absent from this batch")
    if task["kind"] == "review":
        files = book_files(packet)
        result = {"task_id": task["id"], "input_revision": task["input_revision"],
                  "completed_steps": [payload["notes"]], "next_step": "Continue full review",
                  "unresolved": payload["unresolved"], "changes": [], "review": payload["review"],
                  "affected_paths": [], "state_notes": ""}
        validate_result(result, task, files)
        required = set(batch["source_paths"]) & set(files)
        if not required <= set(payload["review"]["coverage"]):
            raise EngineError("Batch review omits source coverage")
    elif payload["review"] is not None:
        raise EngineError("Only review checkpoints may contain findings")
    return batch


def book_files(packet):
    return {p: v for p, v in packet["documents"].items() if p.split("/")[0] in
            {"manuscript", "canon", "possibilities", "research", "reference", "decisions", "revisions"}}


def validate_identity(payload, task, plan):
    if (payload["task_id"] != task["id"] or type(payload["attempt"]) is not int
            or payload["attempt"] != task["attempts"] or payload["plan_sha256"] != plan["plan_sha256"]):
        raise EngineError("Context task, attempt or plan mismatch")


def assemble_result(payload, task, packet, plan, checkpoints):
    exact(payload, ("format", "task_id", "attempt", "plan_sha256", "result", "state_delta"), "context result")
    validate_identity(payload, task, plan)
    required = {b["id"] for b in plan["batches"]}
    if {c["batch_id"] for c in checkpoints} != required:
        raise EngineError("Context reading is incomplete; preserve and continue missing batches")
    result = deepcopy(payload["result"])
    if (not isinstance(result, dict) or not isinstance(result.get("changes"), list)
            or any(not isinstance(c, dict) for c in result["changes"])):
        raise EngineError("Invalid enclosed result")
    if payload["state_delta"] is not None:
        if task["kind"] not in {"write", "revise", "correct_records"}:
            raise EngineError("Only write/revise/correct_records can use a state delta")
        if any(c.get("path") == "canon/state.json" for c in result["changes"]):
            raise EngineError("Cannot send both complete state and state delta")
        result["changes"].append({"path": "canon/state.json",
            "content": apply_delta(packet["documents"]["canon/state.json"], payload["state_delta"])})
    strings(result.get("unresolved"), "result unresolved")
    for checkpoint in checkpoints:
        for issue in checkpoint["unresolved"]:
            if issue not in result["unresolved"]:
                result["unresolved"].append(issue)
    if task["kind"] == "review":
        # Validate final cross-batch synthesis before adding retained findings.
        validate_result(result, task, book_files(packet))
        review = result["review"]
        coverage = set(review["coverage"])
        for checkpoint in checkpoints:
            coverage.update(checkpoint["review"]["coverage"])
            prefix = digest(canonical(checkpoint))
            for finding in checkpoint["review"]["findings"]:
                review["findings"].append({**finding, "id": prefix + ":" + finding["id"]})
        review["coverage"] = sorted(coverage)
    validate_result(result, task, book_files(packet))
    return result
