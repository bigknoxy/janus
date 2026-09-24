#!/usr/bin/env bash
# Nightly dogfood: run the full eval matrix on the laptop against the real
# local models. Output: $JANUS_HOME/logs/dogfood-<date>.{md,json}
# Exit 1 on any CORRUPT / INFRA / BAD-FIXTURE row (that pages the human in
# whatever reads the logs). Install: dev/install_cron.sh (laptop-side).
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HERE/logs"
mkdir -p "$LOGS"
STAMP=$(date +%Y%m%d-%H%M)

export CUDA_VISIBLE_DEVICES="" USE_TF=0
export JANUS_S2_BASE_URL="${JANUS_S2_BASE_URL:-http://127.0.0.1:8081/v1}"
export JANUS_S1_BACKEND="${JANUS_S1_BACKEND:-laya}"

cd "$HERE"
exec nice -n 19 .venv/bin/python dev/eval.py \
  --corpus eval_corpus --md "$LOGS/dogfood-$STAMP.md" --json "$LOGS/dogfood-$STAMP.json" "$@"
