"""Adapter boundary tests; subprocess doubles are NOT real model acceptance."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from novel import adapter


class FakeEngine:
    def __init__(self, root):
        self.root = Path(root)
        self.record = {
            "id": "task-test", "book_id": "selected-book", "kind": "review",
            "input_revision": "revision-one", "instruction": "检查当前输入。",
            "attempts": 0, "status": "queued",
        }
        self.snapshot = {"manuscript/001.md": "甲走进院子。", "canon/state.json": json.dumps({
            "knowledge": [], "characters": [], "world": [], "offstage": [],
        })}
        self.file_calls = []
        self.blocks = []
        self.claims = 0

    def task(self, task_id):
        if task_id != self.record["id"]:
            raise ValueError("unknown task")
        return deepcopy(self.record)

    def files(self, book_id, revision):
        self.file_calls.append((book_id, revision))
        return dict(self.snapshot)

    def claim(self, task_id):
        self.claims += 1
        self.record["attempts"] += 1
        self.record["status"] = "running"

    def block(self, task_id, reason, detail):
        self.blocks.append((task_id, reason, detail))
        self.record["status"] = "blocked"


def ready():
    return {
        "ready": True, "chatgpt_login": True, "capability_ok": True,
        "model_defaults": {"model": "user-selected-model", "reasoning_effort": "high", "config_status": "read"},
    }


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = FakeEngine(self.temp.name)
        self.valid_result = {
            "task_id": "task-test", "input_revision": "revision-one",
            "completed_steps": ["检查所给文本"], "next_step": "作者阅读",
            "unresolved": [], "changes": [], "affected_paths": [], "state_notes": "",
            "review": {
                "coverage": ["manuscript/001.md", "canon/state.json"],
                "dimensions": ["continuity", "character", "world", "reading"], "findings": [],
            },
        }

    def process_factory(self, result=None, returncode=0, stderr_text="", timeout=False):
        def create(command, **kwargs):
            process = Mock()
            process.pid = 4321
            process.returncode = returncode
            process.poll.return_value = None
            def communicate(prompt, timeout=None):
                kwargs["stderr"].write(stderr_text)
                if create.timeout:
                    raise subprocess.TimeoutExpired(command, timeout)
                if result is not None:
                    output = Path(command[command.index("--output-last-message") + 1])
                    output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            process.communicate.side_effect = communicate
            return process
        create.timeout = timeout
        return create

    def test_prepare_requires_claim(self):
        with self.assertRaisesRegex(ValueError, "running"):
            adapter.prepare(self.engine, "task-test")
        self.assertFalse((self.engine.root / "runtime").exists())

    def test_prepare_exports_selected_snapshot_and_hashes(self):
        self.engine.claim("task-test")
        directory = adapter.prepare(self.engine, "task-test")
        packet = json.loads((directory / "packet.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["files"], self.engine.snapshot)
        self.assertEqual(self.engine.file_calls, [("selected-book", "revision-one")])
        self.assertEqual(packet["file_sha256"]["manuscript/001.md"], adapter._digest("甲走进院子。"))
        self.assertEqual(directory.name, "attempt-1")
        self.assertEqual(adapter.prepare(self.engine, "task-test"), directory)
        self.engine.snapshot["manuscript/001.md"] = "changed"
        with self.assertRaisesRegex(ValueError, "differs"):
            adapter.prepare(self.engine, "task-test")

    def test_prepare_rejects_task_path_escape(self):
        self.engine.record["id"] = "../escape"
        self.engine.claim("../escape")
        with self.assertRaisesRegex(ValueError, "unsafe task"):
            adapter.prepare(self.engine, "../escape")

    def test_doctor_checks_capabilities_and_chatgpt_login(self):
        probes = [(0, "codex-cli example"), (0, " ".join(adapter.REQUIRED_FLAGS)), (0, "Logged in using ChatGPT")]
        with patch.object(adapter, "_probe", side_effect=probes) as probe, patch.object(adapter, "_model_defaults", return_value=ready()["model_defaults"]):
            result = adapter.doctor()
        self.assertTrue(result["ready"])
        self.assertEqual(probe.call_args_list[-1].args[1], ["login", "status"])
        probes[-1] = (0, "Logged in using an API key")
        with patch.object(adapter, "_probe", side_effect=probes), patch.object(adapter, "_model_defaults", return_value=ready()["model_defaults"]):
            self.assertFalse(adapter.doctor()["ready"])

    def test_doctor_rejects_missing_flags_and_unreadable_preferences(self):
        probes = [(0, "codex-cli old"), (0, "--sandbox"), (0, "Logged in using ChatGPT")]
        with patch.object(adapter, "_probe", side_effect=probes), patch.object(adapter, "_model_defaults", return_value={"config_status": "unreadable"}):
            result = adapter.doctor()
        self.assertFalse(result["ready"])
        self.assertIn("--output-schema", result["missing_flags"])

    def test_model_preferences_only_read_plain_top_level_selection(self):
        (self.engine.root / "config.toml").write_text('model = "chosen-model"\nmodel_reasoning_effort = "high"\n[model_providers.custom]\napi_key = "do-not-copy"\n', encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(self.engine.root)}):
            defaults = adapter._model_defaults()
        self.assertEqual(defaults, {"model": "chosen-model", "reasoning_effort": "high", "config_status": "read"})

    def test_child_environment_drops_tokens_without_changing_parent(self):
        supplied = {"OPENAI_API_KEY": "test-key", "CODEX_API_KEY": "test-key", "ANTHROPIC_AUTH_TOKEN": "test-token", "OPENAI_BASE_URL": "https://invalid.example"}
        with patch.dict(os.environ, supplied):
            env, removed = adapter._child_environment()
            for key in supplied:
                self.assertNotIn(key, env)
                self.assertIn(key, removed)
                self.assertEqual(os.environ[key], supplied[key])

    def test_run_simulation_returns_validated_candidate_without_publishing(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(self.valid_result)) as popen:
            result = adapter.run(self.engine, "task-test")
        self.assertEqual(result, self.valid_result)
        self.assertEqual(self.engine.record["status"], "running")
        self.assertEqual(self.engine.claims, 1)
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--model") + 1], "user-selected-model")
        self.assertIn("--ignore-user-config", command)
        self.assertIn('web_search="disabled"', command)
        self.assertIn("features.shell_tool=false", command)
        self.assertIn("features.apps=false", command)
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertNotIn("--ignore-rules", command)
        self.assertEqual(command[-1], "-")

    def test_same_attempt_cannot_launch_twice(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(self.valid_result)) as popen:
            adapter.run(self.engine, "task-test")
            with self.assertRaises(adapter.AdapterError) as caught:
                adapter.run(self.engine, "task-test")
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(caught.exception.reason, "no_progress")
        self.assertEqual(self.engine.record["attempts"], 1)

    def test_preflight_failure_blocks_without_spawning(self):
        status = ready()
        status.update(ready=False, chatgpt_login=False)
        with patch.object(adapter, "doctor", return_value=status), patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, "task-test")
        popen.assert_not_called()
        self.assertEqual(self.engine.blocks[-1][1], "authorization")
        self.assertEqual(self.engine.record["attempts"], 1)

    def test_invalid_model_output_is_blocked_by_real_validator(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory({"claimed_success": True})):
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, "task-test")
        self.assertEqual(self.engine.blocks[-1][1], "tool_failure")
        self.assertIn("missing or unknown", self.engine.blocks[-1][2])

    def test_quota_failure_is_persisted_without_retry(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(returncode=1, stderr_text="usage limit reached")) as popen:
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, "task-test")
        self.assertEqual(self.engine.blocks[-1][1], "quota")
        self.assertEqual(popen.call_count, 1)

    def test_timeout_cleans_only_created_process_then_blocks(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(timeout=True)), patch.object(adapter, "_stop_tree") as stop:
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, "task-test", timeout=0.01)
        self.assertEqual(stop.call_args.args[0].pid, 4321)
        self.assertEqual(self.engine.blocks[-1][1], "tool_failure")

    def test_missing_result_is_not_success(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory()):
            with self.assertRaisesRegex(adapter.AdapterError, "without a result"):
                adapter.run(self.engine, "task-test")
        self.assertEqual(self.engine.record["status"], "blocked")

    def test_invalid_timeout_does_not_claim(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                adapter.run(self.engine, "task-test", timeout=timeout)
        self.assertEqual(self.engine.claims, 0)

    def test_strict_result_loader_rejects_duplicate_keys_and_nonstandard_constants(self):
        path = self.engine.root / "result.json"
        for text in ('{"task_id":"one","task_id":"two"}', '{"value":NaN}', '[]'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    adapter.load_result(path)

    def test_research_simulation_enables_only_builtin_web_mode(self):
        self.engine.record["kind"] = "research"
        research = {
            "question": "当前句子是否交代了场景？", "sources": [], "conclusion": "仅能确认场景是院子。",
            "conditions": ["仅依据当前正文"], "uncertainties": ["未做外部来源核查"],
            "affected_paths": ["manuscript/001.md"],
            "claims": [{"kind": "inference", "text": "当前文本描写进入院子。", "source_indexes": []}],
        }
        result = {**self.valid_result, "review": None, "affected_paths": ["manuscript/001.md"],
                  "changes": [{"path": "research/gap.json", "content": json.dumps(research, ensure_ascii=False)}]}
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(result)) as popen:
            adapter.run(self.engine, "task-test")
        self.assertIn('web_search="live"', popen.call_args.args[0])
        prompt = (self.engine.root / "runtime/tasks/task-test/attempt-1/prompt.md").read_text(encoding="utf-8")
        self.assertIn("仅允许内建 web/search", prompt)

    def test_cleanup_failure_is_blocked_and_not_claimed_as_stopped(self):
        with patch.object(adapter, "doctor", return_value=ready()), patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(timeout=True)), patch.object(adapter, "_stop_tree", side_effect=OSError("denied")):
            with self.assertRaisesRegex(adapter.AdapterError, "cleanup unconfirmed"):
                adapter.run(self.engine, "task-test", timeout=0.01)
        self.assertEqual(self.engine.blocks[-1][1], "tool_failure")

    def test_stop_tree_terminates_real_owned_subprocess(self):
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, **options)
        try:
            adapter._stop_tree(process)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
