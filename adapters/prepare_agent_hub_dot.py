"""Prepare an explicitly selected Hub source copy; never deploy or edit grants.

The known source anchors must match exactly. Keep the original source available
for rollback. The runtime registry is operator-owned and defaults to disabled.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Hub source changed; inspect integration anchor before applying")
    return text.replace(old, new, 1)


def prepare(source):
    server_path = source / "backend/mcp_server.py"
    oauth_path = source / "backend/mcp_oauth.py"
    server = server_path.read_text(encoding="utf-8")
    oauth = oauth_path.read_text(encoding="utf-8")
    before = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (server_path, oauth_path)}
    server = replace_once(server, "import logging\n", "import logging\nimport os\n")
    server = replace_once(server, "'agenthub.vps.clients', 'agenthub.novel'}", "'agenthub.vps.clients', 'agenthub.novel', 'agenthub.novel.runtime'}")
    server = replace_once(server, "    extended = bool(controls or event_service or vps or novel)",
        "    dot = None\n    dot_names = {}\n    dot_tools = lambda: []\n"
        "    if os.environ.get('NOVEL_DOT_REGISTRY'):\n"
        "        from novel.dot_transport import DotRegistry, OPERATIONS, tools as runtime_tools\n"
        "        dot = DotRegistry(os.environ['NOVEL_DOT_REGISTRY'])\n"
        "        dot_names, dot_tools = OPERATIONS, runtime_tools\n"
        "    extended = bool(controls or event_service or vps or novel or dot)")
    server = replace_once(server, "+ (novel_tools() if novel else [])}", "+ (novel_tools() if novel else []) + dot_tools()}")
    server = replace_once(server, "        elif method == 'tools/call':\n",
        "            if dot and not ({'agenthub.novel', 'agenthub.novel.runtime'} & set(principal['scope'].split())):\n"
        "                result['tools'] = [tool for tool in result['tools'] if tool['name'] not in dot_names]\n"
        "            if dot and 'agenthub.novel' in principal['scope'].split() and not ({'agenthub.tasks', 'agenthub.vps.clients'} & set(principal['scope'].split())):\n"
        "                result['tools'] = [tool for tool in result['tools'] if not tool['name'].startswith('vps_')\n"
        "                    and tool['name'] not in {'task_submit', 'task_continue', 'task_cancel'}]\n"
        "        elif method == 'tools/call':\n")
    server = replace_once(server, "            if isinstance(name, str) and name in novel_models:",
        "            if isinstance(name, str) and name in dot_names:\n"
        "                try:\n"
        "                    data = await run_in_threadpool(dot.call, principal, name, args)\n"
        "                    result = {'structuredContent': data, 'isError': False,\n"
        "                        'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}]}\n"
        "                except PermissionError as exc:\n"
        "                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}\n"
        "                    if str(exc) == 'NOVEL_RUNTIME_SCOPE_REQUIRED':\n"
        "                        result['_meta'] = {'mcp/www_authenticate': [scope_challenge(oauth, 'agenthub.novel.runtime')]}\n"
        "                except (ValueError, TypeError) as exc:\n"
        "                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}\n"
        "                except OSError:\n"
        "                    result = {'isError': True, 'content': [{'type': 'text', 'text': 'Novel runtime storage unavailable; inspect before retry'}]}\n"
        "                return rpc_result(request_id, result, protocol, method)\n"
        "            if isinstance(name, str) and name in novel_models:")
    oauth = replace_once(oauth, "import logging\n", "import logging\nimport os\n")
    oauth = replace_once(oauth,
        "return {'owner_id': owner_id, 'grant_id': grant['id'], 'scope': grant['scope']}",
        "return {'owner_id': owner_id, 'grant_id': grant['id'], 'client_id': grant['client_id'], 'scope': grant['scope']}")
    oauth = replace_once(oauth, "KNOWN_SCOPES = (SCOPE, TASK_SCOPE, EVENT_SCOPE, VPS_SCOPE, NOVEL_SCOPE)",
        "NOVEL_RUNTIME_SCOPE = 'agenthub.novel.runtime'\nKNOWN_SCOPES = (SCOPE, TASK_SCOPE, EVENT_SCOPE, VPS_SCOPE, NOVEL_SCOPE, NOVEL_RUNTIME_SCOPE)")
    oauth = replace_once(oauth, "+ ([NOVEL_SCOPE] if getattr(self.settings, 'novel_archive_enabled', False) else []))",
        "+ ([NOVEL_SCOPE] if getattr(self.settings, 'novel_archive_enabled', False) else [])\n"
        "            + ([NOVEL_RUNTIME_SCOPE] if os.environ.get('NOVEL_DOT_REGISTRY') else []))")
    oauth = replace_once(oauth, "if NOVEL_SCOPE in requested_scopes else '')\n",
        "if NOVEL_SCOPE in requested_scopes else '')\n"
        "        extra_consent += ('<p>另行授权：仅在管理员登记的 Novel 独立试验副本中读取固定任务、提交写作/审核/返修结果并进行版本校验。不会调用 Codex、Work 或付费 API；不能访问任意路径、执行命令或接管正式作品。仅通过真实试验后另行配置正式接管。</p>' if NOVEL_RUNTIME_SCOPE in requested_scopes else '')\n")
    # Parse both files before writing either, and never touch runtime config/tokens.
    ast.parse(server)
    ast.parse(oauth)
    server_path.write_text(server, encoding="utf-8", newline="\n")
    oauth_path.write_text(oauth, encoding="utf-8", newline="\n")
    return {"before": before, "after": {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (server_path, oauth_path)}, "grants_changed": False, "deployed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source), indent=2))
