"""Crash/attempt integration tests use real processes and disk state."""
from pathlib import Path
import json
import os
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


if __name__ == "__main__":
    unittest.main()
