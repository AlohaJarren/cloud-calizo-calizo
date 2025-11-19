#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   Local:  bash hw4/smoke_test.sh http://localhost:8080
#   Remote: bash hw4/smoke_test.sh "$(cat hw4/url.txt)"

BASE_URL="${1:-http://localhost:8080}"
echo "[smoke] base: ${BASE_URL}"

curl -fsS "${BASE_URL}/healthz" >/dev/null
curl -fsS "${BASE_URL}/readyz"  >/dev/null

# Post a tiny song (no URL to keep it simple)
curl -fsS -X POST "${BASE_URL}/songs" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "title=HW4 Smoke Song" \
  --data-urlencode "genre=Pop" \
  --data-urlencode "performer=Tester" \
  --data-urlencode "writer=Tester" \
  --data-urlencode "release_year=2020" \
  --data-urlencode "release_month=7" \
  --data-urlencode "rating=8" \
  --data-urlencode "lyrics=la la la" >/dev/null

# Fetch list page
curl -fsS "${BASE_URL}/songs" >/dev/null

echo "[smoke] ok"
