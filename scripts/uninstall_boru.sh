#!/bin/sh
# Remove ONLY the paths this installer created. Never touches Jan, OpenCode,
# TIHULU-AUTO, system services or any other owner data.
# Usage: scripts/uninstall_boru.sh [--dry-run] [--target DIR] [--state-dir DIR] [--bin-dir DIR]
set -eu

DRY_RUN=0
TARGET="${BORU_TARGET:-$HOME/.local/share/tihulu-boru}"
STATE_DIR="${BORU_STATE_DIR:-$HOME/.local/state/tihulu-boru}"
BIN_DIR="${BORU_BIN_DIR:-$HOME/.local/bin}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --target) shift; TARGET=${1:?--target needs a directory} ;;
    --state-dir) shift; STATE_DIR=${1:?--state-dir needs a directory} ;;
    --bin-dir) shift; BIN_DIR=${1:?--bin-dir needs a directory} ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

for path in "$TARGET" "$STATE_DIR" "$BIN_DIR/boru"; do
  echo "would remove: $path"
  if [ "$DRY_RUN" -eq 0 ]; then
    rm -rf -- "$path"
  fi
done
echo "Rollback complete: only Boru-owned paths were considered."
if [ "$DRY_RUN" -eq 0 ]; then
  echo "Jan, OpenCode, TIHULU-AUTO and system services were not modified."
fi
