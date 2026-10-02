# Resume pp_infer work after interrupted credit, context or tooling

Open this repository: `/home/ae/Desktop/MasterThesis`.

The user authorized implementation on 2026-10-01. W02 CPU foundations and W03 local ROS adapters are implemented; W04/W05 runtime source migration builds/links against extracted TensorRT 10.16.1.11 and passes synthetic GPU smoke checks; reference semantics, memory/failure checks and W06 remain pending; read PROGRESS.md/tasks.json and the latest checkpoint for verification and remaining blockers. Docker packaging is implemented and verified with synthetic GPU/ROS checks; see docker/README.md and config/docker_inventory.json. Continue using the protocol below, preserving existing work.

The A-to-Z implementation/deployment guide is `docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex`; README now describes the Jazzy workflow. All current build instructions now use colcon; reduced CPU, sanitized CPU and ROS builds/tests passed. Its commands passed syntax/link checks and its synthetic container command passed in isolated ROS domain 91. Built-in LaTeX compilation is pending because the compiler could not retrieve its TeX bundle, before parsing source. Preserve the source and retry with the built-in compiler when available; do not install a terminal TeX distribution for this task.

## Available now

Requirements: Python 3 and Git. No ROS, CUDA, GPU, model access or paid API is needed for checkpoint/status commands. Run from the repository root:

```bash
cd /home/ae/Desktop/MasterThesis
python3 tools/recovery.py status
```

Create a checkpoint at the beginning of a work unit, after coherent edits, after tests, and before a long-running command. Example **for a future W02 implementation session**:

```bash
python3 tools/recovery.py checkpoint \
  --task W02 --state in-progress \
  --next 'Extract CPU geometry from CUDA includes, then run its focused tests.' \
  --evidence 'Not tested yet; see recovery/PROGRESS.md.'
```

After tests actually pass, update progress/ledger first and record their exact command, exit code and saved log path. Then use `--state verified` with evidence. Use `--state blocked` with the missing prerequisite and unblock action when needed. The helper records assertions; it does not run tests or enforce milestone prerequisites.

The helper is run explicitly by the agent or a person. There is no background watcher. A successful checkpoint is an immutable local directory under `.recovery/checkpoints/`; incomplete temporary directories are not accepted as completed checkpoints. Status validates saved content and compares the current tree to the latest completed snapshot. It never checks out, resets, stages, commits or restores files. Save independent backups if disk-loss recovery is required.

Source snapshots include tracked and nonignored untracked eligible UTF-8 text files. Defaults cap files at 1 MiB each, total source snapshots at 16 MiB and each patch at 32 MiB. Build outputs, `.recovery`, model/bag/media binaries, likely credential paths and oversized files are excluded as reported in the manifest. Symlinks are recorded as links, not followed. Ignored artifacts and files outside the repository require their own backup/location/hash records. Exclusions are deliberately not a full-machine backup or a guarantee of detecting every secret; do not put secrets in source or evidence text. Inspect exclusions before relying on a snapshot. Local test logs under `.recovery` remain on disk but are not recursively copied into snapshots.

## Recovery sequence

1. Read `IMPLEMENTATION_ARCHITECTURE.md`, `recovery/tasks.json` and `recovery/PROGRESS.md`. Read repository instructions if present. Do not restart the architecture analysis from scratch.
2. Run `python3 tools/recovery.py status` and inspect the printed checkpoint manifest, integrity result and current drift. Also inspect `git status --short`, `git diff` and `git diff --cached`; account for untracked files separately. A changed HEAD, changed file, failed integrity check or mismatched evidence invalidates any assumption that old tests cover current work.
3. Treat `in-progress` and `blocked` as unfinished. A `verified` label still needs its evidence and relevant hashes. Inspect excluded files relevant to the task. If status reports a corrupt checkpoint, inspect earlier complete checkpoints and their manifests; do not silently trust a fallback or overwrite current files.
4. Check whether an interrupted build, benchmark or engine-generation process is still running before launching another. Inspect outputs before retrying any install/build/promotion command. Keep incomplete engine outputs separate from validated artifacts.
5. Preserve current work. If file recovery is necessary, compare the snapshot file to the working file and recover selected content manually after reviewing the diff. Saved patches describe staged/unstaged state against their recorded base; never blindly apply both onto an already modified checkout. The original Git index is never changed by this helper.
6. Select the interrupted substep first, or the earliest ready task whose dependencies are satisfied. One editor per shared file and one ledger writer. If GPU prerequisites remain blocked, continue independent CPU/ROS work and retain that blocker.
7. Write an `in-progress` checkpoint **before editing**. Complete one coherent patch, run the smallest meaningful affected checks, update progress/ledger, and checkpoint again. Re-run downstream checks when shared contracts change; do not rerun expensive unaffected suites repeatedly.
8. Report what changed, which checks actually passed, what remains blocked and the next action. Never convert absent GPU evidence into a pass.

## Copy into the next chat when ready to implement

> Continue implementation in `/home/ae/Desktop/MasterThesis` using `IMPLEMENTATION_ARCHITECTURE.md`. First read `recovery/RESUME.md`, `recovery/PROGRESS.md` and `recovery/tasks.json`, run `python3 tools/recovery.py status`, and reconcile the actual working tree with the last completed checkpoint. Preserve all existing changes. Resume the interrupted substep or the earliest unblocked task; do not repeat completed work without a reason. Checkpoint before and after each coherent edit/test. Record exact verification evidence and remaining GPU/model blockers. Do not claim inference or real-time performance is verified without target-hardware evidence.

If the old chat is available, resuming it retains conversational context; these files also support a fresh chat. Availability/credits must first permit model work. The local recovery helper cannot increase quota or automatically continue the model after a stop.
