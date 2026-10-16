"""Explicit draft adoption in synthetic offline roots, never real user transfer."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from novel import exchange
from novel.engine import Engine, EngineError, EMPTY_STATE


class ApplyTests(unittest.TestCase):
    def write_result(self, engine, task, text):
        result = {'task_id':task['id'], 'input_revision':task['input_revision'],
                  'completed_steps':['合成修改'], 'next_step':'独立审核', 'unresolved':[],
                  'changes':[{'path':'manuscript/001.md','content':text},
                             {'path':'canon/state.json','content':json.dumps(EMPTY_STATE)}],
                  'affected_paths':['manuscript/001.md','canon/state.json'], 'review':None,'state_notes':'合成'}
        engine.submit(task['id'], result, expected_attempt=task['attempts'])
        return engine.publish(task['id'])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='.novel-apply-test-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.a = Engine.initialize(self.root/'a')
        self.a.create_book('test', '合成')
        first = self.a.claim(self.a.enqueue('test','write','合成第一版')['id'])
        self.write_result(self.a, first, '旧版原文')
        self.feedback = self.a.feedback('test','合成原始反馈：不能因修改丢失历史')
        self.task = self.a.enqueue('test','revise','合成定向返修')
        self.base_revision = self.task['input_revision']
        shutil.copytree(self.a.root, self.root/'b')
        self.b = Engine(self.root/'b')
        self.spec = {'origin':'local','operation_id':'base','task_ids':[self.task['id']], 'artifacts':[],
                     'verification':'合成工程测试', 'unresolved':['真实作品未验收'], 'next_step':'对照', 'excluded':['其他资料']}
        self.base = self.root/'base.json'
        exchange.create(self.a,self.spec,self.base)
        self.a.claim(self.task['id'])
        self.a.block(self.task['id'],'tool_failure','合成首次失败，必须保留')
        self.a.resume(self.task['id'],'合成修复证据')
        self.peer = self.write_result(self.a,self.a.claim(self.task['id']),'新版候选')
        self.target = self.peer['result_revision']
        self.package = self.root/'result.json'
        exchange.create(self.a,{**self.spec,'operation_id':'result'},self.package,self.base)
        exchange.receive(self.b,self.package,self.base)

    def apply(self, **kwargs):
        return exchange.apply(self.b, self.package, self.task['id'], self.base,
                              kwargs.get('base',self.base_revision),kwargs.get('target',self.target))

    def test_adopts_draft_preserves_history_feedback_and_is_idempotent(self):
        before = self.b.files('test')
        with self.b._db() as db:
            original_events = [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id')]
        self.assertFalse(self.apply()['duplicate'])
        self.assertEqual(self.b.book('test')['status'],'draft')
        self.assertEqual(self.b.files('test')['manuscript/001.md'],'新版候选')
        self.assertEqual(self.b.files('test',self.base_revision),before)
        self.assertEqual(self.b.task(self.task['id'])['attempts'],2)
        with self.b._db() as db:
            self.assertEqual(db.execute('SELECT text FROM feedback WHERE id=?',(self.feedback['id'],)).fetchone()[0],self.feedback['text'])
            history = [json.loads(r['payload'])['source_event'] for r in db.execute("SELECT payload FROM events WHERE event='exchange.peer_event'")]
            self.assertTrue(any(r['event']=='task.stopped' and '合成首次失败' in r['payload'] for r in history))
            count = db.execute('SELECT count(*) FROM events').fetchone()[0]
        with self.b._db() as db:
            self.assertEqual([dict(r) for r in db.execute('SELECT * FROM events ORDER BY id')][:len(original_events)],original_events)
        self.assertTrue(self.apply()['duplicate'])
        with self.b._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],count)
        self.assertEqual(self.b.audit()['database'],'ok')
        next_task = self.b.enqueue('test','review','接续独立审核')
        self.assertEqual(self.b.claim(next_task['id'])['status'],'running')

    def test_conflicts_wrong_target_and_local_stops_rejected(self):
        with self.assertRaises(EngineError):
            self.apply(target='0'*64)
        self.b.feedback('test','本地并发新反馈')
        with self.assertRaisesRegex(EngineError,'diverged'):
            self.apply()
        self.assertEqual(self.b.book('test')['current_revision'],self.base_revision)
        # A local stopped task may not be silently completed by incoming success.
        with self.b._db(True) as db:
            db.execute("UPDATE tasks SET status='blocked',stop_reason='decision' WHERE id=?",(self.task['id'],))
        with self.assertRaisesRegex(EngineError,'queued'):
            self.apply()

    def test_legacy_package_readable_but_cannot_apply_without_failure_history(self):
        obj = exchange._read(self.package)
        obj['record']['schema_version'] = 1
        del obj['record']['capture']['task_events']
        obj['record']['state'] = exchange._state(obj['record']['capture'])
        obj['id'] = exchange._sha(obj['record'])
        self.package.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
        self.assertEqual(exchange._read(self.package)['record']['schema_version'],1)
        with self.assertRaisesRegex(EngineError,'v2'):
            self.apply()

    def test_apply_rejects_other_unreconciled_inbox_work(self):
        later = self.a.enqueue('test','review','对端后续审核')
        self.a.claim(later['id'])
        spec = {**self.spec, 'operation_id':'other-active', 'task_ids':[later['id']]}
        other = self.root/'other.json'
        exchange.create(self.a,spec,other)
        exchange.receive(self.b,other)
        with self.assertRaisesRegex(EngineError,'active/stopped'):
            self.apply()
        self.assertEqual(self.b.book('test')['current_revision'],self.base_revision)

    def test_cli_apply_uses_required_expected_versions(self):
        import subprocess, sys
        command = [sys.executable, '-m', 'novel', '--root', str(self.b.root), 'bundle-apply',
                   str(self.package), self.task['id'], '--baseline', str(self.base),
                   '--expected-base', self.base_revision, '--expected-target', self.target]
        for duplicate in (False,True):
            process = subprocess.run(command,cwd=Path(__file__).resolve().parents[1],
                                     capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(process.stdout)['duplicate'],duplicate)

    def test_failure_after_snapshot_rolls_back_and_retry_reuses_orphan(self):
        write = self.b._event
        def fail(db, event, *args, **kwargs):
            if event == 'exchange.applied':
                raise OSError('simulated commit-phase interruption')
            return write(db,event,*args,**kwargs)
        with patch.object(self.b,'_event',side_effect=fail):
            with self.assertRaises(OSError):
                self.apply()
        self.assertEqual(self.b.book('test')['current_revision'],self.base_revision)
        self.assertEqual(self.b.task(self.task['id'])['status'],'queued')
        self.assertEqual(self.b.task(self.task['id'])['attempts'],0)
        self.assertTrue((self.b.root/f'books/test/versions/{self.target}').exists())
        with self.b._db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE event LIKE 'exchange.%'").fetchone()[0],0)
        self.assertFalse(self.apply()['duplicate'])
        self.assertEqual(self.b.audit()['database'],'ok')

    def test_cannot_apply_unreceived_or_review_or_author_decision(self):
        received = self.b.root/'runtime/exchange/inbox/local/result.json'
        saved = received.read_bytes()
        received.unlink()
        with self.assertRaises(OSError):
            self.apply()
        received.write_bytes(saved)
        # Re-seal a synthetic packet: even a consistent envelope cannot authorize decisions.
        obj = exchange._read(self.package)
        task = obj['record']['capture']['tasks'][self.task['id']]['task']
        task['result']['changes'].append({'path':'decisions/forged.md','content':'未经作者确认'})
        task['result']['affected_paths'].append('decisions/forged.md')
        task['result_hash']=exchange._sha(task['result'])
        obj['record']['state']=exchange._state(obj['record']['capture'])
        obj['id']=exchange._sha(obj['record'])
        content=json.dumps(obj,ensure_ascii=False)
        self.package.write_text(content,encoding='utf-8')
        received.write_text(content,encoding='utf-8')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.b.book('test')['current_revision'],self.base_revision)
