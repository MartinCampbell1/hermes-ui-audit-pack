#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
SNAPSHOT_DIR="$BUNDLE_DIR/snapshot"
PATCHES_DIR="$BUNDLE_DIR/patches"
LIVE_HOME="${HERMES_HOME:-$HOME/.hermes}"
LIVE_AGENT="$LIVE_HOME/hermes-agent"
ROLLBACK_ROOT="$BUNDLE_DIR/restore-rollbacks"
STAMP="$(date +%Y%m%d_%H%M%S)"
ROLLBACK_DIR="$ROLLBACK_ROOT/$STAMP"

typeset -a AGENT_FILES=(
  "hermes_cli/auth.py"
  "hermes_cli/auth_commands.py"
  "hermes_cli/main.py"
  "hermes_cli/runtime_provider.py"
  "cli.py"
  "hermes_state.py"
  "agent/account_scheduler.py"
  "agent/credential_pool.py"
  "agent/auxiliary_client.py"
  "run_agent.py"
  "tools/session_search_tool.py"
)

backup_file() {
  local src="$1"
  local dest="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    cp -p "$src" "$dest"
  fi
}

restore_file() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  cp -p "$src" "$dest"
}

restore_or_remove_from_backup() {
  local backup="$1"
  local dest="$2"
  if [[ -f "$backup" ]]; then
    restore_file "$backup" "$dest"
  else
    rm -f "$dest"
  fi
}

rollback_restore() {
  echo "==> Restore failed; rolling back to pre-restore live files" >&2
  restore_or_remove_from_backup "$ROLLBACK_DIR/hermes-home/auth.json" "$LIVE_HOME/auth.json"
  restore_or_remove_from_backup "$ROLLBACK_DIR/hermes-home/config.yaml" "$LIVE_HOME/config.yaml"
  for rel in "${AGENT_FILES[@]}"; do
    restore_or_remove_from_backup "$ROLLBACK_DIR/hermes-agent/$rel" "$LIVE_AGENT/$rel"
  done
}

apply_patch_file() {
  local patch_path="$1"
  local patch_name
  patch_name="$(basename "$patch_path")"
  if [[ ! -f "$patch_path" ]]; then
    echo "Missing patch file: $patch_path" >&2
    return 1
  fi

  if git -C "$LIVE_AGENT" apply --reverse --check "$patch_path" >/dev/null 2>&1; then
    echo "  already applied $patch_name"
    return 0
  fi

  if git -C "$LIVE_AGENT" apply --3way --whitespace=nowarn "$patch_path"; then
    echo "  applied $patch_name"
    return 0
  fi

  echo "Failed to apply patch: $patch_name" >&2
  return 1
}

echo "==> Hermes live restore"
echo "Bundle: $BUNDLE_DIR"

if [[ ! -d "$LIVE_AGENT" ]]; then
  echo "Live Hermes repo not found at: $LIVE_AGENT" >&2
  exit 1
fi

if [[ ! -d "$LIVE_AGENT/.git" ]]; then
  echo "Live Hermes repo is not a git checkout: $LIVE_AGENT" >&2
  exit 1
fi

if [[ ! -f "$PATCHES_DIR/series" ]]; then
  echo "Patch series not found: $PATCHES_DIR/series" >&2
  exit 1
fi

mkdir -p "$ROLLBACK_DIR/hermes-home" "$ROLLBACK_DIR/hermes-agent"

echo "==> Saving rollback copy to: $ROLLBACK_DIR"
backup_file "$LIVE_HOME/auth.json" "$ROLLBACK_DIR/hermes-home/auth.json"
backup_file "$LIVE_HOME/config.yaml" "$ROLLBACK_DIR/hermes-home/config.yaml"

for rel in "${AGENT_FILES[@]}"; do
  backup_file "$LIVE_AGENT/$rel" "$ROLLBACK_DIR/hermes-agent/$rel"
done

echo "==> Restoring preserved config and auth store"
restore_file "$SNAPSHOT_DIR/hermes-home/auth.json" "$LIVE_HOME/auth.json"
restore_file "$SNAPSHOT_DIR/hermes-home/config.yaml" "$LIVE_HOME/config.yaml"
chmod 600 "$LIVE_HOME/auth.json" "$LIVE_HOME/config.yaml" 2>/dev/null || true

echo "==> Applying approved patch stack"
echo "Patch base ref: $(cat "$PATCHES_DIR/base_ref.txt" 2>/dev/null || echo unknown)"
typeset -a PATCH_FILES
PATCH_FILES=("${(@f)$(<"$PATCHES_DIR/series")}")
for patch_name in "${PATCH_FILES[@]}"; do
  if [[ -z "$patch_name" ]]; then
    continue
  fi
  if ! apply_patch_file "$PATCHES_DIR/$patch_name"; then
    rollback_restore
    exit 1
  fi
done

echo "==> Quick syntax check"
python3 -m py_compile \
  "$LIVE_AGENT/hermes_cli/auth.py" \
  "$LIVE_AGENT/hermes_cli/auth_commands.py" \
  "$LIVE_AGENT/hermes_cli/main.py" \
  "$LIVE_AGENT/hermes_cli/runtime_provider.py" \
  "$LIVE_AGENT/cli.py" \
  "$LIVE_AGENT/hermes_state.py" \
  "$LIVE_AGENT/agent/account_scheduler.py" \
  "$LIVE_AGENT/agent/credential_pool.py" \
  "$LIVE_AGENT/agent/auxiliary_client.py" \
  "$LIVE_AGENT/run_agent.py" \
  "$LIVE_AGENT/tools/session_search_tool.py"

echo
echo "Restore complete."
echo "Rollback copy: $ROLLBACK_DIR"
echo "Next step: restart Hermes."
