#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "[1/4] Checking Python..."
"$PYTHON_BIN" - <<'PY'
import sys
major, minor = sys.version_info[:2]
if (major, minor) < (3, 9):
    raise SystemExit("Python 3.9+ is required.")
print(f"Using Python {major}.{minor}")
PY

echo "[2/4] Creating virtualenv at $VENV_DIR ..."
"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[3/4] Installing ScriptMate ..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -e .[dev]

if [ ! -f config.toml ]; then
  echo "[4/4] Creating config.toml from example ..."
  cp config.example.toml config.toml
else
  echo "[4/4] config.toml already exists, leaving it unchanged."
fi

echo ""
echo "Bootstrap complete."
echo "Next steps:"
echo "  1. source \"$VENV_DIR/bin/activate\""
echo "  2. \"$VENV_DIR/bin/scriptmate\" --help"
echo "  3. \"$VENV_DIR/bin/scriptmate\" init --config config.toml"
echo "  4. \"$VENV_DIR/bin/scriptmate\" doctor --config config.toml"
