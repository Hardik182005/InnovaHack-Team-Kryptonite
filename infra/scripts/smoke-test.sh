#!/usr/bin/env bash
# Post-deploy smoke test (testing prompt §39). Exits non-zero on any failure.
set -euo pipefail

BASE="${1:-http://localhost:8000}"
SESSION="smoke-$(date +%s)"
pass=0; fail=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    printf '  \033[32mPASS\033[0m %-46s %s\n' "$name" "$actual"; pass=$((pass+1))
  else
    printf '  \033[31mFAIL\033[0m %-46s got %s, want %s\n' "$name" "$actual" "$expected"; fail=$((fail+1))
  fi
}

code() { curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Id: $SESSION" "$@"; }

echo "Smoke testing $BASE"
check "health"  200 "$(code "$BASE/health")"
check "ready"   200 "$(code "$BASE/ready")"
check "openapi" 200 "$(code "$BASE/openapi.json")"

ANALYSIS=$(curl -s -X POST "$BASE/api/analyses" \
  -H 'Content-Type: application/json' -H "X-Session-Id: $SESSION" \
  -d '{"demo":true,"consent_confirmed":true}' | sed -n 's/.*"analysis_id":"\([^"]*\)".*/\1/p')
[[ -n "$ANALYSIS" ]] && { printf '  \033[32mPASS\033[0m %-46s %s\n' "demo analysis created" "$ANALYSIS"; pass=$((pass+1)); } \
                     || { printf '  \033[31mFAIL\033[0m %-46s\n' "demo analysis created"; fail=$((fail+1)); }


# The pipeline runs in a background task, so the POST returns 202 before the
# analysis is finished. A real client polls /status; so must this test.
STATE=""
for _ in $(seq 1 30); do
  STATE=$(curl -s -H "X-Session-Id: $SESSION" "$BASE/api/analyses/$ANALYSIS/status" \
    | grep -o '"state":"[A-Z_]*"' | head -1 | cut -d'"' -f4)
  [[ "$STATE" == "COMPLETED" || "$STATE" == "FAILED" ]] && break
  sleep 1
done
check "analysis reaches COMPLETED" COMPLETED "$STATE"

for path in summary safe-spare roundups categories recurring leaks cashflow-confidence; do
  check "GET $path" 200 "$(code "$BASE/api/analyses/$ANALYSIS/$path")"
done

# §22: another session must not be able to read it.
check "cross-session read denied" 404 \
  "$(curl -s -o /dev/null -w '%{http_code}' -H "X-Session-Id: other-$SESSION" "$BASE/api/analyses/$ANALYSIS/summary")"

# §25.1: Safe Spare is never negative on the deployed service either.
SAFE=$(curl -s -H "X-Session-Id: $SESSION" "$BASE/api/analyses/$ANALYSIS/safe-spare" \
  | grep -o '"safe_spare_now":"[0-9.]*"' | head -1 | cut -d'"' -f4)
if [[ -n "$SAFE" ]] && awk "BEGIN{exit !($SAFE >= 0)}"; then
  printf '  \033[32mPASS\033[0m %-46s %s\n' "safe spare is not negative" "$SAFE"; pass=$((pass+1))
else
  printf '  \033[31mFAIL\033[0m %-46s %s\n' "safe spare is not negative" "$SAFE"; fail=$((fail+1))
fi

check "delete analysis" 200 "$(curl -s -o /dev/null -w '%{http_code}' -X DELETE -H "X-Session-Id: $SESSION" "$BASE/api/analyses/$ANALYSIS")"
check "deleted analysis is gone" 404 "$(code "$BASE/api/analyses/$ANALYSIS/summary")"

echo
echo "  $pass passed, $fail failed"
[[ $fail -eq 0 ]]
