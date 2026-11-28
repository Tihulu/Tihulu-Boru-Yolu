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

# The launcher records these paths, so they are absolute: a relative one would
# resolve against whatever directory the owner runs the command from later.
abspath() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s\n' "$PWD/$1" ;;
  esac
}
TARGET=$(abspath "$TARGET")
STATE_DIR=$(abspath "$STATE_DIR")
BIN_DIR=$(abspath "$BIN_DIR")

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
# Re-installing replaces Boru's own tree instead of merging into it, so a
# module removed upstream cannot survive here as a stale import.
if [ -e "$TARGET/boru" ]; then
  rm -rf -- "$TARGET/boru"
fi
cp -R "$SOURCE_DIR/boru" "$TARGET/boru"
cp "$SOURCE_DIR/examples/core.example.json" "$TARGET/core.example.json"
cp "$SOURCE_DIR/docs/BORU_CORE.md" "$TARGET/BORU_CORE.md"
cp "$SOURCE_DIR/LICENSE" "$TARGET/LICENSE" 2>/dev/null || true

cat > "$BIN_DIR/boru" <<LAUNCHER
#!/bin/sh
# Boru Core launcher (user-space, no service, no autostart).
# The install directory is on PYTHONPATH so the command works from any
# working directory; nothing else is added to the environment.
PYTHONPATH="$TARGET\${PYTHONPATH:+:\$PYTHONPATH}"
export PYTHONPATH
exec python3 -m boru "\$@"
LAUNCHER
chmod 755 "$BIN_DIR/boru"

echo "installed: $TARGET (add $BIN_DIR to PATH to use the boru command)"
echo "state directory: $STATE_DIR (owner-only, mode 700)"
echo "No system service was installed and nothing was added to autostart."
