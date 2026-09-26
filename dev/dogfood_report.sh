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

# Pull the fine-tune corpus count (laptop-side accumulator)
FT_COUNT=$(ssh -o ConnectTimeout=10 llm-jk 'cat /home/josh/janus/logs/finetune_count.txt 2>/dev/null || echo 0' 2>/dev/null)
FT_LINE=""
[ -n "$FT_COUNT" ] && [ "$FT_COUNT" != "0" ] && FT_LINE=" | finetune corpus: $FT_COUNT decisions"

# Ledger PR: if the laptop's eval_ledger.json differs from ours, open/refresh a PR.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEDGER_PR=""
if scp -q "llm-jk:/home/josh/janus/eval_ledger.json" "$TMP/ledger.json" 2>/dev/null; then
  if ! cmp -s "$TMP/ledger.json" "$REPO_ROOT/eval_ledger.json" 2>/dev/null; then
    cp "$TMP/ledger.json" "$REPO_ROOT/eval_ledger.json"
    cd "$REPO_ROOT"
    git fetch -q origin main 2>/dev/null || true
    git checkout -q main 2>/dev/null || true
    git checkout -q -B ledger-update 2>/dev/null || true
    git add eval_ledger.json
    git -c user.name=janus-bot -c user.email=janus-bot@users.noreply.github.com commit -qm "chore: eval ledger update ($(date -u +%Y-%m-%d))"
    git push -q -f origin ledger-update 2>/dev/null || true
    EXISTING=$(gh pr list --head ledger-update --json number --jq '.[0].number' 2>/dev/null)
    if [ -z "$EXISTING" ]; then
      PR_URL=$(gh pr create --title "chore: eval ledger update" --body "Auto: nightly dogfood metrics → eval_ledger.json (Pages Ledger reads this at view time)." --base main --head ledger-update 2>/dev/null | tail -1)
    else
      PR_URL=$(gh pr view "$EXISTING" --json url --jq .url 2>/dev/null)
    fi
    [ -n "$PR_URL" ] && LEDGER_PR=" | ledger PR: $PR_URL"
  fi
fi

notify "DOGFOOD ($LATEST): $SUMMARY$FT_LINE$LEDGER_PR"
echo "dogfood check-in posted (pulse + telegram)"
