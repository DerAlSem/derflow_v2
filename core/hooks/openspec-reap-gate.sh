#!/usr/bin/env bash
# Reap-гейт полосы C: конец сессии называет незажатые заявки счётом задач.
# Спека: specs/2026-09-13-derflow-rebuild-design.md §3. Не блокирует.
set -uo pipefail
payload=$(cat)
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
d=${cwd:-$PWD}
while [ "$d" != "/" ]; do
  [ -d "$d/openspec/changes" ] && break
  d=$(dirname "$d")
done
[ -d "$d/openspec/changes" ] || exit 0
command -v openspec >/dev/null || exit 0
cd "$d" || exit 0

# ветка по умолчанию — устойчиво, с запасными вариантами
default_ref=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's#^refs/remotes/##')
if [ -z "$default_ref" ]; then
  if git show-ref --verify --quiet refs/heads/main; then
    default_ref=main
  elif git show-ref --verify --quiet refs/heads/master; then
    default_ref=master
  fi
fi

merge_base=""
if [ -n "$default_ref" ]; then
  merge_base=$(git merge-base HEAD "$default_ref" 2>/dev/null)
fi

# кандидат-множество 1: заявки, тронутые в рабочем дереве
# -z + core.quotepath=false: имена с не-ASCII/пробелом/кавычкой не экранируются и не квотируются
wt_names=$(git -c core.quotepath=false status --porcelain -z -- openspec/changes 2>/dev/null \
  | tr '\0' '\n' \
  | grep -oE 'openspec/changes/[^/]+' \
  | sed 's#openspec/changes/##')

# кандидат-множество 2: заявки, тронутые коммитами этой ветки от точки расхождения
commit_names=""
if [ -n "$merge_base" ]; then
  commit_names=$(git -c core.quotepath=false log --name-only -z --pretty=format: "$merge_base"..HEAD -- openspec/changes 2>/dev/null \
    | tr '\0' '\n' \
    | grep -oE 'openspec/changes/[^/]+' \
    | sed 's#openspec/changes/##')
fi

candidates=$(printf '%s\n%s\n' "$wt_names" "$commit_names" \
  | sed '/^$/d' | sort -u | grep -v '^archive$')

[ -n "$candidates" ] || exit 0

cands_json=$(printf '%s\n' "$candidates" | jq -R -s -c 'split("\n") | map(select(length>0))')

lines=$(openspec list --json 2>/dev/null | jq -r --argjson cands "$cands_json" '
  .changes[]?
  | select(.completedTasks != null and .totalTasks != null
           and .completedTasks < .totalTasks
           and (.name as $n | $cands | index($n)) != null)
  | "🔴 заявка \(.name): \(.completedTasks)/\(.totalTasks) задач — жнётся, а не бросается"
' 2>/dev/null)

[ -n "$lines" ] || exit 0

jq -n --arg msg "$lines" '{systemMessage: $msg}'
exit 0
