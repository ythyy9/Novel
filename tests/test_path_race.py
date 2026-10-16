"""Deterministic disappearing sidecar regression; retain link/attribute checks."""
from pathlib import Path
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
