"""Transport-neutral MCP directory and owner/scope checks for Dot workspaces."""
import hashlib
import inspect
import json
from pathlib import Path

from .dot import DotWorkspace
from .engine import EngineError, identifier

SCOPE = "agenthub.novel.runtime"
TEXT = {"type": "string", "minLength": 1, "maxLength": 240}
REVISION = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
WORKSPACE = {"workspace": TEXT}
REQUEST = {**WORKSPACE, "request_id": TEXT}
TASK = {"task_id": TEXT}
ATTEMPT = {"attempt": {"type": "integer", "minimum": 1, "maximum": 10000}}
OPERATIONS = {
    "novel_work_status": ("status", {**WORKSPACE,
        "history_limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "before": {"type": "integer", "minimum": 1}, "include_instructions": {"type": "boolean"}},
        "读取当前版本、全部活动任务和最近10条历史；task_count是总数，tasks_complete=false表示未列全，按next_before传入before分页。history_limit和include_instructions可选；完整任务指令可通过novel_work_read读取task-info.json。不调用模型。"),
    "novel_work_open": ("open_task", {**REQUEST, "kind": {"type": "string", "enum": ["write", "review", "revise", "research", "correct_records"]},
        "instruction": {"type": "string", "minLength": 1, "maxLength": 12000}, "expected_revision": REVISION,
        "context_ref": TEXT}, "领取固定版本任务。correct_records 专用于有来源的记录更正或追加历史说明，读取 record-correction-guide.md；不改正文、旧说明或作者决定。作品由 Dot 直接生成，工程维护另走授权云端流程。context_ref 须来自真实上下文，审稿与写作分开；声明不等于已验真。"),
    "novel_work_read": ("read", {**WORKSPACE, **TASK, "document": TEXT,
        "offset": {"type": "integer", "minimum": 0}}, "分段读取固定任务包。大包先读context-guide.md、context-plan.json和context-progress.json，分批全文阅读并保存checkpoint跨上下文接续；原文件和packet-index.json保持可读。提交后可读result.json。未发布submitted候选修正先读candidate-amend-guide.json；历史见candidate-history.json和candidates/<sha256>.json。按next_offset读完，不以摘要替代全文。不能访问任意路径。"),
    "novel_work_chunk": ("chunk", {**REQUEST, **TASK, **ATTEMPT, "upload_id": TEXT,
        "part": {"type": "integer", "minimum": 0}, "total": {"type": "integer", "minimum": 1, "maximum": 256},
        "content": {"type": "string", "minLength": 1, "maxLength": 6000}}, "按顺序分段保存完整结果 JSON；每段最多6000字符，part从0开始，total固定；相同分段可重放，不可覆盖。submitted write/revise修正使用新upload_id，完整上传novel-candidate-amend-v1。"),
    "novel_work_finish": ("finish", {**REQUEST, **TASK, **ATTEMPT, "upload_id": TEXT},
        "合并并校验全部片段。novel-context-checkpoint-v1只保存分批阅读记录；novel-context-result-v1须全部批次完成，展开状态增量并合并全部问题后按原协议提交候选。novel-candidate-amend-v1绑定旧result_hash、同task/attempt/input_revision及原因，仅修正未发布submitted写作候选，完整context门禁和历史保留。旧结果协议兼容。不会发布、修改当前正文或调用模型。"),
    "novel_work_publish": ("publish", {**REQUEST, **TASK, "expected_revision": REVISION},
        "将已校验候选发布到该独立工作区的新版本，或登记对应版本的审核。不对外公开；规则、旧版本和作者决定保持。"),
    "novel_work_accept": ("accept", {**REQUEST, "expected_revision": REVISION},
        "按现有门禁进行阶段验收；有问题、未决项或缺少独立审核时拒绝。通过不代表作者或读者认可，也不证明通知已送达。"),
}


def tools():
    output = []
    for name, (operation, properties, description) in OPERATIONS.items():
        scopes = [{"type": "oauth2", "scopes": ["agenthub.read", SCOPE]}]
        output.append({"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties,
                "required": ["workspace"] if operation == "status" else list(properties), "additionalProperties": False},
            "annotations": {"readOnlyHint": operation in {"status", "read"}, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False}, "securitySchemes": scopes, "_meta": {"securitySchemes": scopes}})
    return output


class DotRegistry:
    def __init__(self, registry_path):
        self.path = Path(registry_path)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise EngineError("Absolute operator-owned registry required")

    @staticmethod
    def _takeover(entry, workspace_id):
        """Check a pinned operator receipt, not a model's approval declaration."""
        receipt_path = Path(entry.get("takeover_receipt", ""))
        root = Path(entry["root"]).resolve()
        if (not receipt_path.is_absolute() or receipt_path.is_symlink()
                or receipt_path.resolve().is_relative_to(root)):
            raise EngineError("Formal takeover is disabled without an external operator receipt")
        raw = receipt_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.get("takeover_sha256"):
            raise EngineError("Formal takeover receipt hash mismatch")
        receipt = json.loads(raw)
        if (receipt.get("schema_version") != 1 or receipt.get("workspace") != workspace_id
                or receipt.get("book_id") != entry["book_id"]
                or Path(receipt.get("root", "")).resolve() != root
                or receipt.get("source_frozen") is not True
                or receipt.get("pilot_accepted") is not True
                or receipt.get("single_writer") != "dot"):
            raise EngineError("Formal takeover receipt does not authorize this workspace")
        for key in ("source_archive_sha256", "source_revision", "pilot_revision"):
            value = receipt.get(key)
            if not isinstance(value, str) or len(value) != 64 or not set(value) <= set("0123456789abcdef"):
                raise EngineError("Formal takeover receipt lacks source and pilot evidence")
        return {key: receipt[key] for key in ("source_archive_sha256", "source_revision", "pilot_revision", "single_writer")}

    def call(self, principal, name, arguments):
        if SCOPE not in principal.get("scope", "").split():
            raise PermissionError("NOVEL_RUNTIME_SCOPE_REQUIRED")
        if name not in OPERATIONS or not isinstance(arguments, dict):
            raise EngineError("Unknown Novel runtime tool")
        identifier(arguments.get("workspace"))
        registry = json.loads(self.path.read_text(encoding="utf-8"))
        if registry.get("schema_version") != 1:
            raise EngineError("Unsupported runtime registry")
        entry = registry.get("workspaces", {}).get(arguments["workspace"])
        if not entry or not entry.get("enabled") or entry.get("owner_id") != principal.get("owner_id"):
            raise PermissionError("NOVEL_WORKSPACE_DENIED")
        takeover = None
        if entry.get("phase") == "formal":
            takeover = self._takeover(entry, arguments["workspace"])
        elif entry.get("phase") != "pilot":
            raise EngineError("Unknown Novel workspace phase")
        if entry.get("client_id") and entry["client_id"] != principal.get("client_id"):
            raise PermissionError("NOVEL_CLIENT_DENIED")
        operation, properties, _ = OPERATIONS[name]
        required = {"workspace"} if operation == "status" else set(properties)
        if not required <= set(arguments) or set(arguments) - set(properties):
            raise EngineError("Missing or unexpected tool arguments")
        workspace = DotWorkspace(entry["root"], entry["book_id"])
        method = getattr(workspace, operation)
        values = {k: v for k, v in arguments.items() if k != "workspace"}
        inspect.signature(method).bind(**values)
        result = method(**values)
        if operation == "status":
            result.update(workspace_id=arguments["workspace"], phase=entry["phase"], takeover=takeover)
        return result
