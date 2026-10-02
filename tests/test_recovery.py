"""Run with: python3 -m unittest discover -s tests -p 'test_recovery.py' -v."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "recovery.py"


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Recovery Test")
        self.git("config", "user.email", "recovery@example.invalid")
        self.write(".gitignore", ".recovery/\nbuild/\n")
        self.write("source.cpp", "int original = 1;\n")
        self.write("delete.cpp", "int remove_me = 2;\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(self.root), *args])

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def run_tool(self, *args, code=0):
        result = subprocess.run([sys.executable, str(TOOL), *args], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def capture(self, **kwargs):
        return self.run_tool("checkpoint", "--task", "W01", "--state", "in-progress",
                             "--next", "Review source.cpp and run build", "--evidence", "Caller claims a dry run", **kwargs)

    def latest(self):
        directories = sorted(path for path in (self.root / ".recovery/checkpoints").iterdir()
                             if not path.name.startswith("."))
        folder = directories[-1]
        return folder, json.loads((folder / "manifest.json").read_text())

    def test_tracks_new_modified_deleted_and_distinct_stages(self):
        self.write("source.cpp", "int staged = 3;\n")
        self.git("add", "source.cpp")
        self.write("source.cpp", "int unstaged = 4;\n")
        self.write("new.py", "print('new source')\n")
        self.git("rm", "-q", "delete.cpp")
        self.capture()
        folder, manifest = self.latest()
        self.assertEqual((folder / "files/new.py").read_text(), "print('new source')\n")
        self.assertEqual((folder / "files/source.cpp").read_text(), "int unstaged = 4;\n")
        self.assertEqual(manifest["entries"]["delete.cpp"], {"kind": "deleted"})
        self.assertIn("+int staged = 3;", (folder / "staged.patch").read_text())
        self.assertIn("+int unstaged = 4;", (folder / "unstaged.patch").read_text())
        self.assertIn("delete.cpp", (folder / "staged.patch").read_text())
        self.assertEqual(manifest["evidence_source"], "caller-reported; not verified by this tool")
        result = self.run_tool("status")
        self.assertIn("Integrity: OK", result)
        self.assertIn("Worktree drift since checkpoint: none", result)
        self.assertIn("treat it as untested", result)

    def test_unstaged_deleted_file_is_recorded(self):
        (self.root / "delete.cpp").unlink()
        self.capture()
        folder, manifest = self.latest()
        self.assertEqual(manifest["entries"]["delete.cpp"]["kind"], "deleted")
        self.assertIn("delete.cpp", (folder / "unstaged.patch").read_text())

    def test_tracked_directory_replaced_by_regular_file(self):
        self.write("component/old.cpp", "int old_component = 1;\n")
        self.git("add", "component/old.cpp")
        self.git("commit", "-qm", "directory fixture")
        (self.root / "component/old.cpp").unlink()
        (self.root / "component").rmdir()
        self.write("component", "replacement component\n")
        self.capture()
        folder, manifest = self.latest()
        self.assertEqual(manifest["entries"]["component/old.cpp"], {"kind": "deleted"})
        self.assertEqual((folder / "files/component").read_text(), "replacement component\n")
        self.assertIn("component/old.cpp", (folder / "unstaged.patch").read_text())
        self.assertIn("Worktree drift since checkpoint: none", self.run_tool("status"))

    def test_source_index_and_head_are_not_modified(self):
        self.write("source.cpp", "int dirty = 5;\n")
        self.git("add", "source.cpp")
        self.write("new.py", "pass\n")
        original = {name: (self.root / name).read_bytes() for name in ("source.cpp", "new.py", ".git/index")}
        head = self.git("rev-parse", "HEAD")
        status = self.git("status", "--porcelain=v1", "--untracked-files=all")
        self.capture()
        self.run_tool("status")
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.assertEqual(status, self.git("status", "--porcelain=v1", "--untracked-files=all"))
        for name, value in original.items():
            self.assertEqual(value, (self.root / name).read_bytes())

    def test_symlinks_and_symlink_ancestors_are_not_followed(self):
        self.write("nested/tracked.py", "original\n")
        self.git("add", "nested/tracked.py")
        self.git("commit", "-qm", "nested")
        outside = self.root / ".recovery-outside"
        outside.mkdir()
        self.write(".recovery-outside/tracked.py", "PRIVATE OUTSIDE DATA\n")
        # Keep the outside fixture ignored so it cannot be discovered independently.
        self.write(".gitignore", ".recovery/\n.recovery-outside/\nbuild/\n")
        (self.root / "link.py").symlink_to(outside / "tracked.py")
        (self.root / "nested/tracked.py").unlink()
        (self.root / "nested").rmdir()
        (self.root / "nested").symlink_to(outside, target_is_directory=True)
        self.capture()
        folder, manifest = self.latest()
        self.assertEqual(manifest["entries"]["link.py"]["kind"], "symlink")
        self.assertIn("symlink ancestor", manifest["excluded"]["nested/tracked.py"])
        self.assertFalse((folder / "files/link.py").exists())
        self.assertFalse((folder / "files/nested/tracked.py").exists())
        for path in folder.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE OUTSIDE DATA", path.read_bytes())

    def test_secret_binary_ignored_and_oversized_files_excluded(self):
        self.write(".env", "TOKEN=private\n")
        self.write("credentials.json", '{"password":"private"}\n')
        self.write("build/generated.cpp", "ignored\n")
        self.write("large.txt", "x" * (1024 * 1024 + 1))
        (self.root / "binary.dat").write_bytes(b"binary\0data")
        self.git("add", ".env", "credentials.json", "binary.dat")
        self.capture()
        folder, manifest = self.latest()
        for name in (".env", "credentials.json", "binary.dat", "large.txt"):
            self.assertIn(name, manifest["excluded"])
            self.assertFalse((folder / "files" / name).exists())
        self.assertNotIn("build/generated.cpp", manifest["entries"])
        self.assertNotIn("TOKEN=private", (folder / "staged.patch").read_text())
        self.assertEqual(manifest["limits"]["file_bytes"], 1024 * 1024)

    def test_partial_checkpoint_is_ignored(self):
        self.capture()
        folder, _ = self.latest()
        partial = folder.parent / ".tmp-999999999999"
        partial.mkdir()
        (partial / "manifest.json").write_text('{"complete": true}')
        incomplete = folder.parent / "999999999999"
        incomplete.mkdir()
        result = self.run_tool("status")
        self.assertIn(str(folder), result)
        self.assertNotIn(str(partial), result)

    def test_binary_history_is_not_embedded_in_patches(self):
        (self.root / "old.dat").write_bytes(b"OLD PRIVATE BINARY\0DATA")
        self.git("add", "old.dat")
        self.git("commit", "-qm", "binary history")
        self.git("rm", "-q", "old.dat")
        self.capture()
        folder, manifest = self.latest()
        self.assertEqual(manifest["entries"]["old.dat"]["kind"], "deleted")
        self.assertIn("historical binary", manifest["patch_excluded"]["old.dat"])
        self.assertNotIn("old.dat", (folder / "staged.patch").read_text())

    def test_missing_ignore_rule_is_actionable_and_publishes_nothing(self):
        self.write(".gitignore", "build/\n")
        self.assertIn("Add .recovery/ to .gitignore", self.capture(code=2))
        self.assertFalse((self.root / ".recovery").exists())

    def test_corrupt_snapshot_is_reported_not_silently_skipped(self):
        self.capture()
        folder, _ = self.latest()
        (folder / "files/source.cpp").write_text("corrupt\n")
        result = self.run_tool("status", code=1)
        self.assertIn("Integrity: FAILED", result)
        self.assertIn("files/source.cpp", result)

    def test_drift_and_new_head_are_reported(self):
        self.capture()
        self.write("source.cpp", "int next_version = 8;\n")
        self.write("later.py", "pass\n")
        self.git("add", "source.cpp")
        self.git("commit", "-qm", "later")
        result = self.run_tool("status")
        self.assertIn("(CHANGED)", result)
        self.assertIn("Changed: 'source.cpp'", result)
        self.assertIn("Changed: 'later.py'", result)

    def test_refuses_symlink_recovery_directory(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / ".recovery").symlink_to(outside, target_is_directory=True)
            result = self.capture(code=2)
            self.assertIn("Refusing symlink recovery directory", result)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
