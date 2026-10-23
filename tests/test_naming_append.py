"""Synthetic recovery tests; no production data, model, network or task access."""
from copy import deepcopy
from contextlib import ExitStack
import json
import unittest
from unittest.mock import patch

from novel import naming_append as recovery
from novel.engine import EngineError, canonical, digest
from novel.records import ValidationError, validate_result
import test_context


class NamingAppendTests(unittest.TestCase):
    def setUp(self):
        self.h = test_context.StagedDotTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.engine, self.dot = self.h.engine, self.h.dot
        seed = self.h.open()
        initial = {"task_id": seed["id"], "input_revision": seed["input_revision"],
                   "completed_steps": ["fixture"], "next_step": "fixture",
                   "unresolved": [], "review": None, "state_notes": "fixture",
                   "changes": [{"path": "manuscript/001.md", "content": "Synthetic fixture."},
                               {"path": "canon/state.json", "content": self.engine.files("fixture")["canon/state.json"]}],
                   "affected_paths": ["manuscript/001.md"]}
        self.h.send(seed, initial)
        self.dot.publish(request_id=self.h.request(), task_id=seed["id"], expected_revision=seed["input_revision"])
        self.task = self.h.open("revise")
        self.plan = json.loads(self.h.read_all(self.task, "context-plan.json"))
        for batch in self.plan["batches"]:
            self.h.send(self.task, self.h.checkpoint(self.task, self.plan, batch, issue=True))
        self.payload = self.h.result(self.task, self.plan)
        self.payload["state_delta"] = None
        self.payload["result"]["changes"] = [{"path": recovery.PATH, "content": "Synthetic naming evidence; original motivation Unknown.\n"}]
        self.payload["result"]["affected_paths"] = [recovery.PATH]
        self.files = self.engine.files("fixture")

    def bound(self):
        stack = ExitStack()
        for key, value in {"TASK_ID": self.task["id"], "BOOK_ID": "fixture",
                           "INPUT_REVISION": self.task["input_revision"],
                           "CONTROL_HASH": self.task["control_hash"],
                           "CONTENT_SHA256": digest(self.payload["result"]["changes"][0]["content"])}.items():
            stack.enter_context(patch.object(recovery, key, value))
        return stack

    def snapshot_dot(self, table):
        with self.dot._db() as db:
            return [tuple(row) for row in db.execute("SELECT * FROM " + table)]

    def test_old_error_preserved_same_attempt_upload_checkpoints_publish_review_gate(self):
        raw = canonical(self.payload)
        for i, content in enumerate((raw[:len(raw)//2], raw[len(raw)//2:])):
            self.dot.chunk(request_id=self.h.request(), task_id=self.task["id"], attempt=1,
                           upload_id="retained-upload", part=i, total=2, content=content)
        args = dict(task_id=self.task["id"], attempt=1, upload_id="retained-upload")
        with self.assertRaisesRegex(ValidationError, "must change manuscript"):
            self.dot.finish(request_id="old-error", **args)
        before_parts = self.snapshot_dot("parts")
        before_checkpoints = self.snapshot_dot("context_checkpoints")
        before_requests = self.snapshot_dot("requests")
        with self.bound():
            with self.assertRaisesRegex(EngineError, "must change manuscript"):
                self.dot.finish(request_id="old-error", **args)
            receipt = self.dot.finish(request_id="new-finish", **args)
            self.assertFalse(receipt["published"])
            self.assertEqual(self.engine.files("fixture"), self.files)
            self.assertTrue(self.dot.finish(request_id="new-finish", **args)["replayed"])
            saved = self.engine.task(self.task["id"])
            self.assertEqual(saved["attempts"], 1)
            self.assertEqual(saved["no_progress"], 0)
            self.assertIn("Synthetic unresolved concern", saved["result"]["unresolved"])
            virtual = json.loads(self.h.read_all(self.task, "result.json"))
            self.assertEqual(virtual, saved["result"])
            published = self.dot.publish(request_id="publish-fixture", task_id=self.task["id"], expected_revision=self.task["input_revision"])
            self.assertFalse(published["assessment"]["can_accept"])
            self.assertIn("No independent review of this revision", published["assessment"]["blockers"])
            with self.assertRaisesRegex(EngineError, "Cannot accept"):
                self.dot.accept(request_id="accept-fixture", expected_revision=published["book"]["current_revision"])
        self.assertEqual(self.snapshot_dot("parts"), before_parts)
        self.assertEqual(self.snapshot_dot("context_checkpoints"), before_checkpoints)
        for row in before_requests:
            self.assertIn(row, self.snapshot_dot("requests"))
        final = self.engine.files("fixture")
        self.assertEqual({p: final[p] for p in self.files}, self.files)
        self.assertEqual(set(final) - set(self.files), {recovery.PATH})

    def test_scope_and_content_cannot_be_self_declared_or_extended(self):
        with self.bound():
            validate_result(self.payload["result"], self.task, self.files)
            for field, value in (("id", "other"), ("book_id", "other"), ("attempts", 2),
                                 ("attempts", True), ("kind", "write"),
                                 ("control_hash", "other"), ("input_revision", "other")):
                task = {**self.task, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    validate_result(self.payload["result"], task, self.files)
            for path in ("revisions/other.md", "../escape.md", "decisions/new.md", "policies/limits.json"):
                result = deepcopy(self.payload["result"])
                result["changes"][0]["path"] = path
                result["affected_paths"] = [path]
                with self.subTest(path=path), self.assertRaises(ValidationError):
                    validate_result(result, self.task, self.files)
            for extra in ("manuscript/001.md", "canon/state.json", "decisions/new.md"):
                result = deepcopy(self.payload["result"])
                result["changes"].append({"path": extra, "content": self.files.get(extra, "fixture")})
                with self.subTest(extra=extra), self.assertRaises(ValidationError):
                    validate_result(result, self.task, self.files)
            for content in ("changed", self.payload["result"]["changes"][0]["content"] + " "):
                result = deepcopy(self.payload["result"])
                result["changes"][0]["content"] = content
                with self.assertRaisesRegex(ValidationError, "bytes changed"):
                    validate_result(result, self.task, self.files)
            for path in (recovery.PATH, recovery.PATH.upper()):
                with self.assertRaisesRegex(ValidationError, "already exists"):
                    validate_result(self.payload["result"], self.task, {**self.files, path: "history"})

    def test_missing_pin_fails_closed_and_publish_revalidates(self):
        with self.bound():
            with patch.object(recovery, "CONTENT_SHA256", None):
                with self.assertRaisesRegex(ValidationError, "not verified"):
                    self.h.send(self.task, self.payload)
            self.h.send(self.task, self.payload)
            with patch.object(recovery, "CONTENT_SHA256", "0" * 64):
                with self.assertRaisesRegex(ValidationError, "bytes changed"):
                    self.engine.publish(self.task["id"])
            self.assertEqual(self.engine.files("fixture"), self.files)

    def test_context_identity_coverage_delta_and_pending_remain_guarded(self):
        from novel.context import assemble_result
        packet = self.dot._packet(self.task)
        checkpoints = self.dot._checkpoints(self.task, self.plan)
        with self.bound():
            for field, value in (("attempt", 2), ("plan_sha256", "wrong"), ("task_id", "wrong")):
                with self.subTest(field=field), self.assertRaises(EngineError):
                    assemble_result({**self.payload, field: value}, self.task, packet, self.plan, checkpoints)
            with self.assertRaisesRegex(EngineError, "incomplete"):
                assemble_result(self.payload, self.task, packet, self.plan, [])
            delta = {"base_sha256": self.plan["state_sha256"], "operations": []}
            with self.assertRaisesRegex(ValidationError, "only the authorized"):
                assemble_result({**self.payload, "state_delta": delta}, self.task, packet, self.plan, checkpoints)
            args = dict(task_id=self.task["id"], attempt=1, upload_id="unknown")
            signature = digest(canonical(["finish", args]))
            with self.dot._db() as db:
                db.execute("INSERT INTO requests VALUES (?,?,'pending',NULL,?)", ("pending-fixture", signature, "fixture"))
            with self.assertRaisesRegex(EngineError, "Uncertain prior operation"):
                self.dot.finish(request_id="pending-fixture", **args)
            self.assertEqual(self.engine.task(self.task["id"])["status"], "running")
