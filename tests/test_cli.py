"""Real subprocess CLI acceptance; fixture prose is not model or reader evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
EMPTY_STATE = {"knowledge": [], "characters": [], "world": [], "offstage": []}
MANUSCRIPT = "# 命令行验收章\n\n这是测试输入：船在落日前抵港。\n"


class CliTests(unittest.TestCase):
    def setUp(self):
        # AppContainer's system TEMP can reject directory rename on Windows.
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-cli-test-", dir=REPOSITORY)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = os.environ.copy()
        self.environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        initialized = self.json_command("init")
        self.assertEqual(initialized["initialized"], str(self.root.resolve()))
        self.assertFalse(initialized["model_called"])
        self.book = self.json_command("book-create", "cli-book", "--title", "命令行验收样本")

    def command(self, *arguments, root=None, expected=0):
        process = subprocess.run(
            [sys.executable, "-m", "novel", "--root", str(root or self.root), *map(str, arguments)],
            cwd=REPOSITORY,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(
            process.returncode,
            expected,
            f"CLI {arguments!r}\nstdout:\n{process.stdout}\nstderr:\n{process.stderr}",
        )
        if expected == 0:
            self.assertEqual(process.stderr, "", process.stderr)
        else:
            self.assertNotIn("Traceback", process.stderr)
            self.assertEqual(process.stdout, "")
        return process

    def json_command(self, *arguments, **kwargs):
        return json.loads(self.command(*arguments, **kwargs).stdout)

    def error_command(self, *arguments, root=None):
        error = json.loads(self.command(*arguments, root=root, expected=1).stderr)
        self.assertEqual(set(error), {"error", "type"})
        self.assertTrue(error["error"])
        return error

    def text_file(self, name, content, *, bom=False):
        path = self.root / name
        path.write_text(content, encoding="utf-8-sig" if bom else "utf-8", newline="\n")
        return path

    def json_file(self, name, value):
        return self.text_file(name, json.dumps(value, ensure_ascii=False), bom=True)

    def create_task(self, kind="write"):
        return self.json_command("task-create", "cli-book", kind, "--instruction", "执行当前命令行验收场景")

    def result(self, task, *, review=None):
        return {
            "task_id": task["id"],
            "input_revision": task["input_revision"],
            "completed_steps": ["完成命令行输入输出协议验收"],
            "next_step": "发布结果后核对当前版本",
            "unresolved": [],
            "changes": [] if review is not None else [
                {"path": "manuscript/001.md", "content": MANUSCRIPT},
                {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE, ensure_ascii=False)},
            ],
            "review": review,
            "affected_paths": [] if review is not None else ["manuscript/001.md"],
            "state_notes": "验收文本没有新增人物所知，保留空状态。",
        }

    def test_impact_cli_reads_revision_and_rejects_absent_file(self):
        before = self.json_command("audit")
        report = self.json_command("impact", "cli-book", "canon/state.json",
                                   "--revision", self.book["current_revision"])
        self.assertEqual(report["revision"], self.book["current_revision"])
        self.assertEqual(report["references"], [])
        self.assertEqual(len(report["source_hash"]), 64)
        self.assertEqual(self.json_command("search", "cli-book", "knowledge",
                                          "--revision", self.book["current_revision"])[0]["path"], "canon/state.json")
        self.error_command("search", "cli-book", "knowledge", "--revision", "missing")
        page = self.json_command("search", "cli-book", "knowledge", "--page-size", "1")
        self.assertEqual(page["revision"], self.book["current_revision"])
        self.assertEqual(len(page["matches"]), 1)
        self.error_command("search", "cli-book", "knowledge", "--page-size", "1", "--offset", "1")
        self.error_command("search", "cli-book", "knowledge", "--offset", "1")
        self.error_command("impact", "cli-book", "manuscript/missing.md")
        self.assertEqual(self.json_command("audit"), before)

    def test_complete_write_review_accept_flow_and_readback(self):
        instruction = "  按这份测试任务书写入完整验收章。\n保留作者输入的换行。\n"
        instruction_file = self.text_file("测试 指令.txt", instruction, bom=True)
        task = self.json_command("task-create", "cli-book", "write", "--instruction-file", instruction_file)
        self.assertEqual(task["instruction"], instruction)
        self.assertEqual(task["status"], "queued")
        claimed = self.json_command("task-claim", task["id"])
        self.assertEqual(claimed["attempts"], 1)
        result_path = self.json_file("写作 结果.json", self.result(claimed))
        submitted = self.json_command("task-submit", task["id"], result_path, "--expected-attempt", "1")
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(self.json_command("files", "cli-book"), ["canon/state.json"])
        handoff = self.json_command("handoff", task["id"])
        self.assertTrue(handoff["input_verified"])
        self.assertTrue(handoff["input_is_current"])
        self.assertIn("manuscript/001.md", handoff["changed_files"])

        published = self.json_command("task-publish", task["id"])
        self.assertEqual(published["status"], "completed")
        self.assertEqual(self.command("read", "cli-book", "manuscript/001.md").stdout, MANUSCRIPT)
        self.assertEqual(self.json_command("book-show", "cli-book")["current_revision"], published["result_revision"])
        self.assertFalse(self.json_command("assess", "cli-book")["can_accept"])
        self.assertEqual(self.error_command("accept", "cli-book")["type"], "EngineError")

        review_task = self.create_task("review")
        self.json_command("task-claim", review_task["id"])
        review = {
            "coverage": ["manuscript/001.md"],
            "dimensions": ["continuity", "character", "world", "reading"],
            "findings": [],
        }
        review_path = self.json_file("审核结果.json", self.result(review_task, review=review))
        self.json_command("task-submit", review_task["id"], review_path, "--expected-attempt", "1")
        self.json_command("task-publish", review_task["id"])
        assessment = self.json_command("assess", "cli-book")
        self.assertTrue(assessment["can_accept"])
        self.assertEqual(assessment["blockers"], [])
        evidence = self.json_command("impact", "cli-book", "manuscript/001.md")
        self.assertEqual(evidence["reviews"][0]["task_id"], review_task["id"])
        self.assertEqual(evidence["reviews"][0]["revision"], published["result_revision"])
        self.assertEqual(evidence["reviews"][0]["review"], review)
        self.assertEqual(evidence["research"], [])
        differences = self.json_command("diff", "cli-book", self.book["current_revision"],
                                        "--to-revision", published["result_revision"])
        manuscript = next(entry for entry in differences["changes"] if entry["path"] == "manuscript/001.md")
        self.assertEqual(manuscript["status"], "added")
        self.error_command("diff", "cli-book", "missing")
        excerpt = self.json_command("excerpt", "cli-book", "manuscript/001.md",
                                    "--revision", published["result_revision"], "--start-line", "2", "--line-count", "1")
        self.assertEqual(excerpt["lines"], [{"line": 2, "text": ""}])
        self.assertTrue(excerpt["has_more"])
        self.error_command("excerpt", "cli-book", "manuscript/001.md", "--line-count", "0")
        self.assertEqual(self.json_command("accept", "cli-book")["status"], "accepted")
        self.assertEqual(self.json_command("audit")["snapshots_verified"], 2)
        self.assertEqual(len(self.json_command("tasks", "--book", "cli-book")), 2)

    def test_feedback_diagnosis_cli_preserves_historical_input(self):
        revision = self.json_command("book-show", "cli-book")["current_revision"]
        note = self.text_file("feedback-original.txt", "合成反馈：证据不足，先查原因。\n")
        original = self.json_command("feedback", "cli-book", "--text-file", note, "--revision", revision)
        spec = self.json_file("diagnosis.json", {
            "evidence": [], "hypothesis": "资料缺失，原因未知。", "prevention": "先列可见依据。",
            "scope": "合成接口验证", "validation_plan": "补齐资料后检验其他案例及误报。",
            "actual_result": None, "experiment_id": None})
        added = self.json_command("feedback-diagnose", original["id"], spec)
        result = self.json_command("feedback-show", original["id"])
        self.assertEqual(result["feedback"]["text"], note.read_text(encoding="utf-8"))
        self.assertEqual(result["feedback"]["revision"], revision)
        self.assertEqual(result["diagnoses"], [added])

    def test_external_submission_requires_and_binds_attempt(self):
        task = self.create_task()
        self.json_command("task-claim", task["id"])
        result_path = self.json_file("external-result.json", self.result(task))
        self.command("task-submit", task["id"], result_path, expected=2)
        self.json_command("task-recover", task["id"], "--note", "工程夹具执行者已停止")
        self.json_command("task-resume", task["id"], "--note", "工程夹具明确接续")
        second = self.json_command("task-claim", task["id"])
        self.assertEqual(second["attempts"], 2)
        self.assertEqual(second["input_revision"], task["input_revision"])
        stale = self.error_command("task-submit", task["id"], result_path, "--expected-attempt", "1")
        self.assertIn("superseded", stale["error"])
        self.assertIsNone(self.json_command("task-show", task["id"])["result"])
        for invalid in ("0", "-1"):
            self.error_command("task-submit", task["id"], result_path, "--expected-attempt", invalid)
        # A newly prepared second-attempt fixture; identical content is allowed, identity is explicit.
        second_path = self.json_file("external-result-attempt-2.json", self.result(second))
        submitted = self.json_command("task-submit", task["id"], second_path, "--expected-attempt", "2")
        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(self.json_command("task-submit", task["id"], second_path, "--expected-attempt", "2"), submitted)
        self.error_command("task-submit", task["id"], result_path, "--expected-attempt", "1")
        self.assertEqual(self.json_command("task-publish", task["id"])["status"], "completed")

    def test_bad_json_and_duplicate_keys_fail_without_submitting(self):
        task = self.create_task()
        self.json_command("task-claim", task["id"])
        for name, content in (
            ("duplicate.json", '{"task_id": "first", "task_id": "second"}'),
            ("malformed.json", '{"task_id":'),
        ):
            with self.subTest(name=name):
                path = self.text_file(name, content, bom=True)
                error = self.error_command("task-submit", task["id"], path, "--expected-attempt", "1")
                self.assertEqual(error["type"], "ValidationError")
                if name == "duplicate.json":
                    self.assertIn("duplicate", error["error"].lower())
                current = self.json_command("task-show", task["id"])
                self.assertEqual(current["status"], "running")
                self.assertIsNone(current["result"])
        self.assertEqual(self.json_command("book-show", "cli-book")["current_revision"], self.book["current_revision"])

    def test_wrong_root_returns_nonzero_and_does_not_initialize_it(self):
        missing = self.root / "未初始化的目录"
        error = self.error_command("books", root=missing)
        self.assertEqual(error["type"], "EngineError")
        self.assertIn("not initialized", error["error"])
        self.assertFalse(missing.exists())
        self.assertEqual(len(self.json_command("books")), 1)

    def test_operator_decision_and_reference_import_preserve_exact_text(self):
        imports = (
            ("decision", "decisions/", "  作者原话：这一点暂不决定。\n\n不要改写本句。  \n"),
            ("reference-import", "reference/", "  参考原文：候选方案不等于新作品事实。\n保留引号“原话”。  \n"),
        )
        for command, prefix, source in imports:
            with self.subTest(command=command):
                text_path = self.text_file(f"{command} 原文.txt", source, bom=True)
                imported = self.json_command(command, "cli-book", "--text-file", text_path)
                self.assertEqual(imported["text"], source)
                self.assertTrue(imported["path"].startswith(prefix))
                self.assertEqual(self.command("read", "cli-book", imported["path"]).stdout, source)
                self.assertEqual(self.json_command("book-show", "cli-book")["current_revision"], imported["revision"])
        canon = json.loads(self.command("read", "cli-book", "canon/state.json").stdout)
        self.assertEqual(canon, EMPTY_STATE)
        self.assertEqual(self.json_command("audit")["snapshots_verified"], 3)

    def test_evaluation_cli_routes_blind_feedback_and_summary(self):
        spec = {
            "id": "cli-method",
            "hypothesis": "验收假说：不同方法的反馈应可分开保留。",
            "baseline_method": "测试基准方法",
            "candidate_method": "测试候选方法",
            "cases": [
                {"id": "development", "split": "development", "input": "开发案例输入",
                 "baseline_output": "开发基准文本", "candidate_output": "开发候选文本"},
                {"id": "holdout", "split": "holdout", "input": "留出案例输入",
                 "baseline_output": "留出基准文本", "candidate_output": "留出候选文本"},
            ],
        }
        created = self.json_command("eval-create", self.json_file("对照案例.json", spec))
        self.assertEqual(created["id"], spec["id"])
        self.assertEqual(created["case_count"], 2)
        blind = self.json_command("eval-blind", spec["id"])
        self.assertEqual(blind, self.json_command("eval-blind", spec["id"]))
        for case in blind["cases"]:
            self.assertEqual(set(case), {"id", "split", "input", "A", "B"})
            self.assertNotEqual(case["A"], case["B"])
        initial = self.json_command("eval-summary", spec["id"])
        self.assertFalse(initial["retain_eligible"])
        self.assertIsNone(initial["latest_decision"])

        rationale = "  验收用反馈原话：各有长短。\n这不是实际读者评价。  \n"
        rationale_file = self.text_file("反馈 原话.txt", rationale, bom=True)
        for case, reviewer in (("development", "agent"), ("holdout", "author")):
            judged = self.json_command("eval-judge", spec["id"], case, "tie", "--reviewer", reviewer,
                                       "--rationale-file", rationale_file)
            self.assertEqual(judged["rationale"], rationale)
            self.assertEqual(judged["reviewer"], reviewer)
        trial = self.json_command("eval-decide", spec["id"], "trial", "--note", "验收暂用流程，不宣称改进")
        self.assertEqual(trial["action"], "trial")
        summary = self.json_command("eval-summary", spec["id"])
        self.assertEqual(summary["groups"]["development"]["counts_by_reviewer"]["agent"]["tie"], 1)
        self.assertEqual(summary["groups"]["holdout"]["counts_by_reviewer"]["author"]["tie"], 1)
        self.assertEqual(summary["latest_decision"]["id"], trial["id"])
        self.assertFalse(summary["retain_eligible"])
        self.error_command("eval-decide", spec["id"], "retain", "--note", "没有胜出证据时不能保留")

    def test_recover_resume_and_stop_keep_state_across_processes(self):
        task = self.create_task()
        self.json_command("task-claim", task["id"])
        recovered = self.json_command("task-recover", task["id"], "--note", "前一进程中断，显式接续")
        self.assertEqual(recovered["status"], "blocked")
        self.assertEqual(recovered["stop_reason"], "tool_failure")
        self.assertEqual(self.json_command("task-show", task["id"])["attempts"], 1)
        handoff = self.json_command("handoff", task["id"])
        self.assertEqual(handoff["task"]["status"], "blocked")
        self.error_command("task-claim", task["id"])
        resumed = self.json_command("task-resume", task["id"], "--note", "条件已恢复，允许有限重试")
        self.assertEqual(resumed["status"], "queued")
        self.assertEqual(resumed["attempts"], 1)
        self.assertEqual(self.json_command("task-claim", task["id"])["attempts"], 2)
        stopped = self.json_command("task-stop", task["id"], "quota", "--note", "配额不足，保留停止原因")
        self.assertEqual(stopped["stop_reason"], "quota")
        cancelled = self.json_command("task-cancel", task["id"], "--note", "明确取消此次验收任务")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["attempts"], 2)

    def test_missing_file_and_unknown_task_return_structured_errors(self):
        self.assertEqual(self.error_command("read", "cli-book", "manuscript/missing.md")["type"], "ValueError")
        self.assertEqual(self.error_command("task-show", "unknown-task")["type"], "EngineError")
        self.assertEqual(self.json_command("book-show", "cli-book"), self.book)
        self.assertEqual(self.json_command("tasks", "--book", "cli-book"), [])


if __name__ == "__main__":
    unittest.main()
