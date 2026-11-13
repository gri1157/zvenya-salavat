#!/usr/bin/env bash
# Собирает задачи этого прогона по меткам в один файл.
# Использование: collect.sh <с какого времени ISO> <файл> <метка> [метка...]
set -euo pipefail
SINCE="$1"; OUT="$2"; shift 2
: > "$OUT"
for L in "$@"; do
  gh api "repos/${GITHUB_REPOSITORY}/issues?labels=${L}&state=all&since=${SINCE}&per_page=50" \
    --jq '.[] | "\n\n=====\n# Задача #\(.number): \(.title)\n\n\(.body)"' >> "$OUT" || true
done
wc -c "$OUT"
