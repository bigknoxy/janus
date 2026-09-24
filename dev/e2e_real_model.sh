#!/usr/bin/env bash
# ISC-3/ISC-4 harness: run janus against real qwen3-4b on seeded-bug fixtures.
# Usage (on the laptop): bash dev/e2e_real_model.sh <workdir>
# Prints PASS/FAIL per fixture and leaves raw S2 captures in $WORK/captures.jsonl
set -u
WORK="${1:-$(mktemp -d)}"
JANUS="/home/josh/janus/.venv/bin/janus"
export CUDA_VISIBLE_DEVICES="" USE_TF=0 JANUS_S2_BASE_URL=http://127.0.0.1:8081/v1
mkdir -p "$WORK"

fixture() {  # name, calc-like module body, test body, prompt
  local dir="$WORK/$1"
  mkdir -p "$dir"
  printf '%s\n' "$2" > "$dir/mod.py"
  printf '%s\n' "$3" > "$dir/test_mod.py"
  printf '%s' "$4"
}

run_fixture() {
  local name="$1" prompt="$2" dir="$WORK/$1"
  local before; before=$(cat "$dir/mod.py")
  (cd "$dir" && JANUS_VERIFY_COMMAND="/home/josh/janus/.venv/bin/python -m pytest -q test_mod.py" \
     JANUS_S2_LOG_RAW="$WORK/captures.jsonl" \
     timeout 600 "$JANUS" run --yes --s1-backend laya "$prompt" --root "$dir" \
     > "$WORK/$name.log" 2>&1)
  local code=$?
  local after; after=$(cat "$dir/mod.py")
  if [ $code -eq 0 ] && [ "$after" != "$before" ] && grep -q patched_verified "$WORK/$name.log"; then
    echo "PASS $name (file changed, suite green)"; return 0
  elif [ "$after" = "$before" ]; then
    echo "FAIL-SAFE $name (rolled back clean, exit=$code)"; return 1
  else
    echo "FAIL-CORRUPT $name (file changed without green suite!)"; return 2
  fi
}

# --- Fixture 1: semantics bug (multiplies instead of discounting) -----------------
P1=$(fixture f1_operator 'def discount(price, pct):
    return price * pct  # BUG: should subtract pct fraction of price' 'from mod import discount

def test_discount():
    assert abs(discount(200, 0.1) - 180.0) < 1e-9
' "fix the discount function in mod.py: it should subtract pct as a fractional discount from the price")

# --- Fixture 2: off by one ------------------------------------------------------
P2=$(fixture f2_offbyone 'def first_n(items, n):
    return items[: n - 1]  # BUG: off-by-one' 'from mod import first_n

def test_first_n():
    assert first_n([1, 2, 3, 4], 2) == [1, 2]
' "fix first_n in mod.py which returns one item too few")

# --- Fixture 3: missing guard ---------------------------------------------------
P3=$(fixture f3_guard 'def safe_div(a, b):
    return a / b  # BUG: no zero guard' 'from mod import safe_div

def test_div():
    assert safe_div(4, 2) == 2
    assert safe_div(1, 0) is None
' "fix safe_div in mod.py to return None when dividing by zero")

R=0
run_fixture f1_operator "$P1" || R=$((R+1))
run_fixture f2_offbyone "$P2" || R=$((R+1))
run_fixture f3_guard "$P3" || R=$((R+1))
echo "fixture failures: $R; workdir: $WORK"
exit $R
