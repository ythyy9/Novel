"""Crash/recovery fixtures use synthetic books only."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from novel.dot import DotWorkspace
from novel.engine import Engine, EngineError


class OpenRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-recovery-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine.initialize(self.temp.name)
        self.engine.create_book("fixture", "Synthetic recovery")
        self.dot = DotWorkspace(self.temp.name, "fixture")
        self.args = dict(request_id="original", kind="write", instruction="Synthetic fixture",
                         expected_revision=self.engine.book("fixture")["current_revision"], context_ref="writer")

    def original(self):
        with self.dot._db() as db:
            return dict(db.execute("SELECT * FROM requests WHERE id='original'").fetchone())

    def recover(self, request_id="recovery", **overrides):
        task = self.engine.tasks("fixture")[0]
        args = dict(request_id=request_id, failed_request_id="original", task_id=task["id"],
                    expected_attempt=task["attempts"], expected_revision=task["input_revision"],
                    context_ref="writer", note="Verified synthetic failure and original identity")
        return self.dot.recover_open_task(**{**args, **overrides})

    def fail_save(self):
        with patch.object(self.dot, "_save_packet", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.dot.open_task(**self.args)

    def test_failed_save_recovers_original_attempt_and_retains_error_receipt(self):
        self.fail_save()
        before, task = self.original(), self.engine.tasks("fixture")[0]
        self.assertEqual(self.dot.status()["recoverable_open_requests"][0]["task_id"], task["id"])
        receipt = self.recover()
        self.assertEqual(receipt["task"]["id"], task["id"])
        self.assertEqual(self.engine.task(task["id"]), task)
        self.assertEqual(self.original(), before)
        self.assertTrue(self.recover()["replayed"])
        self.assertEqual(self.dot.status()["recoverable_open_requests"], [])
        self.assertEqual(self.engine.audit()["dot"]["tasks_verified"], 1)
        with self.assertRaisesRegex(EngineError, "synthetic disk failure"):
            self.dot.open_task(**self.args)

    def test_interruption_before_claim_preserves_pending_and_claims_only_once(self):
        with patch.object(self.dot.engine, "claim", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.dot.open_task(**self.args)
        before = self.original()
        self.assertEqual(self.engine.tasks()[0]["attempts"], 0)
        self.recover()
        self.recover(expected_attempt=0)
        self.assertEqual(self.engine.tasks()[0]["attempts"], 1)
        self.assertEqual(self.original(), before)
        self.assertEqual(self.dot.status()["uncertain_requests"], [])

    def test_crash_after_enqueue_before_registration_uses_preassigned_identity(self):
        original = self.engine.enqueue
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(self.dot.engine, "enqueue", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.dot.open_task(**self.args)
        task = self.engine.tasks()[0]
        self.assertEqual(json.loads(self.original()["receipt"])["task_id"], task["id"])
        self.recover()
        self.assertEqual(len(self.engine.tasks()), 1)
        self.assertEqual(self.engine.task(task["id"])["attempts"], 1)

    def test_saved_packet_with_lost_receipt_reuses_identical_bytes(self):
        save = self.dot._save_packet
        def interrupted(*args, **kwargs):
            save(*args, **kwargs)
            raise OSError("receipt lost")
        with patch.object(self.dot, "_save_packet", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.dot.open_task(**self.args)
        path = self.dot.base / "packets" / (self.engine.tasks()[0]["id"] + ".json")
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.recover()
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_recovery_rejects_wrong_identity_stale_controls_and_stopped_task(self):
        self.fail_save()
        for change in ({"expected_attempt": 2}, {"expected_revision": "0" * 64}, {"context_ref": "other"}):
            with self.assertRaises(EngineError):
                self.recover(request_id="bad-" + next(iter(change)), **change)
        task = self.engine.tasks()[0]
        self.engine.block(task["id"], "tool_failure", "Preserve stop evidence")
        with self.assertRaises(EngineError):
            self.recover(request_id="stopped")
        self.assertEqual(self.engine.task(task["id"])["status"], "blocked")

    def test_missing_packet_with_uploaded_evidence_is_not_reconstructed(self):
        self.fail_save()
        task = self.engine.tasks()[0]
        self.dot.chunk(request_id="part", task_id=task["id"], attempt=1,
                       upload_id="upload", part=0, total=1, content="{}")
        with self.assertRaisesRegex(EngineError, "restore the original backup"):
            self.recover()
        self.assertEqual(self.engine.task(task["id"])["attempts"], 1)

    def test_incomplete_packet_write_never_publishes_partial_file(self):
        original = self.dot.engine._new_file
        def interrupted(path, content):
            if path.name.startswith(".pending-"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("partial", encoding="utf-8")
                raise OSError("partial write")
            return original(path, content)
        with patch.object(self.dot.engine, "_new_file", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.dot.open_task(**self.args)
        task = self.engine.tasks()[0]
        self.assertFalse((self.dot.base / "packets" / (task["id"] + ".json")).exists())
        self.recover()
        self.assertEqual(self.engine.audit()["dot"]["tasks_verified"], 1)


if __name__ == "__main__":
    unittest.main()
