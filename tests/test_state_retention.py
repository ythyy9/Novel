"""Complete-state and delta submissions share stable identity protection."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from novel.engine import Engine, EngineError, canonical


class StateRetentionTests(unittest.TestCase):
    def test_all_state_sections_reject_missing_or_replaced_identity(self):
        with tempfile.TemporaryDirectory(prefix=".novel-state-test-", dir=Path(__file__).resolve().parents[1]) as root:
            engine = Engine.initialize(root)
            engine.create_book("fixture", "Synthetic retention")
            previous = {}
            for section in ("knowledge", "characters", "world", "offstage"):
                row = {"id": section + "-one", "statement": "A letter arrived.",
                       "sources": [{"path": "manuscript/001.md", "quote": "A letter arrived."}]}
                if section == "knowledge":
                    row.update(kind="world_fact", holder=None)
                previous[section] = [row]
            def result(task, state, prose):
                return {"task_id": task["id"], "input_revision": task["input_revision"],
                    "completed_steps": ["Synthetic state update"], "next_step": "Review", "unresolved": [],
                    "changes": [{"path": "canon/state.json", "content": canonical(state)},
                                {"path": "manuscript/001.md", "content": prose}],
                    "review": None, "affected_paths": ["canon/state.json", "manuscript/001.md"], "state_notes": "Synthetic"}
            initial = engine.claim(engine.enqueue("fixture", "write", "Seed all sections")["id"])
            engine.submit(initial["id"], result(initial, previous, "A letter arrived."))
            engine.publish(initial["id"])
            task = engine.claim(engine.enqueue("fixture", "revise", "Exercise accidental omissions")["id"])
            old_revision = engine.book("fixture")["current_revision"]
            for section in previous:
                for replace in (False, True):
                    updated = deepcopy(previous)
                    if replace:
                        updated[section][0]["id"] = "replacement"
                    else:
                        updated[section].clear()
                    with self.subTest(section=section, replace=replace), self.assertRaisesRegex(EngineError, "stable " + section):
                        engine.submit(task["id"], result(task, updated, "A letter arrived. A second letter arrived."))
                    self.assertEqual(engine.task(task["id"])["status"], "running")
                    self.assertEqual(engine.book("fixture")["current_revision"], old_revision)
            engine.submit(task["id"], result(task, previous, "A letter arrived. A second letter arrived."))
            engine.publish(task["id"])
            self.assertEqual(json.loads(engine.files("fixture")["canon/state.json"]), previous)


if __name__ == "__main__":
    unittest.main()
