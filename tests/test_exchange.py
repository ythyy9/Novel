"""Offline two-directory fixtures, not a real workstation/cloud transport test."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from novel import exchange
from novel.engine import Engine, EngineError, canonical


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix=".novel-exchange-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.a = Engine.initialize(self.root / "a")
        self.a.create_book("sample", "合成资料")
        self.task = self.a.enqueue("sample", "review", "合成只读审核")
        self.artifact = "runtime/inputs/sample.txt"
        self.a._new_file(self.a.root / self.artifact, "第一版\r\n")
        shutil.copytree(self.a.root, self.root / "b")
        self.b = Engine(self.root / "b")
        self.spec = {"origin": "local", "operation_id": "base", "task_ids": [self.task["id"]],
                     "artifacts": [self.artifact], "verification": "未运行模型；合成工程输入。",
                     "unresolved": ["读者未验收"], "next_step": "先核对对端状态", "excluded": ["未选定文件及认证、原作、日志"]}
        self.base = self.root / "base.json"
        exchange.create(self.a, self.spec, self.base)

    def package(self, engine, name, origin="local", baseline=True):
        spec = {**self.spec, "operation_id": name, "origin": origin}
        path = self.root / (name + ".json")
        exchange.create(engine, spec, path, self.base if baseline else None)
        return path

    def test_bidirectional_preflight_and_offline_receipt_never_overwrites(self):
        self.assertEqual(exchange.check(self.b, self.base)["status"], "same_selected_state")
        (self.a.root / self.artifact).write_bytes("第二版\r\n".encode("utf-8"))
        incoming = self.package(self.a, "local-second")
        self.assertEqual(exchange.check(self.b, incoming)["status"], "unknown_baseline")
        self.assertEqual(exchange.check(self.b, incoming, self.base)["status"], "incoming_ahead")
        received = exchange.receive(self.b, incoming, self.base)
        self.assertFalse(received["receipt"]["duplicate"])
        self.assertTrue(exchange.receive(self.b, incoming, self.base)["receipt"]["duplicate"])
        self.assertEqual((self.b.root / self.artifact).read_bytes(), "第一版\r\n".encode("utf-8"))
        saved = self.b.root / received["receipt"]["path"]
        incoming.unlink()  # Simulate sender disconnected; retained copy remains readable.
        self.assertEqual(exchange._read(saved)["record"]["capture"]["artifacts"][self.artifact], "第二版\r\n")
        back = self.package(self.b, "cloud-state", "cloud")
        self.assertEqual(exchange.check(self.a, back, self.base)["status"], "local_ahead")
        (self.b.root / self.artifact).write_text("云端并发版本", encoding="utf-8")
        branch = self.package(self.b, "cloud-branch", "cloud")
        self.assertEqual(exchange.check(self.a, branch, self.base)["status"], "diverged")
        self.assertFalse(exchange.check(self.a, branch, self.base)["peer_latest_known"])

    def test_same_operation_changed_payload_tampering_and_wrong_baseline(self):
        first = self.package(self.a, "operation")
        exchange.receive(self.b, first, self.base)
        changed = self.root / "changed.json"
        exchange.create(self.a, {**self.spec, "operation_id": "operation", "next_step": "不同操作内容"}, changed, self.base)
        with self.assertRaisesRegex(EngineError, "Operation id"):
            exchange.receive(self.b, changed, self.base)
        with self.assertRaisesRegex(EngineError, "baseline"):
            exchange.check(self.b, first, changed)
        obj = json.loads(first.read_text(encoding="utf-8"))
        obj["record"]["capture"]["artifacts"][self.artifact] = "损坏内容"
        first.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "integrity"):
            exchange.receive(self.b, first, self.base)

    def test_completed_task_and_feedback_visible_without_live_import(self):
        claimed = self.a.claim(self.task["id"])
        result = {"task_id": claimed["id"], "input_revision": claimed["input_revision"],
                  "completed_steps": ["合成审核完成"], "next_step": "等待真人反馈", "unresolved": [],
                  "changes": [], "affected_paths": [], "state_notes": "无修改",
                  "review": {"coverage": ["canon/state.json"], "dimensions": ["continuity", "character", "world", "reading"], "findings": []}}
        self.a.submit(claimed["id"], result, expected_attempt=1)
        self.a.publish(claimed["id"])
        original = self.a.feedback("sample", "合成作者原话，非真实用户反馈")
        package = self.package(self.a, "completed")
        report = exchange.receive(self.b, package, self.base)
        self.assertEqual(report["preflight"]["incoming_completed_tasks"], [claimed["id"]])
        self.assertEqual(self.b.task(claimed["id"])["status"], "queued")
        capture = exchange._read(package)["record"]["capture"]
        self.assertEqual(capture["feedback"]["sample"][0]["text"], original["text"])
        self.assertEqual(capture["tasks"][claimed["id"]]["task"]["attempts"], 1)

    def test_stopped_history_and_missing_local_task_stay_visible(self):
        self.a.claim(self.task["id"])
        self.a.block(self.task["id"], "no_progress", "合成停止")
        package = self.package(self.a, "stopped")
        empty = Engine.initialize(self.root / "empty")
        report = exchange.check(empty, package, self.base)
        self.assertEqual(report["status"], "diverged")
        task = exchange._read(package)["record"]["capture"]["tasks"][self.task["id"]]["task"]
        self.assertEqual((task["attempts"], task["no_progress"], task["stop_reason"]), (1, 1, "no_progress"))
        self.assertEqual(empty.tasks(), [])

    def test_malformed_task_payload_and_missing_artifact_rejected(self):
        package = self.package(self.a, "malformed")
        obj = exchange._read(package)
        obj["record"]["capture"]["tasks"][self.task["id"]]["task"] = None
        obj["record"]["state"] = exchange._state(obj["record"]["capture"])
        obj["id"] = exchange._sha(obj["record"])
        package.write_text(canonical(obj), encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "handoff"):
            exchange.receive(self.b, package)
        (self.a.root / self.artifact).unlink()
        with self.assertRaisesRegex(EngineError, "Missing artifact"):
            self.package(self.a, "missing")

    def test_rejects_paths_scope_changes_and_source_changes(self):
        from unittest.mock import patch
        for path in ("../escape.txt", "runtime/novel.sqlite3", "runtime/inputs/../secret.txt", "runtime/inputs/CON.txt"):
            spec = {**self.spec, "artifacts": [path]}
            with self.subTest(path=path), self.assertRaises(EngineError):
                exchange.create(self.a, spec, self.root / "bad.json")
        with self.assertRaisesRegex(EngineError, "Selection changed"):
            exchange.create(self.a, {**self.spec, "artifacts": []}, self.root / "scope.json", self.base)
        original = exchange._capture(self.a, self.spec, required=True)
        altered = copy.deepcopy(original)
        altered["artifacts"][self.artifact] = "changed"
        with patch.object(exchange, "_capture", side_effect=[original, altered]):
            with self.assertRaisesRegex(EngineError, "Source changed"):
                exchange.create(self.a, self.spec, self.root / "raced.json")
        self.assertFalse((self.root / "raced.json").exists())
        with self.assertRaises(FileExistsError):
            exchange.create(self.a, self.spec, self.base)
