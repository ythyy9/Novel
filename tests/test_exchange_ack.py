"""Two synthetic endpoints; acknowledgment is not transport or author approval."""
import json
import unittest
from unittest.mock import patch

from novel import exchange, exchange_ack
from novel.engine import EngineError
import test_exchange_apply as fixtures


class AcknowledgmentTests(unittest.TestCase):
    setUp = fixtures.ApplyTests.setUp
    apply = fixtures.ApplyTests.apply
    write_result = fixtures.ApplyTests.write_result

    def handshake(self):
        self.apply()
        self.receipt = self.root/'receipt.json'
        self.agreement = self.root/'agreement.json'
        exchange_ack.receipt(self.b,self.package,self.receipt)
        self.confirmed = exchange_ack.confirm(self.a,self.package,self.receipt,self.agreement)
        return exchange_ack.acknowledge(self.b,self.package,self.receipt,self.agreement)

    def test_full_roundtrip_new_baseline_and_reverse_revision(self):
        ack = self.handshake()
        self.assertEqual(ack['agreement_id'],self.confirmed['id'])
        self.assertFalse(ack['author_approval'])
        self.assertEqual(exchange._baseline(self.a,self.agreement)['id'],exchange._baseline(self.b,self.agreement)['id'])
        task = self.b.enqueue('test','revise','合成反向修改')
        target = self.write_result(self.b,self.b.claim(task['id']),'反向候选')['result_revision']
        package = self.root/'reverse.json'
        spec = {**self.spec,'origin':'cloud','operation_id':'reverse','task_ids':[task['id']]}
        exchange.create(self.b,spec,package,self.agreement)
        self.assertEqual(exchange.check(self.a,package,self.agreement)['status'],'incoming_ahead')
        exchange.receive(self.a,package,self.agreement)
        original_event = self.a._event
        def fail_import(db,event,*args,**kwargs):
            if event == 'exchange.applied':
                raise OSError('synthetic failure after importing new revise task')
            return original_event(db,event,*args,**kwargs)
        with patch.object(self.a,'_event',side_effect=fail_import), self.assertRaises(OSError):
            exchange.apply(self.a,package,task['id'],self.agreement,self.target,target)
        with self.assertRaises(EngineError):
            self.a.task(task['id'])
        self.assertEqual(self.a.book('test')['current_revision'],self.target)
        result = exchange.apply(self.a,package,task['id'],self.agreement,self.target,target)
        self.assertEqual(result['revision'],target)
        self.assertEqual(self.a.files('test')['manuscript/001.md'],'反向候选')
        self.assertEqual(self.a.files('test',self.base_revision)['manuscript/001.md'],'旧版原文')
        self.assertEqual(self.a.book('test')['status'],'draft')
        self.assertEqual(self.a.audit()['database'],'ok')
        self.assertEqual(self.b.audit()['database'],'ok')
        # Close the reverse adoption too; neither side's original audit rows are erased.
        reverse_receipt = self.root/'reverse-receipt.json'
        reverse_agreement = self.root/'reverse-agreement.json'
        exchange_ack.receipt(self.a,package,reverse_receipt)
        exchange_ack.confirm(self.b,package,reverse_receipt,reverse_agreement)
        exchange_ack.acknowledge(self.a,package,reverse_receipt,reverse_agreement)
        # Old confirmation replay cannot move either current pointer backwards.
        exchange_ack.confirm(self.a,self.package,self.receipt,self.agreement)
        exchange_ack.acknowledge(self.b,self.package,self.receipt,self.agreement)
        self.assertEqual(self.a.book('test')['current_revision'],target)
        self.assertEqual(self.b.book('test')['current_revision'],target)

    def test_receiving_is_not_adoption_and_missing_confirmation_is_rejected(self):
        with self.assertRaisesRegex(EngineError,'No local adoption'):
            exchange_ack.receipt(self.b,self.package,self.root/'receipt.json')
        self.apply()
        receipt = self.root/'receipt.json'
        agreement = self.root/'agreement.json'
        exchange_ack.receipt(self.b,self.package,receipt)
        exchange_ack.confirm(self.a,self.package,receipt,agreement)
        with self.assertRaisesRegex(EngineError,'not confirmed'):
            exchange._baseline(self.b,agreement)
        with self.assertRaises(OSError):
            exchange_ack.confirm(self.a,self.package,self.root/'absent.json',agreement)

    def test_wrong_version_receipt_and_divergence_refused(self):
        self.apply()
        receipt = self.root/'receipt.json'
        agreement = self.root/'agreement.json'
        obj = exchange_ack.receipt(self.b,self.package,receipt)
        original = receipt.read_bytes()
        obj['record']['target']='0'*64
        obj['id']=exchange._sha(obj['record'])
        receipt.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaisesRegex(EngineError,'mismatch'):
            exchange_ack.confirm(self.a,self.package,receipt,agreement)
        receipt.write_bytes(original)
        self.a.feedback('test','源端并发意见')
        with self.assertRaisesRegex(EngineError,'diverged'):
            exchange_ack.confirm(self.a,self.package,receipt,agreement)
        self.assertFalse(agreement.exists())

    def test_partial_confirmation_failure_and_replay_are_recoverable(self):
        self.apply()
        receipt = self.root/'receipt.json'
        agreement = self.root/'agreement.json'
        exchange_ack.receipt(self.b,self.package,receipt)
        original_event = self.a._event
        def fail(db,event,*args,**kwargs):
            if event=='exchange.agreement_registered':
                raise OSError('synthetic interruption after confirmation file')
            return original_event(db,event,*args,**kwargs)
        with patch.object(self.a,'_event',side_effect=fail), self.assertRaises(OSError):
            exchange_ack.confirm(self.a,self.package,receipt,agreement)
        self.assertTrue(agreement.exists())
        with self.assertRaisesRegex(EngineError,'not confirmed'):
            exchange._baseline(self.a,agreement)
        first = exchange_ack.confirm(self.a,self.package,receipt,agreement)
        self.assertEqual(exchange_ack.confirm(self.a,self.package,receipt,agreement),first)
        exchange_ack.acknowledge(self.b,self.package,receipt,agreement)
        exchange_ack.acknowledge(self.b,self.package,receipt,agreement)
        for engine in (self.a,self.b):
            with engine._db() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM events WHERE event='exchange.agreement_registered'").fetchone()[0],1)
        self.assertEqual(self.b.task(self.task['id'])['attempts'],2)

    def test_cli_confirmation_and_scope_limit(self):
        import subprocess, sys
        self.apply()
        receipt, agreement = self.root/'cli-receipt.json', self.root/'cli-agreement.json'
        for engine, args in ((self.b,['bundle-receipt',str(self.package),str(receipt)]),
                             (self.a,['bundle-confirm',str(self.package),str(receipt),str(agreement)]),
                             (self.b,['bundle-ack',str(self.package),str(receipt),str(agreement)])):
            process = subprocess.run([sys.executable,'-m','novel','--root',str(engine.root),*args],
                                     capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
        with self.assertRaisesRegex(EngineError,'confirmed book version'):
            exchange.create(self.b,{**self.spec,'operation_id':'wrong-task'},self.root/'wrong.json',agreement)
        self.assertFalse((self.root/'wrong.json').exists())

    def test_pending_stopped_work_prevents_new_confirmation(self):
        self.apply()
        receipt = self.root/'receipt.json'
        exchange_ack.receipt(self.b,self.package,receipt)
        stopped = self.a.claim(self.a.enqueue('test','review','待解决')['id'])
        self.a.block(stopped['id'],'decision','等待作者决定')
        with self.assertRaisesRegex(EngineError,'active/stopped'):
            exchange_ack.confirm(self.a,self.package,receipt,self.root/'agreement.json')
        self.assertEqual(self.a.task(stopped['id'])['stop_reason'],'decision')

    def test_receiver_fork_before_acknowledgment_rejected(self):
        self.apply()
        receipt = self.root/'receipt.json'
        agreement = self.root/'agreement.json'
        exchange_ack.receipt(self.b,self.package,receipt)
        exchange_ack.confirm(self.a,self.package,receipt,agreement)
        self.b.feedback('test','回执之后新增本地反馈')
        with self.assertRaisesRegex(EngineError,'diverged'):
            exchange_ack.acknowledge(self.b,self.package,receipt,agreement)
