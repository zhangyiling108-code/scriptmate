#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
RUNNER="$("$SCRIPT_DIR/bootstrap.sh")"
exec "$RUNNER" "$@"
