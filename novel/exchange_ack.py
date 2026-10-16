"""Explicit adoption receipt and shared semantic baseline; no transport/approval."""
from pathlib import Path

from .engine import EngineError, canonical, checked_path
from . import evaluation, exchange
from .records import _json


def shared(capture):
    """Keep executable state, not per-end audit rows, clocks, or historical detail.

    The full captures remain in the original bundles and receipt. These omitted
    audit fields are never rewritten to manufacture byte-identical databases.
    """
    keys = ('id', 'book_id', 'kind', 'instruction', 'input_revision', 'control_hash',
            'status', 'attempts', 'no_progress', 'stop_reason', 'result_hash', 'result_revision')
    state = exchange._state(capture)
    state.pop('task_events', None)
    state['tasks'] = {tid: exchange._sha({k: h['task'][k] for k in keys})
                      for tid, h in capture['tasks'].items()}
    return state


def _read(path, kind):
    path = Path(path).absolute()
    checked_path(path.parent, path.name)
    if path.stat().st_size > exchange.MAX_BYTES:
        raise EngineError('Confirmation exceeds size limit')
    obj = _json(path.read_text(encoding='utf-8'), kind)
    evaluation._exact(obj, ('id', 'record'), kind)
    if not isinstance(obj['record'], dict) or obj['record'].get('kind') != kind or obj['id'] != exchange._sha(obj['record']):
        raise EngineError('Confirmation kind/integrity mismatch')
    return obj


def _write(output, record):
    obj = {'id': exchange._sha(record), 'record': record}
    output = Path(output).absolute()
    checked_path(output.parent, output.name)
    encoded = canonical(obj) + '\n'
    if len(encoded.encode('utf-8')) > exchange.MAX_BYTES:
        raise EngineError('Confirmation exceeds size limit')
    if output.exists():
        if _read(output, record['kind']) != obj:
            raise EngineError('Do not overwrite a different confirmation')
    else:
        from .engine import Engine
        Engine._new_file(output, encoded)
    return obj


def _source(path):
    source = exchange._read(path)
    spec = source['record']['spec']
    if len(spec['task_ids']) != 1 or spec['artifacts']:
        raise EngineError('Confirmation requires the single-task adoption scope')
    task = source['record']['capture']['tasks'][spec['task_ids'][0]]['task']
    if task['status'] != 'completed' or task['kind'] not in ('write', 'revise'):
        raise EngineError('Confirmation requires a completed write/revise')
    return source, task


def _quiescent(db, book_id):
    if db.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('running','submitted','blocked','exhausted')", (book_id,)).fetchone():
        raise EngineError('Resolve active/stopped work before confirming a baseline')


def receipt(engine, source_path, output):
    source, task = _source(source_path)
    with engine._db(True) as db:
        _quiescent(db, task['book_id'])
        import json
        evidence = [json.loads(r['payload']) for r in db.execute(
            "SELECT payload FROM events WHERE event='exchange.applied' AND task_id=?", (task['id'],))]
        if not any(e['bundle_id'] == source['id'] for e in evidence):
            raise EngineError('No local adoption evidence; receiving alone is not adoption')
        capture = exchange._capture(engine, source['record']['spec'], required=True)
        if shared(capture) != shared(source['record']['capture']):
            raise EngineError('Receiver changed since adoption; cannot confirm this target')
        return _write(output, {'kind':'adoption_receipt', 'source_id':source['id'],
                              'task_id':task['id'], 'target':task['result_revision'], 'capture':capture})


def _receipt_matches(receipt_obj, source, task):
    record = receipt_obj['record']
    evaluation._exact(record, ('kind','source_id','task_id','target','capture'), 'adoption receipt')
    try:
        matches = (record['source_id'] == source['id'] and record['task_id'] == task['id']
                   and record['target'] == task['result_revision']
                   and shared(record['capture']) == shared(source['record']['capture']))
    except (KeyError, TypeError, AttributeError) as exc:
        raise EngineError('Malformed receipt capture') from exc
    if not matches:
        raise EngineError('Receipt package/version/state mismatch')


def _registered(db, agreement_id):
    import json
    return any(json.loads(r['payload']).get('agreement_id') == agreement_id for r in db.execute(
        "SELECT payload FROM events WHERE event='exchange.agreement_registered'"))


def confirm(engine, source_path, receipt_path, output):
    source, task = _source(source_path)
    received = _read(receipt_path, 'adoption_receipt')
    _receipt_matches(received, source, task)
    record = {'kind':'agreement', 'source_id':source['id'], 'receipt':received,
              'spec':source['record']['spec'], 'state':shared(source['record']['capture'])}
    agreement_id = exchange._sha(record)
    with engine._db(True) as db:
        if not _registered(db, agreement_id):
            _quiescent(db, task['book_id'])
            if exchange._state(exchange._capture(engine, record['spec'], required=True)) != source['record']['state']:
                raise EngineError('Source has diverged; cannot confirm a new shared baseline')
        obj = _write(output, record)
        if not _registered(db, agreement_id):
            engine._event(db, 'exchange.agreement_registered', {'agreement_id':agreement_id,
                          'source_id':source['id'], 'role':'source_confirmation'}, book_id=task['book_id'])
    return obj


def read_agreement(path):
    obj = _read(path, 'agreement')
    record = obj['record']
    evaluation._exact(record, ('kind','source_id','receipt','spec','state'), 'agreement')
    exchange._spec(record['spec'])
    receipt_obj = record['receipt']
    try:
        if (receipt_obj['id'] != exchange._sha(receipt_obj['record'])
                or receipt_obj['record']['kind'] != 'adoption_receipt'
                or receipt_obj['record']['source_id'] != record['source_id']
                or shared(receipt_obj['record']['capture']) != record['state']):
            raise EngineError('Agreement receipt mismatch')
    except (KeyError, TypeError, AttributeError) as exc:
        raise EngineError('Malformed agreement receipt') from exc
    return obj


def acknowledge(engine, source_path, receipt_path, agreement_path):
    source, task = _source(source_path)
    received, agreement = _read(receipt_path, 'adoption_receipt'), read_agreement(agreement_path)
    _receipt_matches(received, source, task)
    record = agreement['record']
    if (record['source_id'] != source['id'] or record['receipt'] != received
            or record['spec'] != source['record']['spec'] or record['state'] != shared(source['record']['capture'])):
        raise EngineError('Wrong source confirmation')
    with engine._db(True) as db:
        if not _registered(db, agreement['id']):
            _quiescent(db, task['book_id'])
            if shared(exchange._capture(engine, record['spec'], required=True)) != record['state']:
                raise EngineError('Receiver has diverged before acknowledgment')
            engine._event(db, 'exchange.agreement_registered', {'agreement_id':agreement['id'],
                          'source_id':source['id'], 'role':'receiver_acknowledgment'}, book_id=task['book_id'])
    return {'agreement_id':agreement['id'], 'status':'registered_locally', 'author_approval':False}
