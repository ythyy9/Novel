"""Bounded status pagination must retain every active task and all history access."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from novel.dot import DotWorkspace
from novel.engine import Engine, EngineError
from novel.dot_transport import tools


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-status-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine.initialize(self.temp.name)
        self.engine.create_book("fixture", "Synthetic status")
        self.dot = DotWorkspace(self.temp.name, "fixture")
        self.active = self.dot.open_task(request_id="open", kind="write", instruction="Original full instruction",
            expected_revision=self.engine.book("fixture")["current_revision"], context_ref="writer")["task"]
        with self.engine._db(True) as db, self.dot._db() as gateway:
            for i in range(31):
                name = f"history-{i:03d}"
                db.execute("INSERT INTO tasks(id,book_id,kind,instruction,input_revision,control_hash,status,created_at,updated_at) VALUES (?,?,?,?,?,?,'cancelled',?,?)",
                    (name, "fixture", "write", "Long synthetic instruction. " * 1000, self.active["input_revision"], self.active["control_hash"], "fixture", "fixture"))
                gateway.execute("INSERT INTO tasks VALUES (?,?,?)", (name, "writer", "write"))

    def test_default_is_bounded_and_does_not_load_results(self):
        with patch.object(self.dot.engine, "task", side_effect=AssertionError("No per-task result loading")):
            state = self.dot.status()
        self.assertEqual(state["task_count"], 32)
        self.assertEqual(len(state["tasks"]), 11)
        self.assertEqual(state["active_task_count"], 1)
        self.assertEqual(state["tasks"][0]["id"], self.active["id"])
        self.assertNotIn("instruction", state["tasks"][0])
        self.assertFalse(state["tasks_complete"])
        self.assertLess(len(json.dumps(state)), 20000)

    def test_pagination_retains_active_and_visits_all_history_once(self):
        before, seen = None, []
        while True:
            state = self.dot.status(history_limit=7, before=before)
            self.assertEqual(state["tasks"][0]["id"], self.active["id"])
            seen.extend(t["id"] for t in state["tasks"] if t["status"] == "cancelled")
            before = state["next_before"]
            if before is None:
                break
        self.assertEqual(len(seen), 31)
        self.assertEqual(len(set(seen)), 31)

    def test_full_instruction_remains_readable_and_old_tool_arguments_work(self):
        detail = self.dot.read(task_id=self.active["id"], document="task-info.json")
        self.assertEqual(json.loads(detail["text"])["instruction"], "Original full instruction")
        state = self.dot.status(include_instructions=True)
        self.assertIn("instruction", state["tasks"][0])
        schema = next(t["inputSchema"] for t in tools() if t["name"] == "novel_work_status")
        self.assertEqual(schema["required"], ["workspace"])
        for bad in ({"history_limit": 0}, {"before": -1}, {"include_instructions": "yes"}):
            with self.assertRaises(EngineError):
                self.dot.status(**bad)

    def test_cached_old_tool_schema_can_page_via_existing_read(self):
        state = self.dot.status()
        document = state["next_history_document"]
        text, offset = "", 0
        while offset is not None:
            page = self.dot.read(task_id=self.active["id"], document=document, offset=offset)
            text += page["text"]
            offset = page["next_offset"]
        following = json.loads(text)
        old = {t["id"] for t in state["tasks"] if t["status"] == "cancelled"}
        new = {t["id"] for t in following["tasks"] if t["status"] == "cancelled"}
        self.assertFalse(old & new)
        self.assertEqual(len(new), 10)


if __name__ == "__main__":
    unittest.main()
