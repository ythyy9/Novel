"""Synthetic controller recovery tests; not literary review or native execution."""
import json
from pathlib import Path
import tempfile
import unittest

from novel.context import CHECKPOINT, RESULT, cached_plan, book_files
from novel.dot import DotWorkspace
from novel.dot_fence import FILE, FORMAT
from novel.engine import Engine, EngineError, EMPTY_STATE, canonical, digest


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-fence-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.engine = Engine.initialize(self.temp.name)
        self.engine.create_book("book", "Synthetic fixture")
        self.dot = DotWorkspace(self.temp.name, "book")
        self.prefix = "1" * 32
        self.seq = 0
        writer = self.dot.open_task(request_id="write-open", kind="write", instruction="fixture",
            expected_revision=self.engine.book("book")["current_revision"], context_ref="writer")["task"]
        result = self.result(writer)
        result["changes"] = [{"path":"manuscript/001.md", "content":"The letter arrived.\n" * 650},
            {"path":"canon/state.json", "content":canonical(EMPTY_STATE)}]
        result["affected_paths"] = [c["path"] for c in result["changes"]]
        self.upload(writer, result, False)
        self.dot.publish(request_id="write-publish", task_id=writer["id"], expected_revision=writer["input_revision"])
        self.task = self.dot.open_task(request_id="review-open", kind="review", instruction="fixture",
            expected_revision=self.engine.book("book")["current_revision"], context_ref="old-reviewer")["task"]

    def request(self, authorized=True):
        self.seq += 1
        return (self.prefix + "_" if authorized else "old-") + str(self.seq)

    def result(self, task):
        return {"task_id":task["id"], "input_revision":task["input_revision"], "completed_steps":["fixture"],
            "next_step":"Review", "unresolved":[], "changes":[], "review":None if task["kind"]=="write" else {
                "coverage":["manuscript/001.md"], "dimensions":["continuity","character","world","reading"], "findings":[]},
            "affected_paths":[], "state_notes":"Synthetic fixture"}

    def upload(self, task, result, authorized=True):
        raw = canonical(result)
        upload_id = "upload-" + str(self.seq)
        chunks = [raw[i:i+6000] for i in range(0,len(raw),6000)]
        for i, text in enumerate(chunks):
            self.dot.chunk(request_id=self.request(authorized), task_id=task["id"], attempt=task["attempts"],
                upload_id=upload_id, part=i, total=len(chunks), content=text)
        return self.dot.finish(request_id=self.request(authorized), task_id=task["id"], attempt=task["attempts"], upload_id=upload_id)

    def install(self, evidence=None):
        config = {"format":FORMAT, "book_id":"book", "task_id":self.task["id"], "attempt":1,
            "input_revision":self.task["input_revision"], "generation":"test-recovery", "created_at":"fixture",
            "request_prefix_sha256":digest(self.prefix), "evidence":evidence or []}
        (self.dot.base/FILE.format(book_id="book")).write_text(canonical(config),encoding="utf-8")
        return config

    def checkpoint(self, plan, views, batch, authorized):
        offset = 0
        while offset is not None:
            offset = self.dot.read(task_id=self.task["id"], document=batch["document"], offset=offset)["next_offset"]
        fragment = next(f for f in json.loads(views[batch["document"]])["fragments"] if f["text"])
        cp = {"format":CHECKPOINT,"task_id":self.task["id"],"attempt":1,"plan_sha256":plan["plan_sha256"],
            "batch_id":batch["id"],"context_ref":"new-reviewer" if authorized else "old-reviewer",
            "notes":"Synthetic evidence","evidence":[{"document":fragment["document"],"quote":fragment["text"][:20]}],
            "unresolved":[],"review":{"coverage":sorted(set(batch["source_paths"]) & set(book_files(self.dot._packet(self.task)))),"dimensions":["continuity","character","world","reading"],"findings":[]}}
        return self.upload(self.task,cp,authorized)

    def test_old_mutations_rejected_without_changing_original_state(self):
        self.install()
        before = self.engine.task(self.task["id"])
        with self.dot._db() as db:
            counts = [db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("requests","parts","context_checkpoints")]
        calls = [lambda:self.dot.chunk(request_id="stale-chunk",task_id=self.task["id"],attempt=1,upload_id="stale",part=0,total=1,content="{}"),
            lambda:self.dot.finish(request_id="stale-finish",task_id=self.task["id"],attempt=1,upload_id="stale"),
            lambda:self.dot.publish(request_id="stale-publish",task_id=self.task["id"],expected_revision=self.task["input_revision"]),
            lambda:self.dot.open_task(request_id="stale-open",kind="review",instruction="duplicate",context_ref="stale",expected_revision=self.task["input_revision"]),
            lambda:self.dot.accept(request_id="stale-accept",expected_revision=self.task["input_revision"])]
        for call in calls:
            with self.assertRaisesRegex(EngineError,"Execution fenced"):
                call()
        self.assertEqual(before,self.engine.task(self.task["id"]))
        with self.dot._db() as db:
            self.assertEqual(counts,[db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("requests","parts","context_checkpoints")])

    def test_same_attempt_resumes_real_checkpoint_flow_and_preserves_packet(self):
        packet_path=self.dot.base/"packets"/(self.task["id"]+".json")
        original_packet=packet_path.read_bytes()
        plan,views=cached_plan(self.dot._packet(self.task))
        self.assertGreater(len(plan["batches"]),1)
        first=self.checkpoint(plan,views,plan["batches"][0],False)
        self.install()
        self.dot=DotWorkspace(self.temp.name,"book")
        for batch in plan["batches"][1:]:
            self.checkpoint(plan,views,batch,True)
        checkpoints=self.dot._checkpoints(self.task,plan)
        self.assertEqual(first["checkpoint_sha256"],digest(canonical(checkpoints[0])))
        self.assertEqual(original_packet,packet_path.read_bytes())
        self.upload(self.task,{"format":RESULT,"task_id":self.task["id"],"attempt":1,"plan_sha256":plan["plan_sha256"],"result":self.result(self.task),"state_delta":None})
        self.dot.publish(request_id=self.request(),task_id=self.task["id"],expected_revision=self.task["input_revision"])
        current=self.engine.task(self.task["id"])
        self.assertEqual((current["status"],current["attempts"],current["no_progress"]),("completed",1,0))
        self.assertEqual(len(checkpoints),len(plan["batches"]))
        self.assertEqual(self.engine.audit()["database"],"ok")

    def test_malformed_or_wrong_identity_fence_fails_closed(self):
        config=self.install()
        for changed in ({**config,"attempt":2},{**config,"book_id":"other"},{**config,"request_prefix_sha256":"bad"}):
            (self.dot.base/FILE.format(book_id="book")).write_text(canonical(changed),encoding="utf-8")
            with self.assertRaisesRegex(EngineError,"Invalid continuation fence"):
                self.dot.chunk(request_id=self.request(),task_id=self.task["id"],attempt=1,upload_id="new",part=0,total=1,content="{}")

    def test_pending_request_prefix_is_not_disclosed_by_status(self):
        self.install()
        with self.dot._db() as db:
            db.execute("INSERT INTO requests VALUES (?,?,?,?,?)",(self.prefix+"_pending","signature","pending",None,"fixture"))
        state=self.dot.status()
        self.assertNotIn(self.prefix,canonical(state))
        self.assertIn("continuation-request_pending",state["uncertain_requests"])
        self.assertEqual(state["continuation"]["task_id"],self.task["id"])

    def test_private_prefix_cannot_be_stored_even_when_split_across_parts(self):
        self.install()
        with self.assertRaisesRegex(EngineError,"private continuation prefix"):
            self.dot.chunk(request_id=self.request(),task_id=self.task["id"],attempt=1,upload_id="new",part=0,total=1,content=self.prefix)
        for i,piece in enumerate((self.prefix[:16],self.prefix[16:])):
            self.dot.chunk(request_id=self.request(),task_id=self.task["id"],attempt=1,upload_id="split",part=i,total=2,content=piece)
        with self.assertRaisesRegex(EngineError,"private continuation prefix"):
            self.dot.finish(request_id=self.request(),task_id=self.task["id"],attempt=1,upload_id="split")

    def test_exact_legacy_result_requires_operator_allowlist_and_hash(self):
        # This completed review exists in the same Engine, but was never
        # registered with Dot, as with an inherited pre-Dot review.
        legacy=self.engine.claim(self.engine.enqueue("book","review","legacy")["id"])
        result=self.result(legacy)
        self.engine.submit(legacy["id"],result,expected_attempt=1)
        self.engine.publish(legacy["id"])
        self.install([{"task_id":legacy["id"],"result_sha256":digest(canonical(result))}])
        with self.assertRaisesRegex(EngineError,"not registered"):
            self.dot.read(task_id=legacy["id"],document="result.json")
        reply=self.dot.read(task_id=self.task["id"],document="continuation-evidence/"+legacy["id"]+".json")
        self.assertEqual(reply["text"],canonical(result))
        self.assertEqual(reply["sha256"],digest(canonical(result)))
        self.assertNotIn(self.prefix,self.dot.read(task_id=self.task["id"],document="continuation-guide.json")["text"])
        with self.assertRaisesRegex(EngineError,"allowlist"):
            self.dot.read(task_id=self.task["id"],document="continuation-evidence/unknown.json")
        self.install([{"task_id":legacy["id"],"result_sha256":"0"*64}])
        with self.assertRaisesRegex(EngineError,"hash mismatch"):
            self.dot.read(task_id=self.task["id"],document="continuation-evidence/"+legacy["id"]+".json")

    def test_completed_replays_remain_idempotent_and_other_tasks_are_unchanged(self):
        args=dict(request_id="old-part",task_id=self.task["id"],attempt=1,upload_id="original",part=0,total=2,content="{")
        original=self.dot.chunk(**args)
        self.install()
        replay=self.dot.chunk(**args)
        self.assertTrue(replay["replayed"])
        self.assertEqual(original["sha256"],replay["sha256"])
        self.engine.create_book("other","Other fixture")
        other=DotWorkspace(self.temp.name,"other")
        self.assertNotIn("continuation",other.status())
        opened=other.open_task(request_id="other-open",kind="write",instruction="other",context_ref="other",
            expected_revision=self.engine.book("other")["current_revision"])
        self.assertEqual(opened["task"]["book_id"],"other")


if __name__ == "__main__":
    unittest.main()
