"""Reader contract tests use real files/SQLite and synthetic writing only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

from novel.engine import Engine, EngineError, canonical, digest, now
from novel.reader import ExportSource, RootSource, chapters, make_handler


class ReaderFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".novel-reader-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = Engine.initialize(self.root)
        self.engine.create_book("test-book", "阅读器工程样本")
        self.files = {"manuscript/001.md": "# 第一章 样本\n\n<script>不执行</script>\n",
                      "manuscript/002-name.md": "# 第二章 另一个样本\n\n工程夹具，不是作品。\n",
                      "decisions/private.md": "不允许通过阅读器读出"}
        self.revision = self.publish(self.files)
        self.source = RootSource(self.root, "test-book")

    def publish(self, files):
        parent = self.engine.book("test-book")["current_revision"]
        revision = self.engine._snapshot("test-book", files, parent, None)
        with self.engine._db(True) as db:
            db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)", (revision, "test-book", parent, "draft", None, now()))
            db.execute("UPDATE books SET current_revision=? WHERE id=?", (revision, "test-book"))
        return revision


class ReaderTests(ReaderFixture, unittest.TestCase):
    def test_hub_adapter_preserves_live_source_line_endings(self):
        from adapters.prepare_reader_hub import prepare, REGISTRATION
        folder = self.root / "hub-copy/backend"
        folder.mkdir(parents=True)
        sample = ('def create_app():\n    def authenticated(request: Request):\n        return {}\n'
                  '    dist = ROOT / "frontend" / "dist"\n    return app\n')
        for newline in ("\n", "\r\n"):
            original = sample.replace("\n", newline).encode("utf-8")
            target = folder / "api.py"
            target.write_bytes(original)
            prepare(folder.parent)
            self.assertEqual(target.read_bytes().replace(REGISTRATION.replace("\n", newline).encode("utf-8"), b"", 1), original)
            with self.assertRaises(ValueError):
                prepare(folder.parent)

    def test_refresh_reads_current_but_chapter_stays_pinned(self):
        before = self.source.catalog()
        self.assertEqual([c["number"] for c in before["chapters"]], [1, 2])
        second = self.publish({**self.files, "manuscript/001.md": "# 第一章\n\n真实返修工程样本\n"})
        self.assertEqual(self.source.catalog()["revision"], second)
        self.assertEqual(self.source.chapter(self.revision, "manuscript/001.md")["text"], self.files["manuscript/001.md"])
        self.assertNotEqual(self.source.chapter(second, "manuscript/001.md")["text"], self.files["manuscript/001.md"])

    def test_reads_do_not_change_database_or_manuscript(self):
        database = self.root / "runtime/novel.sqlite3"
        before = database.read_bytes()
        manifest = self.root / "books/test-book/versions" / self.revision / "manifest.json"
        original = manifest.read_bytes()
        self.source.catalog()
        self.source.chapter(self.revision, "manuscript/002-name.md")
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(manifest.read_bytes(), original)

    def test_rejects_non_manuscript_traversal_and_foreign_revision(self):
        for path in ["decisions/private.md", "../../secret", "manuscript/../../private.md", "manuscript/003.md"]:
            with self.assertRaises(EngineError):
                self.source.chapter(self.revision, path)
        self.engine.create_book("other", "另一个作品")
        with self.assertRaises(EngineError):
            self.source.chapter(self.engine.book("other")["current_revision"], "manuscript/001.md")

    def test_tampering_fails_closed(self):
        path = self.root / "books/test-book/versions" / self.revision / "manuscript/001.md"
        path.write_text("未经控制器修改的内容", encoding="utf-8")
        with self.assertRaises(EngineError):
            self.source.catalog()

    def test_manifest_tampering_fails_closed(self):
        path = self.root / "books/test-book/versions" / self.revision / "manifest.json"
        path.write_text('{"book_id":"test-book","hashes":{}}', encoding="utf-8")
        with self.assertRaises(EngineError):
            self.source.catalog()

    def test_natural_order_and_duplicate_chapter_numbers(self):
        self.assertEqual([c["number"] for c in chapters({"manuscript/10.md":"十", "manuscript/2.md":"二"})], [2, 10])
        with self.assertRaises(EngineError):
            chapters({"manuscript/002.md":"二", "manuscript/002-old.md":"旧二"})

    def test_verified_copy_has_explicit_provenance_and_integrity(self):
        value = {"schema":"novel-reader-export-v1", "book":self.engine.book("test-book"),
                 "revision":self.revision, "checked_at":now(),
                 "documents":[{"path":p,"text":t,"sha256":digest(t),"characters":len(t)}
                              for p,t in self.files.items() if p.startswith("manuscript/")]}
        path = self.root / "reading.json"
        path.write_text(canonical(value), encoding="utf-8")
        source = ExportSource(path)
        self.assertEqual(source.catalog()["source_mode"], "verified_copy")
        self.assertEqual(source.chapter(self.revision,"manuscript/001.md")["text"], self.files["manuscript/001.md"])
        value["documents"][0]["text"] = "篡改"
        path.write_text(canonical(value), encoding="utf-8")
        with self.assertRaises(EngineError):
            source.catalog()

    def test_http_private_headers_no_arbitrary_files_and_rebinding_denied(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.source))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/book") as response:
                self.assertEqual(json.load(response)["revision"], self.revision)
                self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            for request, code in [(base+"/runtime/novel.sqlite3",404),
                                  (Request(base+"/api/book",headers={"Host":"untrusted.example"}),403),
                                  (Request(base+"/api/book",headers={"Sec-Fetch-Site":"cross-site"}),403)]:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request)
                self.assertEqual(caught.exception.code,code)
        finally:
            server.shutdown(); server.server_close(); thread.join()


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"), "Optional Hub web dependencies not installed")
class HubReaderTests(ReaderFixture, unittest.TestCase):
    def test_hub_existing_session_and_workspace_ownership_required(self):
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.testclient import TestClient
        from novel.reader_hub import install_reader, WORKSPACE
        receipt = {"schema_version":1,"workspace":WORKSPACE,"book_id":"test-book", "root":str(self.root),
                   "source_frozen":True,"pilot_accepted":True,"single_writer":"dot",
                   "source_archive_sha256":"a"*64,"source_revision":"b"*64,"pilot_revision":"c"*64}
        receipt_path = self.root.parent / (self.root.name + "-receipt.json")
        self.addCleanup(lambda: receipt_path.unlink(missing_ok=True))
        receipt_path.write_text(canonical(receipt),encoding="utf-8")
        registry_path = self.root / "registry.json"
        registry_path.write_text(canonical({"schema_version":1,"workspaces":{WORKSPACE:{
            "enabled":True,"phase":"formal","root":str(self.root),"book_id":"test-book","owner_id":"owner-a",
            "takeover_receipt":str(receipt_path),"takeover_sha256":hashlib.sha256(receipt_path.read_bytes()).hexdigest()}}}),encoding="utf-8")
        def authenticated(request: Request):
            owner = request.headers.get("X-Synthetic-Test-Owner")
            if not owner: raise HTTPException(401)
            return {"owner_id":owner}
        app = FastAPI()
        install_reader(app, authenticated, registry_path)
        with TestClient(app) as client:
            for route in ["/", "/reader.js", "/api/book", "/api/chapter?revision="+self.revision+"&id=manuscript/001.md"]:
                url = "/novel/reader" + route
                anonymous = client.get(url, follow_redirects=False)
                self.assertEqual(anonymous.status_code,303 if route == "/" else 401)
                if route == "/":
                    self.assertEqual(anonymous.headers["location"], "/")
                self.assertEqual(client.get(url,headers={"X-Synthetic-Test-Owner":"other-owner"}).status_code,403)
                response = client.get(url,headers={"X-Synthetic-Test-Owner":"owner-a"})
                self.assertEqual(response.status_code,200)
                self.assertIn("no-store",response.headers["Cache-Control"])
