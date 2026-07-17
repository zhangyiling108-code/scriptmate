# ScriptMate Universal Skill Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize the latest ScriptMate application into GitHub and publish a small, platform-neutral Skill package under `skills/scriptmate/`.

**Architecture:** Keep the Python application at the repository root as the single source of truth. The Skill package contains only agent instructions and two POSIX shell launchers; it uses the current checkout when available and otherwise installs the canonical GitHub repository into a user cache.

**Tech Stack:** Python 3.9+, Typer, pytest, POSIX shell, Git, FFmpeg, Markdown/YAML frontmatter

## Global Constraints

- Keep `src/`, `tests/`, and `pyproject.toml` as the canonical application implementation.
- Keep the distributable Skill at `skills/scriptmate/`; do not add a root `SKILL.md`.
- Use only `name` and `description` in Skill YAML frontmatter.
- Keep the Skill independent of any particular agent product, registry, uploader, or authentication flow.
- Exclude generated outputs, local environments, caches, archives, sample runs, and process-only packaging notes.
- Preserve unrelated content in the user's existing worktree.
- Require Python 3.9+, Git, and FFmpeg for a complete runtime.
- Update GitHub `main` with a normal non-force push only after every verification passes.

---

## File Structure

- Modify `README.md` and `README.zh-CN.md`: document the synchronized review, local-library, and scoring features.
- Modify `src/cmm/cli.py`: expose local-library indexing and updated matching options.
- Modify `src/cmm/library/__init__.py`: export library index helpers.
- Modify `src/cmm/library/matcher.py`: match indexed local assets and preserve metadata.
- Modify `src/cmm/library/scanner.py`: build and reuse a durable local asset index.
- Modify `src/cmm/models.py`: carry score breakdown and local-library metadata.
- Create `src/cmm/outputs/html_review.py`: generate the static HTML review surface.
- Modify `src/cmm/outputs/report.py`: include score and review details in reports.
- Modify `src/cmm/outputs/writer.py`: write `review.html` and expanded structured output.
- Modify `src/cmm/pipeline.py`: connect indexing, scoring, and output generation.
- Modify `src/cmm/scorer.py`: expose transparent technical and semantic score signals.
- Modify `tests/test_cli.py`, `tests/test_config.py`, and `tests/test_scorer.py`: cover synchronized behavior and hermetic configuration.
- Create `tests/test_library_index.py` and `tests/test_review_html.py`: cover local indexing and HTML review generation.
- Create `tests/test_skill_package.py`: enforce the portable Skill contract.
- Create `skills/scriptmate/SKILL.md`: concise, generic agent workflow.
- Create `skills/scriptmate/scripts/bootstrap.sh`: obtain and install a cached runtime safely.
- Create `skills/scriptmate/scripts/scriptmate.sh`: delegate CLI arguments to the cached runtime.

### Task 1: Synchronize the Latest Application

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `src/cmm/cli.py`
- Modify: `src/cmm/library/__init__.py`
- Modify: `src/cmm/library/matcher.py`
- Modify: `src/cmm/library/scanner.py`
- Modify: `src/cmm/models.py`
- Create: `src/cmm/outputs/html_review.py`
- Modify: `src/cmm/outputs/report.py`
- Modify: `src/cmm/outputs/writer.py`
- Modify: `src/cmm/pipeline.py`
- Modify: `src/cmm/scorer.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_library_index.py`
- Create: `tests/test_review_html.py`
- Modify: `tests/test_scorer.py`

**Interfaces:**
- Consumes: the supplied source snapshot and the existing `cmm` package interfaces.
- Produces: `scan_library(root, metadata_path=None, index_path=None, force=False)`, the `library-index` command, score-breakdown fields on `MaterialCandidate`, and `write_review_html(result, output_dir)`.

- [ ] **Step 1: Install the synchronized tests before implementation**

Apply the source snapshot versions of the five test files listed above without importing generated artifacts or packaging files.

- [ ] **Step 2: Run the focused tests and verify the old implementation fails**

Run:

```bash
python -m pytest \
  tests/test_cli.py tests/test_config.py tests/test_library_index.py \
  tests/test_review_html.py tests/test_scorer.py -q
```

Expected: FAIL because the current GitHub implementation lacks the library index, HTML review writer, and expanded score details.

- [ ] **Step 3: Apply the synchronized application implementation**

Apply the supplied source snapshot versions of the application and README files listed in this task. Do not import its root Skill file, bootstrap packaging, dependency mirror, archives, caches, or internal packaging notes.

- [ ] **Step 4: Run the synchronized test suite**

Run:

```bash
python -m pytest -q
```

Expected: `86 passed` and no failures.

- [ ] **Step 5: Commit the synchronized application**

```bash
git add README.md README.zh-CN.md src tests
git commit -m "feat: sync latest ScriptMate review workflow"
```

### Task 2: Add the Portable Skill Contract

**Files:**
- Create: `tests/test_skill_package.py`
- Create: `skills/scriptmate/SKILL.md`
- Create: `skills/scriptmate/scripts/bootstrap.sh`
- Create: `skills/scriptmate/scripts/scriptmate.sh`

**Interfaces:**
- Consumes: `SCRIPTMATE_REPOSITORY_URL`, `SCRIPTMATE_REVISION`, `SCRIPTMATE_CACHE_DIR`, `SCRIPTMATE_SOURCE_DIR`, and `SCRIPTMATE_PYTHON` environment overrides.
- Produces: `bootstrap.sh` prints one absolute `scriptmate` executable path to stdout; `scriptmate.sh` forwards all CLI arguments and returns the CLI exit code.

- [ ] **Step 1: Write the failing package contract tests**

Create `tests/test_skill_package.py` with the following assertions:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "scriptmate"


def test_skill_package_has_only_required_runtime_files():
    files = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    }
    assert files == {
        "SKILL.md",
        "scripts/bootstrap.sh",
        "scripts/scriptmate.sh",
    }


def test_skill_frontmatter_has_portable_metadata():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    keys = {
        line.split(":", 1)[0].strip()
        for line in frontmatter.splitlines()
        if ":" in line
    }
    assert keys == {"name", "description"}
    assert "name: scriptmate" in frontmatter


def test_skill_uses_the_generic_launcher():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "scripts/scriptmate.sh" in text
    assert "upload" not in text.lower()
    assert not (ROOT / "SKILL.md").exists()
```

Also add `test_launcher_keeps_virtualenv_interpreter_paths_valid`. Create a temporary fake Python executable that writes its own absolute path into a fake `scriptmate` shebang, run `scripts/scriptmate.sh --help` with temporary source and cache overrides, and assert the command returns zero after environment activation. This catches launchers that create a virtual environment in one directory and then move it elsewhere.

- [ ] **Step 2: Run the package tests and verify they fail**

Run:

```bash
python -m pytest tests/test_skill_package.py -q
```

Expected: FAIL because `skills/scriptmate/` does not exist.

- [ ] **Step 3: Create concise generic Skill instructions**

Create `skills/scriptmate/SKILL.md` with only `name` and `description` frontmatter. Direct the agent to gather a script or transcript, aspect ratio, output directory, optional local library, and provider configuration; run `scripts/scriptmate.sh doctor`, `analyze`, `match`, `search`, or `library-index`; review `summary.md`, `review.html`, `manifest.json`, and CSV output; and never reveal API keys or silently enable fallback modes.

- [ ] **Step 4: Implement the bootstrap contract**

Implement `skills/scriptmate/scripts/bootstrap.sh` so that it:

```text
1. Fails with an actionable message when Python 3.9+, Git, or FFmpeg is unavailable.
2. Uses SCRIPTMATE_SOURCE_DIR when explicitly provided.
3. Uses the enclosing repository checkout when it contains pyproject.toml and src/cmm.
4. Otherwise clones the configured repository and revision into the configured user cache.
5. Updates an existing clean cache with fetch plus merge --ff-only; keeps the cached revision on update failure.
6. Backs up the working environment, builds its replacement at the final path so interpreter references remain valid, and restores the backup if installation fails.
7. Prints only the installed scriptmate executable path to stdout; sends progress to stderr.
```

- [ ] **Step 5: Implement argument delegation**

Create `skills/scriptmate/scripts/scriptmate.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNNER="$("$SCRIPT_DIR/bootstrap.sh")"
exec "$RUNNER" "$@"
```

Mark both scripts executable with `chmod 755`.

- [ ] **Step 6: Validate the package and run its tests**

Run:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/scriptmate
python -m pytest tests/test_skill_package.py -q
bash -n skills/scriptmate/scripts/bootstrap.sh
bash -n skills/scriptmate/scripts/scriptmate.sh
```

Expected: validator succeeds, `4 passed`, and both shell syntax checks exit zero.

- [ ] **Step 7: Commit the portable Skill**

```bash
git add skills/scriptmate tests/test_skill_package.py
git commit -m "feat: add portable ScriptMate skill"
```

### Task 3: Release Verification and GitHub Synchronization

**Files:**
- Verify: all tracked files changed since `origin/main`.

**Interfaces:**
- Consumes: the synchronized application and portable Skill package.
- Produces: a verified non-force update of GitHub `main`.

- [ ] **Step 1: Run the full automated suite**

```bash
python -m pytest -q
git diff --check origin/main...HEAD
```

Expected: all tests pass and `git diff --check` emits no output.

- [ ] **Step 2: Run a clean Skill smoke test**

```bash
cache_dir="$(mktemp -d)"
SCRIPTMATE_SOURCE_DIR="$PWD" \
SCRIPTMATE_CACHE_DIR="$cache_dir" \
skills/scriptmate/scripts/scriptmate.sh --help
rm -rf "$cache_dir"
```

Expected: bootstrap succeeds and Typer prints ScriptMate CLI help.

- [ ] **Step 3: Check package limits and platform neutrality**

```bash
find skills/scriptmate -type f | wc -l
du -sk skills/scriptmate
term_a="$(printf '%s%s' 'red' 'skill')"
term_b="$(printf '%s%s' 'xiaohong' 'shu')"
term_c="$(printf '%s%s' '小红' '书')"
if git grep -n -i -E "$term_a|$term_b|$term_c"; then exit 1; fi
```

Expected: three files, comfortably below 10 MiB, and no disallowed platform-specific terms.

- [ ] **Step 4: Review the final commit range**

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
```

Expected: a clean branch containing only the design, plan, synchronized source, tests, READMEs, and `skills/scriptmate/`.

- [ ] **Step 5: Push without rewriting remote history**

```bash
git fetch origin main
test "$(git rev-parse origin/main)" = "$(git merge-base HEAD origin/main)"
git push origin HEAD:main
```

Expected: GitHub accepts a fast-forward update to `main`.
