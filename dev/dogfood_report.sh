#!/usr/bin/env bash
# Dogfood check-in: pulls the laptop's latest nightly report and posts a
# one-line status to Pulse (this box) AND Telegram (allowedUserId profile).
# Laptop dogfood turns at 03:17 UTC; this runs ~07:30 UTC on the dev box.
set -u

TG_PROFILE="${PI_TELEGRAM_PROFILE:-/root/.pi/agent/telegram.json}"

notify_pulse() {
  curl -s -X POST http://localhost:31337/notify -H 'Content-Type: application/json' \
    -d "$(printf '{"message": "%s"}' "$(printf '%s' "$1" | tr '"' "'")")" >/dev/null 2>&1 || true
}

notify_telegram() {
  [ -f "$TG_PROFILE" ] || return 0
  local token chat
  token=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["profiles"]["default"]["botToken"])' "$TG_PROFILE" 2>/dev/null) || return 0
  chat=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["profiles"]["default"]["allowedUserId"])' "$TG_PROFILE" 2>/dev/null) || return 0
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    -d chat_id="$chat" --data-urlencode "text=$1" >/dev/null 2>&1 || true
}

notify() { notify_pulse "$1"; notify_telegram "$1"; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

LATEST=$(ssh -o ConnectTimeout=10 llm-jk 'ls -t /home/josh/janus/logs/ 2>/dev/null | grep dogfood | grep "\.md$" | head -1') || LATEST=""
if [ -z "$LATEST" ]; then
  notify "DOGFOOD: no report found on laptop — nightly cron did not fire"
  exit 1
fi
scp -q "llm-jk:/home/josh/janus/logs/$LATEST" "$TMP/report.md" || {
  notify "DOGFOOD: report fetch failed ($LATEST)"
  exit 1
}

SUMMARY=$(tail -5 "$TMP/report.md" | tr '\n' ' ' | head -c 400)
notify "DOGFOOD ($LATEST): $SUMMARY"
echo "dogfood check-in posted (pulse + telegram)"
