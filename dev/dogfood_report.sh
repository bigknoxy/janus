#!/usr/bin/env bash
# Dogfood check-in: pulls the laptop's latest nightly report and posts a
# one-line status to Pulse (03:17 run + runtime ≈ results by 07:30 UTC).
# Installed on the dev box (where Pulse lives).
set -u
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
scp -q "llm-jk:/home/josh/janus/logs/$(ssh llm-jk 'ls -t /home/josh/janus/logs/ | grep dogfood | grep "\.md$" | head -1')" "$TMP/report.md" 2>/dev/null || {
  curl -s -X POST http://localhost:31337/notify -H "Content-Type: application/json" \
    -d '{"message": "DOGFOOD: no report found on laptop — cron did not fire"}' >/dev/null
  exit 1
}
SUMMARY=$(tail -5 "$TMP/report.md" | tr '\n' ' ' | tr '"' "'")
TMPSAFE=$(echo "$SUMMARY" | head -c 400)
curl -s -X POST http://localhost:31337/notify -H "Content-Type: application/json" \
  -d "{\"message\": \"DOGFOOD: $TMPSAFE\"}" >/dev/null
echo "dogfood check-in posted"
