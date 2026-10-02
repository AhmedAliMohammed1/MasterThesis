#!/usr/bin/env python3
"""Offline, read-only-to-Git work checkpoints. Never restores files or runs a model."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone

FILE_LIMIT = 1024 * 1024
TOTAL_LIMIT = 16 * FILE_LIMIT
PATCH_LIMIT = 32 * FILE_LIMIT
SKIP_DIRS = {".recovery", ".git", "build", "install", "log", "node_modules",
             "__pycache__", ".venv", "venv", "models", "bags", "assets"}
SKIP_SUFFIXES = {".bag", ".db3", ".mcap", ".pt", ".pth", ".onnx", ".engine",
                 ".bin", ".weights", ".pem", ".key", ".p12", ".pfx"}


def git(root, *args, check=True):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    return result.stdout if result.returncode == 0 else b""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(root):
    index = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "index")).strip())
    if not index.is_absolute():
        index = root / index
    return {"head": git(root, "rev-parse", "--verify", "HEAD", check=False).decode().strip() or None,
            "branch": git(root, "symbolic-ref", "--short", "HEAD", check=False).decode().strip() or "(detached/unborn)",
            "index_sha256": digest(index.read_bytes()) if index.is_file() else None}


def policy(path):
    parts = Path(path).parts
    if not parts or Path(path).is_absolute() or ".." in parts:
        return "unsafe path"
    if any(part.lower() in SKIP_DIRS for part in parts):
        return "generated, asset, or recovery directory"
    name = parts[-1].lower()
    if (name.startswith(".env") or any(word in name for word in ("secret", "credential"))
            or name in {"id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc"}
            or Path(name).suffix in SKIP_SUFFIXES):
        return "secret, model, bag, or binary filename"
    return None


def paths(root):
    found = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    # HEAD also contains files already removed from the index by git rm.
    found += git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD", check=False)
    return sorted(set(os.fsdecode(value) for value in found.split(b"\0") if value))


def read_entry(root, name):
    path = root / name
    for parent in Path(name).parents:
        if parent != Path(".") and (root / parent).is_symlink():
            return None, None, "symlink ancestor (not followed)"
    try:
        info = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return {"kind": "deleted"}, None, None
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", "target": os.readlink(path), "mode": mode}, None, None
    if not stat.S_ISREG(info.st_mode):
        return None, None, "non-regular file"
    if info.st_size > FILE_LIMIT:
        return None, None, "exceeds 1 MiB per-file cap"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        data = stream.read(FILE_LIMIT + 1)
    if len(data) > FILE_LIMIT:
        return None, None, "exceeds 1 MiB per-file cap"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None, None, "non-UTF-8/binary content"
    if b"\0" in data:
        return None, None, "NUL/binary content"
    return {"kind": "file", "mode": mode, "size": len(data), "sha256": digest(data)}, data, None


def inventory(root, output=None):
    entries, excluded, total = {}, {}, 0
    for name in paths(root):
        reason = policy(name)
        if reason:
            excluded[name] = reason
            continue
        entry, data, reason = read_entry(root, name)
        if reason:
            excluded[name] = reason
            continue
        total += len(data or b"")
        if total > TOTAL_LIMIT:
            raise RuntimeError("Text snapshot exceeds 16 MiB total cap; no checkpoint published.")
        entries[name] = entry
        if output is not None and data is not None:
            target = output / "files" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return entries, excluded


def save_patch(root, target, names, staged=False):
    if not names:
        target.write_bytes(b"")
        return
    command = ["git", "--no-optional-locks", "--literal-pathspecs", "-C", str(root),
               "diff", "--binary", "--no-ext-diff", "--no-textconv"]
    if staged:
        command.append("--cached")
    command += ["--", *names]
    with target.open("wb") as stream, subprocess.Popen(command, stdout=subprocess.PIPE,
                                                       stderr=subprocess.DEVNULL) as process:
        total = 0
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > PATCH_LIMIT:
                process.kill()
                raise RuntimeError("Patch exceeds 32 MiB cap; no checkpoint published.")
            stream.write(chunk)
        if process.wait():
            raise RuntimeError("Git could not generate a recovery patch.")


def patch_scope(root, entries):
    """Do not embed excluded binary/oversized historical blobs inside patches."""
    excluded = {name: "symlink recorded in manifest only" for name, entry in entries.items()
                if entry["kind"] == "symlink"}
    records = git(root, "ls-files", "--stage", "-z") + git(root, "ls-tree", "-r", "-z", "HEAD", check=False)
    seen = {}
    for record in records.split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        name = os.fsdecode(raw_name)
        if name not in entries or name in excluded:
            continue
        fields = metadata.split()
        oid = fields[2] if fields[1] == b"blob" else fields[1]
        if oid not in seen:
            if fields[0] not in (b"100644", b"100755"):
                seen[oid] = "historical symlink or non-regular object"
            elif int(git(root, "cat-file", "-s", oid.decode())) > FILE_LIMIT:
                seen[oid] = "historical blob exceeds 1 MiB cap"
            else:
                blob = git(root, "cat-file", "blob", oid.decode())
                try:
                    blob.decode("utf-8")
                    seen[oid] = "historical binary blob" if b"\0" in blob else None
                except UnicodeDecodeError:
                    seen[oid] = "historical non-UTF-8 blob"
        if seen[oid]:
            excluded[name] = seen[oid]
    return [name for name in entries if name not in excluded], excluded


def recovery_dir(root, create=False):
    target = root
    for name in (".recovery", "checkpoints"):
        target = target / name
        if target.is_symlink():
            raise RuntimeError(f"Refusing symlink recovery directory: {target}")
        if create:
            target.mkdir(exist_ok=True, mode=0o700)
    return target


def checkpoint(root, args):
    recovery_dir(root)  # Check for symlinks before asking Git to inspect that path.
    if not git(root, "check-ignore", ".recovery/checkpoints/probe", check=False):
        raise RuntimeError("Add .recovery/ to .gitignore before creating local checkpoints.")
    location = recovery_dir(root, create=True)
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    temporary = location / (".tmp-" + label)
    temporary.mkdir(mode=0o700)
    try:
        before = identity(root)
        status_before = git(root, "status", "--porcelain=v1", "--untracked-files=all")
        entries, excluded = inventory(root, temporary)
        names, patch_excluded = patch_scope(root, entries)
        save_patch(root, temporary / "staged.patch", names, staged=True)
        save_patch(root, temporary / "unstaged.patch", names)
        (temporary / "git-status.txt").write_bytes(status_before)
        if identity(root) != before or inventory(root) != (entries, excluded) or git(
                root, "status", "--porcelain=v1", "--untracked-files=all") != status_before:
            raise RuntimeError("Worktree or Git state changed during capture; retry checkpoint.")
        artifacts = {name: digest((temporary / name).read_bytes())
                     for name in ("staged.patch", "unstaged.patch", "git-status.txt")}
        manifest = {"format": 1, "complete": True, "created_utc": label, "root": str(root),
                    "task": args.task, "state": args.state, "next": args.next,
                    "evidence": args.evidence, "evidence_source": "caller-reported; not verified by this tool",
                    **before, "entries": entries, "excluded": excluded, "patch_excluded": patch_excluded,
                    "artifacts": artifacts,
                    "limits": {"file_bytes": FILE_LIMIT, "total_file_bytes": TOTAL_LIMIT,
                               "each_patch_bytes": PATCH_LIMIT},
                    "scope": "tracked + nonignored untracked UTF-8 files; filename exclusions are not a secret scanner"}
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")
        # Flush before atomic publication. Partial .tmp-* directories are never resumed.
        for path in temporary.rglob("*"):
            if path.is_file():
                with path.open("rb") as stream:
                    os.fsync(stream.fileno())
        temporary.rename(location / label)
        print(f"Checkpoint saved: {location / label}")
        print(f"Captured {len(entries)} paths; excluded {len(excluded)}. Limits: 1 MiB/file, 16 MiB text total, 32 MiB/patch.")
        print("State and evidence are caller-reported. No tests were run; no source or Git index was changed.")
        for name, reason in excluded.items():
            print(f"  Excluded {name!r}: {reason}")
        for name, reason in patch_excluded.items():
            print(f"  Patch omitted for {name!r}: {reason}")
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def status(root):
    location = recovery_dir(root)
    candidates = sorted((path for path in location.iterdir() if path.is_dir() and not path.is_symlink()
                         and not path.name.startswith(".") and (path / "manifest.json").is_file()),
                        reverse=True) if location.exists() else []
    if not candidates:
        print("No complete checkpoint found. Partial .tmp-* checkpoints are ignored.")
        return 1
    latest = candidates[0]
    if (latest / "manifest.json").is_symlink():
        raise RuntimeError("Refusing symlink checkpoint manifest.")
    manifest = json.loads((latest / "manifest.json").read_text())
    if manifest.get("format") != 1 or manifest.get("complete") is not True:
        raise RuntimeError(f"Invalid checkpoint manifest: {latest}")
    failures = []
    checks = {**manifest["artifacts"], **{"files/" + name: entry["sha256"]
              for name, entry in manifest["entries"].items() if entry["kind"] == "file"}}
    for name, expected in checks.items():
        path = latest / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink() or any(
                parent.is_symlink() for parent in path.parents if parent != latest):
            failures.append(name + " (unsafe snapshot path)")
        elif not path.is_file() or digest(path.read_bytes()) != expected:
            failures.append(name)
    print(f"Checkpoint: {latest}\nTask: {manifest['task']}\nState (caller-reported): {manifest['state']}")
    print(f"Next: {manifest['next']}\nEvidence (caller-reported, unverified): {manifest['evidence'] or '(none)'}")
    print("Integrity: " + ("FAILED: " + ", ".join(failures) if failures else "OK (snapshot and patch SHA-256 checks)"))
    if manifest["state"] in {"in-progress", "blocked"}:
        print("WARNING: This checkpoint contains unfinished work; treat it as untested.")
    else:
        print("The verified state is a caller claim; independently rerun the recorded checks.")
    current = identity(root)
    print(f"HEAD: {manifest['head']} -> {current['head']}" + (" (CHANGED)" if current['head'] != manifest['head'] else " (unchanged)"))
    print(f"Branch: {manifest['branch']} -> {current['branch']}")
    if current["index_sha256"] != manifest["index_sha256"]:
        print("Git index changed since checkpoint; review git diff --cached.")
    entries, excluded = inventory(root)
    drift = [name for name in sorted(set(entries) | set(manifest["entries"]))
             if entries.get(name) != manifest["entries"].get(name)]
    print("Worktree drift since checkpoint: " + (str(len(drift)) + " path(s)" if drift else "none within captured scope"))
    for name in drift:
        print(f"  Changed: {name!r}")
    old_status = (latest / "git-status.txt").read_bytes() if not failures else b""
    if old_status != git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        print("Git status differs (staging and/or file status changed); review git diff and git diff --cached.")
    print(f"Excluded at capture: {len(manifest['excluded'])}; excluded now: {len(excluded)}; patch omissions: {len(manifest['patch_excluded'])}. See manifest.json for reasons.")
    print("Limits: 1 MiB/file, 16 MiB text total, 32 MiB/patch. Ignored files and excluded data are not backed up.")
    print("Resume by reviewing the manifest, current diffs, and Next instruction. Restoration is manual; this tool never overwrites work.")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("checkpoint", help="Save a local checkpoint without changing Git or source files")
    capture.add_argument("--task", required=True)
    capture.add_argument("--state", choices=("in-progress", "blocked", "verified"), required=True)
    capture.add_argument("--next", required=True)
    capture.add_argument("--evidence", default="")
    commands.add_parser("status", help="Verify and describe the latest complete checkpoint")
    args = parser.parse_args()
    try:
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
        if args.command == "checkpoint":
            checkpoint(root, args)
            return 0
        return status(root)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"Recovery error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
