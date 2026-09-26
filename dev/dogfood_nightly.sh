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
nice -n 19 .venv/bin/python dev/eval.py \
  --corpus eval_corpus --md "$LOGS/dogfood-$STAMP.md" --json "$LOGS/dogfood-$STAMP.json" "$@"
code=$?
# accumulate fine-tuning corpus from the run (cheap, label-rich)
nice -n 19 .venv/bin/python dev/build_finetune_corpus.py >> "$LOGS/cron.log" 2>&1 || true
exit $code
