"""Claims consult retained peer evidence; all data is synthetic."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import unittest
from unittest.mock import patch

from novel import exchange
from novel.engine import Engine, EngineError
import test_exchange as fixtures


class ExchangeGateTests(unittest.TestCase):
    setUp = fixtures.ExchangeTests.setUp
    package = fixtures.ExchangeTests.package

    def test_no_inbox_and_matching_inbox_compatible_with_later_local_progress(self):
        self.assertEqual(self.a.claim(self.task['id'])['attempts'], 1)
        exchange.receive(self.b, self.base)
        self.assertEqual(self.b.claim(self.task['id'])['attempts'], 1)
        self.b.cancel(self.task['id'], '合成完成处理')
        next_task = self.b.enqueue('sample', 'review', '后续独立工作')
        self.assertEqual(self.b.claim(next_task['id'])['status'], 'running')
        with self.b._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE event='exchange.baseline_checked'").fetchone()[0], 1)

    def test_ahead_diverged_and_unknown_all_reject_without_attempt_increment(self):
        (self.a.root / self.artifact).write_text('本地第二版', encoding='utf-8')
        package = self.package(self.a, 'ahead')
        exchange.receive(self.b, package, self.base)
        with self.assertRaisesRegex(EngineError, 'Unreconciled'):
            self.b.claim(self.task['id'])
        (self.b.root / self.artifact).write_text('不同的云端版本', encoding='utf-8')
        with self.assertRaises(EngineError):
            self.b.claim(self.task['id'])
        self.assertEqual(self.b.task(self.task['id'])['attempts'], 0)
        self.assertEqual(self.b.task(self.task['id'])['status'], 'queued')

    def test_completed_peer_task_is_never_claimed(self):
        claimed = self.a.claim(self.task['id'])
        self.a.submit(claimed['id'], {
            'task_id': claimed['id'], 'input_revision': claimed['input_revision'],
            'completed_steps': ['合成审核'], 'next_step': '等待反馈', 'unresolved': [],
            'changes': [], 'affected_paths': [], 'state_notes': '只读',
            'review': {'coverage': ['canon/state.json'], 'dimensions': ['continuity', 'character', 'world', 'reading'], 'findings': []}}, expected_attempt=1)
        self.a.publish(claimed['id'])
        package = self.package(self.a, 'finished')
        exchange.receive(self.b, package)
        with self.assertRaisesRegex(EngineError, 'already finished'):
            self.b.claim(self.task['id'])

    def test_new_evidence_rechecked_and_verified_successor_can_reconcile_old(self):
        exchange.receive(self.b, self.base)
        (self.a.root / self.artifact).write_text('曾经不同', encoding='utf-8')
        older = self.package(self.a, 'old')
        exchange.receive(self.b, older)
        with self.assertRaises(EngineError):
            self.b.claim(self.task['id'])
        (self.a.root / self.artifact).write_bytes((self.b.root / self.artifact).read_bytes())
        newer = self.root / 'new.json'
        exchange.create(self.a, {**self.spec, 'operation_id':'new'}, newer, older)
        exchange.receive(self.b, newer, older)
        self.assertEqual(self.b.claim(self.task['id'])['attempts'], 1)
        self.b.cancel(self.task['id'], '结束')
        task2 = self.b.enqueue('sample', 'review', '另一个任务')
        self.a.claim(self.task['id'])
        fresh = self.package(self.a, 'peer-running')
        exchange.receive(self.b, fresh)
        with self.assertRaisesRegex(EngineError, 'active/stopped'):
            self.b.claim(task2['id'])

    def test_late_peer_evidence_blocks_prepare_and_run_before_doctor(self):
        from novel import adapter
        self.b.claim(self.task['id'])
        self.a.claim(self.task['id'])
        self.a.block(self.task['id'], 'no_progress', '保留停止')
        package = self.package(self.a, 'late-stop')
        exchange.receive(self.b, package)
        with self.assertRaises(EngineError):
            adapter.prepare(self.b, self.task['id'])
        with patch.object(adapter, 'doctor') as doctor:
            with self.assertRaises(EngineError):
                adapter.run(self.b, self.task['id'])
            doctor.assert_not_called()
        self.assertEqual(self.b.task(self.task['id'])['attempts'], 1)
        self.assertEqual(self.b.task(self.task['id'])['status'], 'running')

    def test_failed_claim_rolls_back_ack_and_successor_cannot_reset_counters(self):
        exchange.receive(self.b, self.base)
        self.a.claim(self.task['id'])
        self.a.block(self.task['id'], 'no_progress', '保留次数')
        stopped = self.package(self.a, 'z-stopped')
        exchange.receive(self.b, stopped)
        with self.assertRaises(EngineError):
            self.b.claim(self.task['id'])
        with self.b._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE event='exchange.baseline_checked'").fetchone()[0], 0)
        reset = self.root / 'reset.json'
        exchange.create(self.b, {**self.spec, 'operation_id': 'reset'}, reset, stopped)
        exchange.receive(self.b, reset)
        with self.assertRaisesRegex(EngineError, 'resets cumulative'):
            self.b.claim(self.task['id'])

    def test_peer_evidence_arriving_during_probe_prevents_spawn_and_releases_reservation(self):
        from novel import adapter
        self.b.claim(self.task['id'])
        def doctor(_):
            self.a.claim(self.task['id'])
            self.a.block(self.task['id'], 'no_progress', 'Peer stopped during probe')
            exchange.receive(self.b, self.package(self.a, 'during-probe'))
            return {'ready': True, 'chatgpt_login': True,
                    'model_defaults': {'model': 'fixture-only', 'reasoning_effort': 'high'}}
        with patch.object(adapter, 'doctor', side_effect=doctor), patch.object(adapter.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(EngineError, 'active/stopped'):
                adapter.run(self.b, self.task['id'])
            popen.assert_not_called()
        marker = self.b.root / 'runtime/tasks' / self.task['id'] / 'attempt-1/execution-started.json'
        self.assertFalse(marker.exists())
        self.assertEqual(self.b.task(self.task['id'])['status'], 'running')
        self.assertEqual(self.b.task(self.task['id'])['attempts'], 1)

    def test_tampered_inbox_fails_closed(self):
        receipt = exchange.receive(self.b, self.base)['receipt']
        path = self.b.root / receipt['path']
        path.write_text('{}', encoding='utf-8')
        with self.assertRaises(EngineError):
            self.b.claim(self.task['id'])
        self.assertEqual(self.b.task(self.task['id'])['attempts'], 0)

    def test_receive_serializes_with_claim(self):
        self.a.claim(self.task['id'])
        self.a.block(self.task['id'], 'no_progress', '保留停止')
        package = self.package(self.a, 'stop')
        entered, release, claiming = Event(), Event(), Event()
        write = self.b._new_file
        def delayed(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test synchronization timed out')
            return write(*args)
        def claim():
            claiming.set()
            return Engine(self.b.root).claim(self.task['id'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            with patch.object(self.b, '_new_file', side_effect=delayed):
                receiving = pool.submit(exchange.receive, self.b, package)
                self.assertTrue(entered.wait(5))
                attempting = pool.submit(claim)
                self.assertTrue(claiming.wait(5))
                self.assertFalse(attempting.done())
                release.set()
                receiving.result(timeout=10)
                with self.assertRaisesRegex(EngineError, 'active/stopped'):
                    attempting.result(timeout=10)
        self.assertEqual(self.b.task(self.task['id'])['attempts'], 0)
