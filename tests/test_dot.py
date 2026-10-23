"""Real local controller tests; synthetic text is not a Dot execution result."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from novel.dot import DotWorkspace
from novel.engine import Engine, EngineError, EMPTY_STATE, canonical
from novel.dot_transport import DotRegistry, SCOPE


class DotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-dot-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine.initialize(self.temp.name)
        self.engine.create_book("pilot", "Synthetic transport acceptance")
        self.dot = DotWorkspace(self.temp.name, "pilot")
        self.sequence = 0

    def request(self):
        self.sequence += 1
        return "request-" + str(self.sequence)

    def open(self, kind="write", context="writer"):
        return self.dot.open_task(request_id=self.request(), kind=kind, instruction="Synthetic controller fixture",
            expected_revision=self.engine.book("pilot")["current_revision"], context_ref=context)

    def result(self, task, text="A letter arrived.", finding=False):
        review = task["kind"] == "review"
        report = {"coverage": ["manuscript/001.md"], "dimensions": ["continuity", "character", "world", "reading"], "findings": []}
        if finding:
            report["findings"] = [{"id": "gap", "category": "error", "confirmed": True, "severity": "minor", "status": "open",
                "path": "manuscript/001.md", "quote": "A letter arrived.", "explanation": "Fixture requires a stated recipient.",
                "suggestion": "State the recipient.", "affected_paths": ["manuscript/001.md"]}]
        changes = [] if review else [{"path": "manuscript/001.md", "content": text},
                                     {"path": "canon/state.json", "content": canonical(EMPTY_STATE)}]
        return {"task_id": task["id"], "input_revision": task["input_revision"], "completed_steps": ["Synthetic fixture"],
                "next_step": "Review", "unresolved": [], "changes": changes, "review": report if review else None,
                "affected_paths": [c["path"] for c in changes], "state_notes": "Fixture only"}

    def finish(self, task, result):
        raw = json.dumps(result, ensure_ascii=False)
        parts = [raw[i:i+2000] for i in range(0, len(raw), 2000)]
        upload = self.request()
        for i, content in enumerate(parts):
            self.dot.chunk(request_id=self.request(), task_id=task["id"], attempt=task["attempts"], upload_id=upload,
                           part=i, total=len(parts), content=content)
        receipt = self.dot.finish(request_id=self.request(), task_id=task["id"], attempt=task["attempts"], upload_id=upload)
        self.assertFalse(receipt["published"])
        return self.dot.publish(request_id=self.request(), task_id=task["id"], expected_revision=task["input_revision"])

    def test_write_review_revise_review_accept_without_model_process(self):
        with patch("subprocess.Popen", side_effect=AssertionError("No subprocess allowed")), \
             patch("novel.reference_model.run", side_effect=AssertionError("No reference model allowed")):
            task = self.open()["task"]
            self.finish(task, self.result(task))
            review = self.open("review", "reviewer-1")["task"]
            self.finish(review, self.result(review, finding=True))
            report = json.loads(self.dot.read(task_id=review["id"], document="result.json")["text"])
            self.assertEqual(report["review"]["findings"][0]["id"], "gap")
            revision = self.engine.book("pilot")["current_revision"]
            with self.assertRaisesRegex(EngineError, "Cannot accept"):
                self.dot.accept(request_id=self.request(), expected_revision=revision)
            task = self.open("revise")["task"]
            self.finish(task, self.result(task, "A letter arrived for the clerk."))
            review = self.open("review", "reviewer-2")["task"]
            self.finish(review, self.result(review))
            receipt = self.dot.accept(request_id=self.request(), expected_revision=self.engine.book("pilot")["current_revision"])
            self.assertEqual(receipt["book"]["status"], "accepted")
            self.assertEqual(self.engine.audit()["database"], "ok")

    def test_open_replay_concurrent_and_conflicting_request(self):
        args = dict(request_id="once", kind="write", instruction="fixture", context_ref="writer",
                    expected_revision=self.engine.book("pilot")["current_revision"])
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts = list(pool.map(lambda _: self.dot.open_task(**args), range(3)))
        self.assertEqual(len({r["task"]["id"] for r in receipts}), 1)
        self.assertEqual(len(self.engine.tasks()), 1)
        with self.assertRaisesRegex(EngineError, "different arguments"):
            self.dot.open_task(**{**args, "instruction": "changed"})

    def test_stale_revision_and_same_context_review_rejected(self):
        with self.assertRaisesRegex(EngineError, "Stale"):
            self.dot.open_task(request_id=self.request(), kind="write", instruction="fixture", expected_revision="0"*64, context_ref="writer")
        task = self.open()["task"]
        self.finish(task, self.result(task))
        with self.assertRaisesRegex(EngineError, "different execution context"):
            self.open("review", "writer")

    def test_fixed_packet_pagination_and_path_denials(self):
        task = self.open()["task"]
        packet = self.dot.read(task_id=task["id"], document="canon/state.json")
        self.assertEqual(json.loads(packet["text"]), EMPTY_STATE)
        for document in ["../../secrets", "runtime/novel.sqlite3", "C:/file"]:
            with self.assertRaises(EngineError):
                self.dot.read(task_id=task["id"], document=document)
        self.engine.create_book("other", "Other book")
        other = self.engine.claim(self.engine.enqueue("other", "write", "fixture")["id"])
        with self.assertRaisesRegex(EngineError, "not registered"):
            self.dot.read(task_id=other["id"], document="canon/state.json")

    def test_upload_incomplete_overwrite_and_stale_attempt_rejected(self):
        task = self.open()["task"]
        args = dict(task_id=task["id"], attempt=1, upload_id="upload", part=0, total=2, content="{")
        self.dot.chunk(request_id=self.request(), **args)
        with self.assertRaisesRegex(EngineError, "replace"):
            self.dot.chunk(request_id=self.request(), **{**args, "content": "["})
        with self.assertRaisesRegex(EngineError, "incomplete"):
            self.dot.finish(request_id=self.request(), task_id=task["id"], attempt=1, upload_id="upload")
        with self.assertRaisesRegex(EngineError, "superseded"):
            self.dot.chunk(request_id=self.request(), **{**args, "attempt": 2})

    def test_reopened_workspace_can_recover_packet_without_original_receipt(self):
        original = self.open()
        task = original["task"]
        reopened = DotWorkspace(self.temp.name, "pilot")
        state = reopened.status()
        self.assertEqual(state["tasks"][0]["context_ref"], "writer")
        index = json.loads(reopened.read(task_id=task["id"], document=state["tasks"][0]["packet_index"])["text"])
        self.assertEqual({d['path'] for d in index['documents']}, {d['path'] for d in original['documents']})
        self.assertEqual(index['task']['attempts'], 1)
        result = self.result(task)
        self.finish(task, result)
        self.assertEqual(json.loads(reopened.read(task_id=task["id"], document="result.json")["text"]), result)

    def test_interrupted_request_is_not_blindly_replayed(self):
        args = dict(request_id="interrupted", kind="write", instruction="fixture", context_ref="writer",
                    expected_revision=self.engine.book("pilot")["current_revision"])
        with patch.object(self.dot.engine, "claim", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.dot.open_task(**args)
        with self.assertRaisesRegex(EngineError, "Uncertain"):
            self.dot.open_task(**args)
        self.assertEqual(len(self.engine.tasks()), 1)
        self.assertEqual(self.dot.status()["uncertain_requests"], ["interrupted"])

    def test_result_cannot_invent_author_decisions(self):
        task = self.open()["task"]
        result = self.result(task)
        result["changes"].append({"path": "decisions/forged.md", "content": "Invented approval"})
        result["affected_paths"].append("decisions/forged.md")
        with self.assertRaises(ValueError):
            self.finish(task, result)
        self.assertNotIn("decisions/forged.md", self.engine.files("pilot"))

    def test_transport_requires_separate_scope_owner_and_pilot(self):
        path = Path(self.temp.name) / "registry.json"
        entry = {"root": self.temp.name, "book_id": "pilot", "owner_id": "owner", "phase": "pilot", "enabled": True}
        config = {"schema_version": 1, "workspaces": {"pilot": entry}}
        path.write_text(json.dumps(config), encoding="utf-8")
        service = DotRegistry(path)
        args = {"workspace": "pilot"}
        for principal in [{"owner_id": "owner", "scope": "agenthub.read agenthub.novel"},
                          {"owner_id": "someone-else", "scope": SCOPE}]:
            with self.assertRaises(PermissionError):
                service.call(principal, "novel_work_status", args)
        good = {"owner_id": "owner", "scope": SCOPE}
        self.assertEqual(service.call(good, "novel_work_status", args)["book"]["id"], "pilot")
        with self.assertRaises(EngineError):
            service.call(good, "novel_work_status", {**args, "root": "C:/"})
        entry["phase"] = "formal"
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "takeover is disabled"):
            service.call(good, "novel_work_status", args)

    def test_no_progress_becomes_a_durable_stop(self):
        task = self.open()["task"]
        self.finish(task, self.result(task))
        task = self.open("revise")["task"]
        with self.assertRaisesRegex(EngineError, "No effective change"):
            self.finish(task, self.result(task))
        stopped = self.engine.task(task["id"])
        self.assertEqual(stopped["status"], "blocked")
        self.assertEqual(stopped["stop_reason"], "no_progress")

    def test_operator_adoption_preserves_attempt_and_history_then_can_submit(self):
        from novel.dot_transport import OPERATIONS
        self.assertNotIn("adopt_running_task", [value[0] for value in OPERATIONS.values()])
        task = self.engine.claim(self.engine.enqueue("pilot", "write", "Existing source work")["id"])
        self.engine.block(task["id"], "no_progress", "Retained prior failure", expected_attempt=1)
        self.engine.resume(task["id"], "Real input issue resolved before migration")
        task = self.engine.claim(task["id"])
        before = self.engine.handoff(task["id"])
        args = dict(request_id="adopt-once", task_id=task["id"], expected_attempt=2,
                    expected_revision=task["input_revision"], context_ref="dot-writer",
                    supplemental_documents={"handoff/naming-before-draft.md": "Original unfinished naming notes"})
        with patch("subprocess.Popen", side_effect=AssertionError("No executor allowed")):
            receipt = self.dot.adopt_running_task(**args)
            self.assertTrue(receipt["task_record_unchanged"])
            self.assertEqual(self.engine.handoff(task["id"]), before)
            self.assertTrue(self.dot.adopt_running_task(**args)["replayed"])
            reopened = DotWorkspace(self.temp.name, "pilot")
            self.assertEqual(reopened.status()["tasks"][0]["attempts"], 2)
            self.assertEqual(reopened.status()["tasks"][0]["no_progress"], 1)
            self.assertEqual(reopened.read(task_id=task["id"], document="handoff/naming-before-draft.md")["text"],
                             "Original unfinished naming notes")
            self.assertNotIn("handoff/naming-before-draft.md", self.engine.files("pilot"))
            self.finish(task, self.result(task))
        self.assertEqual(self.engine.task(task["id"])["status"], "completed")
        self.assertEqual(self.engine.task(task["id"])["attempts"], 2)
        self.assertEqual(self.engine.task(task["id"])["no_progress"], 1)

    def test_operator_adoption_rejects_stale_stopped_and_foreign_tasks(self):
        task = self.engine.claim(self.engine.enqueue("pilot", "write", "Existing source work")["id"])
        args = dict(task_id=task["id"], expected_attempt=1, expected_revision=task["input_revision"], context_ref="dot-writer")
        for path in ("decisions/forged.md", "handoff/../canon/state.json"):
            with self.assertRaisesRegex(EngineError, "fixed handoff directory"):
                self.dot.adopt_running_task(request_id=self.request(), **args, supplemental_documents={path: "bad"})
        with self.assertRaisesRegex(EngineError, "exact running attempt"):
            self.dot.adopt_running_task(request_id=self.request(), **{**args, "expected_attempt": 2})
        with self.assertRaisesRegex(EngineError, "Stale"):
            self.dot.adopt_running_task(request_id=self.request(), **{**args, "expected_revision": "0" * 64})
        self.engine.block(task["id"], "tool_failure", "Keep stopped state")
        with self.assertRaisesRegex(EngineError, "exact running attempt"):
            self.dot.adopt_running_task(request_id=self.request(), **args)
        self.engine.create_book("other", "Other book")
        foreign = self.engine.claim(self.engine.enqueue("other", "write", "foreign")["id"])
        with self.assertRaisesRegex(EngineError, "another book"):
            self.dot.adopt_running_task(request_id=self.request(), **{**args, "task_id": foreign["id"]})
        self.assertEqual(self.dot.status()["tasks"], [])

    def test_formal_workspace_requires_pinned_operator_handoff_receipt(self):
        external = tempfile.TemporaryDirectory(prefix=".novel-dot-receipt-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(external.cleanup)
        receipt_path = Path(external.name) / "takeover.json"
        receipt = {"schema_version": 1, "workspace": "formal", "book_id": "pilot", "root": self.temp.name,
            "source_frozen": True, "pilot_accepted": True, "single_writer": "dot",
            "source_archive_sha256": "1" * 64, "source_revision": "2" * 64, "pilot_revision": "3" * 64}
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        entry = {"root": self.temp.name, "book_id": "pilot", "owner_id": "owner", "client_id": "novel-client",
            "phase": "formal", "enabled": True, "takeover_receipt": str(receipt_path),
            "takeover_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
        registry_path = Path(external.name) / "registry.json"
        config = {"schema_version": 1, "workspaces": {"formal": entry}}
        registry_path.write_text(json.dumps(config), encoding="utf-8")
        service = DotRegistry(registry_path)
        principal = {"owner_id": "owner", "client_id": "novel-client", "scope": SCOPE}
        args = {"workspace": "formal"}
        state = service.call(principal, "novel_work_status", args)
        self.assertEqual(state["phase"], "formal")
        self.assertEqual(state["takeover"]["source_revision"], "2" * 64)
        with self.assertRaisesRegex(PermissionError, "CLIENT_DENIED"):
            service.call({**principal, "client_id": "other"}, "novel_work_status", args)
        receipt["source_frozen"] = False
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "hash mismatch"):
            service.call(principal, "novel_work_status", args)
        entry["takeover_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        registry_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "does not authorize"):
            service.call(principal, "novel_work_status", args)


if __name__ == "__main__":
    unittest.main()
