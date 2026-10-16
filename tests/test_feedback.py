"""Synthetic diagnostic history; no author feedback or model causality evidence."""
import copy
import json
import shutil
from pathlib import Path
import tempfile
import unittest

from novel import evaluation, feedback
from novel.engine import Engine, EngineError
from test_evaluation import spec as experiment_spec


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix=".novel-feedback-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.engine = Engine.initialize(temp.name)
        self.engine.create_book("fixture", "合成案例")
        self.engine.reference("fixture", "合成原文：他忽然理解了所有人的想法。")
        self.revision = self.engine.book("fixture")["current_revision"]
        self.path = next(p for p in self.engine.files("fixture") if p.startswith("reference/"))
        self.original = self.engine.feedback("fixture", "  为什么他能知道别人的想法？\n", "author")
        self.spec = {"evidence": [{"revision": self.revision, "path": self.path,
                                  "quote": "他忽然理解了所有人的想法。"}],
                     "hypothesis": "可能未区分人物可知范围；不能据文本断定模型内部原因。",
                     "prevention": "候选：写作前列出可见线索，保持合理推断的可能性。",
                     "scope": "仅此合成案例，不推广为禁止人物推断。",
                     "validation_plan": "开发案例与未参与修改的留出案例比较；检查误报和退步。",
                     "actual_result": None, "experiment_id": None}

    def test_append_preserves_original_history_and_controls(self):
        controls = self.engine._controls()
        first = feedback.append(self.engine, self.original["id"], self.spec)
        self.engine.decision("fixture", "合成的后续版本")
        second_spec = copy.deepcopy(self.spec)
        second_spec["actual_result"] = "手动检查：当前句已变更；其他案例未验证，不能认定预防有效。"
        second = feedback.append(self.engine, self.original["id"], second_spec)
        history = feedback.show(Engine(self.engine.root), self.original["id"])
        self.assertEqual(history["feedback"]["text"], "  为什么他能知道别人的想法？\n")
        self.assertEqual(history["feedback"]["revision"], self.revision)
        self.assertEqual(history["diagnoses"], [first, second])
        self.assertIsNone(first["spec"]["actual_result"])
        self.assertEqual(self.engine._controls(), controls)
        self.assertNotIn("resolved", history)
        backup = self.engine.root / "backup"
        shutil.copytree(self.engine.root / "runtime", backup / "runtime")
        shutil.copytree(self.engine.root / "books", backup / "books")
        shutil.copytree(self.engine.root / "policies", backup / "policies")
        shutil.copytree(self.engine.root / "methods", backup / "methods")
        self.assertEqual(feedback.show(Engine(backup), self.original["id"]), history)

    def test_historical_feedback_and_foreign_revision(self):
        self.engine.decision("fixture", "后续版本")
        old = self.engine.feedback("fixture", "迟到的原话", revision=self.revision)
        self.assertEqual(feedback.show(self.engine, old["id"])["feedback"]["revision"], self.revision)
        other = self.engine.create_book("other", "其他作品")
        with self.assertRaises(EngineError):
            self.engine.feedback("fixture", "错误关联", revision=other["current_revision"])
        bad = copy.deepcopy(self.spec)
        bad["evidence"][0]["revision"] = other["current_revision"]
        with self.assertRaises(EngineError):
            feedback.append(self.engine, old["id"], bad)

    def test_rejects_absent_quotes_missing_fields_and_empty_results(self):
        invalid = []
        for field, value in (("path", "manuscript/missing.md"), ("quote", "不存在的证据"), ("revision", "missing")):
            bad = copy.deepcopy(self.spec)
            bad["evidence"][0][field] = value
            invalid.append(bad)
        bad = copy.deepcopy(self.spec)
        del bad["hypothesis"]
        invalid.append(bad)
        bad = copy.deepcopy(self.spec)
        bad["actual_result"] = " "
        invalid.append(bad)
        for bad in invalid:
            with self.subTest(spec=bad), self.assertRaises(EngineError):
                feedback.append(self.engine, self.original["id"], bad)
        self.assertEqual(feedback.show(self.engine, self.original["id"])["diagnoses"], [])
        self.spec["evidence"] = []
        self.spec["scope"] = "原文缺失；没有可验证的文本观察，原因未知。"
        feedback.append(self.engine, self.original["id"], self.spec)

    def test_experiment_snapshot_does_not_promote_agent_judgments(self):
        data = experiment_spec()
        evaluation.create(self.engine.root, data)
        self.spec["experiment_id"] = data["id"]
        first = feedback.append(self.engine, self.original["id"], self.spec)
        for case in evaluation.blind(self.engine.root, data["id"])["cases"]:
            evaluation.judge(self.engine.root, data["id"], case["id"], "tie", "合成回归：无明确改善", "agent")
        second = feedback.append(self.engine, self.original["id"], self.spec)
        self.assertFalse(second["experiment"]["summary_at_recording"]["retain_eligible"])
        self.assertNotEqual(first["experiment"], second["experiment"])
        self.assertEqual(feedback.show(self.engine, self.original["id"])["diagnoses"][0], first)
        with self.assertRaises(EngineError):
            evaluation.decide(self.engine.root, data["id"], "retain", "不能仅由Agent升级规则")

    def test_tampering_and_cross_feedback_copy_rejected(self):
        note = feedback.append(self.engine, self.original["id"], self.spec)
        path = self.engine.root / f"runtime/feedback/{self.original['id']}/{note['id']}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["record"]["spec"]["hypothesis"] = "伪造确定原因"
        path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(EngineError):
            feedback.show(self.engine, self.original["id"])
        path.unlink()
        another = self.engine.feedback("fixture", "另一条意见")
        target = self.engine.root / f"runtime/feedback/{another['id']}/{note['id']}.json"
        evaluation._write(target, note)
        with self.assertRaises(EngineError):
            feedback.show(self.engine, another["id"])
