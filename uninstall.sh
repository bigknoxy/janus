#!/bin/sh
set -eu

# Janus uninstaller — removes the package and (optionally) the Laya checkpoint.
# Usage: curl -fsSL https://raw.githubusercontent.com/bigknoxy/janus/main/uninstall.sh | sh

log() { printf '[janus] %s\n' "$*" >&2; }

if command -v pipx >/dev/null 2>&1; then
  pipx uninstall janus-code 2>/dev/null || pipx uninstall janus 2>/dev/null || true
else
  python3 -m pip uninstall -y janus-code 2>/dev/null || true
fi
log "package removed"

# Laya checkpoints live in the HF cache; only touch them on explicit request.
if [ "${JANUS_PURGE_CHECKPOINTS:-0}" = "1" ]; then
  rm -rf "$HOME/.cache/huggingface/hub/models--convaiinnovations--laya" 2>/dev/null || true
  log "laya checkpoints purged"
else
  log "laya checkpoints kept (JANUS_PURGE_CHECKPOINTS=1 to also remove)"
fi
log "clean."
