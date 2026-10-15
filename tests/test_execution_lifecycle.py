"""Real SQLite/thread regressions; fake CLI output is not model evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch

from novel import adapter, cli
from novel.engine import Engine, EngineError, EMPTY_STATE


class ExecutionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-execution-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = Engine.initialize(self.root)
        self.engine.create_book("sample", "Engineering input, not an author work")
        self.ready = {"ready": True, "chatgpt_login": True,
                      "model_defaults": {"model": "fixture-only", "reasoning_effort": "high"}}

    def task(self, kind="review"):
        return self.engine.enqueue("sample", kind, "Exercise the execution lifecycle")

    def result(self, task, changes=None):
        return {
            "task_id": task["id"], "input_revision": task["input_revision"],
            "completed_steps": ["Deterministic executor fixture"], "next_step": "Inspect candidate",
            "unresolved": [], "changes": changes or [],
            "review": {"coverage": ["canon/state.json"],
                       "dimensions": ["continuity", "character", "world", "reading"],
                       "findings": []} if task["kind"] == "review" else None,
            "affected_paths": [item["path"] for item in changes or []], "state_notes": "Engineering fixture",
        }

    def process_factory(self, result, started=None, release=None):
        def spawn(command, **kwargs):
            process = Mock()
            process.pid = 4321
            process.returncode = 0
            def communicate(prompt, timeout=None):
                if started:
                    started.set()
                    if not release.wait(15):
                        raise RuntimeError("Test did not release the fake executor")
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text(json.dumps(result), encoding="utf-8")
            process.communicate.side_effect = communicate
            return process
        return spawn

    def seed(self):
        task = self.engine.claim(self.task("write")["id"])
        changes = [{"path": "manuscript/001.md", "content": "Seed input."},
                   {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE)}]
        self.engine.submit(task["id"], self.result(task, changes))
        self.engine.publish(task["id"])

    def test_concurrent_duplicate_does_not_stop_owner_or_change_its_log(self):
        task = self.task()
        entered, release = Event(), Event()
        with patch.object(adapter, "doctor", return_value=self.ready), \
             patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(self.result(task), entered, release)) as popen, \
             ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(adapter.run_and_submit, self.engine, task["id"])
            try:
                self.assertTrue(entered.wait(15))
                directory = self.root / "runtime/tasks" / task["id"] / "attempt-1"
                before = {p.name: p.read_bytes() for p in directory.iterdir()}
                with self.assertRaises(adapter.AdapterError):
                    adapter.run(self.engine, task["id"])
                self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
                current = self.engine.task(task["id"])
                self.assertEqual((current["status"], current["attempts"], current["no_progress"]), ("running", 1, 0))
            finally:
                release.set()
            self.assertEqual(future.result(timeout=15)["status"], "submitted")
            self.assertEqual(popen.call_count, 1)
        self.assertEqual(self.engine.task(task["id"])["no_progress"], 0)
        self.engine.publish(task["id"])
        self.engine.audit()

    def test_changed_controls_rejected_by_prepare_and_before_preflight(self):
        task = self.engine.claim(self.task()["id"])
        path = self.root / "methods/review.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged control.\n", encoding="utf-8")
        with self.assertRaisesRegex(EngineError, "Policies or methods"):
            adapter.prepare(self.engine, task["id"])
        self.assertFalse((self.root / "runtime/tasks").exists())
        with patch.object(adapter, "doctor") as doctor, patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, task["id"])
            doctor.assert_not_called()
            popen.assert_not_called()
        self.assertEqual(self.engine.task(task["id"])["status"], "blocked")

    def test_new_revision_before_execution_prevents_launch(self):
        task = self.engine.claim(self.task()["id"])
        writer = self.engine.claim(self.task("revise")["id"])
        changes = [{"path": "manuscript/001.md", "content": "A newer revision."},
                   {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE)}]
        self.engine.submit(writer["id"], self.result(writer, changes))
        self.engine.publish(writer["id"])
        with patch.object(adapter, "doctor") as doctor, patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(adapter.AdapterError, "Stale input"):
                adapter.run(self.engine, task["id"])
            doctor.assert_not_called()
            popen.assert_not_called()

    def test_controls_changed_during_preflight_prevent_launch(self):
        task = self.task()
        def doctor(_):
            path = self.root / "methods/review.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nChanged during probe.\n", encoding="utf-8")
            return self.ready
        with patch.object(adapter, "doctor", side_effect=doctor), patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaises(adapter.AdapterError):
                adapter.run(self.engine, task["id"])
            popen.assert_not_called()
        self.assertEqual(self.engine.task(task["id"])["status"], "blocked")

    def test_superseded_during_preflight_does_not_stop_next_attempt(self):
        task = self.task()
        def doctor(_):
            self.engine.recover(task["id"], "No process launched; replace this test attempt")
            self.engine.resume(task["id"], "Explicit test recovery")
            self.engine.claim(task["id"])
            return self.ready
        with patch.object(adapter, "doctor", side_effect=doctor), patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(adapter.AdapterError, "superseded"):
                adapter.run(self.engine, task["id"])
            popen.assert_not_called()
        current = self.engine.task(task["id"])
        self.assertEqual((current["status"], current["attempts"], current["no_progress"]), ("running", 2, 0))

    def test_no_effect_result_stops_and_keeps_raw_output_and_counters(self):
        self.seed()
        task = self.task("revise")
        files = self.engine.files("sample")
        result = self.result(task, [{"path": p, "content": text} for p, text in files.items()])
        args = cli.parser().parse_args(["--root", str(self.root), "task-run", task["id"]])
        with patch.object(adapter, "doctor", return_value=self.ready), \
             patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(result)) as popen:
            with self.assertRaises(adapter.AdapterError) as error:
                cli.execute(args)
            self.assertEqual(error.exception.reason, "no_progress")
            stopped = Engine(self.root).task(task["id"])
            self.assertEqual((stopped["status"], stopped["attempts"], stopped["no_progress"]), ("blocked", 1, 1))
            output = self.root / "runtime/tasks" / task["id"] / "attempt-1/result.json"
            self.assertEqual(json.loads(output.read_text()), result)
            self.assertIsNone(stopped["result"])
            self.assertEqual(self.engine.book("sample")["current_revision"], task["input_revision"])
            self.engine.resume(task["id"], "Explicitly test cumulative second no-progress result")
            with self.assertRaises(adapter.AdapterError):
                cli.execute(args)
            exhausted = Engine(self.root).task(task["id"])
            self.assertEqual((exhausted["status"], exhausted["attempts"], exhausted["no_progress"]), ("exhausted", 2, 2))
            self.assertEqual(popen.call_count, 2)
            self.assertEqual(json.loads(output.read_text()), result)

    def test_size_rejection_stops_as_tool_failure(self):
        path = self.root / "policies/limits.json"
        limits = json.loads(path.read_text())
        limits["max_result_bytes"] = 1024
        path.write_text(json.dumps(limits), encoding="utf-8")
        task = self.task()
        result = self.result(task)
        result["completed_steps"] = ["x" * 2048]
        with patch.object(adapter, "doctor", return_value=self.ready), \
             patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(result)):
            with self.assertRaisesRegex(adapter.AdapterError, "size limit"):
                adapter.run_and_submit(self.engine, task["id"])
        current = self.engine.task(task["id"])
        self.assertEqual((current["status"], current["stop_reason"], current["no_progress"]), ("blocked", "tool_failure", 0))
        self.assertIsNone(current["result"])

    def test_late_submission_failure_cannot_stop_newer_attempt(self):
        task = self.task()
        original_submit = self.engine.submit
        def submit(*args, **kwargs):
            self.engine.recover(task["id"], "Executor returned; simulate explicit recovery at submission boundary")
            self.engine.resume(task["id"], "Test next attempt")
            self.engine.claim(task["id"])
            return original_submit(*args, **kwargs)
        with patch.object(adapter, "doctor", return_value=self.ready), \
             patch.object(adapter.subprocess, "Popen", side_effect=self.process_factory(self.result(task))), \
             patch.object(self.engine, "submit", side_effect=submit):
            with self.assertRaisesRegex(adapter.AdapterError, "superseded"):
                adapter.run_and_submit(self.engine, task["id"])
        current = self.engine.task(task["id"])
        self.assertEqual((current["status"], current["attempts"], current["no_progress"]), ("running", 2, 0))

    def test_late_stop_preserves_submitted_and_cancelled_states(self):
        task = self.engine.claim(self.task()["id"])
        self.engine.submit(task["id"], self.result(task))
        before = self.engine.task(task["id"])
        audit = self.engine.audit()
        self.engine.block(task["id"], "no_progress", "Stale failure callback", expected_attempt=1)
        self.assertEqual(self.engine.task(task["id"]), before)
        self.assertEqual(self.engine.audit(), audit)
        self.engine.cancel(task["id"], "Explicit cancellation")
        before = self.engine.task(task["id"])
        self.engine.block(task["id"], "tool_failure", "Stale failure callback", expected_attempt=1)
        self.assertEqual(self.engine.task(task["id"]), before)

    def test_wrapper_does_not_switch_to_an_attempt_resumed_before_run(self):
        task = self.task()
        original_task = self.engine.task
        calls = 0
        def read(task_id):
            nonlocal calls
            calls += 1
            if calls == 2:
                other = Engine(self.root)
                other.claim(task_id)
                other.recover(task_id, "No executor launched in this fixture")
                other.resume(task_id, "Explicitly queued next test attempt")
            return original_task(task_id)
        with patch.object(self.engine, "task", side_effect=read), patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(ValueError, "superseded"):
                adapter.run_and_submit(self.engine, task["id"])
            popen.assert_not_called()
        current = original_task(task["id"])
        self.assertEqual((current["status"], current["attempts"]), ("queued", 1))
        self.assertFalse((self.root / "runtime/tasks").exists())

    def test_claim_checks_expected_counter_under_its_write_transaction(self):
        task = self.task()
        original_claim = self.engine.claim
        def claim(task_id, **kwargs):
            other = Engine(self.root)
            other.claim(task_id)
            other.recover(task_id, "No executor launched in this fixture")
            other.resume(task_id, "Explicitly queued next test attempt")
            return original_claim(task_id, **kwargs)
        with patch.object(self.engine, "claim", side_effect=claim), patch.object(adapter.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(EngineError, "superseded"):
                adapter.run(self.engine, task["id"])
            popen.assert_not_called()
        current = self.engine.task(task["id"])
        self.assertEqual((current["status"], current["attempts"]), ("queued", 1))

    def test_started_log_failure_terminates_real_owned_process(self):
        import subprocess
        import sys
        task = self.task()
        original_popen = subprocess.Popen
        original_event = adapter._event
        processes = []
        def spawn(command, **kwargs):
            if command[0] != "codex":
                return original_popen(command, **kwargs)
            process = original_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
            processes.append(process)
            return process
        def event(directory, kind, **details):
            if kind == "started":
                raise OSError("Injected log write failure after spawn")
            return original_event(directory, kind, **details)
        try:
            with patch.object(adapter, "doctor", return_value=self.ready), \
                 patch.object(adapter.subprocess, "Popen", side_effect=spawn), \
                 patch.object(adapter, "_event", side_effect=event):
                with self.assertRaisesRegex(adapter.AdapterError, "process tree was stopped"):
                    adapter.run(self.engine, task["id"])
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())
            self.assertTrue(processes[0].stdin.closed)
            self.assertEqual(self.engine.task(task["id"])["status"], "blocked")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)

    def test_manual_rejected_submit_can_still_be_corrected_without_reclaim(self):
        self.seed()
        task = self.engine.claim(self.task("revise")["id"])
        files = self.engine.files("sample")
        result = self.result(task, [{"path": p, "content": text} for p, text in files.items()])
        with self.assertRaises(EngineError):
            self.engine.submit(task["id"], result)
        self.assertEqual(self.engine.task(task["id"])["status"], "running")
        for change in result["changes"]:
            if change["path"].startswith("manuscript/"):
                change["content"] += " Corrected."
        self.assertEqual(self.engine.submit(task["id"], result)["status"], "submitted")


if __name__ == "__main__":
    unittest.main()
