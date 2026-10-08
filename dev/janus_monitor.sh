#!/usr/bin/env bash
# janus event monitor — quiet by default (2026-09-29, after the hourly
# watcher was shut off for noise). Cron checks every 20 min; pings Telegram
# ONLY on real events:
#   1. JB-1 sweep transition (miner exit → the yield report, once)
#   2. zero-yield miner exit (a finding, not silence)
#   3. eval process death mid-run (no completed md)
#   4. ledger-PR staleness (laptop ledger ≠ the COMMITTED main ledger —
#      ping ONCE per episode; the old working-tree comparison fired through
#      every rebase — the 2026-10-01 ping storm, one ping per 20-min sweep
#      while a branch's stale ledger sat in the tree)
#   5. repo parked off main → AUTO-FIX (atomic rescue) + ping
# The ledger-PR and eval-death watches stay armed permanently; the sweep
# transition fires once.
set -u
STATE=/root/janus/logs/monitor-state.json
touch "$STATE" 2>/dev/null || STATE=/tmp/monitor-state.json

tg() {
  TG=/root/.pi/agent/telegram.json
  token=$(python3 -c "import json;print(json.load(open('$TG'))['profiles']['default']['botToken'])" 2>/dev/null) || return 0
  chat=$(python3 -c "import json;print(json.load(open('$TG'))['profiles']['default']['allowedUserId'])" 2>/dev/null)
  [ -n "$token" ] && [ -n "$chat" ] && curl -sS -m 20 -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=$chat" --data-urlencode "text=$1" >/dev/null 2>&1
}

stget() { python3 -c "import json;print(json.load(open('$STATE')).get('$1',''))" 2>/dev/null; }
stset() { python3 - "$STATE" "$1" "$2" <<'PYEOF'
import json, sys
p, k, v = sys.argv[1], sys.argv[2], sys.argv[3]
d = {}
try: d = json.load(open(p))
except Exception: pass
d[k] = v
open(p, "w").write(json.dumps(d))
PYEOF
}

# --- 1+2: miner lifecycle ---
miner_now=$(pgrep -f "dev/mine_external" | head -1 | wc -l)
fixtures=$(ls /root/janus/eval_corpus/external 2>/dev/null | wc -l)
miner_was=$(stget miner_alive)
if [ "$miner_was" = "1" ] && [ "$miner_now" = "0" ]; then
  if [ "$fixtures" = "0" ]; then
    tg "⚠️ janus: JB-1 miner exited with 0 external fixtures — a finding, not silence. Check /tmp/jb1-*.log"
  else
    tg "⛏️ janus: JB-1 sweep closed — $fixtures external fixture(s) in eval_corpus/external.
Next: curation (dedupe by test function to the ISC bar) → laptop eval → the claim verdict."
  fi
fi
stset miner_alive "$miner_now"

# --- 3: eval death mid-run ---
eval_alive=$(ssh -o ConnectTimeout=15 llm-jk "pgrep -f 'dev/eval.py' | wc -l" 2>/dev/null | tail -1)
eval_was=$(stget eval_alive)
if [ "$eval_was" = "1" ] && [ "$eval_alive" = "0" ]; then
  done_md=$(ssh -o ConnectTimeout=15 llm-jk "ls /home/josh/janus/logs/fresh-rank2-full.md 2>/dev/null | wc -l" 2>/dev/null | tail -1)
  [ "$done_md" = "0" ] && tg "⚠️ janus: laptop eval process died mid-run (no completed summary). Check /home/josh/janus/logs/"
fi
stset eval_alive "$eval_alive"

# --- 4: ledger-PR staleness ---
# Compare against the COMMITTED main ledger, never the working tree: branch
# operations leave stale/conflicted ledgers in the tree and the monitor
# fired through them every sweep (2026-10-01 ping storm). Gated on state:
# ping once per episode; a resolved episode re-arms.
lap=$(mktemp)
# The laptop's COMMITTED ledger, never the working tree (the scp of the
# tree file was the 2026-10-08 false alarm: the working tree holds an
# eval row the moment a run finishes — same class as the 2026-10-01
# branch ping-pong; the comment already said this, the code didn't).
if ssh -o ConnectTimeout=15 llm-jk 'git -C /home/josh/janus show main:eval_ledger.json' > "$lap" 2>/dev/null && [ -s "$lap" ]; then
  git -C /root/janus show main:eval_ledger.json > "$lap.repo" 2>/dev/null
  if [ -s "$lap.repo" ] && ! cmp -s "$lap" "$lap.repo"; then
    if [ "$(stget ledger_stale)" != "1" ]; then
      tg "⏳ janus: laptop ledger differs from the repo's committed ledger — an eval row may be unsynced."
      stset ledger_stale 1
    fi
  else
    [ "$(stget ledger_stale)" = "1" ] && stset ledger_stale 0
  fi
fi
rm -f "$lap" "$lap.repo" 2>/dev/null

# --- 4b: laptop git frozen (rsync excludes .git) → auto-fix ---
# The rsync syncs code but not .git, so the laptop's main drifts to
# whatever commit it was cloned at while its working tree stays current
# — the committed ledger then never advances and every diff-based check
# reads a stale baseline (2026-10-08: laptop main at the #67 era).
if ! ssh -o ConnectTimeout=15 llm-jk 'git -C /home/josh/janus fetch -q origin && git -C /home/josh/janus merge --ff-only -q origin/main' >/dev/null 2>&1; then
  if [ "$(stget laptop_git_frozen)" != "1" ]; then
    tg "🔧 janus: laptop git rescue failed — working tree and committed state may disagree."
    stset laptop_git_frozen 1
  fi
else
  [ "$(stget laptop_git_frozen)" = "1" ] && stset laptop_git_frozen 0
fi

# --- 5: repo parked off main → auto-fix ---
branch=$(git -C /root/janus branch --show-current 2>/dev/null)
if [ -n "$branch" ] && [ "$branch" != "main" ] && [ "$branch" != "ledger-update" ]; then
  # untracked files (??) survive the rescue — only modified TRACKED files
  # are work at risk (the 188-fixture false alarm was untracked output)
  if git -C /root/janus status --porcelain | grep -vE "^\?\?" | grep -q .; then
    tg "🔧 janus: dev repo parked on '$branch' WITH uncommitted changes — needs a human look (rescue would risk losing work)."
  else
    git -C /root/janus fetch -q origin && git -C /root/janus checkout -q main && git -C /root/janus reset --hard -q origin/main
    tg "🔧 janus: dev repo was parked on '$branch' — auto-returned to main (atomic rescue)."
  fi
fi
