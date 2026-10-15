"""Deterministic engineering fixtures, explicitly not real reading acceptance."""
from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from email.message import Message
import zipfile

from novel import adapter, reference_io, reference_model
from novel.engine import Engine
from novel.references import ReferenceLibrary, units, validate_result


ROOT = Path(__file__).resolve().parents[1]


def epub(missing=False, bad_anchor=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>')
        z.writestr("OEBPS/book.opf", '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture</dc:title><dc:creator>Tester</dc:creator></metadata><manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="n" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine><itemref idref="c"/></spine></package>')
        z.writestr("OEBPS/toc.ncx", '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint><content src="chapter.xhtml#' + ('missing' if bad_anchor else 'c1') + '"/></navPoint></navMap></ncx>')
        if not missing:
            z.writestr("OEBPS/chapter.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><h1 id="c1">CHAPTER 1</h1><p>A fixture chapter ends here.</p><h2>Appendix</h2><p>Retain this appendix.</p></body></html>')
    return stream.getvalue()


class FixtureRunner:
    def __init__(self):
        self.calls = []
        self.discovery_error = None
        self.read_error = None
        self.more = []

    def __call__(self, mode, packet, directory, timeout):
        self.calls.append((mode, deepcopy(packet)))
        if mode == "discover":
            if self.discovery_error:
                raise self.discovery_error
            work = ReferenceLibrary.work("fixture", "Fixture", "Tester", "en")
            work["sources"] = [{"url": "https://example.org/catalog", "title": "Engineering fixture, not a real source", "accessed": "2026-10-15"}]
            return {"series": "Fixture series", "works": [work] + self.more, "gaps": ["这是测试目录，未声称真实检索"]}
        if mode == "read":
            if self.read_error:
                raise self.read_error
            return {"unit_id": packet["unit_id"], "summary": "工程夹具摘要，不是模型阅读。", "findings": [{"kind": "text_fact", "claim": "工程夹具引文", "quote": packet["text"][:30]}], "gaps": []}
        return {"summary": "工程夹具综合，不是真实模型分析。", "conclusions": [{"claim": "测试证据传递", "evidence_ids": [x["id"] for x in packet["evidence"]]}], "revisions": [], "gaps": []}


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-reference-test-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Engine.initialize(self.root)
        self.library = ReferenceLibrary(self.root, "fixture-series")
        self.file = self.root / "fixture.epub"
        self.file.write_bytes(epub())
        self.library.add(self.file, "Fixture", "Tester", work_id="fixture")
        self.runner = FixtureRunner()

    def run_library(self, **kwargs):
        return self.library.run(runner=self.runner, **kwargs)

    def test_epub_audit_keeps_appendix_and_checks_targets(self):
        text, report = reference_io.extract(epub(), ".epub")
        self.assertIn("Retain this appendix.", text)
        self.assertEqual(report["issues"], [])
        self.assertFalse(report["publisher_full_text_collated"])
        _, report = reference_io.extract(epub(bad_anchor=True), ".epub")
        self.assertTrue(any(x.startswith("broken_toc_anchor") for x in report["issues"]))
        with self.assertRaisesRegex(ValueError, "No readable text"):
            reference_io.extract(epub(missing=True), ".epub")

    def test_contiguous_lossless_coverage_includes_whitespace(self):
        text = "前言\n\n" + "正文段落\n" * 21 + "\n附录。\n"
        chunks = list(units(text, 19))
        self.assertEqual("".join(c["text"] for c in chunks), text)
        self.assertEqual(chunks[0]["start"], 0)
        self.assertEqual(chunks[-1]["end"], len(text))
        for a, b in zip(chunks, chunks[1:]):
            self.assertEqual(a["end"], b["start"])

    def test_numbered_missing_chapter_is_flagged(self):
        _, audit = reference_io.extract(b"CHAPTER 1\nOne.\n\nCHAPTER 3\nThree.", ".txt")
        self.assertIn("chapter_number_gap_or_order", audit["issues"])

    def test_unsupported_source_retained_and_reports_gap(self):
        path = self.root / "unreadable.lit"
        path.write_bytes(b"ITOLITLS fixture")
        self.library.add(path, "Missing", "Tester", work_id="missing")
        result = self.run_library()
        self.assertEqual(result["editions"][1]["read_chars"], 0)
        state = self.library.load()
        self.assertEqual(self.library.read_artifact(state["editions"][1]["source"]), path.read_bytes())
        self.assertTrue(result["editions"][0]["all_units_analyzed"])
        self.assertTrue(any("Unsupported format" in g for g in result["gaps"]))

    def test_reads_all_then_reuses_units_but_refreshes_catalogue(self):
        first = self.run_library()
        self.assertTrue(first["editions"][0]["all_units_analyzed"])
        self.assertTrue(first["series_analysis_available"])
        self.assertEqual([m for m, _ in self.runner.calls], ["discover", "read", "synthesize", "synthesize"])
        self.runner.calls.clear()
        self.run_library()
        self.assertEqual([m for m, _ in self.runner.calls], ["discover"])

    def test_missing_sequel_does_not_prevent_existing_analysis(self):
        sequel = ReferenceLibrary.work("sequel", "Unavailable sequel", "Tester")
        sequel["sources"] = [{"url": "https://example.org/sequel", "title": "Fixture", "accessed": "2026-10-15"}]
        sequel["downloads"] = [{"url": "https://example.org/sequel.epub", "scope": "full", "note": "Fixture"}]
        self.runner.more = [sequel]
        def denied(*args):
            raise ValueError("rights_unverified")
        result = self.run_library(fetcher=denied)
        self.assertEqual(result["catalogued_works"], 2)
        self.assertTrue(result["editions"][0]["all_units_analyzed"])
        self.assertTrue(any("缺全文" in g for g in result["gaps"]))
        self.assertIsNone(result["stop"])

    def test_readable_copy_does_not_suppress_new_full_edition(self):
        original_runner = self.runner
        def catalogue_with_candidate(mode, packet, directory, timeout):
            result = original_runner(mode, packet, directory, timeout)
            if mode == "discover":
                result["works"][0]["downloads"] = [{"url": "https://example.org/authorized-expanded.txt", "scope": "full", "note": "Engineering fixture: new edition with appendix"}]
            return result
        def fetch(url, allowed):
            return b"Fixture\nCHAPTER 1\nA readable original.\nAppendix\nNew material.", ".txt", {"requested_url": url, "final_url": url, "content_type": "text/plain"}
        result = self.library.run(runner=catalogue_with_candidate, fetcher=fetch)
        self.assertEqual(len(result["editions"]), 2)
        self.assertTrue(all(e["all_units_analyzed"] for e in result["editions"]))

    def test_search_failure_still_analyzes_local_text(self):
        self.runner.discovery_error = ValueError("No completed web_search event")
        result = self.run_library()
        self.assertTrue(result["editions"][0]["all_units_analyzed"])
        self.assertIsNone(result["stop"])
        self.assertTrue(any("书目查询失败" in g for g in result["gaps"]))
        self.runner.calls.clear()
        self.run_library()
        self.assertEqual(self.runner.calls, [])

    def test_quota_stop_needs_explicit_resume_and_preserves_attempts(self):
        self.runner.discovery_error = adapter.AdapterError("quota", "quota fixture")
        first = self.run_library()
        self.assertEqual(first["stop"]["reason"], "quota")
        self.assertEqual(len(self.runner.calls), 1)
        self.run_library()
        self.assertEqual(len(self.runner.calls), 1)
        self.runner.discovery_error = None
        result = self.run_library(resume_note="Fixture quota is now available")
        self.assertIsNone(result["stop"])
        discovery = [j for j in self.library.load()["jobs"].values() if j["mode"] == "discover"]
        self.assertEqual(discovery[0]["attempts"], 2)

    def test_resume_does_not_reset_cumulative_attempt_limit(self):
        self.runner.discovery_error = adapter.AdapterError("quota", "quota fixture")
        self.run_library()
        self.run_library(resume_note="retry two")
        self.run_library(resume_note="retry three")
        result = self.run_library(resume_note="fourth must not run")
        self.assertEqual(len(self.runner.calls), 3)
        self.assertEqual(result["stop"]["reason"], "attempt_limit")

    def test_new_day_does_not_reset_failed_discovery_attempt_budget(self):
        self.runner.discovery_error = adapter.AdapterError("quota", "quota fixture")
        for day in (15, 16, 17):
            with patch("novel.references.now", return_value=f"2026-10-{day}T12:00:00+00:00"):
                self.run_library(resume_note="Explicit retry on another day")
        with patch("novel.references.now", return_value="2026-10-18T12:00:00+00:00"):
            result = self.run_library(resume_note="A new day must not reset attempts")
        self.assertEqual(len(self.runner.calls), 3)
        self.assertEqual(result["stop"]["reason"], "attempt_limit")

    def test_budget_pause_resumes_without_rereading_completed_units(self):
        result = self.run_library(max_calls=2)
        self.assertTrue(result["editions"][0]["all_units_analyzed"])
        self.assertFalse(result["series_analysis_available"])
        self.runner.calls.clear()
        self.run_library()
        self.assertNotIn("read", [m for m, _ in self.runner.calls])
        self.assertNotIn("discover", [m for m, _ in self.runner.calls])
        self.assertIn("synthesize", [m for m, _ in self.runner.calls])

    def test_interrupted_job_is_not_silently_replaced_by_new_cycle(self):
        state = self.library.load()
        state["jobs"]["orphaned"] = {"mode": "read", "status": "running", "attempts": 1}
        self.library.save(state)
        result = self.run_library()
        self.assertEqual(result["stop"]["reason"], "interrupted")
        self.assertEqual(self.runner.calls, [])

    def test_detected_title_mismatch_does_not_become_readable_work(self):
        path = self.root / "wrong.epub"
        path.write_bytes(epub())
        result = self.library.add(path, "Wrong Title", "Tester", work_id="wrong")
        self.assertIn("identity_mismatch", result["editions"][1]["errors"][0])
        self.assertEqual(result["editions"][1]["total_chars"], 0)

    def test_short_file_against_external_count_is_a_gap_not_complete(self):
        state = self.library.load()
        work = state["works"]["fixture"]
        work["expected_chapters"] = 5
        work["expected_words"] = 10000
        work["language"] = "en"
        self.library.save(state)
        result = self.library.status()
        self.assertTrue(any("chapter_count_mismatch" in g for g in result["gaps"]))
        self.assertTrue(any("word_count_shortfall" in g for g in result["gaps"]))

    def test_chinese_character_count_is_not_compared_as_english_words(self):
        text = self.root / "chinese.txt"
        text.write_text("第一章\n" + "汉字正文" * 100, encoding="utf-8")
        self.library.add(text, "中文测试", "测试作者", work_id="chinese", language="zh")
        state = self.library.load()
        state["works"]["chinese"]["expected_words"] = 400
        self.library.save(state)
        gaps = self.library.status()["gaps"]
        self.assertFalse(any("word_count_shortfall" in gap for gap in gaps))
        self.assertTrue(any("count_units_unverified" in gap for gap in gaps))

    def test_download_redirect_rechecks_host(self):
        headers = Message()
        headers["Location"] = "https://unregistered.example/book.txt"
        redirect = HTTPError("https://www.gutenberg.org/a", 302, "redirect", headers, None)
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch.object(reference_io.socket, "getaddrinfo", return_value=public), patch.object(reference_io, "build_opener") as opener:
            opener.return_value.open.side_effect = redirect
            with self.assertRaisesRegex(ValueError, "rights_unverified"):
                reference_io.download("https://www.gutenberg.org/a")
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_public_domain_redirect_never_sends_http(self):
        headers = Message()
        headers["Location"] = "http://www.gutenberg.org/cache/book.txt"
        redirect = HTTPError("https://www.gutenberg.org/a", 302, "redirect", headers, None)
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch.object(reference_io.socket, "getaddrinfo", return_value=public), patch.object(reference_io, "build_opener") as opener:
            opener.return_value.open.side_effect = [redirect, ValueError("end of engineering probe")]
            with self.assertRaisesRegex(ValueError, "engineering probe"):
                reference_io.download("https://www.gutenberg.org/a")
            second = opener.return_value.open.call_args_list[1].args[0]
            self.assertEqual(second.full_url, "https://www.gutenberg.org/cache/book.txt")

    def test_rejects_fabricated_reading_and_synthesis_evidence(self):
        packet = {"unit_id": "u1", "text": "Exact words."}
        result = {"unit_id": "u1", "summary": "Summary", "findings": [{"kind": "text_fact", "claim": "claim", "quote": "invented"}], "gaps": []}
        with self.assertRaisesRegex(ValueError, "substring"):
            validate_result("read", result, packet)
        result = {"summary": "Summary", "conclusions": [{"claim": "claim", "evidence_ids": ["absent"]}], "revisions": [], "gaps": []}
        with self.assertRaisesRegex(ValueError, "absent"):
            validate_result("synthesize", result, {"evidence": []})

    def test_original_tampering_never_reports_reading_complete(self):
        self.run_library()
        state = self.library.load()
        self.library.path(state["editions"][0]["source"]["path"]).write_bytes(b"tampered")
        result = self.library.status()
        self.assertFalse(result["editions"][0]["all_units_analyzed"])
        self.assertIn("hash mismatch", result["editions"][0]["errors"][0])

    def test_new_edition_preserves_old_source_and_report(self):
        self.run_library()
        before = self.library.load()
        old_report = self.library.read_artifact(before["latest_report"])
        updated = self.root / "updated.txt"
        updated.write_text("Fixture\nCHAPTER 1\nChanged content.\nAppendix\nNew evidence.", encoding="utf-8")
        self.library.add(updated, "Fixture", "Tester", work_id="fixture")
        result = self.run_library()
        self.assertEqual(len(result["editions"]), 2)
        self.assertEqual(self.library.read_artifact(before["latest_report"]), old_report)
        self.assertTrue(all(e["all_units_analyzed"] for e in result["editions"]))

    def test_binding_versions_report_without_changing_canon(self):
        self.run_library()
        engine = Engine(self.root)
        engine.create_book("fiction", "Fiction fixture")
        canon = engine.files("fiction")["canon/state.json"]
        binding = self.library.bind(engine, "fiction")
        self.assertTrue(binding["path"].startswith("reference/"))
        self.assertIn("novel-reference:fixture-series", binding["text"])
        self.assertEqual(engine.files("fiction")["canon/state.json"], canon)
        revision = engine.book("fiction")["current_revision"]
        self.library.bind(engine, "fiction")
        self.assertEqual(engine.book("fiction")["current_revision"], revision)

    def test_cli_reference_use_binds_report_and_task_creation_refreshes(self):
        from novel.cli import execute, parser
        engine = Engine(self.root)
        engine.create_book("fiction", "Fiction fixture")
        original_run = ReferenceLibrary.run
        def fixture_run(library, **kwargs):
            return original_run(library, runner=self.runner, **kwargs)
        with patch.object(ReferenceLibrary, "run", autospec=True, side_effect=fixture_run):
            bound = execute(parser().parse_args(["--root", str(self.root), "reference-use", self.library.id, "--book", "fiction"]))
            self.assertIn("binding", bound)
            self.runner.calls.clear()
            task = execute(parser().parse_args(["--root", str(self.root), "task-create", "fiction", "research", "--instruction", "Fixture research only"]))
            self.assertEqual([m for m, _ in self.runner.calls], ["discover"])
            self.assertEqual(task["input_revision"], engine.book("fiction")["current_revision"])
            self.assertTrue(any("novel-reference:" in text for text in engine.files("fiction", task["input_revision"]).values()))

    def test_bound_running_task_rejected_before_external_calls(self):
        from novel.references import refresh_bound
        self.run_library()
        engine = Engine(self.root)
        engine.create_book("fiction", "Fiction fixture")
        self.library.bind(engine, "fiction")
        task = engine.enqueue("fiction", "research", "Fixture")
        engine.claim(task["id"])
        with patch.object(ReferenceLibrary, "run") as run:
            with self.assertRaisesRegex(ValueError, "executing tasks"):
                refresh_bound(engine, "fiction")
            run.assert_not_called()

    def test_cli_offline_import_preserves_source_without_model(self):
        from novel.cli import execute, parser
        args = parser().parse_args(["--root", str(self.root), "reference-add", "offline", "--file", str(self.file),
                                   "--title", "Fixture", "--author", "Tester", "--offline"])
        with patch.object(ReferenceLibrary, "run") as run:
            result = execute(args)
            run.assert_not_called()
        self.assertFalse(result["all_acquired_content_analyzed"])
        self.assertEqual(result["editions"][0]["read_chars"], 0)

    def test_model_spawn_log_failure_stops_owned_process(self):
        process = Mock()
        process.pid = 12345
        status = {"ready": True, "model_defaults": {"model": "fixture-model", "reasoning_effort": "high"}}
        original_event = adapter._event
        def fail_started(directory, kind, **details):
            if kind == "started":
                raise OSError("Injected reference log failure")
            original_event(directory, kind, **details)
        with patch.object(adapter, "doctor", return_value=status), patch.object(reference_model.subprocess, "Popen", return_value=process), patch.object(adapter, "_event", side_effect=fail_started), patch.object(adapter, "_stop_tree") as stop:
            with self.assertRaisesRegex(OSError, "Injected reference log failure"):
                reference_model.run("read", {"unit_id": "fixture", "text": "Fixture only"}, self.root / "model-attempt")
            stop.assert_called_once_with(process)

    def test_download_does_not_contact_unregistered_host(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch.object(reference_io.socket, "getaddrinfo", return_value=public), patch.object(reference_io, "build_opener") as opener:
            with self.assertRaisesRegex(ValueError, "rights_unverified"):
                reference_io.download("https://example.org/book.epub")
            opener.return_value.open.assert_not_called()

    def test_public_download_rejects_private_and_credential_urls(self):
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch.object(reference_io.socket, "getaddrinfo", return_value=private):
            with self.assertRaisesRegex(ValueError, "Non-public"):
                reference_io.download("https://www.gutenberg.org/ebooks/1.txt.utf-8")
        with self.assertRaisesRegex(ValueError, "credentials"):
            reference_io.public_url("https://user:pass@example.org/book.epub")


if __name__ == "__main__":
    unittest.main()
