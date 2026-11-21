#!/bin/sh
# User-space install for the Boru Core P1 slice. Non-destructive, no sudo,
# no system service, no autostart, no dependency on TIHULU-AUTO, OpenCode or Jan.
# Usage: scripts/install_boru.sh [--dry-run] [--target DIR] [--state-dir DIR] [--bin-dir DIR]
set -eu

DRY_RUN=0
TARGET="${BORU_TARGET:-$HOME/.local/share/tihulu-boru}"
STATE_DIR="${BORU_STATE_DIR:-$HOME/.local/state/tihulu-boru}"
BIN_DIR="${BORU_BIN_DIR:-$HOME/.local/bin}"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

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

echo "source:       $SOURCE_DIR"
echo "install dir:  $TARGET"
echo "state dir:    $STATE_DIR"
echo "launcher dir: $BIN_DIR"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: no files created, no services started, no configuration changed"
  exit 0
fi

mkdir -p "$TARGET" "$STATE_DIR" "$BIN_DIR"
chmod 700 "$STATE_DIR"
cp -R "$SOURCE_DIR/boru" "$TARGET/boru"
cp "$SOURCE_DIR/examples/core.example.json" "$TARGET/core.example.json"
cp "$SOURCE_DIR/docs/BORU_CORE.md" "$TARGET/BORU_CORE.md"
cp "$SOURCE_DIR/LICENSE" "$TARGET/LICENSE" 2>/dev/null || true

cat > "$BIN_DIR/boru" <<'LAUNCHER'
#!/bin/sh
# Boru Core launcher (user-space, no service, no autostart).
exec python3 -m boru "$@"
LAUNCHER
chmod 755 "$BIN_DIR/boru"

echo "installed: $TARGET (add $BIN_DIR to PATH to use the boru command)"
echo "state directory: $STATE_DIR (owner-only, mode 700)"
echo "No system service was installed and nothing was added to autostart."
