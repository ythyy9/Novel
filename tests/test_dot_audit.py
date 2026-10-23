"""Recovery audit must include gateway evidence without treating partial work as loss."""
from pathlib import Path
import shutil
import tempfile
import unittest

from novel.dot import DotWorkspace
from novel.engine import Engine, EngineError
import test_context as fixtures


class DotAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StagedDotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.task = self.fixture.open()
        self.dot, self.engine = self.fixture.dot, self.fixture.engine

    def test_missing_packet_or_gateway_fails_without_recreation(self):
        path = self.dot.base / "packets" / (self.task["id"] + ".json")
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(EngineError, "missing fixed packet"):
            self.engine.audit()
        path.write_bytes(original)
        self.dot.db_path.unlink()
        with self.assertRaisesRegex(EngineError, "gateway database is missing"):
            self.engine.audit()
        self.assertFalse(self.dot.db_path.exists())

    def test_partial_upload_is_valid_but_missing_acknowledged_part_fails(self):
        self.dot.chunk(request_id="part", task_id=self.task["id"], attempt=1,
                       upload_id="partial", part=0, total=2, content="{")
        self.assertEqual(self.engine.audit()["dot"]["uploads_verified"], 0)
        with self.dot._db() as db:
            db.execute("DELETE FROM parts")
        with self.assertRaisesRegex(EngineError, "no matching upload part"):
            self.engine.audit()

    def checkpoint(self):
        import json
        plan = json.loads(self.fixture.read_all(self.task, "context-plan.json"))
        payload = self.fixture.checkpoint(self.task, plan, plan["batches"][0])
        self.fixture.send(self.task, payload)
        return payload

    def test_checkpoint_corruption_or_missing_read_coverage_fails(self):
        self.checkpoint()
        self.assertEqual(self.engine.audit()["dot"]["checkpoints_verified"], 1)
        with self.dot._db() as db:
            db.execute("DELETE FROM context_reads")
        with self.assertRaisesRegex(EngineError, "complete delivery evidence"):
            self.engine.audit()

    def test_missing_checkpoint_is_detected_from_durable_finish_receipt(self):
        self.checkpoint()
        with self.dot._db() as db:
            db.execute("DELETE FROM context_checkpoints")
        with self.assertRaisesRegex(EngineError, "no matching checkpoint"):
            self.engine.audit()

    def test_quiescent_copy_retains_packet_upload_and_checkpoint_progress(self):
        self.checkpoint()
        self.dot.chunk(request_id="partial", task_id=self.task["id"], attempt=1,
                       upload_id="partial", part=0, total=2, content="{")
        before = self.engine.audit()
        with tempfile.TemporaryDirectory(prefix=".novel-audit-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            copied = Path(tmp) / "copy"
            shutil.copytree(self.engine.root, copied)
            restored = Engine(copied)
            self.assertEqual(restored.audit(), before)
            reopened = DotWorkspace(copied, "fixture")
            self.assertEqual(reopened.read(task_id=self.task["id"], document="context-progress.json"),
                             self.dot.read(task_id=self.task["id"], document="context-progress.json"))
            self.assertEqual(restored.task(self.task["id"]), self.engine.task(self.task["id"]))


if __name__ == "__main__":
    unittest.main()
