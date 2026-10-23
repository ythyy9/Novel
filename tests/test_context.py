"""Engineering fixtures for bounded reading; never evidence of literary review."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import novel.context as context

from novel.context import (CHECKPOINT, RESULT, apply_delta, assemble_result, build_plan,
                           factor_state, restore_state)
from novel.dot import DotWorkspace
from novel.engine import Engine, EngineError, canonical, digest


class ContextTests(unittest.TestCase):
    def test_derived_cache_reuses_verified_plan_and_preserves_hashes(self):
        packet = self.packet()
        expected = build_plan(packet)
        with context._PLAN_CACHE_LOCK:
            context._PLAN_CACHE.clear()
        with patch.object(context, "build_plan", wraps=build_plan) as builds:
            plan, views = context.cached_plan(packet)
            plan["batches"].clear()
            for _ in range(10):
                current, current_views = context.cached_plan(deepcopy(packet))
                self.assertEqual(current, expected[0])
                self.assertEqual(dict(current_views), expected[1])
            self.assertEqual(builds.call_count, 1)
        with self.assertRaises(TypeError):
            views["context-guide.md"] = "corrupt"
        packet["documents"]["manuscript/001.md"] += "Changed"
        with self.assertRaisesRegex(EngineError, "hash"):
            context.cached_plan(packet)

    def test_cache_budget_evicts_without_changing_plan(self):
        with context._PLAN_CACHE_LOCK:
            context._PLAN_CACHE.clear()
        with patch.object(context, "_PLAN_CACHE_ITEMS", 1):
            first = self.packet()
            context.cached_plan(first)
            second = deepcopy(first)
            second["task"]["id"] = "second"
            self.assertEqual(context.cached_plan(second)[0], build_plan(second)[0])
            self.assertEqual(len(context._PLAN_CACHE), 1)
            self.assertEqual(context.cached_plan(first)[0], build_plan(first)[0])

    def packet(self, state=None):
        source = {"path": "manuscript/001.md", "quote": "The letter arrived."}
        record = {"id": "letter", "kind": "world_fact", "holder": None,
                  "statement": "The letter arrived.", "sources": [source, source]}
        state = state or {"knowledge": [record], "characters": [], "world": [], "offstage": []}
        documents = {"canon/state.json": json.dumps(state, indent=2),
                     "manuscript/001.md": "The letter arrived.\n" * 2000,
                     "decisions/001.md": "Keep Unknown.", "reference/empty.md": ""}
        return {"task": {"id": "test", "attempts": 1, "input_revision": "r", "control_hash": "c"},
                "context_ref": "fixture", "documents": documents,
                "sha256": {p: digest(v) for p, v in documents.items()}}

    def test_lossless_factorization_preserves_order_duplicates_and_all_fields(self):
        packet = self.packet()
        original = packet["documents"]["canon/state.json"]
        records, sources = factor_state(original)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(records[0]["record"]["sources"]), 2)
        self.assertEqual(restore_state(records, sources), json.loads(original))
        self.assertEqual(packet["documents"]["canon/state.json"], original)
        sources[0]["source"]["quote"] = "forged"
        with self.assertRaisesRegex(EngineError, "integrity"):
            restore_state(records, sources)

    def test_batches_cover_every_character_without_truncation_or_reordering(self):
        packet = self.packet()
        # Escaped controls expand JSON sixfold; ordinary text/chunk tests miss this.
        packet["documents"]["reference/escapes.md"] = "\x01" * 9000
        packet["sha256"]["reference/escapes.md"] = digest("\x01" * 9000)
        plan, views = build_plan(packet)
        self.assertEqual((plan, views), build_plan(deepcopy(packet)))
        restored = {}
        for batch in plan["batches"]:
            text = views[batch["document"]]
            self.assertLessEqual(len(text), 12000)
            self.assertEqual(digest(text), batch["sha256"])
            for fragment in json.loads(text)["fragments"]:
                path = fragment["document"]
                current = restored.get(path, "")
                self.assertEqual(len(current), fragment["start"])
                restored[path] = current + fragment["text"]
                self.assertEqual(len(restored[path]), fragment["end"])
        expected = {p: t for p, t in packet["documents"].items() if p != "canon/state.json"}
        expected.update({p: views[p] for p in ("context/state-records.jsonl", "context/state-sources.jsonl")})
        self.assertEqual(restored, expected)

    def test_packet_tampering_or_omitted_hash_rejected(self):
        packet = self.packet()
        packet["documents"]["manuscript/001.md"] += "changed"
        with self.assertRaisesRegex(EngineError, "hash"):
            build_plan(packet)
        packet = self.packet()
        packet["sha256"].pop("decisions/001.md")
        with self.assertRaisesRegex(EngineError, "hash"):
            build_plan(packet)

    def test_delta_cas_preserves_unedited_records_sources_and_noop_bytes(self):
        original = self.packet()["documents"]["canon/state.json"]
        delta = {"base_sha256": digest(original), "operations": []}
        self.assertEqual(apply_delta(original, delta), original)
        record = json.loads(original)["knowledge"][0]
        operation = {"section": "knowledge", "id": "letter", "before_sha256": digest(canonical(record)),
                     "set": {"statement": "The recipient read it."},
                     "append_sources": [{"path": "manuscript/002.md", "quote": "She read it."}]}
        delta["operations"] = [operation]
        result = json.loads(apply_delta(original, delta))
        self.assertEqual(result["knowledge"][0]["sources"][:2], record["sources"])
        self.assertEqual(result["knowledge"][0]["kind"], "world_fact")
        for bad in [dict(operation, before_sha256="stale"), dict(operation, set={"id": "new"})]:
            with self.assertRaises(EngineError):
                apply_delta(original, {**delta, "operations": [bad]})
        with self.assertRaisesRegex(EngineError, "Duplicate"):
            apply_delta(original, {**delta, "operations": [operation, operation]})
        with self.assertRaisesRegex(EngineError, "base"):
            apply_delta(original, {**delta, "base_sha256": "stale"})


class StagedDotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-context-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine.initialize(self.temp.name)
        self.engine.create_book("fixture", "Engineering only")
        self.dot = DotWorkspace(self.temp.name, "fixture")
        self.sequence = 0

    def request(self):
        self.sequence += 1
        return "context-" + str(self.sequence)

    def open(self, kind="write"):
        return self.dot.open_task(request_id=self.request(), kind=kind, instruction="Synthetic context fixture",
            expected_revision=self.engine.book("fixture")["current_revision"], context_ref=kind)["task"]

    def read_all(self, task, document):
        output, offset = "", 0
        while offset is not None:
            part = self.dot.read(task_id=task["id"], document=document, offset=offset)
            output += part["text"]
            offset = part["next_offset"]
        return output

    def send(self, task, payload):
        raw = canonical(payload)
        parts = [raw[i:i+6000] for i in range(0, len(raw), 6000)]
        upload = self.request()
        for part, content in enumerate(parts):
            self.dot.chunk(request_id=self.request(), task_id=task["id"], attempt=task["attempts"],
                           upload_id=upload, part=part, total=len(parts), content=content)
        return self.dot.finish(request_id=self.request(), task_id=task["id"], attempt=task["attempts"], upload_id=upload)

    def checkpoint(self, task, plan, batch, *, deliver=True, issue=False):
        packet = self.dot._packet(task)
        _, views = build_plan(packet)
        if deliver:
            self.read_all(task, batch["document"])
        fragment = next(f for f in json.loads(views[batch["document"]])["fragments"] if f["text"].strip())
        review = None
        if task["kind"] == "review":
            paths = [p for p in packet["documents"] if p.startswith(("canon/", "manuscript/"))]
            review = {"coverage": paths, "dimensions": ["continuity", "character", "world", "reading"], "findings": []}
            if issue:
                review["findings"] = [{"id": "real-fixture-error", "category": "error", "confirmed": True,
                    "severity": "minor", "status": "open", "path": "manuscript/001.md", "quote": "A letter arrived.",
                    "explanation": "Synthetic required recipient is absent.", "suggestion": "Identify recipient.",
                    "affected_paths": ["manuscript/001.md"]}]
        return {"format": CHECKPOINT, "task_id": task["id"], "attempt": task["attempts"],
                "plan_sha256": plan["plan_sha256"], "batch_id": batch["id"], "context_ref": "native-fixture-" + batch["id"],
                "notes": "Engineering fixture only; not a model reading claim.",
                "evidence": [{"document": fragment["document"], "quote": fragment["text"][:40]}],
                "unresolved": ["Synthetic unresolved concern"] if issue else [], "review": review}

    def result(self, task, plan):
        result = {"task_id": task["id"], "input_revision": task["input_revision"], "completed_steps": ["Fixture"],
                  "next_step": "Independent review", "unresolved": [], "changes": [], "review": None,
                  "affected_paths": ["manuscript/001.md"], "state_notes": "Fixture state change"}
        delta = None
        if task["kind"] == "review":
            result["review"] = {"coverage": ["manuscript/001.md"],
                "dimensions": ["continuity", "character", "world", "reading"], "findings": []}
        else:
            result["changes"] = [{"path": "manuscript/001.md", "content": "A letter arrived."}]
            delta = {"base_sha256": plan["state_sha256"], "operations": [
                {"section": "knowledge", "id": "arrived", "before_sha256": None,
                 "set": {"kind": "world_fact", "holder": None, "statement": "A letter arrived."},
                 "append_sources": [{"path": "manuscript/001.md", "quote": "A letter arrived."}]}]}
        return {"format": RESULT, "task_id": task["id"], "attempt": task["attempts"],
                "plan_sha256": plan["plan_sha256"], "result": result, "state_delta": delta}

    def test_partial_reads_missing_batches_and_legacy_bypass_fail_closed(self):
        task = self.open()
        plan = json.loads(self.read_all(task, "context-plan.json"))
        batch = plan["batches"][0]
        checkpoint = self.checkpoint(task, plan, batch, deliver=False)
        with self.assertRaisesRegex(EngineError, "not all been delivered"):
            self.send(task, checkpoint)
        # Deliver only the last page: no skipped prefix can count as complete.
        self.dot.read(task_id=task["id"], document=batch["document"], offset=batch["characters"] - 1)
        with self.assertRaisesRegex(EngineError, "not all been delivered"):
            self.send(task, checkpoint)
        self.read_all(task, batch["document"])
        self.send(task, checkpoint)
        with self.assertRaisesRegex(EngineError, "Staged reading started"):
            self.send(task, self.result(task, plan)["result"])
        if len(plan["batches"]) > 1:
            with self.assertRaisesRegex(EngineError, "incomplete"):
                self.send(task, self.result(task, plan))
        self.assertEqual(self.engine.task(task["id"]), {**task, "result": None})

    def test_checkpoint_restart_hash_quote_and_attempt_binding(self):
        task = self.open()
        plan = json.loads(self.read_all(task, "context-plan.json"))
        payload = self.checkpoint(task, plan, plan["batches"][0])
        for bad in [dict(payload, plan_sha256="stale"), dict(payload, attempt=2),
                    dict(payload, evidence=[{"document": "canon/state.json", "quote": "invented"}])]:
            with self.assertRaises(EngineError):
                self.send(task, bad)
        receipt = self.send(task, payload)
        self.assertFalse(receipt["submitted"])
        self.dot = DotWorkspace(self.temp.name, "fixture")
        progress = json.loads(self.read_all(task, "context-progress.json"))
        self.assertIn(payload["batch_id"], progress["completed_batches"])
        saved = json.loads(self.read_all(task, progress["checkpoints"][0]["document"]))
        self.assertEqual(saved, payload)
        self.assertEqual(self.engine.task(task["id"]), {**task, "result": None})

    def test_delta_full_validation_and_review_findings_survive_empty_final_opinion(self):
        task = self.open()
        packet_before = (self.dot.base / "packets" / (task["id"] + ".json")).read_bytes()
        plan = json.loads(self.read_all(task, "context-plan.json"))
        for batch in plan["batches"]:
            self.send(task, self.checkpoint(task, plan, batch))
        payload = self.result(task, plan)
        bad = deepcopy(payload)
        bad["state_delta"]["operations"][0]["append_sources"][0]["quote"] = "Fabrication"
        with self.assertRaises(ValueError):
            self.send(task, bad)
        receipt = self.send(task, payload)
        self.assertEqual(receipt["task"]["status"], "submitted")
        complete = json.loads(self.read_all(task, "result.json"))
        self.assertEqual(len(json.loads(complete["changes"][-1]["content"])["knowledge"]), 1)
        self.dot.publish(request_id=self.request(), task_id=task["id"], expected_revision=task["input_revision"])
        self.assertEqual((self.dot.base / "packets" / (task["id"] + ".json")).read_bytes(), packet_before)
        review = self.open("review")
        plan = json.loads(self.read_all(review, "context-plan.json"))
        for i, batch in enumerate(plan["batches"]):
            checkpoint = self.checkpoint(review, plan, batch, issue=i == 0)
            if i == 0:
                with self.assertRaisesRegex(EngineError, "different context"):
                    self.send(review, checkpoint)
            checkpoint["context_ref"] = "independent-review-" + batch["id"]
            self.send(review, checkpoint)
        self.send(review, self.result(review, plan))
        result = json.loads(self.read_all(review, "result.json"))
        self.assertEqual(len(result["review"]["findings"]), 1)
        self.assertIn("Synthetic unresolved concern", result["unresolved"])
        self.dot.publish(request_id=self.request(), task_id=review["id"], expected_revision=review["input_revision"])
        self.assertFalse(self.engine.assessment("fixture")["can_accept"])
        with self.assertRaisesRegex(EngineError, "Cannot accept"):
            self.dot.accept(request_id=self.request(), expected_revision=review["input_revision"])
        self.assertEqual(self.engine.audit()["database"], "ok")


if __name__ == "__main__":
    unittest.main()
