#!/usr/bin/env bash
set -euo pipefail

log() {
  printf 'ScriptMate: %s\n' "$*" >&2
}

die() {
  log "$*"
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

SCRIPT_DIR="$(CDPATH= cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(CDPATH= cd -P "$SCRIPT_DIR/.." && pwd -P)"
REPOSITORY_ROOT="$(CDPATH= cd -P "$SKILL_ROOT/../.." && pwd -P)"

PYTHON_BIN="${SCRIPTMATE_PYTHON:-python3}"
REPOSITORY_URL="${SCRIPTMATE_REPOSITORY_URL:-https://github.com/zhangyiling108-code/scriptmate.git}"
REVISION="${SCRIPTMATE_REVISION:-main}"

require_command "$PYTHON_BIN"
require_command git
require_command ffmpeg

"$PYTHON_BIN" - <<'PY' || die "Python 3.9 or newer is required."
import sys

if sys.version_info < (3, 9):
    raise SystemExit(1)
PY

if [[ -n "${SCRIPTMATE_CACHE_DIR:-}" ]]; then
  CACHE_DIR="$SCRIPTMATE_CACHE_DIR"
elif [[ -n "${XDG_CACHE_HOME:-}" ]]; then
  CACHE_DIR="$XDG_CACHE_HOME/scriptmate"
elif [[ -n "${HOME:-}" ]]; then
  CACHE_DIR="$HOME/.cache/scriptmate"
else
  die "set SCRIPTMATE_CACHE_DIR, XDG_CACHE_HOME, or HOME to choose a cache directory."
fi

mkdir -p "$CACHE_DIR"

SOURCE_DIR="${SCRIPTMATE_SOURCE_DIR:-}"
MANAGED_SOURCE=0
if [[ -z "$SOURCE_DIR" ]]; then
  if [[ -f "$REPOSITORY_ROOT/pyproject.toml" && -d "$REPOSITORY_ROOT/src/cmm" ]]; then
    SOURCE_DIR="$REPOSITORY_ROOT"
  else
    SOURCE_DIR="$CACHE_DIR/source"
    MANAGED_SOURCE=1
  fi
fi

cleanup_source=""
cleanup_venv=""
previous_venv=""
cleanup() {
  [[ -z "$cleanup_source" ]] || rm -rf "$cleanup_source"
  [[ -z "$cleanup_venv" ]] || rm -rf "$cleanup_venv"
  if [[ -n "$previous_venv" && -e "$previous_venv" && ! -e "${VENV_DIR:-}" ]]; then
    mv "$previous_venv" "$VENV_DIR"
  fi
}
trap cleanup EXIT INT TERM

if [[ "$MANAGED_SOURCE" -eq 1 ]]; then
  if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    cleanup_source="$CACHE_DIR/source.build.$$"
    log "cloning $REPOSITORY_URL at $REVISION"
    git clone --filter=blob:none --single-branch --branch "$REVISION" \
      "$REPOSITORY_URL" "$cleanup_source" >&2 || die "unable to clone the ScriptMate repository."
    mv "$cleanup_source" "$SOURCE_DIR"
    cleanup_source=""
  elif [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
    log "cached source has local changes; keeping the current revision."
  elif git -C "$SOURCE_DIR" fetch --depth=1 origin "$REVISION" >&2; then
    if ! git -C "$SOURCE_DIR" merge --ff-only FETCH_HEAD >&2; then
      log "cached source could not fast-forward; keeping the current revision."
    fi
  else
    log "source update failed; keeping the current cached revision."
  fi
fi

[[ -f "$SOURCE_DIR/pyproject.toml" ]] || die "ScriptMate source is missing pyproject.toml: $SOURCE_DIR"
[[ -d "$SOURCE_DIR/src/cmm" ]] || die "ScriptMate source is missing src/cmm: $SOURCE_DIR"

if git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  SOURCE_ID="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  if [[ -n "$(git -C "$SOURCE_DIR" status --porcelain)" ]]; then
    SOURCE_STATE="$(
      git -C "$SOURCE_DIR" diff --binary
      git -C "$SOURCE_DIR" status --porcelain
    )"
    SOURCE_ID="$SOURCE_ID-dirty-$(printf '%s' "$SOURCE_STATE" | cksum | awk '{print $1}')"
  fi
else
  SOURCE_ID="$SOURCE_DIR"
fi

VENV_DIR="$CACHE_DIR/venv"
STAMP_FILE="$VENV_DIR/.scriptmate-source"
RUNNER="$VENV_DIR/bin/scriptmate"

if [[ -x "$RUNNER" && -f "$STAMP_FILE" && "$(<"$STAMP_FILE")" == "$SOURCE_ID" ]]; then
  printf '%s\n' "$RUNNER"
  exit 0
fi

previous_venv="$CACHE_DIR/venv.previous.$$"
log "building an isolated runtime"
if [[ -e "$VENV_DIR" ]]; then
  mv "$VENV_DIR" "$previous_venv"
fi
cleanup_venv="$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR" || die "unable to create a Python virtual environment."
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check "$SOURCE_DIR" >&2 \
  || die "unable to install ScriptMate dependencies."
printf '%s\n' "$SOURCE_ID" > "$VENV_DIR/.scriptmate-source"
cleanup_venv=""
[[ ! -e "$previous_venv" ]] || rm -rf "$previous_venv"
previous_venv=""

[[ -x "$RUNNER" ]] || die "installation completed without a scriptmate executable."
printf '%s\n' "$RUNNER"
