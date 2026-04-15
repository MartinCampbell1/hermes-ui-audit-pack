#!/bin/zsh
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")" && pwd)"
CANARY_HOME="${1:-$HOME/Desktop/hermes-canary-home}"
CANARY_REPO="$CANARY_HOME/hermes-agent"
CANARY_PYTHON="$CANARY_REPO/.venv/bin/python"
CANARY_HERMES="$CANARY_REPO/.venv/bin/hermes"
BOOTSTRAP_PYTHON="$HOME/.hermes/hermes-agent/.venv/bin/python"
UPSTREAM_URL="https://github.com/NousResearch/hermes-agent.git"

echo "==> Preparing Hermes canary"
echo "Canary home: $CANARY_HOME"

mkdir -p "$CANARY_HOME"

if [[ -d "$CANARY_REPO/.git" ]]; then
  echo "==> Updating existing canary repo"
  rm -f "$CANARY_REPO/.git/index.lock"
  git -C "$CANARY_REPO" fetch origin
  git -C "$CANARY_REPO" reset --hard origin/main
  git -C "$CANARY_REPO" clean -fd
else
  echo "==> Cloning upstream Hermes into canary"
  git clone "$UPSTREAM_URL" "$CANARY_REPO"
fi

echo "==> Applying approved restore profile onto canary"
HERMES_HOME="$CANARY_HOME" "$BUNDLE_DIR/restore_hermes_live.command"

if [[ ! -x "$BOOTSTRAP_PYTHON" ]]; then
  echo "Bootstrap Python not found at: $BOOTSTRAP_PYTHON" >&2
  exit 1
fi

echo "==> Creating canary virtualenv"
"$BOOTSTRAP_PYTHON" -m venv "$CANARY_REPO/.venv"

echo "==> Installing canary Hermes package"
"$CANARY_PYTHON" -m pip install --upgrade pip >/dev/null
"$CANARY_PYTHON" -m pip install -e "$CANARY_REPO" >/dev/null

echo
echo "Canary ready."
echo "Smoke checks:"
echo "  HERMES_HOME=\"$CANARY_HOME\" \"$CANARY_HERMES\" auth list openai-codex --check"
echo "  HERMES_HOME=\"$CANARY_HOME\" \"$CANARY_HERMES\" chat -Q -q \"ping\""
echo "  HERMES_HOME=\"$CANARY_HOME\" \"$CANARY_HERMES\""
