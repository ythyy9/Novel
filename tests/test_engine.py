"""真实文件和 SQLite 上的控制层契约测试；不模拟模型或声称作品质量通过。"""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from novel.engine import Engine


EMPTY_STATE = {"knowledge": [], "characters": [], "world": [], "offstage": []}
DIMENSIONS = ["continuity", "character", "world", "reading"]


class EngineTests(unittest.TestCase):
    def setUp(self):
        # Windows AppContainer 的系统临时目录可能允许新建却拒绝目录 rename。
        # 放在已授权工作区，仍由 TemporaryDirectory 在每项测试结束时清理。
        self.temp = tempfile.TemporaryDirectory(
            prefix=".novel-engine-test-", dir=Path(__file__).resolve().parents[1]
        )
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = Engine.initialize(self.root)
        self.engine.create_book("test-book", "控制层验收样本")

    def result(self, task, changes=None, *, review=None, unresolved=None):
        changes = changes or []
        return {
            "task_id": task["id"],
            "input_revision": task["input_revision"],
            "completed_steps": ["完成当前测试用例指定的实际文件变更"],
            "next_step": "交由当前版本审核后再决定下一步",
            "unresolved": unresolved or [],
            "changes": changes,
            "review": review,
            "affected_paths": [item["path"] for item in changes],
            "state_notes": "正文和状态已按本次测试场景一起核对。",
        }

    def manuscript_changes(self, content="# 第一章\n\n验收样本：船在落日前抵港。\n", path="manuscript/001.md"):
        return [
            {"path": path, "content": content},
            {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE, ensure_ascii=False)},
        ]

    def start(self, kind="write", book_id="test-book"):
        task = self.engine.enqueue(book_id, kind, "执行当前控制层验收场景")
        return self.engine.claim(task["id"])

    def write(self, *, kind="write", content="# 第一章\n\n验收样本：船在落日前抵港。\n", path="manuscript/001.md"):
        task = self.start(kind)
        result = self.result(task, self.manuscript_changes(content, path))
        self.engine.submit(task["id"], result)
        return self.engine.publish(task["id"])

    def review(self, *, coverage=None, dimensions=None, findings=None, unresolved=None):
        task = self.start("review")
        if coverage is None:
            coverage = sorted(path for path in self.engine.files("test-book") if path.startswith("manuscript/"))
        report = {
            "coverage": coverage,
            "dimensions": DIMENSIONS if dimensions is None else dimensions,
            "findings": findings or [],
        }
        self.engine.submit(task["id"], self.result(task, review=report, unresolved=unresolved))
        return self.engine.publish(task["id"])

    def task(self, task_id):
        return next(task for task in self.engine.tasks() if task["id"] == task_id)

    def test_initial_book_is_persisted_and_uses_real_sqlite(self):
        first = self.engine.book("test-book")
        reopened = Engine(self.root)
        self.assertEqual(reopened.book("test-book"), first)
        self.assertEqual(first["status"], "accepted")
        self.assertEqual(set(reopened.files("test-book")), {"canon/state.json"})
        self.assertEqual(json.loads(reopened.files("test-book")["canon/state.json"]), EMPTY_STATE)
        sqlite_files = [
            path for path in self.root.rglob("*")
            if path.is_file() and path.suffix in {".db", ".sqlite", ".sqlite3"}
        ]
        self.assertTrue(sqlite_files, "控制层应使用真实持久化 SQLite 数据库")
        with closing(sqlite3.connect(sqlite_files[0])) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_duplicate_book_is_rejected_without_overwriting(self):
        before = self.engine.book("test-book")
        with self.assertRaises(ValueError):
            self.engine.create_book("test-book", "另一个标题")
        self.assertEqual(self.engine.book("test-book"), before)

    def test_book_identifiers_cannot_escape_workspace(self):
        for book_id in ("../escape", "..", "a/b", "a\\b", "C:\\escape"):
            with self.subTest(book_id=book_id), self.assertRaises(ValueError):
                self.engine.create_book(book_id, "非法路径样本")

    def test_running_task_survives_new_engine_instance(self):
        task = self.start()
        reopened = Engine(self.root)
        persisted = next(item for item in reopened.tasks("test-book") if item["id"] == task["id"])
        self.assertEqual(persisted["status"], "running")
        self.assertEqual(persisted["attempts"], 1)
        self.assertEqual(persisted["input_revision"], task["input_revision"])

    def test_submit_does_not_publish_and_publish_preserves_original_revision(self):
        original = self.engine.book("test-book")["current_revision"]
        original_files = self.engine.files("test-book", original)
        task = self.start()
        submitted = self.engine.submit(task["id"], self.result(task, self.manuscript_changes()))
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(self.engine.book("test-book")["current_revision"], original)
        self.assertNotIn("manuscript/001.md", self.engine.files("test-book"))
        published = Engine(self.root).publish(task["id"])
        self.assertEqual(published["status"], "completed")
        self.assertNotEqual(published["result_revision"], original)
        self.assertEqual(self.engine.files("test-book", original), original_files)
        current_files = self.engine.files("test-book")
        self.assertIn("manuscript/001.md", current_files)
        self.assertEqual(json.loads(current_files["canon/state.json"]), EMPTY_STATE)
        self.assertEqual(self.engine.book("test-book")["status"], "draft")

    def test_identical_result_is_idempotent_across_instances(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes())
        first = self.engine.submit(task["id"], result)
        second = Engine(self.root).submit(task["id"], copy.deepcopy(result))
        self.assertEqual(first, second)
        self.assertEqual(self.task(task["id"])["attempts"], 1)

    def test_different_duplicate_result_is_rejected(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes())
        self.engine.submit(task["id"], result)
        changed = copy.deepcopy(result)
        changed["changes"][0]["content"] += "重复提交试图覆盖原结果。\n"
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], changed)
        self.engine.publish(task["id"])
        self.assertEqual(self.engine.files("test-book")["manuscript/001.md"], result["changes"][0]["content"])

    def test_repeated_publish_is_idempotent(self):
        published = self.write()
        before = self.engine.audit()
        repeated = Engine(self.root).publish(published["id"])
        self.assertEqual(repeated, published)
        self.assertEqual(self.engine.audit(), before)

    def test_one_writer_per_book_even_across_engine_instances(self):
        first = self.start()
        second = self.engine.enqueue("test-book", "revise", "竞争同一本书的写锁")
        with self.assertRaises(ValueError):
            Engine(self.root).claim(second["id"])
        self.assertEqual(self.task(first["id"])["status"], "running")
        self.assertEqual(self.task(second["id"])["attempts"], 0)

    def test_simultaneous_claims_have_exactly_one_writer(self):
        tasks = [self.engine.enqueue("test-book", "write", f"并发认领 {number}") for number in (1, 2)]
        barrier = Barrier(2)

        def claim(task):
            engine = Engine(self.root)
            barrier.wait(timeout=10)
            try:
                return engine.claim(task["id"])["status"]
            except ValueError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(claim, tasks))
        self.assertCountEqual(statuses, ["running", "rejected"])
        persisted = Engine(self.root).tasks("test-book")
        self.assertEqual(sum(task["status"] == "running" for task in persisted), 1)
        self.assertEqual(sum(task["attempts"] for task in persisted), 1)

    def test_submitted_writer_keeps_lock_until_publish(self):
        first = self.start()
        self.engine.submit(first["id"], self.result(first, self.manuscript_changes()))
        second = self.engine.enqueue("test-book", "revise", "不能越过尚未发布的结果")
        with self.assertRaises(ValueError):
            self.engine.claim(second["id"])

    def test_different_books_can_have_active_writers(self):
        self.engine.create_book("second-book", "另一本独立的测试书")
        first = self.start()
        second = self.start(book_id="second-book")
        self.assertEqual(first["status"], "running")
        self.assertEqual(second["status"], "running")
        self.assertEqual(len(self.engine.list_books()), 2)
        self.assertEqual(len(self.engine.tasks("second-book")), 1)

    def test_stale_queued_task_cannot_claim_new_current_version(self):
        stale = self.engine.enqueue("test-book", "revise", "基于旧版本排队的任务")
        self.write()
        handoff = self.engine.handoff(stale["id"])
        self.assertTrue(handoff["input_verified"])
        self.assertFalse(handoff["input_is_current"])
        with self.assertRaises(ValueError):
            self.engine.claim(stale["id"])
        self.assertEqual(self.task(stale["id"])["attempts"], 0)

    def test_task_and_result_revision_must_match(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes())
        result["input_revision"] = "0" * 64
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], result)
        self.assertEqual(self.task(task["id"])["status"], "running")

    def test_result_task_id_must_match(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes())
        result["task_id"] = "unrelated-task"
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], result)

    def test_queued_task_cannot_submit_before_claim(self):
        task = self.engine.enqueue("test-book", "write", "未认领任务")
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, self.manuscript_changes()))

    def test_write_requires_manuscript_and_state_together(self):
        for index, changes in enumerate((
            [],
            [{"path": "manuscript/001.md", "content": "正文缺少状态更新。"}],
            [{"path": "canon/state.json", "content": json.dumps(EMPTY_STATE)}],
        )):
            with self.subTest(changes=changes):
                task = self.start()
                with self.assertRaises(ValueError):
                    self.engine.submit(task["id"], self.result(task, changes))
                self.engine.block(task["id"], "tool_failure", "不合法结果已被拒绝")
                self.engine.resume(task["id"], "继续同一任务")
                # 用同一真实任务完成一个有效版本，以释放该测试的写锁。
                task = self.engine.claim(task["id"])
                self.engine.submit(task["id"], self.result(task, self.manuscript_changes(f"# 验收章\n\n第 {index + 1} 个状态同步验收样本。\n")))
                self.engine.publish(task["id"])
                self.review()
                self.engine.accept("test-book")

    def test_empty_manuscript_is_rejected(self):
        task = self.start()
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, self.manuscript_changes("  \n")))

    def test_changed_manuscript_must_be_in_affected_paths(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes())
        result["affected_paths"] = ["canon/state.json"]
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], result)

    def test_paths_outside_allowed_book_data_are_rejected_atomically(self):
        task = self.start()
        original = self.engine.book("test-book")["current_revision"]
        for path in ("../escape.md", "/absolute.md", "C:\\escape.md", "manuscript/../escape.md", "policies/limits.json", "novel/engine.py"):
            with self.subTest(path=path):
                changes = self.manuscript_changes()
                changes.append({"path": path, "content": "不应写入"})
                with self.assertRaises(ValueError):
                    self.engine.submit(task["id"], self.result(task, changes))
                self.assertEqual(self.engine.book("test-book")["current_revision"], original)
                self.assertEqual(set(self.engine.files("test-book")), {"canon/state.json"})

    def test_duplicate_change_paths_are_rejected(self):
        task = self.start()
        changes = self.manuscript_changes()
        changes.append({"path": "manuscript/001.md", "content": "同一路径的第二份内容"})
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, changes))

    def test_case_collisions_are_rejected_before_any_publication(self):
        task = self.start()
        changes = self.manuscript_changes(path="manuscript/Chapter.md")
        changes.append({"path": "manuscript/chapter.md", "content": "Windows 上指向同一个文件。"})
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, changes))
            self.engine.publish(task["id"])
        self.assertNotIn("manuscript/Chapter.md", self.engine.files("test-book"))

    def test_identical_revision_content_cannot_report_progress(self):
        self.write()
        task = self.start("revise")
        changes = [{"path": path, "content": content} for path, content in self.engine.files("test-book").items()]
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, changes))
        self.assertEqual(self.task(task["id"])["status"], "running")

    def test_draft_blocks_next_chapter_but_allows_revision(self):
        self.write()
        with self.assertRaises(ValueError):
            self.engine.enqueue("test-book", "write", "尚未通过就写下一章")
        revised = self.write(kind="revise", content="# 第一章\n\n验收样本：船因逆风在入夜后抵港。\n")
        self.assertEqual(revised["status"], "completed")
        self.assertEqual(self.engine.book("test-book")["status"], "draft")

    def test_accept_requires_a_review_of_current_manuscript(self):
        self.write()
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")
        self.review()
        accepted = self.engine.accept("test-book")
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(Engine(self.root).book("test-book")["status"], "accepted")

    def test_review_never_mutates_book_files(self):
        self.write()
        before = self.engine.files("test-book")
        revision = self.engine.book("test-book")["current_revision"]
        self.review()
        self.assertEqual(self.engine.files("test-book"), before)
        self.assertEqual(self.engine.book("test-book")["current_revision"], revision)

    def test_review_task_cannot_modify_manuscript(self):
        self.write()
        task = self.start("review")
        report = {"coverage": ["manuscript/001.md"], "dimensions": DIMENSIONS, "findings": []}
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, self.manuscript_changes(), review=report))

    def test_review_missing_dimensions_does_not_allow_acceptance(self):
        self.write()
        with self.assertRaises(ValueError):
            self.review(dimensions=["continuity", "character", "world"])
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_review_coverage_must_include_all_manuscript_files(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        self.write(path="manuscript/002.md", content="# 第二章\n\n验收样本：港内的灯一盏盏熄灭。\n")
        self.review(coverage=["manuscript/002.md"])
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_unresolved_items_block_acceptance(self):
        self.write()
        self.review(unresolved=["测试未决项：人物是否知道船期尚待作者决定"])
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def finding(self, *, category="error", confirmed=True, severity="minor"):
        return {
            "id": "test-finding",
            "category": category,
            "confirmed": confirmed,
            "severity": severity,
            "path": "manuscript/001.md",
            "quote": "船在落日前抵港。",
            "explanation": "验收植入问题：叙述缺少时间依据。",
            "suggestion": "核对航行时间及人物已知信息。",
            "affected_paths": ["manuscript/001.md"],
            "status": "open",
        }

    def test_confirmed_error_blocks_acceptance_even_if_later_review_is_clean(self):
        self.write()
        self.review(findings=[self.finding()])
        self.review()
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_major_concern_blocks_acceptance_without_confirmed_error(self):
        self.write()
        self.review(findings=[self.finding(category="concern", confirmed=False, severity="major")])
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_minor_reading_concern_can_be_preserved_and_accepted(self):
        self.write()
        self.review(findings=[self.finding(category="experience", confirmed=False)])
        self.assertEqual(self.engine.accept("test-book")["status"], "accepted")

    def test_new_review_reopens_accepted_revision_and_stops_new_and_queued_writes(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        queued = self.engine.enqueue("test-book", "write", "通过旧审核后排队的下一章")
        self.review(findings=[self.finding()])
        self.assertEqual(self.engine.book("test-book")["status"], "draft")
        with self.assertRaises(ValueError):
            self.engine.enqueue("test-book", "write", "不能越过新发现的问题")
        with self.assertRaises(ValueError):
            self.engine.claim(queued["id"])
        self.assertEqual(self.task(queued["id"])["attempts"], 0)

    def test_new_review_stops_already_running_next_chapter_submission(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        writer = self.start()
        self.review(findings=[self.finding()])
        changes = self.manuscript_changes("# 第二章\n\n不能越过已重新开启的前章审核。", "manuscript/002.md")
        with self.assertRaises(ValueError):
            self.engine.submit(writer["id"], self.result(writer, changes))
        self.assertNotIn("manuscript/002.md", self.engine.files("test-book"))

    def test_writer_unresolved_item_is_not_erased_by_clean_review(self):
        task = self.start()
        result = self.result(task, self.manuscript_changes(), unresolved=["创作任务保留的重大未决项"])
        self.engine.submit(task["id"], result)
        self.engine.publish(task["id"])
        self.review()
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_revision_invalidates_prior_accepted_review(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        accepted_revision = self.engine.book("test-book")["current_revision"]
        self.write(kind="revise", content="# 第一章\n\n验收样本：船在清晨抵港，旧审核已失效。\n")
        self.assertNotEqual(self.engine.book("test-book")["current_revision"], accepted_revision)
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")
        self.review()
        self.engine.accept("test-book")

    def test_stale_running_review_cannot_publish_for_new_revision(self):
        self.write()
        review_task = self.start("review")
        self.write(kind="revise", content="# 第一章\n\n验收样本：修订发生在审阅期间。\n")
        report = {"coverage": ["manuscript/001.md"], "dimensions": DIMENSIONS, "findings": []}
        with self.assertRaises(ValueError):
            self.engine.submit(review_task["id"], self.result(review_task, review=report))
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_submitted_review_becomes_stale_before_publication(self):
        self.write()
        task = self.start("review")
        report = {"coverage": ["manuscript/001.md"], "dimensions": DIMENSIONS, "findings": []}
        self.engine.submit(task["id"], self.result(task, review=report))
        self.write(kind="revise", content="# 第一章\n\n验收样本：审核提交之后发生了修订。\n")
        with self.assertRaises(ValueError):
            self.engine.publish(task["id"])
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_research_preserves_unknown_and_requires_new_version_review(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        previous = self.engine.book("test-book")["current_revision"]
        task = self.start("research")
        research = {
            "question": "船能否在落日前抵港？",
            "sources": [],
            "conclusion": "Unknown",
            "conditions": ["缺少距离、天气和船型"],
            "uncertainties": ["缺少前提，无法验证时间"],
            "affected_paths": ["manuscript/001.md"],
            "claims": [{"kind": "inference", "text": "目前条件不足。", "source_indexes": []}],
        }
        changes = [{"path": "research/travel.json", "content": json.dumps(research, ensure_ascii=False)}]
        result = self.result(task, changes)
        result["affected_paths"].append("manuscript/001.md")
        self.engine.submit(task["id"], result)
        published = self.engine.publish(task["id"])
        self.assertNotEqual(published["result_revision"], previous)
        self.assertEqual(self.engine.files("test-book")["manuscript/001.md"], self.engine.files("test-book", previous)["manuscript/001.md"])
        self.assertEqual(json.loads(self.engine.files("test-book")["research/travel.json"])["conclusion"], "Unknown")
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")
        self.review()
        self.engine.accept("test-book")

    def test_candidate_cannot_be_adopted_without_decision_source(self):
        task = self.start()
        candidate_state = copy.deepcopy(EMPTY_STATE)
        candidate_state["knowledge"] = [{
            "id": "harbor-arrival", "kind": "candidate", "statement": "船在落日前抵港。",
            "holder": None, "sources": [{"path": "possibilities/arrival.md", "quote": "船在落日前抵港。"}],
        }]
        changes = self.manuscript_changes()
        changes[1]["content"] = json.dumps(candidate_state, ensure_ascii=False)
        changes.append({"path": "possibilities/arrival.md", "content": "候选：船在落日前抵港。"})
        self.engine.submit(task["id"], self.result(task, changes))
        self.engine.publish(task["id"])
        revision = self.engine.book("test-book")["current_revision"]

        revised = self.start("revise")
        adopted_state = copy.deepcopy(candidate_state)
        adopted_state["knowledge"][0]["kind"] = "world_fact"
        adopted_state["knowledge"][0]["sources"] = [{"path": "manuscript/001.md", "quote": "船在落日前抵港。"}]
        changes = self.manuscript_changes("# 第一章\n\n验收修订：船在落日前抵港。码头已关。\n")
        changes[1]["content"] = json.dumps(adopted_state, ensure_ascii=False)
        with self.assertRaises(ValueError):
            self.engine.submit(revised["id"], self.result(revised, changes))
        self.assertEqual(self.engine.book("test-book")["current_revision"], revision)

        # 保留旧ID、另加新ID，也不能把同一句候选事实悄悄采用。
        remapped = copy.deepcopy(candidate_state)
        adopted = copy.deepcopy(adopted_state["knowledge"][0])
        adopted["id"] = "new-identity-for-the-same-candidate"
        remapped["knowledge"].append(adopted)
        changes[1]["content"] = json.dumps(remapped, ensure_ascii=False)
        with self.assertRaises(ValueError):
            self.engine.submit(revised["id"], self.result(revised, changes))

        # 只有独立的作者决定入口写入的既有依据才可用于后续采用。
        self.engine.cancel(revised["id"], "转入独立的作者决定记录，再创建新任务")
        decision_text = "验收输入：采用船在落日前抵港这一事实。"
        decision = self.engine.decision("test-book", decision_text)
        self.assertEqual(decision["text"], decision_text)
        self.assertEqual(self.engine.files("test-book")[decision["path"]], decision_text)
        self.assertEqual(self.engine.book("test-book")["status"], "draft")
        approved = self.start("revise")
        adopted_state["knowledge"][0]["sources"].append({"path": decision["path"], "quote": decision_text})
        changes[1]["content"] = json.dumps(adopted_state, ensure_ascii=False)
        self.engine.submit(approved["id"], self.result(approved, changes))
        self.engine.publish(approved["id"])
        actual = json.loads(self.engine.files("test-book")["canon/state.json"])
        self.assertEqual(actual["knowledge"][0]["kind"], "world_fact")

    def test_model_result_cannot_forge_decisions_or_original_reference(self):
        task = self.start()
        for path in ("decisions/forged-author.md", "reference/original-source.md"):
            with self.subTest(path=path):
                changes = self.manuscript_changes()
                changes.append({"path": path, "content": "模型不能把自己的输出写成作者决定或原始材料。"})
                with self.assertRaises(ValueError):
                    self.engine.submit(task["id"], self.result(task, changes))
                self.assertNotIn(path, self.engine.files("test-book"))

    def test_stop_and_resume_preserve_attempts_across_instances(self):
        task = self.start()
        stopped = self.engine.block(task["id"], "tool_failure", "测试中断：工具未返回")
        self.assertEqual(stopped["status"], "blocked")
        self.assertEqual(stopped["attempts"], 1)
        reopened = Engine(self.root)
        resumed = reopened.resume(task["id"], "已检查工具恢复，可进行下一次有限尝试")
        self.assertEqual(resumed["status"], "queued")
        self.assertEqual(resumed["attempts"], 1)
        claimed = reopened.claim(task["id"])
        self.assertEqual(claimed["attempts"], 2)

    def test_decision_quota_and_authorization_stops_persist_without_auto_retry(self):
        for reason in ("decision", "quota", "authorization"):
            with self.subTest(reason=reason):
                task = self.start()
                self.engine.block(task["id"], reason, f"保留 {reason} 停止原因")
                reopened = Engine(self.root)
                persisted = next(item for item in reopened.tasks() if item["id"] == task["id"])
                self.assertEqual(persisted["status"], "blocked")
                self.assertEqual(persisted["stop_reason"], reason)
                self.assertEqual(persisted["attempts"], 1)
                with self.assertRaises(ValueError):
                    reopened.claim(task["id"])
                reopened.cancel(task["id"], "已明确结束当前停止场景，不执行重试")

    def test_blocked_writer_retains_ownership(self):
        task = self.start()
        self.engine.block(task["id"], "tool_failure", "停止后仍保留当前任务责任")
        with self.assertRaises(ValueError):
            competitor = self.engine.enqueue("test-book", "revise", "不能通过另开任务绕过停止条件")
            Engine(self.root).claim(competitor["id"])

    def test_stopped_review_also_blocks_an_active_writer_for_the_book(self):
        writer = self.start()
        reviewer = self.start("review")
        self.engine.block(reviewer["id"], "quota", "审核额度不足，同书停止状态不得绕过")
        with self.assertRaises(ValueError):
            self.engine.submit(writer["id"], self.result(writer, self.manuscript_changes()))
        self.engine.cancel(reviewer["id"], "明确取消该审核任务后继续控制层验收")
        self.engine.submit(writer["id"], self.result(writer, self.manuscript_changes()))
        self.engine.publish(writer["id"])

    def test_explicit_cancel_releases_lock_and_keeps_attempt_history(self):
        task = self.start()
        self.engine.block(task["id"], "decision", "等待作者决定")
        cancelled = self.engine.cancel(task["id"], "已明确取消此方案")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["attempts"], 1)
        next_task = self.start()
        self.assertEqual(next_task["status"], "running")
        self.assertEqual(self.task(task["id"])["attempts"], 1)

    def test_no_progress_limit_survives_resume(self):
        task = self.start()
        first = self.engine.block(task["id"], "no_progress", "第一轮未带来有效变化")
        self.assertEqual(first["status"], "blocked")
        self.engine.resume(task["id"], "保留累计无进展记录，再试一次不同方法")
        self.engine.claim(task["id"])
        second = self.engine.block(task["id"], "no_progress", "第二轮仍没有有效变化")
        self.assertEqual(second["status"], "exhausted")
        self.assertEqual(second["no_progress"], 2)
        self.assertEqual(second["attempts"], 2)
        with self.assertRaises(ValueError):
            Engine(self.root).resume(task["id"], "新会话不能清零无进展记录")

    def test_retry_exhaustion_cannot_be_reset_by_new_instance(self):
        task = self.start()
        for attempt in range(1, 4):
            stopped = self.engine.block(task["id"], "tool_failure", f"第 {attempt} 次真实状态转换")
            self.assertEqual(stopped["attempts"], attempt)
            if attempt < 3:
                self.engine = Engine(self.root)
                self.engine.resume(task["id"], "继续同一任务，保留重试次数")
                task = self.engine.claim(task["id"])
        self.assertEqual(stopped["status"], "exhausted")
        with self.assertRaises(ValueError):
            Engine(self.root).resume(task["id"], "新会话不能清零重试")
        with self.assertRaises(ValueError):
            competitor = self.engine.enqueue("test-book", "revise", "耗尽后新任务不能抢写")
            Engine(self.root).claim(competitor["id"])

    def test_recover_marks_running_task_blocked_without_retrying(self):
        task = self.start()
        reopened = Engine(self.root)
        recovered = reopened.recover(task["id"], "此前进程中断，显式恢复状态")
        self.assertEqual(recovered["status"], "blocked")
        self.assertEqual(recovered["attempts"], 1)
        self.assertNotIn("manuscript/001.md", reopened.files("test-book"))
        with self.assertRaises(ValueError):
            reopened.claim(task["id"])

    def test_handoff_reports_persisted_task_and_input_revision(self):
        task = self.start()
        handoff = Engine(self.root).handoff(task["id"])
        serialized = json.dumps(handoff, ensure_ascii=False)
        self.assertIn(task["id"], serialized)
        self.assertIn(task["input_revision"], serialized)
        self.assertIn("canon/state.json", serialized)
        self.assertIn("next_step", handoff)

    def test_file_corruption_is_detected_before_handoff(self):
        task = self.start()
        state_file = self.root / "books" / "test-book" / "versions" / task["input_revision"] / "canon" / "state.json"
        self.assertTrue(state_file.is_file())
        state_file.write_text('{"tampered": true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            Engine(self.root).files("test-book")
        with self.assertRaises(ValueError):
            Engine(self.root).handoff(task["id"])
        with self.assertRaises(ValueError):
            Engine(self.root).audit()

    def test_policy_change_freezes_inflight_result(self):
        task = self.start()
        original = self.engine.book("test-book")["current_revision"]
        policy_path = self.root / "policies" / "limits.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["max_attempts"] = 100
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertFalse(self.engine.handoff(task["id"])["controls_match"])
        with self.assertRaises(ValueError):
            self.engine.submit(task["id"], self.result(task, self.manuscript_changes()))
        self.assertEqual(self.engine.book("test-book")["current_revision"], original)

    def test_rollback_creates_new_draft_and_does_not_reuse_old_review(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        revision_one = self.engine.book("test-book")["current_revision"]
        files_one = self.engine.files("test-book")
        self.write(kind="revise", content="# 第一章\n\n验收样本：第二版改变了抵港时间。\n")
        revision_two = self.engine.book("test-book")["current_revision"]
        self.engine.rollback("test-book", revision_one, "验收回滚，保留所有历史版本")
        restored = self.engine.book("test-book")
        self.assertNotIn(restored["current_revision"], {revision_one, revision_two})
        self.assertEqual(restored["status"], "draft")
        self.assertEqual(self.engine.files("test-book"), files_one)
        self.assertNotEqual(self.engine.files("test-book", revision_two), files_one)
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_rollback_cannot_displace_active_writer(self):
        initial = self.engine.book("test-book")["current_revision"]
        self.start()
        with self.assertRaises(ValueError):
            self.engine.rollback("test-book", initial, "不能绕过正在执行的任务")

    def test_search_returns_current_content_and_source_path(self):
        self.write()
        matches = self.engine.search("test-book", "落日前")
        serialized = json.dumps(matches, ensure_ascii=False)
        self.assertTrue(matches)
        self.assertIn("manuscript/001.md", serialized)
        self.assertIn("落日前", serialized)
        self.assertEqual(self.engine.search("test-book", "绝不存在的词串XYZ"), [])

    def test_audit_can_read_a_completed_local_flow(self):
        self.write()
        self.review()
        self.engine.accept("test-book")
        result = Engine(self.root).audit()
        self.assertEqual(result["database"], "ok")
        self.assertEqual(result["snapshots_verified"], 2)
        self.assertGreater(result["events"], 0)
        self.assertIn("not OS isolation", result["protection"])

    def test_audit_and_accept_reject_corrupted_review_copy(self):
        self.write()
        reviewed = self.review()
        with closing(sqlite3.connect(self.root / "runtime" / "novel.sqlite3")) as connection:
            connection.execute("UPDATE reviews SET result=? WHERE task_id=?", ("{}", reviewed["id"]))
            connection.commit()
        with self.assertRaises(ValueError):
            Engine(self.root).audit()
        with self.assertRaises(ValueError):
            self.engine.accept("test-book")

    def test_audit_rejects_current_revision_pointer_to_another_book(self):
        other = self.engine.create_book("other-book", "用于检测版本归属错误")
        with closing(sqlite3.connect(self.root / "runtime" / "novel.sqlite3")) as connection:
            connection.execute("UPDATE books SET current_revision=? WHERE id=?", (other["current_revision"], "test-book"))
            connection.commit()
        with self.assertRaises(ValueError):
            Engine(self.root).audit()
        with self.assertRaises(ValueError):
            self.engine.files("test-book")


if __name__ == "__main__":
    unittest.main()
