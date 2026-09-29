#!/usr/bin/env bash
# Hourly watcher: posts a compact status of the live janus runs (rank probe,
# external miner) to Telegram until both are finished, then final message
# and self-removal from cron. Used once 2026-09-27 overnight.
set -u
LN=/root/janus
RANK_LOG=~/janus-check.log

ping_tg() {
  TG=/root/.pi/agent/telegram.json
  token=$(python3 -c "import json;print(json.load(open('$TG'))['profiles']['default']['botToken'])" 2>/dev/null) || return 0
  chat=$(python3 -c "import json;print(json.load(open('$TG'))['profiles']['default']['allowedUserId'])" 2>/dev/null)
  [ -n "$token" ] && [ -n "$chat" ] && curl -sS -m 20 -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=$chat" --data-urlencode "text=$1" >/dev/null 2>&1
}

rank_rows=$(ssh -o ConnectTimeout=15 llm-jk "grep -cE '^\[' /home/josh/janus/logs/fresh-rank2-full.log 2>/dev/null" 2>/dev/null || echo "?")
rank_alive=$(ssh -o ConnectTimeout=15 llm-jk "pgrep -c -f 'dev/eval.py'" 2>/dev/null || echo 0)
miner_alive=$(pgrep -f mine_external.py >/dev/null && echo yes || echo no)
miner_done=$(ls /root/janus/eval_corpus/external 2>/dev/null | wc -l)

msg="🕐 janus watcher
rank-run rows: ${rank_rows}/23 (proc alive: ${rank_alive})
JB-1 external fixtures: ${miner_done} (miner running: ${miner_alive})"

if [ "${rank_rows}" = "23" ] || { [ "${rank_alive}" = "0" ] && [ "${rank_rows}" != "?" ]; }; then
  if [ "${miner_alive}" = "no" ]; then
    ping_tg "✅ both janus runs complete.
rank-run rows: ${rank_rows}/23 · external fixtures: ${miner_done}
details: /home/josh/janus/logs/fresh-rank2-full.md (laptop), eval_corpus/external (dev)
WATCHER DONE; cron removed."
    crontab -l 2>/dev/null | grep -v hourly_watch.sh | crontab -
    exit 0
  fi
fi
ping_tg "$msg"

# NOTE: the row count here counts mode-lines (3x fixtures: full/no-gate/no-repair);
# read eval_ledger.json runs for the real count (2026-09-28 lesson).
