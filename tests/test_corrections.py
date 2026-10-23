import copy
import json
from pathlib import Path
import tempfile
import unittest

from novel.engine import Engine, EngineError
from novel.dot import DotWorkspace
from novel.records import ValidationError, validate_result


class CorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.old = {"id": "arrival", "kind": "world_fact", "holder": None,
                    "statement": "Arrived before noon.",
                    "sources": [{"path": "manuscript/001.md", "quote": "The letter arrived."}]}
        self.state = {"knowledge": [self.old], "characters": [], "world": [], "offstage": []}
        self.files = {"manuscript/001.md": "The letter arrived. It was after noon.",
                      "canon/state.json": json.dumps(self.state),
                      "revisions/old.md": "Before noon."}
        self.task = {"id": "t", "kind": "correct_records", "input_revision": "r"}
        self.evidence = {"path": "manuscript/001.md", "quote": "It was after noon."}
        self.new = {**copy.deepcopy(self.old), "statement": "Arrived after noon.",
                    "sources": self.old["sources"] + [self.evidence]}

    def result(self, records=True, annotations=False):
        note = {"format": "novel-record-correction-v1", "reason": "Correct timing.",
                "records": [{"section": "knowledge", "id": "arrival", "before": self.old,
                             "after": self.new, "reason": "The manuscript states after noon.",
                             "evidence": [self.evidence]}] if records else [],
                "annotations": [{"path": "revisions/old.md", "quote": "Before noon.",
                                 "correction": "Read as after noon.", "evidence": [self.evidence]}] if annotations else []}
        changes = [{"path": "revisions/correction-t.json", "content": json.dumps(note)}]
        if records:
            changes.append({"path": "canon/state.json", "content": json.dumps({**self.state, "knowledge": [self.new]})})
        return {"task_id": "t", "input_revision": "r", "completed_steps": ["Verified original evidence."],
                "next_step": "Independent review.", "unresolved": [], "changes": changes, "review": None,
                "affected_paths": [c["path"] for c in changes] + (["revisions/old.md"] if annotations else []),
                "state_notes": "Only documented correction."}

    def test_state_and_annotation_modes(self):
        for records, annotations in [(True, False), (False, True), (True, True)]:
            with self.subTest(records=records, annotations=annotations):
                validate_result(self.result(records, annotations), self.task, self.files)

    def test_rejects_undocumented_or_destructive_state_changes(self):
        for field, value in [("id", "replacement"), ("kind", "candidate"), ("holder", "someone"),
                             ("sources", [self.evidence])]:
            with self.subTest(field=field):
                r = self.result()
                note = json.loads(r["changes"][0]["content"])
                note["records"][0]["after"][field] = value
                r["changes"][0]["content"] = json.dumps(note)
                with self.assertRaises(ValidationError):
                    validate_result(r, self.task, self.files)
        r = self.result()
        r["changes"][1]["content"] = json.dumps({**self.state, "knowledge": []})
        with self.assertRaisesRegex(ValidationError, "state differs"):
            validate_result(r, self.task, self.files)

    def test_rejects_source_forgery_history_rewrite_and_prose_edits(self):
        r = self.result(False, True)
        note = json.loads(r["changes"][0]["content"])
        note["annotations"][0]["evidence"][0]["quote"] = "Invented source"
        r["changes"][0]["content"] = json.dumps(note)
        with self.assertRaises(ValidationError):
            validate_result(r, self.task, self.files)
        for path in ("manuscript/001.md", "decisions/forged.md", "revisions/old.md"):
            r = self.result(False, True)
            r["changes"].append({"path": path, "content": "Overwrite"})
            with self.assertRaises(ValidationError):
                validate_result(r, self.task, self.files)

    def test_wrong_before_missing_impact_and_empty_note_rejected(self):
        r = self.result()
        note = json.loads(r["changes"][0]["content"])
        note["records"][0]["before"]["statement"] = "Not the original"
        r["changes"][0]["content"] = json.dumps(note)
        with self.assertRaisesRegex(ValidationError, "before record"):
            validate_result(r, self.task, self.files)
        for r in (self.result(False, False), {**self.result(), "affected_paths": []}):
            with self.assertRaises(ValidationError):
                validate_result(r, self.task, self.files)

    def test_publish_preserves_original_and_requires_new_review(self):
        with tempfile.TemporaryDirectory(prefix=".novel-correction-test-", dir=Path(__file__).resolve().parents[1]) as folder:
            engine = Engine.initialize(folder)
            engine.create_book("fixture", "Fixture")
            writer = engine.claim(engine.enqueue("fixture", "write", "Initial fixture")["id"])
            r = self.result()
            r.update(task_id=writer["id"], input_revision=writer["input_revision"])
            r["changes"] = [{"path": p, "content": c} for p, c in self.files.items()]
            r["affected_paths"] = list(self.files)
            engine.submit(writer["id"], r, expected_attempt=1)
            engine.publish(writer["id"])
            original = engine.book("fixture")["current_revision"]
            dot = DotWorkspace(folder, "fixture")
            receipt = dot.open_task(request_id="correct-open", kind="correct_records", instruction="Correct timing",
                                    expected_revision=original, context_ref="corrector")
            task = receipt["task"]
            self.assertIn("record-correction-guide.md", [d["path"] for d in receipt["documents"]])
            r = self.result(True, True)
            r.update(task_id=task["id"], input_revision=task["input_revision"])
            engine.submit(task["id"], r, expected_attempt=1)
            engine.publish(task["id"])
            self.assertFalse(engine.assessment("fixture")["can_accept"])
            with self.assertRaises(EngineError):
                engine.accept("fixture")
            files = engine.files("fixture")
            self.assertEqual(files["manuscript/001.md"], self.files["manuscript/001.md"])
            self.assertEqual(files["revisions/old.md"], self.files["revisions/old.md"])
            self.assertEqual(engine.files("fixture", original)["canon/state.json"], self.files["canon/state.json"])
            self.assertEqual(engine.task(task["id"])["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
