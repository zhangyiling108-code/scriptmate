import os
import subprocess
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


def test_launcher_keeps_virtualenv_interpreter_paths_valid(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        """#!/bin/sh
set -eu
if [ "${1:-}" = "-" ]; then
  exit 0
fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
  target="$3"
  mkdir -p "$target/bin"
  cp "$0" "$target/bin/python"
  chmod 755 "$target/bin/python"
  exit 0
fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "pip" ]; then
  runner="$(dirname "$0")/scriptmate"
  printf '#!%s\\nprintf "%%s\\n" "fake ScriptMate help"\\n' "$0" > "$runner"
  chmod 755 "$runner"
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_ffmpeg = fake_bin / "ffmpeg"
    fake_ffmpeg.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_ffmpeg.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SCRIPTMATE_PYTHON": str(fake_python),
            "SCRIPTMATE_SOURCE_DIR": str(ROOT),
            "SCRIPTMATE_CACHE_DIR": str(tmp_path / "cache"),
        }
    )
    result = subprocess.run(
        [str(SKILL_ROOT / "scripts" / "scriptmate.sh"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "fake ScriptMate help" in result.stdout
