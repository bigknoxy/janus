#!/usr/bin/env bash
# Install the nightly dogfood on this host (laptop). Idempotent.
# Runs 03:17 local time. Env overrides allowed in the user crontab entry.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
LINE="17 3 * * * JANUS_S1_BACKEND=laya JANUS_S2_BASE_URL=http://127.0.0.1:8081/v1 $HERE/dev/dogfood_nightly.sh >> $HERE/logs/cron.log 2>&1"
( crontab -l 2>/dev/null | grep -v "dogfood_nightly.sh" ; echo "$LINE" ) | crontab -
echo "installed:"; crontab -l | grep dogfood
