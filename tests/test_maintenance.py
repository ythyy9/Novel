import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("maintenance", Path(__file__).resolve().parents[1] / "ops/maintenance.py")
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


class ManifestTests(unittest.TestCase):
    def payload(self):
        return {"request_id": "repair-test", "base_sha256": "a" * 64,
                "reason": "Fix a tested regression.", "files": {"novel/example.py": "VALUE = 1\n"}}

    def test_supported_source_is_compiled_without_execution(self):
        data = self.payload()
        data["files"]["novel/example.py"] = "raise RuntimeError('must not run')\n"
        self.assertIn("novel/example.py", maintenance.check_manifest(data))

    def test_denies_business_paths_shell_and_path_escapes(self):
        for path in ("../novel/a.py", "/novel/a.py", "novel/../a.py", "novel\\a.py",
                     "novel/x/a.py", "books/book.py", "runtime/data.py", "ops/maintenance.py",
                     "policies/principles.py", "tests/helper.py", "novel/a.py/"):
            with self.subTest(path=path):
                data = self.payload()
                data["files"] = {path: "x = 1"}
                with self.assertRaises(ValueError):
                    maintenance.check_manifest(data)
        data = self.payload()
        data["command"] = "anything"
        with self.assertRaises(ValueError):
            maintenance.check_manifest(data)

    def test_invalid_identity_size_and_syntax_are_rejected(self):
        for field, value in (("request_id", "../bad"), ("base_sha256", "bad"), ("files", {}), ("reason", "")):
            data = self.payload()
            data[field] = value
            with self.assertRaises(ValueError):
                maintenance.check_manifest(data)
        data = self.payload()
        data["files"] = {"novel/x.py": "this is ! invalid"}
        with self.assertRaises(SyntaxError):
            maintenance.check_manifest(data)

    def test_release_replay_conflict_stale_baseline_and_validation_gate(self):
        with tempfile.TemporaryDirectory(prefix=".novel-ops-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            base = Path(tmp)
            (base / "releases").mkdir()
            source = base / "seed"
            (source / "novel").mkdir(parents=True)
            (source / "novel/example.py").write_text("VALUE = 0\n")
            active = {"source": str(source), "unit": "fixture", "port": 1, "slot": "legacy"}
            maintenance.save(base / "current.json", active)
            service = maintenance.Maintenance({"base": str(base)})
            files = maintenance.inventory(source)
            baseline = maintenance.sha(maintenance.encoded(files))
            service.status = lambda: {"active": active, "files": files, "source_sha256": baseline}
            data = {**self.payload(), "base_sha256": baseline}
            first = service.stage(data)
            self.assertEqual(first, service.stage(data))
            with self.assertRaisesRegex(ValueError, "different arguments"):
                service.stage({**data, "reason": "Changed"})
            with self.assertRaisesRegex(ValueError, "Stale"):
                service.stage({**data, "request_id": "stale", "base_sha256": "b" * 64})
            with self.assertRaisesRegex(ValueError, "validation"):
                service.deploy(first["id"])
            self.assertEqual((source / "novel/example.py").read_text(), "VALUE = 0\n")

    def test_interrupted_operations_require_inspection(self):
        with tempfile.TemporaryDirectory(prefix=".novel-ops-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            base = Path(tmp)
            folder = base / "releases/example"
            folder.mkdir(parents=True)
            maintenance.save(folder / "receipt.json", {"state": "deploying"})
            service = maintenance.Maintenance({"base": str(base)})
            self.assertEqual(service.release("example")["state"], "interrupted")
            with self.assertRaisesRegex(ValueError, "validation"):
                service.deploy("example")

    def test_staging_snapshots_actual_managed_service_without_accepting_caller_ops(self):
        with tempfile.TemporaryDirectory(prefix=".novel-ops-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            base = Path(tmp)
            (base / "releases").mkdir()
            source = base / "seed"
            (source / "novel").mkdir(parents=True)
            (source / "ops").mkdir()
            (source / "novel/example.py").write_text("VALUE = 0\n")
            (source / "ops/maintenance.py").write_text("OLD_SNAPSHOT = True\n")
            (base / "maintenance.py").write_text("ACTUAL_SERVICE = True\n")
            (base / "private-token.json").write_text("synthetic secret must stay out")
            active = {"source": str(source), "unit": "fixture", "port": 1, "slot": "legacy"}
            maintenance.save(base / "current.json", active)
            service = maintenance.Maintenance({"base": str(base)})
            files = maintenance.inventory(source)
            baseline = maintenance.sha(maintenance.encoded(files))
            service.status = lambda: {"active": active, "files": files, "source_sha256": baseline}
            receipt = service.stage({**self.payload(), "base_sha256": baseline})
            staged = Path(receipt["source"])
            self.assertEqual((staged / "ops/maintenance.py").read_bytes(), (base / "maintenance.py").read_bytes())
            self.assertEqual(receipt["managed_source_snapshots"], {"ops/maintenance.py": maintenance.sha((base / "maintenance.py").read_bytes())})
            self.assertFalse((staged / "private-token.json").exists())
            self.assertEqual(service.stage({**self.payload(), "base_sha256": baseline}), receipt)
            with self.assertRaisesRegex(ValueError, "Only novel"):
                service.stage({**self.payload(), "base_sha256": baseline, "files": {"ops/maintenance.py": "CALLER = True\n"}})

    def test_source_inventory_keeps_reader_assets_and_excludes_runtime(self):
        with tempfile.TemporaryDirectory(prefix=".novel-ops-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            root = Path(tmp)
            for name in ("novel/reader_assets/index.html", "novel/reader_assets/app.js",
                         "novel/reader_assets/style.css", "runtime/secret.json"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture")
            files = maintenance.inventory(root)
            self.assertEqual(set(files), {"novel/reader_assets/index.html", "novel/reader_assets/app.js",
                                          "novel/reader_assets/style.css"})

    def test_drain_preserves_old_api_if_proxy_still_requires_it(self):
        service = object.__new__(maintenance.Maintenance)
        service.lock = maintenance.threading.Lock()
        service.config = {"proxy_unit": "proxy.service"}
        service.current = lambda: {"unit": "novel-api-blue.service"}
        service.run = Mock(return_value=Mock(stdout="Requires=agent-hub-api.service\n"))
        service.drain({"unit": "agent-hub-api.service", "port": 8765})
        self.assertEqual(service.run.call_count, 1)
        self.assertEqual(service.run.call_args.args[0][:3], ["systemctl", "show", "proxy.service"])

    def test_deployed_release_replay_has_no_runtime_or_receipt_changes(self):
        with tempfile.TemporaryDirectory(prefix=".novel-ops-test-", dir=Path(__file__).resolve().parents[1]) as tmp:
            base = Path(tmp)
            folder = base / "releases/done"
            folder.mkdir(parents=True)
            expected = {"id": "done", "state": "deployed", "deployed_at": 123,
                        "source_sha256": "a" * 64, "business_writes": False}
            path = folder / "receipt.json"
            maintenance.save(path, expected)
            before = (path.read_bytes(), path.stat().st_mtime_ns)
            service = maintenance.Maintenance({"base": str(base)})
            service.activate = Mock(side_effect=AssertionError("Must not switch or restart"))
            service.run = Mock(side_effect=AssertionError("Must not run a command"))
            service.status = Mock(side_effect=AssertionError("Must return saved receipt directly"))
            self.assertEqual(service.deploy("done"), expected)
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
            service.activate.assert_not_called()
            service.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
