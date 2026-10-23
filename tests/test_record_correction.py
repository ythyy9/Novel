"""Self-contained synthetic content tests; require the reconstructed code baseline.

No real chapters/state or original upload are embedded. All pins patched below
are local unittest fixtures; there is no production bypass switch.
"""
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from novel import record_correction as fix
from novel.records import ValidationError, validate_result


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def digest(value):return sha256(value.encode()).hexdigest()


class MinimalRecordCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.old="Synthetic statement: tomorrow. Unknown remains Unknown."
        self.new=self.old.replace("tomorrow", "at an unknown time")
        new_source={"path":"manuscript/025.md","quote":"Synthetic source B."}
        self.source={"path":"manuscript/025.md","quote":"Synthetic source A."}
        target=dict(id=fix.RECORD_ID,kind="character_knowledge",holder="Fixture",statement=self.old,sources=[self.source])
        other=dict(id="unchanged",kind="undecided",holder=None,statement="Unknown",sources=[self.source])
        state=dict(knowledge=[target,other],characters=[],world=[],offstage=[])
        self.files={fix.STATE:encode(state),fix.OLD_APPENDIX:"Synthetic old appendix.",
                    "manuscript/025.md":self.source["quote"]+"\n"+new_source["quote"],
                    "manuscript/031.md":"Synthetic medical source."}
        self.updated=deepcopy(state)
        self.updated["knowledge"][0]["statement"]=self.new
        self.updated["knowledge"][0]["sources"].append(deepcopy(new_source))
        self.appendix=self.old+"\n"+self.new+"\nSynthetic correction appendix."
        self.task=dict(id=fix.TASK_ID,book_id=fix.BOOK_ID,kind="revise",attempts=1,input_revision=fix.INPUT_REVISION,control_hash=fix.CONTROL_HASH)
        self.result=dict(task_id=fix.TASK_ID,input_revision=fix.INPUT_REVISION,completed_steps=["fixture"],
                         next_step="Independent review",unresolved=[],review=None,state_notes="fixture",
                         changes=[dict(path=fix.STATE,content=encode(self.updated)),dict(path=fix.PATH,content=self.appendix)],
                         affected_paths=[fix.STATE,fix.PATH])
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(fix,"INPUT_PINS",{p:digest(v) for p,v in self.files.items()}))
        stack.enter_context(patch.object(fix,"APPENDIX_SHA256",digest(self.appendix)))
        stack.enter_context(patch.object(fix,"UPDATED_STATE_SHA256",digest(encode(self.updated))))

    def reject(self,result=None,task=None,files=None):
        with self.assertRaises(ValidationError):validate_result(result or self.result,task or self.task,files or self.files)

    def test_minimal_change_validates_without_manuscript_change(self):
        validate_result(self.result,self.task,self.files)
        self.assertEqual(self.updated["knowledge"][1],json.loads(self.files[fix.STATE])["knowledge"][1])

    def test_delete_history_change_other_entry_or_sources_rejected(self):
        for action in (lambda s:s["knowledge"].pop(),
                       lambda s:s["knowledge"][1].update(statement="decided"),
                       lambda s:s["knowledge"][0].update(kind="world_fact"),
                       lambda s:s["knowledge"][0]["sources"].pop(0),
                       lambda s:s["knowledge"].reverse()):
            state=deepcopy(self.updated);action(state)
            result=deepcopy(self.result);result["changes"][0]["content"]=encode(state)
            self.reject(result)

    def test_extra_manuscript_decision_and_history_edit_rejected(self):
        for path in ("manuscript/025.md","decisions/new.md",fix.OLD_APPENDIX):
            result=deepcopy(self.result);result["changes"].append(dict(path=path,content="changed"));self.reject(result)

    def test_wrong_identity_attempt_and_kind_rejected(self):
        for key,value in (("book_id","other"),("attempts",2),("attempts",True),("kind","review"),("control_hash","other")):
            self.reject(task={**self.task,key:value})
        self.reject(result={**self.result,"task_id":"old-task"})

    def test_appendix_newline_and_preexisting_record_rejected(self):
        result=deepcopy(self.result);result["changes"][1]["content"]+="\n";self.reject(result)
        self.reject(files={**self.files,fix.PATH:"history"})


if __name__=="__main__":unittest.main()
