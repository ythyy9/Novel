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
    search.add_argument("--revision")
    search.add_argument("--page-size", type=int, help="分页输出，每页 1-1000 条；不指定则保留完整列表输出")
    search.add_argument("--offset", type=int, default=0, help="分页结果偏移，后续页必须指定 --revision")
    impact = sub.add_parser("impact", help="查询显式状态引用、研究影响及同版本审核覆盖，不推断语义影响")
    impact.add_argument("book")
    impact.add_argument("path")
    impact.add_argument("--revision")
    diff = sub.add_parser("diff", help="比较同作品两个快照的文件内容哈希，不修改版本")
    diff.add_argument("book")
    diff.add_argument("from_revision")
    diff.add_argument("--to-revision", help="默认当前版本")
    excerpt = sub.add_parser("excerpt", help="按版本和行号读取有限原文，返回来源哈希")
    excerpt.add_argument("book")
    excerpt.add_argument("path")
    excerpt.add_argument("--revision")
    excerpt.add_argument("--start-line", type=int, default=1)
    excerpt.add_argument("--line-count", type=int, default=100)
    create = sub.add_parser("task-create")
    create.add_argument("book")
    create.add_argument("kind", choices=sorted(KINDS))
    create.add_argument("--reference", action="append", default=[], help="先检查并分析参考资料库，再把报告绑定到任务输入")
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
    submit.add_argument("--expected-attempt", type=int, required=True,
                        help="生成结果时任务包中的 attempts；不得改填当前次数来导入旧结果")
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
            command.add_argument("--revision", help="反馈对应的实际阅读版本，默认当前版本")
    sub.add_parser("feedback-show").add_argument("feedback")
    diagnose = sub.add_parser("feedback-diagnose", help="追加原因假设、预防计划及实际验证记录，不自动修改方法")
    diagnose.add_argument("feedback")
    diagnose.add_argument("spec", type=Path)
    bundle = sub.add_parser("bundle-create", help="生成本地离线包，不传输或发布")
    bundle.add_argument("spec", type=Path)
    bundle.add_argument("output", type=Path)
    bundle.add_argument("--baseline", type=Path)
    for name in ("bundle-check", "bundle-receive"):
        bundle = sub.add_parser(name, help="校验离线交接；接收仅保存独立副本，不覆盖当前资料")
        bundle.add_argument("package", type=Path)
        bundle.add_argument("--baseline", type=Path)
    adoption = sub.add_parser("bundle-apply", help="显式接续单个完成的写作/返修为待审核版本，不合并冲突")
    adoption.add_argument("package", type=Path)
    adoption.add_argument("task")
    adoption.add_argument("--baseline", type=Path, required=True)
    adoption.add_argument("--expected-base", required=True)
    adoption.add_argument("--expected-target", required=True)
    receipt = sub.add_parser("bundle-receipt", help="导出采用回执，不代表作者批准")
    receipt.add_argument("source", type=Path)
    receipt.add_argument("output", type=Path)
    confirm = sub.add_parser("bundle-confirm", help="源端核对回执并生成共同基线")
    confirm.add_argument("source", type=Path)
    confirm.add_argument("receipt", type=Path)
    confirm.add_argument("output", type=Path)
    ack = sub.add_parser("bundle-ack", help="接收端核对源端确认并登记同一基线")
    ack.add_argument("source", type=Path)
    ack.add_argument("receipt", type=Path)
    ack.add_argument("agreement", type=Path)
    sub.add_parser("audit")
    ref = sub.add_parser("reference-add", help="导入参考书并自动查全系列、获取、完整阅读分析；原文件保留")
    ref.add_argument("reference")
    ref.add_argument("--file", type=Path, required=True)
    ref.add_argument("--original-file", type=Path, help="转换前原件；与可读文件分别保留")
    ref.add_argument("--title", required=True)
    ref.add_argument("--author", required=True)
    ref.add_argument("--work-id")
    ref.add_argument("--language", default="unknown")
    ref.add_argument("--kind", choices=("volume", "extra", "appendix", "standalone"), default="volume")
    ref.add_argument("--offline", action="store_true", help="仅保存和结构检查；联网及阅读保持待完成")
    ref.add_argument("--book", help="将带缺口的分析报告追加到作品参考资料，并绑定后续使用")
    use = sub.add_parser("reference-use", help="重新检查系列更新，接续全部实有内容的分析")
    use.add_argument("reference")
    use.add_argument("--book")
    use.add_argument("--resume-note", help="明确接续先前失败；保留累计尝试次数，不自动循环重试")
    for command in (ref, use):
        command.add_argument("--max-calls", type=int, default=24)
        command.add_argument("--timeout", type=float, default=600)
    sub.add_parser("reference-status", help="只读报告书目、版本、阅读覆盖和缺口").add_argument("reference")
    allow = sub.add_parser("reference-allow-source", help="登记已核实可获取的精确 URL；模型不能自行授权")
    allow.add_argument("reference")
    allow.add_argument("url")
    allow.add_argument("--basis", choices=("author_publication", "open_license", "owned_access"), required=True)
    allow.add_argument("--evidence-url", required=True)
    allow.add_argument("--note", required=True)
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
    if cmd in ("reference-add", "reference-use", "reference-status", "reference-allow-source"):
        from .references import ReferenceLibrary
        library = ReferenceLibrary(engine.root, args.reference)
        if cmd == "reference-status":
            return library.status()
        if cmd == "reference-allow-source":
            return library.allow_source(args.url, args.basis, args.evidence_url, args.note)
        if args.book:
            engine.book(args.book)
            if any(t["status"] in ("running", "submitted") for t in engine.tasks(args.book)):
                raise ValueError("Finish or cancel executing tasks before binding references")
        if cmd == "reference-add":
            result = library.add(args.file, args.title, args.author, work_id=args.work_id,
                                 language=args.language, kind=args.kind, original=args.original_file)
            if not args.offline:
                result = library.run(max_calls=args.max_calls, timeout=args.timeout)
        else:
            result = library.run(max_calls=args.max_calls, timeout=args.timeout, resume_note=args.resume_note)
        if args.book:
            result["binding"] = library.bind(engine, args.book)
        return result
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
    if cmd.startswith("bundle-"):
        from . import exchange
        if cmd in ("bundle-receipt", "bundle-confirm", "bundle-ack"):
            from . import exchange_ack
            if cmd == "bundle-receipt":
                return exchange_ack.receipt(engine, args.source, args.output)
            if cmd == "bundle-confirm":
                return exchange_ack.confirm(engine, args.source, args.receipt, args.output)
            return exchange_ack.acknowledge(engine, args.source, args.receipt, args.agreement)
        if cmd == "bundle-apply":
            return exchange.apply(engine, args.package, args.task, args.baseline,
                                  args.expected_base, args.expected_target)
        if cmd == "bundle-create":
            return exchange.create(engine, _json(args.spec.read_text(encoding="utf-8-sig"), "handoff spec"),
                                   args.output, args.baseline)
        if cmd == "bundle-check":
            return exchange.check(engine, args.package, args.baseline)
        return exchange.receive(engine, args.package, args.baseline)
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
        if args.page_size is not None:
            return engine.search_page(args.book, args.query, args.revision, args.page_size, args.offset)
        if args.offset:
            raise ValueError("--offset requires --page-size")
        return engine.search(args.book, args.query, args.revision)
    if cmd == "impact":
        return engine.impact(args.book, args.path, args.revision)
    if cmd == "diff":
        return engine.diff(args.book, args.from_revision, args.to_revision)
    if cmd == "excerpt":
        return engine.excerpt(args.book, args.path, args.revision, args.start_line, args.line_count)
    if cmd == "task-create":
        from .references import ReferenceLibrary, refresh_bound
        if args.reference and any(t["status"] in ("running", "submitted") for t in engine.tasks(args.book)):
            raise ValueError("Finish or cancel executing tasks before refreshing references")
        refreshed = refresh_bound(engine, args.book)
        bound_ids = {r["id"] for r in refreshed}
        remaining_calls = max(0, 24 - sum(r.get("last_run", {}).get("model_calls", 0) for r in refreshed))
        for ref_id in args.reference:
            if ref_id not in bound_ids:
                library = ReferenceLibrary(engine.root, ref_id)
                result = library.run(max_calls=remaining_calls)
                remaining_calls -= result.get("last_run", {}).get("model_calls", 0)
                library.bind(engine, args.book)
                bound_ids.add(ref_id)
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
        return engine.submit(args.task, result, expected_attempt=args.expected_attempt)
    if cmd == "task-publish":
        return engine.publish(args.task)
    if cmd == "task-prepare":
        from .adapter import prepare
        return {"packet_directory": str(prepare(engine, args.task))}
    if cmd == "task-run":
        from .adapter import run_and_submit
        return run_and_submit(engine, args.task, timeout=args.timeout)
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
    if cmd in ("feedback-diagnose", "feedback-show"):
        from . import feedback
        if cmd == "feedback-show":
            return feedback.show(engine, args.feedback)
        return feedback.append(engine, args.feedback, _json(args.spec.read_text(encoding="utf-8-sig"), "feedback diagnosis"))
    if cmd == "feedback":
        return engine.feedback(args.book, args.text_file.read_text(encoding="utf-8-sig"), args.source, args.revision)
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
