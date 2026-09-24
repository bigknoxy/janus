#!/bin/sh
set -eu

# Janus installer — idempotent, POSIX sh
# Usage: curl -fsSL https://raw.githubusercontent.com/bigknoxy/janus/main/install.sh | sh
# Env overrides:
#   JANUS_REF      — git ref/tag to install        (default: latest GitHub release tag)
#   JANUS_EXTRA    — "" (core) or "[laya]"         (default: [laya])

REPO="bigknoxy/janus"
EXTRA="${JANUS_EXTRA:-[laya]}"

log() { printf '[janus] %s\n' "$*" >&2; }
err() { printf '[janus] ERROR: %s\n' "$*" >&2; exit 1; }

# ── resolve the latest release tag (falls back to main) ──────────────────────
if [ -z "${JANUS_REF:-}" ]; then
  JANUS_REF=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' || true)
fi
[ -n "${JANUS_REF:-}" ] || JANUS_REF="main"
log "Installing janus ($JANUS_REF)…"

# ── prefer pipx; fall back to pip --user ─────────────────────────────────────
PKG="janus-code$EXTRA @ git+https://github.com/$REPO.git@$JANUS_REF"

if command -v pipx >/dev/null 2>&1; then
  PIP_NO_CACHE_DIR=1 pipx install --force "$PKG" || err "pipx install failed"
  BIN_DIR="$HOME/.local/bin"
else
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 (3.11+) is required."
  fi
  log "pipx not found — using pip --user (install pipx for cleaner isolation: https://pipx.pypa.io)"
  PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")')
  [ "$PYV" -ge 311 ] || err "python 3.11+ required"
  PIP_NO_CACHE_DIR=1 python3 -m pip install --user --break-system-packages "git+https://github.com/$REPO.git@$JANUS_REF#egg=janus-code$EXTRA" \
    2>/dev/null || PIP_NO_CACHE_DIR=1 python3 -m pip install --user "git+https://github.com/$REPO.git@$JANUS_REF#egg=janus-code$EXTRA"
  BIN_DIR="$(python3 -c 'import site; print(site.getuserbase())')/bin"
fi

command -v janus >/dev/null 2>&1 || case ":$PATH:" in *":$BIN_DIR:"*) ;; *) log "Add $BIN_DIR to PATH";; esac
log "Done. Check your rig: janus doctor"
log "First fix: janus run \"fix <symbol> in <file>\" --root ."
