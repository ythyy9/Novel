"""Crash/attempt integration tests use real processes and disk state."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from novel.engine import Engine, EMPTY_STATE


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-recovery-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = Engine.initialize(self.root)
        self.engine.create_book("test", "Engineering crash sample")

    def result(self, task):
        return {"task_id": task["id"], "input_revision": task["input_revision"], "completed_steps": ["fixture"],
                "next_step": "independent review", "unresolved": [], "changes": [
                    {"path": "manuscript/001.md", "content": "The boat arrived before sunset.\n"},
                    {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE)}],
                "review": None, "affected_paths": ["manuscript/001.md"], "state_notes": "No additional state in this crash fixture"}

    def test_process_death_after_snapshot_before_commit_recovers_without_partial_publish(self):
        task = self.engine.enqueue("test", "write", "crash fixture")
        self.engine.claim(task["id"])
        self.engine.submit(task["id"], self.result(task))
        before = self.engine.book("test")["current_revision"]
        code = """
import os, sys
from novel.engine import Engine
engine = Engine(sys.argv[1])
original = engine._snapshot
def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(23)
engine._snapshot = crash
engine.publish(sys.argv[2])
"""
        run = subprocess.run([sys.executable, "-c", code, str(self.root), task["id"]],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 23, run.stderr)
        reopened = Engine(self.root)
        self.assertEqual(reopened.book("test")["current_revision"], before)
        self.assertEqual(reopened.task(task["id"])["status"], "submitted")
        self.assertNotIn("manuscript/001.md", reopened.files("test"))
        published = reopened.publish(task["id"])
        self.assertEqual(published["status"], "completed")
        self.assertNotEqual(published["result_revision"], before)
        self.assertEqual(reopened.audit()["database"], "ok")
        self.assertEqual(len(list((self.root / "books/test/versions").iterdir())), 2)

    def test_late_result_cannot_submit_for_new_attempt(self):
        task = self.engine.enqueue("test", "write", "attempt fixture")
        self.engine.claim(task["id"])
        self.engine.recover(task["id"], "worker confirmed stopped")
        self.engine.resume(task["id"], "restart explicitly requested")
        self.engine.claim(task["id"])
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task), expected_attempt=1)
        self.assertEqual(self.engine.task(task["id"])["status"], "running")
        self.engine.submit(task["id"], self.result(task), expected_attempt=2)

    def test_initialized_project_exports_real_policy_and_methods(self):
        documents = self.engine.control_documents()
        self.assertIn("methods/writing.md", documents)
        self.assertIn("policies/principles.md", documents)
        self.assertIn("policies/limits.json", documents)
        from novel.adapter import prepare, load_result
        task = self.engine.enqueue("test", "write", "packet fixture")
        self.engine.claim(task["id"])
        packet = load_result(prepare(self.engine, task["id"]) / "packet.json")
        self.assertEqual(packet["policies_and_methods"], documents)

    def test_quiescent_backup_restores_stop_history_and_experiments_in_new_process(self):
        from novel import evaluation
        task = self.engine.claim(self.engine.enqueue("test", "write", "backup fixture")["id"])
        self.engine.submit(task["id"], self.result(task))
        self.engine.publish(task["id"])
        stopped = self.engine.claim(self.engine.enqueue("test", "revise", "stop fixture")["id"])
        self.engine.block(stopped["id"], "no_progress", "工程停止证据，不能在恢复副本中清零")
        experiment = {"id": "restore-check", "hypothesis": "工程备份检验", "baseline_method": "fixture baseline",
                      "candidate_method": "fixture candidate", "cases": [
                          {"id": kind, "split": kind, "input": "工程输入", "baseline_output": "旧", "candidate_output": "新"}
                          for kind in ("development", "holdout")]}
        evaluation.create(self.root, experiment)
        evaluation.judge(self.root, "restore-check", "development", "inconclusive", "工程测试记录，不是作者反馈", "agent")
        before = self.engine.handoff(stopped["id"])
        summary = evaluation.summarize(self.root, "restore-check")
        # No writer is running; copy the complete documented set, including any WAL sidecars.
        restored_temp = tempfile.TemporaryDirectory(prefix=".novel-recovery-test-", dir=self.root.parent)
        self.addCleanup(restored_temp.cleanup)
        restored = Path(restored_temp.name) / "restored"
        restored.mkdir()
        for folder in ("books", "runtime", "policies", "methods", "evaluations"):
            shutil.copytree(self.root / folder, restored / folder)
        def cli(*args):
            process = subprocess.run([sys.executable, "-m", "novel", "--root", str(restored), *args],
                                     cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                     text=True, encoding="utf-8", timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            return json.loads(process.stdout)
        self.assertEqual(cli("audit"), self.engine.audit())
        self.assertEqual(cli("handoff", stopped["id"]), before)
        self.assertEqual(cli("eval-summary", "restore-check"), summary)
        reopened = Engine(restored)
        queued = reopened.enqueue("test", "revise", "cannot bypass restored stop")
        with self.assertRaises(ValueError):
            reopened.claim(queued["id"])
        self.assertEqual(reopened.task(stopped["id"])["attempts"], 1)
        self.assertEqual(reopened.task(stopped["id"])["no_progress"], 1)
        self.assertEqual(self.engine.handoff(stopped["id"]), before)
        # A Git-only or runtime-only backup must not pass the recovery audit.
        shutil.rmtree(restored / "books")
        with self.assertRaises((ValueError, OSError)):
            reopened.audit()


if __name__ == "__main__":
    unittest.main()
