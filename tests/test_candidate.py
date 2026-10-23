"""Synthetic candidate amendment regressions; never touches production books."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import test_context as fixtures
from novel.candidate import FORMAT
from novel.dot import DotWorkspace
from novel.engine import EngineError, canonical, digest


class CandidateTests(unittest.TestCase):
    for _name in ('setUp', 'request', 'open', 'read_all', 'send', 'checkpoint', 'result'):
        locals()[_name] = getattr(fixtures.StagedDotTests, _name)

    def prepare(self):
        task = self.open()
        plan = json.loads(self.read_all(task, 'context-plan.json'))
        for batch in plan['batches']:
            self.send(task, self.checkpoint(task, plan, batch))
        original = self.result(task, plan)
        upload, finish = self.upload(task, original)
        self.original_finish = finish
        self.dot.finish(**finish)
        task = self.engine.task(task['id'])
        amended = deepcopy(original)
        amended['result']['changes'][0]['content'] += ' The recipient opened it.'
        amended['state_delta']['operations'][0]['set']['statement'] = 'The recipient opened the letter.'
        return task, {'format': FORMAT, 'task_id': task['id'], 'attempt': task['attempts'],
            'input_revision': task['input_revision'], 'expected_result_hash': task['result_hash'],
            'reason': 'Clarify synthetic recipient action.', 'candidate': amended}

    def upload(self, task, value):
        raw = canonical(value)
        parts = [raw[i:i+6000] for i in range(0, len(raw), 6000)]
        upload = self.request()
        for part, content in enumerate(parts):
            self.dot.chunk(request_id=self.request(), task_id=task['id'], attempt=task['attempts'],
                upload_id=upload, part=part, total=len(parts), content=content)
        return upload, dict(request_id=self.request(), task_id=task['id'], attempt=task['attempts'], upload_id=upload)

    def preserved(self):
        with self.dot._db() as db:
            return {t: [tuple(r) for r in db.execute('SELECT * FROM '+t)]
                    for t in ('tasks', 'parts', 'context_reads', 'context_checkpoints', 'requests')}

    def test_amend_history_replay_and_preserved_business(self):
        task, payload = self.prepare()
        snapshot = self.engine.files('fixture')
        book = self.engine.book('fixture')
        packet = self.read_all(task, 'packet-index.json')
        progress = self.read_all(task, 'context-progress.json')
        old = self.read_all(task, 'result.json')
        prior = self.preserved()
        _, finish = self.upload(task, payload)
        receipt = self.dot.finish(**finish)
        current = self.engine.task(task['id'])
        self.assertTrue(receipt['amended'])
        self.assertFalse(receipt['published'])
        for key in task:
            if key not in {'result','result_hash','updated_at'}:
                self.assertEqual(task[key], current[key], key)
        self.assertEqual(book, self.engine.book('fixture'))
        self.assertEqual(snapshot, self.engine.files('fixture'))
        self.assertEqual(packet, self.read_all(task, 'packet-index.json'))
        self.assertEqual(progress, self.read_all(task, 'context-progress.json'))
        for table, rows in prior.items():
            after = self.preserved()[table]
            self.assertTrue(all(row in after for row in rows), table)
        history = json.loads(self.read_all(task, 'candidate-history.json'))
        self.assertEqual(len(history['amendments']), 1)
        self.assertEqual(history['amendments'][0]['reason'], payload['reason'])
        self.assertEqual(old, self.read_all(task, 'candidates/'+task['result_hash']+'.json'))
        self.assertEqual(self.read_all(task, 'result.json'), self.read_all(task, 'candidates/'+current['result_hash']+'.json'))
        self.assertTrue(self.dot.finish(**finish)['replayed'])
        self.assertTrue(self.dot.finish(**self.original_finish)['replayed'])
        self.assertEqual(current, self.engine.task(task['id']))
        with self.assertRaises(ValueError):
            self.dot.finish(**{**self.original_finish, 'request_id': self.request()})
        self.assertEqual(current, self.engine.task(task['id']))
        self.dot = DotWorkspace(self.temp.name, 'fixture')
        self.assertEqual(history, json.loads(self.read_all(task, 'candidate-history.json')))

    def test_stale_identity_and_hash_rejected_atomically(self):
        task, payload = self.prepare()
        for key, value in [('expected_result_hash', '0'*64), ('input_revision','0'*64), ('attempt',2), ('task_id','another')]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError): self.send(task, {**payload,key:value})
                self.assertEqual(task, self.engine.task(task['id']))
        self.assertEqual([], json.loads(self.read_all(task,'candidate-history.json'))['amendments'])

    def test_current_revision_rechecked_in_transaction(self):
        task, payload = self.prepare()
        # Change only the transaction's freshness observation, without inventing a version.
        original = self.dot.engine._row
        def changed(db, table, key):
            row = original(db, table, key)
            return {**row, 'current_revision':'0'*64} if table == 'books' else row
        with patch.object(self.dot.engine, '_row', side_effect=changed):
            with self.assertRaisesRegex(EngineError, 'Stale input'):
                self.send(task, payload)
        self.assertEqual(task, self.engine.task(task['id']))

    def test_invalid_sources_and_fields_preserve_candidate_and_failure(self):
        task, payload = self.prepare()
        for mode in ('source','identity','decision','adoption'):
            value=deepcopy(payload)
            candidate=value['candidate']
            if mode=='source': candidate['state_delta']['operations'][0]['append_sources'][0]['quote']='not present'
            if mode=='identity': candidate['state_delta']['operations'][0]['set']['id']='forbidden'
            if mode=='decision': candidate['result']['changes'].append({'path':'decisions/forged.md','content':'forged'})
            if mode=='adoption': candidate['state_delta']['operations'][0]['set']['kind']='candidate'
            if mode=='adoption':
                # Exercise the production adoption guard failure without weakening other checks.
                with patch.object(self.dot.engine, '_check_adoption', side_effect=EngineError('adoption rejected')):
                    with self.assertRaises(ValueError): self.send(task,value)
            else:
                with self.assertRaises(ValueError): self.send(task,value)
            self.assertEqual(task,self.engine.task(task['id']))
        with self.dot._db() as db:
            self.assertEqual(4,db.execute("SELECT count(*) FROM requests WHERE state='error'").fetchone()[0])
        self.assertEqual([], json.loads(self.read_all(task,'candidate-history.json'))['amendments'])

    def test_missing_coverage_and_legacy_bypass_rejected(self):
        task,payload=self.prepare()
        with patch.object(self.dot,'_checkpoints',return_value=[]):
            with self.assertRaisesRegex(EngineError,'incomplete'): self.send(task,payload)
        with self.assertRaisesRegex(EngineError,'complete novel-context'):
            self.send(task,{**payload,'candidate':payload['candidate']['result']})
        self.assertEqual(task,self.engine.task(task['id']))

    def test_completed_review_and_superseded_attempt_rejected(self):
        task,payload=self.prepare()
        _,finish=self.upload(task,payload)
        for field,value in [('status','completed'),('kind','review'),('attempts',2),('result_revision',task['input_revision'])]:
            with self.engine._db(True) as db: db.execute('UPDATE tasks SET '+field+'=? WHERE id=?',(value,task['id']))
            before=self.engine.task(task['id'])
            with self.assertRaises(ValueError): self.dot.finish(**{**finish,'request_id':self.request()})
            self.assertEqual(before,self.engine.task(task['id']))
            with self.engine._db(True) as db: db.execute('UPDATE tasks SET '+field+'=? WHERE id=?',(task[field],task['id']))

    def test_event_and_candidate_rollback_together(self):
        task,payload=self.prepare()
        original=self.dot.engine._event
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise EngineError('injected transaction failure')
        with patch.object(self.dot.engine,'_event',side_effect=fail):
            with self.assertRaisesRegex(EngineError,'transaction failure'):self.send(task,payload)
        self.assertEqual(task,self.engine.task(task['id']))
        self.assertEqual([],json.loads(self.read_all(task,'candidate-history.json'))['amendments'])

    def test_stale_amendment_cannot_revert_new_candidate(self):
        task,payload=self.prepare()
        self.send(task,payload)
        current=self.engine.task(task['id'])
        with self.assertRaisesRegex(EngineError,'Stale candidate'):self.send(task,payload)
        self.assertEqual(current,self.engine.task(task['id']))
        with self.assertRaises(ValueError):self.engine.submit(task['id'],task['result'],expected_attempt=1)
        self.assertEqual(current,self.engine.task(task['id']))

    def test_guide_and_path_confinement(self):
        task,payload=self.prepare()
        self.assertEqual(FORMAT,json.loads(self.read_all(task,'candidate-amend-guide.json'))['format'])
        for document in ['candidates/../../runtime/novel.sqlite3','candidates/'+'0'*64+'.json']:
            with self.assertRaises(EngineError):self.read_all(task,document)

    def test_concurrent_amendments_compare_and_swap(self):
        from concurrent.futures import ThreadPoolExecutor
        task,payload=self.prepare()
        _,first=self.upload(task,payload)
        other=deepcopy(payload)
        other['candidate']['result']['changes'][0]['content']+=' Another fixture sentence.'
        _,second=self.upload(task,other)
        def execute(args):
            try:return self.dot.finish(**args)
            except EngineError as exc:return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(execute,[first,second]))
        self.assertEqual(1,sum(isinstance(o,dict) for o in outcomes))
        self.assertEqual(1,sum(isinstance(o,str) and 'Stale candidate' in o for o in outcomes))
        self.assertEqual(1,len(json.loads(self.read_all(task,'candidate-history.json'))['amendments']))

    def test_request_conflict_and_original_upload_immutable(self):
        task,payload=self.prepare()
        _,finish=self.upload(task,payload)
        self.dot.finish(**finish)
        current=self.engine.task(task['id'])
        with self.assertRaisesRegex(EngineError,'different arguments'):
            self.dot.finish(**{**finish,'upload_id':self.original_finish['upload_id']})
        with self.assertRaisesRegex(EngineError,'replace an existing'):
            self.dot.chunk(request_id=self.request(),task_id=task['id'],attempt=1,
                upload_id=self.original_finish['upload_id'],part=0,total=1,content='{}')
        self.assertEqual(current,self.engine.task(task['id']))

    def test_invalid_result_rolls_back_even_after_archive_insert(self):
        task,payload=self.prepare()
        original=self.dot.engine._row
        def fail(db,table,key):
            value=original(db,table,key)
            if table=='tasks' and value['result_hash']!=task['result_hash']:
                raise EngineError('injected after update')
            return value
        with patch.object(self.dot.engine,'_row',side_effect=fail):
            with self.assertRaisesRegex(EngineError,'after update'):self.send(task,payload)
        self.assertEqual(task,self.engine.task(task['id']))
        self.assertEqual([],json.loads(self.read_all(task,'candidate-history.json'))['amendments'])
