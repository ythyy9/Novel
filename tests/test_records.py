"""Semantic protocol checks, including malformed and provenance-breaking input."""

import copy
import json
from pathlib import Path
import unittest

from novel.records import ValidationError, validate_path, validate_result, validate_state


def state():
    return {"knowledge": [], "characters": [], "world": [], "offstage": []}


def knowledge(kind="world_fact", path="manuscript/01.md", quote="城门已关闭。"):
    return {"id": "gate", "kind": kind, "statement": "城门关闭", "holder": None,
            "sources": [{"path": path, "quote": quote}]}


def task(kind="write"):
    return {"id": "task-1", "input_revision": "rev-1", "kind": kind}


def result():
    return {"task_id": "task-1", "input_revision": "rev-1",
            "completed_steps": ["写作"], "next_step": "审核", "unresolved": [],
            "changes": [{"path": "manuscript/01.md", "content": "城门已关闭。"},
                        {"path": "canon/state.json", "content": json.dumps(state())}],
            "review": None, "affected_paths": ["manuscript/01.md"],
            "state_notes": "本章没有新增人物所知；保持原状态。"}


def research():
    return {"question": "条件不足时能否确定运输成本？", "sources": [],
            "conclusion": "目前未知", "conditions": ["缺少路线与载重"],
            "uncertainties": ["没有足够资料"], "affected_paths": ["manuscript/01.md"],
            "claims": [{"kind": "inference", "text": "现有证据不足。", "source_indexes": []}]}


def research_result(data=None):
    value = result()
    value["changes"] = [{"path": "research/transport.json", "content": json.dumps(data or research())}]
    value["state_notes"] = ""
    return value


def review_result():
    value = result()
    value["changes"] = []
    value["state_notes"] = ""
    value["review"] = {"coverage": ["manuscript/01.md"],
                       "dimensions": ["continuity", "character", "world", "reading"],
                       "findings": []}
    return value


def finding():
    return {"id": "F1", "category": "concern", "confirmed": False,
            "severity": "major", "path": "manuscript/01.md", "quote": "城门已关闭。",
            "explanation": "缺少关闭时间的依据。", "suggestion": "核查上一章。",
            "affected_paths": ["manuscript/01.md"], "status": "open"}


class PathTests(unittest.TestCase):
    def test_valid_relative_paths(self):
        for path in ["manuscript/第 01 章.md", "research/transport.json", "canon/人物/阿甲.json"]:
            with self.subTest(path=path):
                self.assertEqual(validate_path(path), path)

    def test_rejects_traversal_absolute_and_windows_aliases(self):
        for path in ["../canon/a.json", "/manuscript/a.md", "C:/manuscript/a.md",
                     "manuscript\\a.md", "manuscript//a.md", "manuscript/./a.md",
                     "manuscript/../a.md", "manuscript/.hidden.md", "manuscript/a.md.",
                     "manuscript/a.md ", "manuscript/CON.md", "manuscript/com1.json",
                     "manuscript/LPT¹.md", "manuscript/a:b.md", "manuscript/a?.md",
                     "manuscript/a\n.md", "runtime/state.json", "canon/a.py", "canon/a.JSON",
                     "manuscript/e\u0301.md", "manuscript/\ud800.md", "manuscript"]:
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    validate_path(path)

    def test_path_types_are_not_coerced(self):
        for value in [None, 5, {}, [], ""]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_path(value)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.files = {"manuscript/01.md": "城门已关闭。甲并不知道。", "possibilities/choice.md": "丁可能背叛。",
                      "reference/analysis.md": "相似作品有背叛。", "decisions/author.md": "作者采用：城门关闭。"}

    def test_all_six_information_kinds_and_sourced_indexes(self):
        data = state()
        for number, kind in enumerate(["world_fact", "character_knowledge", "character_belief", "reader_knowledge", "undecided", "candidate"]):
            item = knowledge(kind)
            item["id"] = str(number)
            if kind.startswith("character_"):
                item["holder"] = "甲"
            data["knowledge"].append(item)
        for section in ("characters", "world", "offstage"):
            data[section].append({"id": "record", "statement": "城门已关闭。", "sources": knowledge()["sources"]})
        data["characters"][0]["name"] = "守城人"
        validate_state(data, self.files)

    def test_character_knowledge_requires_holder(self):
        for kind in ["character_knowledge", "character_belief"]:
            data = state()
            data["knowledge"] = [knowledge(kind)]
            with self.assertRaises(ValidationError):
                validate_state(data, self.files)

    def test_quote_must_be_nonempty_and_exact(self):
        for quote in ["", " ", "城门已开放。"]:
            data = state()
            data["knowledge"] = [knowledge(quote=quote)]
            with self.assertRaises(ValidationError):
                validate_state(data, self.files)

    def test_missing_and_self_referential_sources_rejected(self):
        for path in ["manuscript/missing.md", "canon/state.json"]:
            data = state()
            data["knowledge"] = [knowledge(path=path)]
            with self.assertRaises(ValidationError):
                validate_state(data, {**self.files, "canon/state.json": "城门已关闭。"})

    def test_candidates_and_reference_do_not_establish_fact(self):
        for path, quote in [("possibilities/choice.md", "丁可能背叛。"), ("reference/analysis.md", "相似作品有背叛。")]:
            data = state()
            data["knowledge"] = [knowledge(path=path, quote=quote)]
            with self.assertRaises(ValidationError):
                validate_state(data, self.files)
            data["knowledge"][0]["kind"] = "candidate"
            validate_state(data, self.files)

    def test_duplicate_ids_unknown_fields_and_unknown_kinds_rejected(self):
        invalid = []
        duplicate = state()
        duplicate["knowledge"] = [knowledge(), knowledge()]
        invalid.append(duplicate)
        extra = state()
        extra["adopted"] = True
        invalid.append(extra)
        unknown = state()
        item = knowledge()
        item["kind"] = "probably_canon"
        unknown["knowledge"] = [item]
        invalid.append(unknown)
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    validate_state(data, self.files)


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.files = {"manuscript/01.md": "城门已关闭。", "canon/state.json": json.dumps(state())}

    def test_valid_write_validates_state_against_new_text(self):
        value = result()
        value["changes"][0]["content"] = "城门终于开启。"
        data = state()
        data["knowledge"] = [knowledge(quote="城门终于开启。")]
        value["changes"][1]["content"] = json.dumps(data)
        validate_result(value, task(), self.files)

    def test_stale_identity_or_unknown_result_fields_rejected(self):
        for field, content in [("task_id", "task-other"), ("input_revision", "rev-0"), ("approved", True)]:
            value = result()
            value[field] = content
            with self.assertRaises(ValidationError):
                validate_result(value, task(), self.files)

    def test_write_and_revise_require_synchronized_state_and_impact(self):
        for kind in ["write", "revise"]:
            for field, content in [("changes", result()["changes"][:1]), ("affected_paths", []), ("state_notes", ""),
                                   ("completed_steps", []), ("next_step", "")]:
                value = result()
                value[field] = content
                with self.subTest(kind=kind, field=field):
                    with self.assertRaises(ValidationError):
                        validate_result(value, task(kind), self.files)

    def test_duplicate_change_paths_and_unknown_impact_rejected(self):
        value = result()
        value["changes"].append(copy.deepcopy(value["changes"][0]))
        with self.assertRaises(ValidationError):
            validate_result(value, task(), self.files)
        value = result()
        value["affected_paths"].append("manuscript/missing.md")
        with self.assertRaises(ValidationError):
            validate_result(value, task(), self.files)

    def test_json_rejects_duplicate_keys_nonstandard_constants_and_bad_shape(self):
        for content in ['{"knowledge": [], "knowledge": []}', '{"knowledge": NaN}', '[]', '{']:
            value = result()
            value["changes"][1]["content"] = content
            with self.subTest(content=content):
                with self.assertRaises(ValidationError):
                    validate_result(value, task(), self.files)

    def test_research_can_preserve_unknown_without_fabricated_sources(self):
        validate_result(research_result(), task("research"), self.files)

    def test_external_research_facts_require_valid_sources(self):
        data = research()
        data["sources"] = [{"url": "https://example.org/paper", "title": "论文", "accessed": "2026-10-14"}]
        data["claims"][0].update(kind="external_fact", source_indexes=[0])
        validate_result(research_result(data), task("research"), self.files)
        for indexes in [[], [-1], [1], [True], [0, 0], ["0"]]:
            data["claims"][0]["source_indexes"] = indexes
            with self.subTest(indexes=indexes):
                with self.assertRaises(ValidationError):
                    validate_result(research_result(data), task("research"), self.files)

    def test_research_rejects_local_urls_bad_dates_and_missing_context(self):
        for url, accessed in [("file:///secret", "2026-10-14"), ("https://user:password@example.org", "2026-10-14"),
                              ("https://example.org", "2026-02-30"), ("https://example.org", "20261014")]:
            data = research()
            data["sources"] = [{"url": url, "title": "来源", "accessed": accessed}]
            with self.assertRaises(ValidationError):
                validate_result(research_result(data), task("research"), self.files)
        for field in ["conditions", "uncertainties", "claims"]:
            data = research()
            data[field] = []
            with self.assertRaises(ValidationError):
                validate_result(research_result(data), task("research"), self.files)

    def test_research_cannot_overwrite_or_modify_canon(self):
        for path in ["canon/state.json", "manuscript/01.md", "research/old.json", "research/notes.md"]:
            value = research_result()
            value["changes"][0]["path"] = path
            with self.assertRaises(ValidationError):
                validate_result(value, task("research"), {**self.files, "research/old.json": "{}"})

    def test_research_impact_cannot_be_hidden_from_result(self):
        value = research_result()
        value["affected_paths"] = []
        with self.assertRaises(ValidationError):
            validate_result(value, task("research"), self.files)

    def test_review_may_report_major_concern_without_mutating_or_claiming_pass(self):
        value = review_result()
        value["review"]["findings"] = [finding()]
        validate_result(value, task("review"), self.files)

    def test_review_cannot_change_files_or_miss_dimension_or_coverage(self):
        for field, content in [("coverage", []), ("coverage", ["manuscript/missing.md"]),
                               ("dimensions", ["reading"]), ("dimensions", ["reading"] * 4)]:
            value = review_result()
            value["review"][field] = content
            with self.subTest(field=field, content=content):
                with self.assertRaises(ValidationError):
                    validate_result(value, task("review"), self.files)
        value = review_result()
        value["changes"] = result()["changes"]
        with self.assertRaises(ValidationError):
            validate_result(value, task("review"), self.files)

    def test_findings_need_real_locations_and_cannot_self_resolve(self):
        for field, content in [("quote", "不存在的话"), ("path", "canon/state.json"), ("status", "resolved"),
                               ("status", "dismissed"), ("confirmed", 1), ("suggestion", "")]:
            value = review_result()
            item = finding()
            item[field] = content
            value["review"]["findings"] = [item]
            with self.subTest(field=field, content=content):
                with self.assertRaises(ValidationError):
                    validate_result(value, task("review"), self.files)

    def test_nonreview_tasks_cannot_submit_their_own_review(self):
        value = result()
        value["review"] = review_result()["review"]
        with self.assertRaises(ValidationError):
            validate_result(value, task(), self.files)


class StructuredSchemaTests(unittest.TestCase):
    def test_every_schema_object_is_closed_and_all_fields_required(self):
        path = Path(__file__).resolve().parents[1] / "schemas" / "result.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))

        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node["additionalProperties"], False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)

        check(schema)
        self.assertEqual(set(schema["properties"]), set(result()))
        self.assertIn({"type": "null"}, schema["properties"]["review"]["anyOf"])


if __name__ == "__main__":
    unittest.main()
