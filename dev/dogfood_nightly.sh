#!/usr/bin/env bash
# Nightly dogfood: run the full eval matrix on the laptop against the real
# local models. Output: $JANUS_HOME/logs/dogfood-<date>.{md,json}
# Exit 1 on any CORRUPT / INFRA / BAD-FIXTURE row; exit 3 on disk-guard
# abort. Install: dev/install_cron.sh (laptop-side).
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HERE/logs"
mkdir -p "$LOGS"
STAMP=$(date +%Y%m%d-%H%M)

# Single-flight lock: a manual probing run and the cron run must never
# fight the same single-slot llama-server (2026-09-27 rank-probe collision).
# Manual-launch pattern (2026-09-30 flock lesson): flock must hold the lock
# for the eval's lifetime —
#   nohup flock "$LOGS/.eval.lock" -c "env ... eval.py ... > log 2>&1" &
# never `flock ... -c "nohup eval ... &"` — the inner & releases the lock when
# the wrapper shell exits, and the eval runs outside single-flight.
LOCK="$LOGS/.eval.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[skip] another janus eval is running (lock: $LOCK)" >&2
  exit 0
fi

export CUDA_VISIBLE_DEVICES="" USE_TF=0
export JANUS_S2_BASE_URL="${JANUS_S2_BASE_URL:-http://127.0.0.1:8081/v1}"
export JANUS_S1_BACKEND="${JANUS_S1_BACKEND:-laya}"

# Disk pre-flight: this laptop historically runs at 100% — prune the
# re-downloadable pip cache and hard-fail loud if still tight (<800MB
# risks OOM-adjacent writes mid-run).
FREE_MB=$(df -m "$HERE" | awk 'NR==2 {print $4}')
if [ "$FREE_MB" -lt 800 ]; then
  echo "[disk-guard] ${FREE_MB}MB free — pruning pip cache" >&2
  rm -rf ~/.cache/pip/* 2>/dev/null || true
  FREE_MB=$(df -m "$HERE" | awk 'NR==2 {print $4}')
fi
if [ "$FREE_MB" -lt 400 ]; then
  echo "[disk-guard] ABORT: only ${FREE_MB}MB free after prune" >&2
  exit 3
fi

# Memory pre-flight: llama servers hold ~9GiB of 14GiB; the eval loads a
# Laya checkpoint per fixture (transient ~1.7GiB). Refuse to start under
# 2.5GiB available rather than trigger an OOM storm at 03:17.
AVAIL_MB=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
if [ "$AVAIL_MB" -lt "${DOGFOOD_MIN_FREE_MB:-2500}" ]; then
  echo "[mem-guard] ABORT: only ${AVAIL_MB}MB available (need 2500)" >&2
  exit 4
fi

cd "$HERE"
# Nightly corpus scope: janus fixtures only. eval_corpus/external/ (mined
# fixtures) fails on the janus venv's pinned pydantic-core, and
# eval_corpus/external_raw/ holds 891 raw mined fixtures — the corpus rglob
# catches both (2026-09-30 nightly ran ~18h to a contaminated 53-fixture
# row). Copy to a tempdir minus both.
NIGHTLY_CORPUS=$(mktemp -d /tmp/janus-nightly-XXXXXX)
trap 'rm -rf "$NIGHTLY_CORPUS"' EXIT
rsync -a --exclude=external/ --exclude=external_raw/ --exclude=finetune.jsonl \
  eval_corpus/ "$NIGHTLY_CORPUS"/
nice -n 19 .venv/bin/python dev/eval.py \
  --corpus "$NIGHTLY_CORPUS" --md "$LOGS/dogfood-$STAMP.md" --json "$LOGS/dogfood-$STAMP.json" "$@"
code=$?
# accumulate fine-tuning corpus from the run (cheap, label-rich)
nice -n 19 .venv/bin/python dev/build_finetune_corpus.py >> "$LOGS/cron.log" 2>&1 || true
exit $code
