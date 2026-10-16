"""Bounded Linux synthetic acceptance; no model calls or private input.

Run: python scripts/validate_scale.py --output .local-validation/scale-001
The output must not exist. The supervisor kills the worker after 120 seconds.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from novel.engine import Engine, EMPTY_STATE

SPEC = {"chapters": 100, "characters_per_chapter": 10000, "batch_chapters": 20,
        "page_size": 17, "timeout_seconds": 120, "address_space_mib": 512,
        "data_limit_mib": 256, "model_calls": 0}


def check(value, message):
    if not value:
        raise RuntimeError(message)


def worker(output):
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    started = time.perf_counter()
    timings = {}
    source = output / "source"
    engine = Engine.initialize(source)
    engine.create_book("scale", "Synthetic storage fixture, not a novel")

    def submit(changes, kind="revise"):
        task = engine.claim(engine.enqueue("scale", kind, "Synthetic scale acceptance")["id"])
        result = {"task_id": task["id"], "input_revision": task["input_revision"],
                  "completed_steps": ["Synthetic fixture"], "next_step": "Verify storage",
                  "unresolved": [], "changes": changes, "review": None,
                  "affected_paths": [c["path"] for c in changes], "state_notes": "Empty synthetic state"}
        engine.submit(task["id"], result)
        return task

    def state():
        return {"path": "canon/state.json", "content": json.dumps(EMPTY_STATE)}

    for batch in range(5):
        changes = [state()]
        for number in range(batch * 20, (batch + 1) * 20):
            marker = f"章索引 {number:03d}\n"
            text = marker + "测" * (10000 - len(marker))
            changes.append({"path": f"manuscript/{number:03d}.md", "content": text})
        task = submit(changes, "write" if batch == 0 else "revise")
        engine.publish(task["id"])
    revision = engine.book("scale")["current_revision"]
    files = engine.files("scale")
    characters = sum(len(v) for p, v in files.items() if p.startswith("manuscript/"))
    check(characters == 1_000_000, "Wrong synthetic character count")
    timings["build_seconds"] = time.perf_counter() - started
    pending = submit([state(), {"path": "manuscript/000.md", "content": files["manuscript/000.md"].replace("测", "验", 1)}])
    engine.create_book("stopped", "Synthetic stopped task")
    stopped = engine.claim(engine.enqueue("stopped", "write", "Stop preservation")["id"])
    engine.block(stopped["id"], "no_progress", "Synthetic stop, preserve counters")
    expected_handoff = engine.handoff(pending["id"])
    expected_stop = engine.handoff(stopped["id"])
    expected_audit = engine.audit()
    t = time.perf_counter()
    hits, offset, pages = [], 0, 0
    while True:
        page = engine.search_page("scale", "章索引", revision, 17, offset)
        check(page["revision"] == revision, "Search revision drift")
        hits.extend(page["matches"])
        pages += 1
        check(pages <= 6, "Unexpected page count")
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    check([(h["path"], h["line"]) for h in hits] ==
          [(f"manuscript/{n:03d}.md", 1) for n in range(100)], "Missing or duplicate search hits")
    timings["paging_seconds"] = time.perf_counter() - t
    t = time.perf_counter()
    restored = output / "restored"
    shutil.copytree(source, restored)  # All writers stopped; includes SQLite sidecars.
    recovered = Engine(restored)
    check(recovered.audit() == expected_audit, "Backup audit mismatch")
    check(recovered.handoff(pending["id"]) == expected_handoff, "Pending handoff mismatch")
    check(recovered.handoff(stopped["id"]) == expected_stop, "Stop counters/history mismatch")
    command = subprocess.run([sys.executable, "-m", "novel", "--root", str(restored), "audit"],
                             cwd=REPO, capture_output=True, text=True, timeout=20)
    check(command.returncode == 0, command.stderr)
    check(json.loads(command.stdout) == expected_audit, "Fresh CLI audit mismatch")
    published = recovered.publish(pending["id"])
    check(recovered.publish(pending["id"]) == published, "Publish not idempotent")
    check(engine.task(pending["id"])["status"] == "submitted", "Source was modified")
    check(recovered.files("scale", revision) == files, "Historical snapshot changed")
    delta = recovered.diff("scale", revision)
    check([c["path"] for c in delta["changes"]] == ["manuscript/000.md"], "Unexpected restored changes")
    with closing(sqlite3.connect(recovered.db_path)) as db:
        db.execute("UPDATE tasks SET input_revision='missing' WHERE id=?", (pending["id"],))
        db.commit()
    try:
        recovered.audit()
    except ValueError:
        pass
    else:
        raise RuntimeError("Corrupt revision link was accepted")
    with closing(sqlite3.connect(recovered.db_path)) as db:
        db.execute("UPDATE tasks SET input_revision=? WHERE id=?", (pending["input_revision"], pending["id"]))
        db.commit()
    final_audit = recovered.audit()
    timings["restore_and_fault_seconds"] = time.perf_counter() - t
    data_bytes = sum(p.stat().st_size for folder in (source, restored) for p in folder.rglob("*") if p.is_file())
    check(data_bytes <= 256 * 1024**2, "Data exceeds declared disk budget")
    metrics = {"status": "passed", "spec": SPEC, "characters": characters, "pages": pages,
               "source_snapshots": expected_audit["snapshots_verified"],
               "restored_snapshots": final_audit["snapshots_verified"], "data_bytes": data_bytes,
               "worker_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "child_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
               "elapsed_seconds": time.perf_counter() - started, "timings": timings,
               "limits": "Linux RSS high-water marks, not combined process-tree RSS; one bounded run only"}
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        worker(output)
        return 0
    if sys.platform != "linux":
        parser.error("This acceptance runner requires Linux for explicit resource limits")
    output.mkdir(parents=True, exist_ok=False)
    (output / "spec.json").write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    check(shutil.disk_usage(output).free >= 512 * 1024**2, "Less than 512 MiB disk free")
    with (output / "stdout.log").open("w") as out, (output / "stderr.log").open("w") as err:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", "--output", str(output)],
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            process.wait(timeout=120)
            result = {"exit_code": process.returncode, "timed_out": False}
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            result = {"exit_code": 124, "timed_out": True}
    (output / "execution.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result))
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
