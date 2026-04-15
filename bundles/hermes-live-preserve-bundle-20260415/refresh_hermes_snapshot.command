#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
SNAPSHOT_DIR="$BUNDLE_DIR/snapshot"
PATCHES_DIR="$BUNDLE_DIR/patches"
LIVE_HOME="${HERMES_HOME:-$HOME/.hermes}"
LIVE_AGENT="$LIVE_HOME/hermes-agent"

typeset -a PATCH_001_FILES=(
  "hermes_cli/auth.py"
  "hermes_cli/auth_commands.py"
  "hermes_cli/runtime_provider.py"
)

typeset -a PATCH_002_FILES=(
  "hermes_cli/main.py"
  "cli.py"
)

typeset -a PATCH_003_FILES=(
  "agent/account_scheduler.py"
  "agent/credential_pool.py"
  "agent/auxiliary_client.py"
  "run_agent.py"
)

typeset -a PATCH_004_FILES=(
  "hermes_state.py"
  "tools/session_search_tool.py"
)

copy_file() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  cp -p "$src" "$dest"
}

write_patch() {
  local patch_name="$1"
  shift
  local patch_path="$PATCHES_DIR/$patch_name"
  git -C "$LIVE_AGENT" diff --binary -- "$@" > "$patch_path"
  if [[ ! -s "$patch_path" ]]; then
    rm -f "$patch_path"
    echo "  skipped $patch_name (no diff)"
    return 1
  fi
  echo "  captured $patch_name"
  return 0
}

write_checksums() {
  local -a checksum_inputs
  checksum_inputs=(
    ./patches/base_ref.txt
    ./patches/series
    ./snapshot/hermes-home/auth.json
    ./snapshot/hermes-home/config.yaml
  )

  local -a patch_files
  patch_files=("${(@f)$(find ./patches -maxdepth 1 -type f -name '*.patch' | sort)}")
  if (( ${#patch_files[@]} > 0 )); then
    checksum_inputs+=("${patch_files[@]}")
  fi

  shasum -a 256 "${checksum_inputs[@]}" > ./checksums.sha256
}

echo "==> Refreshing Hermes preserve snapshot"
echo "Bundle: $BUNDLE_DIR"

if [[ ! -d "$LIVE_AGENT" ]]; then
  echo "Live Hermes repo not found at: $LIVE_AGENT" >&2
  exit 1
fi

if [[ ! -d "$LIVE_AGENT/.git" ]]; then
  echo "Live Hermes repo is not a git checkout: $LIVE_AGENT" >&2
  exit 1
fi

rm -rf "$SNAPSHOT_DIR/hermes-agent" "$PATCHES_DIR"
mkdir -p "$SNAPSHOT_DIR/hermes-home" "$PATCHES_DIR"

copy_file "$LIVE_HOME/auth.json" "$SNAPSHOT_DIR/hermes-home/auth.json"
copy_file "$LIVE_HOME/config.yaml" "$SNAPSHOT_DIR/hermes-home/config.yaml"
chmod 600 "$SNAPSHOT_DIR/hermes-home/auth.json" "$SNAPSHOT_DIR/hermes-home/config.yaml" 2>/dev/null || true

git -C "$LIVE_AGENT" rev-parse HEAD > "$PATCHES_DIR/base_ref.txt"
: > "$PATCHES_DIR/series"

if write_patch "001-auth-runtime.patch" "${PATCH_001_FILES[@]}"; then
  echo "001-auth-runtime.patch" >> "$PATCHES_DIR/series"
fi
if write_patch "002-cli-dashboard.patch" "${PATCH_002_FILES[@]}"; then
  echo "002-cli-dashboard.patch" >> "$PATCHES_DIR/series"
fi
if write_patch "003-pool-runtime.patch" "${PATCH_003_FILES[@]}"; then
  echo "003-pool-runtime.patch" >> "$PATCHES_DIR/series"
fi
if write_patch "004-thread-sessions.patch" "${PATCH_004_FILES[@]}"; then
  echo "004-thread-sessions.patch" >> "$PATCHES_DIR/series"
fi

(
  cd "$BUNDLE_DIR"
  write_checksums
)

echo
echo "Snapshot refreshed."
