"""Small explicit CLI. No background loops, implicit retry or automatic acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .engine import Engine, KINDS, STOP_REASONS
from .records import _json


def parser():
    p = argparse.ArgumentParser(prog="python -m novel", description="Novel 本地创作工作流")
    p.add_argument("--root", type=Path, default=Path.cwd(), help="项目资料目录，默认当前目录")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="初始化本地数据库与策略，不调用模型")
    sub.add_parser("doctor", help="只读检查 Codex CLI 与 ChatGPT 登录")
    sub.add_parser("books")
    add = sub.add_parser("book-create")
    add.add_argument("book")
    add.add_argument("--title", required=True)
    for name in ("book-show", "files", "assess", "accept"):
        sub.add_parser(name).add_argument("book")
    read = sub.add_parser("read")
    read.add_argument("book")
    read.add_argument("path")
    read.add_argument("--revision")
    search = sub.add_parser("search")
    search.add_argument("book")
    search.add_argument("query")
    create = sub.add_parser("task-create")
    create.add_argument("book")
    create.add_argument("kind", choices=sorted(KINDS))
    source = create.add_mutually_exclusive_group(required=True)
    source.add_argument("--instruction")
    source.add_argument("--instruction-file", type=Path)
    listing = sub.add_parser("tasks")
    listing.add_argument("--book")
    for name in ("task-show", "task-claim", "task-publish", "task-prepare", "handoff"):
        sub.add_parser(name).add_argument("task")
    submit = sub.add_parser("task-submit")
    submit.add_argument("task")
    submit.add_argument("result", type=Path)
    run = sub.add_parser("task-run", help="运行一次 Codex 并提交候选；不自动publish或accept")
    run.add_argument("task")
    run.add_argument("--timeout", type=float, default=300)
    for name in ("task-resume", "task-recover", "task-cancel"):
        command = sub.add_parser(name)
        command.add_argument("task")
        command.add_argument("--note", required=True)
    stop = sub.add_parser("task-stop")
    stop.add_argument("task")
    stop.add_argument("reason", choices=sorted(STOP_REASONS))
    stop.add_argument("--note", required=True)
    rollback = sub.add_parser("rollback")
    rollback.add_argument("book")
    rollback.add_argument("revision")
    rollback.add_argument("--note", required=True)
    for name in ("decision", "feedback", "reference-import"):
        command = sub.add_parser(name, help="仅由作者或有明确授权的操作员录入原文")
        command.add_argument("book")
        command.add_argument("--text-file", type=Path, required=True)
        if name == "feedback":
            command.add_argument("--source", choices=("author", "target_reader"), default="author")
    sub.add_parser("audit")
    experiment = sub.add_parser("eval-create")
    experiment.add_argument("spec", type=Path)
    for name in ("eval-blind", "eval-summary"):
        sub.add_parser(name).add_argument("experiment")
    judge = sub.add_parser("eval-judge")
    judge.add_argument("experiment")
    judge.add_argument("case")
    judge.add_argument("choice", choices=("A", "B", "tie", "inconclusive"))
    judge.add_argument("--reviewer", choices=("author", "target_reader", "agent"), required=True)
    judge.add_argument("--rationale-file", type=Path, required=True)
    decide = sub.add_parser("eval-decide")
    decide.add_argument("experiment")
    decide.add_argument("action", choices=("trial", "retain", "rollback"))
    decide.add_argument("--note", required=True)
    return p


def execute(args):
    if args.command == "doctor":
        from .adapter import doctor
        return doctor()
    if args.command == "init":
        Engine.initialize(args.root)
        return {"initialized": str(args.root.resolve()), "model_called": False}
    engine = Engine(args.root)
    cmd = args.command
    if cmd.startswith("eval-"):
        from . import evaluation
        if cmd == "eval-create":
            return evaluation.create(engine.root, _json(args.spec.read_text(encoding="utf-8-sig"), "experiment"))
        if cmd == "eval-blind":
            return evaluation.blind(engine.root, args.experiment)
        if cmd == "eval-summary":
            return evaluation.summarize(engine.root, args.experiment)
        if cmd == "eval-judge":
            return evaluation.judge(engine.root, args.experiment, args.case, args.choice,
                                    args.rationale_file.read_text(encoding="utf-8-sig"), args.reviewer)
        if cmd == "eval-decide":
            return evaluation.decide(engine.root, args.experiment, args.action, args.note)
    if cmd == "book-create":
        return engine.create_book(args.book, args.title)
    if cmd == "books":
        return engine.list_books()
    if cmd == "book-show":
        return engine.book(args.book)
    if cmd == "files":
        return sorted(engine.files(args.book))
    if cmd == "read":
        files = engine.files(args.book, args.revision)
        if args.path not in files:
            raise ValueError("File is absent from this version")
        return files[args.path]
    if cmd == "search":
        return engine.search(args.book, args.query)
    if cmd == "task-create":
        instruction = args.instruction if args.instruction is not None else args.instruction_file.read_text(encoding="utf-8-sig")
        return engine.enqueue(args.book, args.kind, instruction)
    if cmd == "tasks":
        return engine.tasks(args.book)
    if cmd == "task-show":
        return engine.task(args.task)
    if cmd == "task-claim":
        return engine.claim(args.task)
    if cmd == "task-submit":
        result = _json(args.result.read_text(encoding="utf-8-sig"), "task result")
        return engine.submit(args.task, result)
    if cmd == "task-publish":
        return engine.publish(args.task)
    if cmd == "task-prepare":
        from .adapter import prepare
        return {"packet_directory": str(prepare(engine, args.task))}
    if cmd == "task-run":
        from .adapter import run
        before = engine.task(args.task)
        expected_attempt = before["attempts"] + (1 if before["status"] == "queued" else 0)
        result = run(engine, args.task, timeout=args.timeout)
        return engine.submit(args.task, result, expected_attempt=expected_attempt)
    if cmd == "task-stop":
        return engine.block(args.task, args.reason, args.note)
    if cmd in ("task-resume", "task-recover", "task-cancel"):
        return getattr(engine, cmd.removeprefix("task-"))(args.task, args.note)
    if cmd == "handoff":
        return engine.handoff(args.task)
    if cmd == "assess":
        return engine.assessment(args.book)
    if cmd == "accept":
        return engine.accept(args.book)
    if cmd == "rollback":
        return engine.rollback(args.book, args.revision, args.note)
    if cmd == "decision":
        return engine.decision(args.book, args.text_file.read_text(encoding="utf-8-sig"))
    if cmd == "feedback":
        return engine.feedback(args.book, args.text_file.read_text(encoding="utf-8-sig"), args.source)
    if cmd == "reference-import":
        return engine.reference(args.book, args.text_file.read_text(encoding="utf-8-sig"))
    if cmd == "audit":
        return engine.audit()
    raise ValueError("Unknown command")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        output = execute(args)
        if isinstance(output, str):
            print(output, end="" if output.endswith("\n") else "\n")
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1
