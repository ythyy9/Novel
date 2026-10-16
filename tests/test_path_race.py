"""Deterministic disappearing sidecar regression; retain link/attribute checks."""
from pathlib import Path, PureWindowsPath
import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from novel.engine import Engine, EngineError, checked_path


class PathRaceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='.novel-path-test-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        Engine.initialize(self.root)

    def test_disappearing_sqlite_sidecars_do_not_break_engine_open(self):
        original = Path.lstat
        for suffix in ('-wal', '-shm', '-journal'):
            with self.subTest(suffix=suffix):
                target = self.root / ('runtime/novel.sqlite3' + suffix)
                target.write_bytes(b'')
                removed = []
                def disappear(path, *args, **kwargs):
                    if path == target and not removed:
                        target.unlink()
                        removed.append(True)
                    return original(path, *args, **kwargs)
                # Remove after any legacy exists check but before its lstat;
                # new code must also tolerate disappearance at the direct lstat.
                with patch.object(Path, 'lstat', disappear):
                    opened = Engine(self.root)
                self.assertEqual(removed, [True])
                self.assertEqual(opened.audit()['database'], 'ok')

    def test_existing_and_dangling_symlink_modes_and_reparse_attributes_rejected(self):
        target = self.root / 'runtime/entry'
        original = Path.lstat
        for info in (SimpleNamespace(st_mode=stat.S_IFLNK | 0o777),
                     SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0x400)):
            with self.subTest(info=info):
                target.write_text('fixture', encoding='utf-8')
                def attributes(path, *args, **kwargs):
                    return info if path == target else original(path, *args, **kwargs)
                with patch.object(Path, 'lstat', attributes):
                    with self.assertRaisesRegex(EngineError, 'Reparse points'):
                        checked_path(self.root, 'runtime/entry')
        # A dangling link must not be treated like an absent target. This uses
        # lstat metadata without requiring Windows symlink creation privileges.
        target.unlink()
        with patch.object(Path, 'lstat', lambda p, *a, **k: SimpleNamespace(st_mode=stat.S_IFLNK | 0o777) if p == target else original(p, *a, **k)):
            with self.assertRaises(EngineError):
                checked_path(self.root, 'runtime/entry')

    def test_other_lstat_errors_are_not_ignored(self):
        original = Path.lstat
        target = self.root / 'runtime/entry'
        target.write_text('fixture', encoding='utf-8')
        for error in (PermissionError('denied'), NotADirectoryError('not a directory'), OSError('I/O failure')):
            with self.subTest(error=type(error).__name__):
                def failed(path, *args, **kwargs):
                    if path == target:
                        raise error
                    return original(path, *args, **kwargs)
                with patch.object(Path, 'lstat', failed), self.assertRaises(type(error)):
                    checked_path(self.root, 'runtime/entry')

    def test_absent_leaf_is_supported_but_parent_reparse_is_rejected(self):
        self.assertEqual(checked_path(self.root, 'new/entry.txt'), self.root/'new/entry.txt')
        original = Path.lstat
        target = self.root/'runtime'
        def linked_parent(path, *args, **kwargs):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', linked_parent), self.assertRaises(EngineError):
            checked_path(self.root, 'runtime/missing.txt')

    @unittest.skipUnless(os.name == 'nt', 'Windows directory rename contention')
    def test_transient_snapshot_rename_preserves_complete_publication(self):
        original = Path.rename
        attempts = []
        def rename(path, target):
            attempts.append(path)
            if len(attempts) == 1:
                raise PermissionError('temporary snapshot contention')
            return original(path, target)
        opened = Engine(self.root)
        with patch.object(Path, 'rename', rename):
            opened.create_book('fixture', 'Fixture')
        self.assertEqual(len(attempts), 2)
        self.assertIn('canon/state.json', opened.files('fixture'))
        self.assertEqual(opened.audit()['database'], 'ok')

    @unittest.skipUnless(os.name == 'nt', 'Windows directory rename contention')
    def test_permanent_snapshot_rename_error_does_not_publish(self):
        opened = Engine(self.root)
        with patch.object(Path, 'rename', side_effect=PermissionError('permanent denial')) as rename:
            with self.assertRaises(PermissionError):
                opened.create_book('fixture', 'Fixture')
        self.assertEqual(rename.call_count, 4)
        self.assertEqual(opened.list_books(), [])
        self.assertEqual(opened.audit()['database'], 'ok')


class WindowsResolutionTests(unittest.TestCase):
    def deleted_probe(self, *, persistent=False, next_error=None):
        from novel import engine
        root = PureWindowsPath('D:/work/Novel')
        self.deleted_resolutions = []
        class WindowsFixture(PureWindowsPath):
            def lstat(path):
                if self.deleted_resolutions and path != root and next_error:
                    if next_error == 'reparse':
                        return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
                    raise next_error
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
            def resolve(path):
                if path == root:
                    return str(root)
                self.deleted_resolutions.append(path)
                if persistent or len(self.deleted_resolutions) == 1:
                    return 'D:/$Extend/$Deleted/01A90000000002C00C1EE64D'
                return str(path)
        with patch.object(engine, 'os', SimpleNamespace(name='nt')), patch.object(engine, 'Path', PureWindowsPath):
            return checked_path(WindowsFixture(str(root)), 'runtime/novel.sqlite3-wal')

    def test_deleted_sidecar_resolution_is_rechecked(self):
        self.assertEqual(self.deleted_probe(), PureWindowsPath('D:/work/Novel/runtime/novel.sqlite3-wal'))
        self.assertEqual(len(self.deleted_resolutions), 2)

    def test_persistent_deleted_resolution_still_rejected(self):
        with self.assertRaisesRegex(EngineError, 'Path escapes project'):
            self.deleted_probe(persistent=True)
        self.assertLessEqual(len(self.deleted_resolutions), 4)

    def test_reparse_after_deleted_resolution_is_rejected(self):
        with self.assertRaisesRegex(EngineError, 'Reparse points'):
            self.deleted_probe(next_error='reparse')

    def test_permission_error_after_deleted_resolution_is_not_ignored(self):
        with self.assertRaises(PermissionError):
            self.deleted_probe(next_error=PermissionError('denied'))

    def check_resolved(self, root_text, child_text):
        from novel import engine
        root = PureWindowsPath(root_text)
        class WindowsFixture(PureWindowsPath):
            def lstat(self):
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
            def resolve(self):
                return root_text if self == root else child_text
        fixture = WindowsFixture(root_text)
        # Exercise Windows spelling without pretending the host is Windows or
        # changing global os.name. Actual filesystem/reparse tests remain above.
        with patch.object(engine, 'os', SimpleNamespace(name='nt')), patch.object(engine, 'Path', PureWindowsPath):
            return checked_path(fixture, 'runtime/novel.sqlite3-shm')

    def test_equivalent_windows_drive_and_unc_resolution(self):
        slash = chr(92)
        drive = 'D:/work/Novel'
        unc = slash * 2 + 'server/share/Novel'
        prefix = slash * 2 + '?' + slash
        cases = [(drive, prefix + 'd:' + slash + 'WORK' + slash + 'Novel/runtime/novel.sqlite3-shm'),
                 (prefix + 'D:' + slash + 'work/Novel', 'd:/WORK/Novel/runtime/novel.sqlite3-shm'),
                 (unc, prefix + 'UNC' + slash + 'SERVER/share/Novel/runtime/novel.sqlite3-shm')]
        for root, child in cases:
            with self.subTest(root=root, child=child):
                self.check_resolved(root, child)

    def test_windows_resolved_escapes_still_rejected(self):
        prefix = chr(92)*2 + '?' + chr(92)
        for child in ['D:/work/Novel-other/runtime/x', 'E:/work/Novel/runtime/x',
                      prefix + 'D:' + chr(92) + 'elsewhere/runtime/x',
                      prefix + 'UNC' + chr(92) + 'other/share/Novel/runtime/x']:
            with self.subTest(child=child), self.assertRaisesRegex(EngineError, 'Path escapes project'):
                self.check_resolved('D:/work/Novel', child)

    @unittest.skipUnless(os.name == 'nt', 'Real Windows concurrency diagnostic')
    def test_windows_repeated_receive_and_claim(self):
        import test_exchange_gate
        for iteration in range(50):
            with self.subTest(iteration=iteration):
                result = unittest.TestResult()
                test_exchange_gate.ExchangeGateTests('test_receive_serializes_with_claim').run(result)
                self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
