"""Real persisted comparisons; supplied text is fixture data, never model proof."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from novel import evaluation
from novel.engine import EngineError, checked_path


def spec():
    return {"id": "method-01", "hypothesis": "人物关注点提示能改善声音区分。",
            "baseline_method": "现行方法 v1", "candidate_method": "候选方法 v2",
            "cases": [
                {"id": "dev", "split": "development", "input": "开发案例输入原文",
                 "baseline_output": "开发基准正文", "candidate_output": "开发候选正文"},
                {"id": "held", "split": "holdout", "input": "未用于修改方法的案例输入",
                 "baseline_output": "留出基准正文", "candidate_output": "留出候选正文"},
            ]}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-evaluation-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = spec()
        self.experiment_id = self.data["id"]

    def create(self):
        return evaluation.create(self.root, self.data)

    def choice(self, case_id, method="candidate"):
        source = next(case for case in self.data["cases"] if case["id"] == case_id)
        case = next(case for case in evaluation.blind(self.root, self.experiment_id)["cases"] if case["id"] == case_id)
        return next(label for label in ("A", "B") if case[label] == source[f"{method}_output"])

    def judge(self, case_id, method="candidate", reviewer="author"):
        return evaluation.judge(self.root, self.experiment_id, case_id, self.choice(case_id, method), "原话：这个版本更清楚。", reviewer)

    def test_create_and_blind_keep_order_stable_without_method_labels(self):
        created = self.create()
        self.assertEqual(created["case_count"], 2)
        first = evaluation.blind(self.root, self.experiment_id)
        self.assertEqual(first, evaluation.blind(self.root, self.experiment_id))
        self.assertEqual(set(first), {"hypothesis", "cases"})
        for case, source in zip(first["cases"], self.data["cases"]):
            self.assertEqual(set(case), {"id", "split", "input", "A", "B"})
            self.assertEqual({case["A"], case["B"]}, {source["baseline_output"], source["candidate_output"]})

    def test_duplicate_creation_cannot_replace_manifest(self):
        self.create()
        path = self.root / "evaluations/experiments/method-01/manifest.json"
        original = path.read_bytes()
        self.data["hypothesis"] = "试图替换原假说"
        with self.assertRaises(EngineError):
            self.create()
        self.assertEqual(path.read_bytes(), original)

    def test_requires_both_splits_valid_unique_ids_and_nonempty_evidence(self):
        invalid = []
        for field in ("hypothesis", "baseline_method", "candidate_method"):
            value = spec()
            value[field] = " "
            invalid.append(value)
        value = spec()
        value["cases"] = value["cases"][:1]
        invalid.append(value)
        value = spec()
        value["cases"][1]["id"] = "dev"
        invalid.append(value)
        value = spec()
        value["cases"][1]["candidate_output"] = ""
        invalid.append(value)
        value = spec()
        value["id"] = "../escape"
        invalid.append(value)
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(EngineError):
                    evaluation.create(self.root, value)
        self.assertFalse((self.root / "evaluations").exists())

    def test_judgments_append_verbatim_and_prior_record_stays_unchanged(self):
        self.create()
        first = evaluation.judge(self.root, self.experiment_id, "dev", "tie", "  原话：各有长短。\n保留换行。  ", "target_reader")
        path = self.root / f"evaluations/experiments/method-01/judgments/{first['id']}.json"
        original = path.read_bytes()
        second = evaluation.judge(self.root, self.experiment_id, "dev", "inconclusive", "资料不足", "agent")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["rationale"], "  原话：各有长短。\n保留换行。  ")
        self.assertEqual(path.read_bytes(), original)
        summary = evaluation.summarize(self.root, self.experiment_id)
        counts = summary["groups"]["development"]["counts_by_reviewer"]
        self.assertEqual(counts["target_reader"]["tie"], 1)
        self.assertEqual(counts["agent"]["inconclusive"], 1)

    def test_invalid_feedback_sources_and_cases_rejected(self):
        self.create()
        for case, choice, rationale, reviewer in [("missing", "A", "依据", "author"), ("dev", "winner", "依据", "author"),
                                                 ("dev", "A", "", "author"), ("dev", "A", "依据", "human")]:
            with self.assertRaises(EngineError):
                evaluation.judge(self.root, self.experiment_id, case, choice, rationale, reviewer)

    def test_agent_feedback_alone_cannot_qualify_for_retention(self):
        self.create()
        self.judge("dev", reviewer="agent")
        self.judge("held", reviewer="agent")
        summary = evaluation.summarize(self.root, self.experiment_id)
        self.assertFalse(summary["retain_eligible"])
        self.assertIn("not human feedback", summary["evidence_note"])
        with self.assertRaises(EngineError):
            evaluation.decide(self.root, self.experiment_id, "retain", "模型自评说改进")

    def test_retention_requires_feedback_on_all_cases(self):
        self.create()
        self.judge("held")
        with self.assertRaises(EngineError):
            evaluation.decide(self.root, self.experiment_id, "retain", "还未评开发案例")
        self.judge("dev", reviewer="agent")
        decision = evaluation.decide(self.root, self.experiment_id, "retain", "作者认为留出案例更清晰，保留方法")
        self.assertEqual(decision["action"], "retain")
        self.assertEqual(len(decision["judgment_ids"]), 2)

    def test_holdout_loss_prevents_retention_even_with_another_win(self):
        self.create()
        self.judge("dev")
        self.judge("held")
        self.judge("held", method="baseline", reviewer="target_reader")
        summary = evaluation.summarize(self.root, self.experiment_id)
        self.assertFalse(summary["retain_eligible"])
        self.assertTrue(any("candidate loss" in item for item in summary["retain_blockers"]))
        with self.assertRaises(EngineError):
            evaluation.decide(self.root, self.experiment_id, "retain", "不能丢弃反例")

    def test_human_tie_plus_agent_win_does_not_become_human_win(self):
        self.create()
        self.judge("dev")
        self.judge("held", reviewer="agent")
        evaluation.judge(self.root, self.experiment_id, "held", "tie", "没有明确改善", "author")
        self.assertFalse(evaluation.summarize(self.root, self.experiment_id)["retain_eligible"])

    def test_every_holdout_needs_recorded_human_feedback(self):
        extra = copy.deepcopy(self.data["cases"][1])
        extra["id"] = "held-two"
        self.data["cases"].append(extra)
        self.create()
        self.judge("dev")
        self.judge("held")
        self.judge("held-two", reviewer="agent")
        self.assertFalse(evaluation.summarize(self.root, self.experiment_id)["retain_eligible"])

    def test_trial_and_rollback_append_without_mutating_methods(self):
        for folder in ("methods", "policies"):
            (self.root / folder).mkdir()
            (self.root / folder / "original.txt").write_text("immutable original", encoding="utf-8")
        self.create()
        first = evaluation.decide(self.root, self.experiment_id, "trial", "等待作者反馈，暂用")
        second = evaluation.decide(self.root, self.experiment_id, "rollback", "证据不足，回滚")
        summary = evaluation.summarize(self.root, self.experiment_id)
        self.assertEqual([item["id"] for item in summary["decisions"]], [first["id"], second["id"]])
        self.assertEqual(summary["latest_decision"]["action"], "rollback")
        for folder in ("methods", "policies"):
            self.assertEqual((self.root / folder / "original.txt").read_text(encoding="utf-8"), "immutable original")
        with self.assertRaises(EngineError):
            evaluation.decide(self.root, self.experiment_id, "trial", "")

    def test_later_negative_feedback_does_not_rewrite_prior_decision_evidence(self):
        self.create()
        self.judge("dev")
        self.judge("held")
        decision = evaluation.decide(self.root, self.experiment_id, "retain", "根据目前原话保留")
        negative = self.judge("held", method="baseline")
        summary = evaluation.summarize(self.root, self.experiment_id)
        self.assertFalse(summary["retain_eligible"])
        self.assertNotIn(negative["id"], summary["latest_decision"]["judgment_ids"])
        self.assertEqual(summary["latest_decision"], decision)

    def test_manifest_mapping_is_covered_by_integrity_hash(self):
        self.create()
        path = self.root / "evaluations/experiments/method-01/manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping = data["record"]["cases"][0]["mapping"]
        mapping["A"], mapping["B"] = mapping["B"], mapping["A"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(EngineError):
            evaluation.blind(self.root, self.experiment_id)

    def test_modified_feedback_is_detected(self):
        self.create()
        feedback = self.judge("dev")
        path = self.root / f"evaluations/experiments/method-01/judgments/{feedback['id']}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["record"]["reviewer"] = "target_reader"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(EngineError):
            evaluation.summarize(self.root, self.experiment_id)

    def test_concurrent_judgments_all_survive(self):
        self.create()
        def append(index):
            return evaluation.judge(self.root, self.experiment_id, "dev", "tie", f"独立评语 {index}", "agent")
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(append, range(8)))
        self.assertEqual(len({record["id"] for record in records}), 8)
        counts = evaluation.summarize(self.root, self.experiment_id)["groups"]["development"]["counts_by_reviewer"]
        self.assertEqual(counts["agent"]["tie"], 8)

    @unittest.skipUnless(os.name == "nt", "Windows realpath race regression")
    def test_real_directory_creation_during_windows_path_resolution(self):
        import ntpath

        # Instrument only scheduling: every result/error still comes from the
        # real Windows API. A worker creates a real ordinary directory between
        # the initial ERROR_PATH_NOT_FOUND and the next final-path lookup.
        original = ntpath._getfinalpathname
        target = self.root / "new-parent" / "entry.json"
        start, created = Event(), Event()
        errors, worker_errors = [], []

        def make_parent():
            if not start.wait(5):
                return
            try:
                target.parent.mkdir()
            except BaseException as exc:
                worker_errors.append(exc)
            finally:
                created.set()

        def observe(path):
            try:
                return original(path)
            except OSError as exc:
                if str(path) == str(target):
                    errors.append(exc.winerror)
                    if not start.is_set():
                        start.set()
                        if not created.wait(5):
                            raise AssertionError("Directory creation worker did not finish")
                raise

        worker = Thread(target=make_parent)
        worker.start()
        ntpath._getfinalpathname = observe
        try:
            self.assertEqual(checked_path(self.root, "new-parent/entry.json"), target)
        finally:
            ntpath._getfinalpathname = original
            start.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(worker_errors)
        self.assertIn(3, errors)
        self.assertIn(2, errors)
        self.assertFalse(target.parent.lstat().st_file_attributes & 0x400)

    def test_checked_path_still_rejects_lexical_escapes(self):
        for relative in ("../escape", "a/../../escape", "/absolute", "a//b", "a/./b", "C:/escape", "a\\b"):
            with self.subTest(relative=relative):
                with self.assertRaises(EngineError):
                    checked_path(self.root, relative)

    @unittest.skipUnless(os.name == "nt", "Windows junction rejection")
    def test_checked_path_still_rejects_real_windows_junction(self):
        import _winapi

        outside = self.root / "outside"
        outside.mkdir()
        junction = self.root / "linked"
        # Create one real bounded junction. Cleanup removes the link itself
        # with rmdir, never recursively traversing its target.
        try:
            _winapi.CreateJunction(str(outside), str(junction))
        except PermissionError:
            self.skipTest("Host does not permit creating a test junction")
        try:
            self.assertTrue(junction.lstat().st_file_attributes & 0x400)
            with self.assertRaises(EngineError):
                checked_path(self.root, "linked/entry.json")
            with self.assertRaises(EngineError):
                checked_path(junction, "entry.json")
        finally:
            junction.rmdir()


if __name__ == "__main__":
    unittest.main()
