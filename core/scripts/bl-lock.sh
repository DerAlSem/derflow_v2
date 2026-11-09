#!/usr/bin/env bash
# Замок задачи Backlog.md для параллельных сессий.
#
#   bl-lock.sh take <ID> [кто]   взять: замок + In Progress + исполнитель
#   bl-lock.sh who               кто что держит (и сколько)
#   bl-lock.sh drop <ID>         бросить недоделанное: To Do + снять замок
#
# Замок — каталог в ОБЩЕМ git-каталоге (`git rev-parse --git-common-dir`).
# Его видят все ворктри репозитория сразу, он не коммитится и не едет с
# веткой, а `mkdir` атомарен: из двух одновременных сессий возьмёт одна.
# Статус In Progress пишется в своей ветке — остальным его показывает
# `check_active_branches` Backlog.md, но решает всегда замок.
set -euo pipefail

common="$(git rev-parse --path-format=absolute --git-common-dir)"
locks="$common/bl-locks"
mkdir -p "$locks"
branch="$(git rev-parse --abbrev-ref HEAD)"

age() {  # секунды → «3ч 12м»
  local s=$(( $(date +%s) - $1 ))
  printf '%dч %02dм' $((s / 3600)) $((s % 3600 / 60))
}

case "${1:-who}" in
  take)
    id="${2:?нужен ID задачи}"
    who="${3:-$branch}"
    if ! mkdir "$locks/$id" 2>/dev/null; then
      echo "🔒 $id уже взята:" >&2
      sed 's/^/   /' "$locks/$id/owner" >&2
      t="$(sed -n 's/^since: //p' "$locks/$id/owner")"
      [ -n "$t" ] && echo "   держит $(age "$t")" >&2
      echo "   чужая и брошена? — bl-lock.sh drop $id" >&2
      exit 3
    fi
    {
      echo "who: $who"
      echo "branch: $branch"
      echo "tree: $(git rev-parse --show-toplevel)"
      echo "since: $(date +%s)"
    } > "$locks/$id/owner"
    backlog task edit "$id" -s "In Progress" -a "@$who" --plain \
      | head -3
    echo "✅ $id взята ($who, ветка $branch)"
    ;;
  who)
    n=0
    for d in "$locks"/*/; do
      [ -f "$d/owner" ] || continue
      id="$(basename "$d")"
      w="$(sed -n 's/^who: //p' "$d/owner")"
      b="$(sed -n 's/^branch: //p' "$d/owner")"
      t="$(sed -n 's/^since: //p' "$d/owner")"
      echo "$id · $w · $b · $(age "$t")"
      n=$((n + 1))
    done
    [ "$n" -eq 0 ] && echo "замков нет"
    ;;
  drop)
    id="${2:?нужен ID задачи}"
    backlog task edit "$id" -s "To Do" -a "" --plain | head -1
    rm -rf "${locks:?}/$id"
    echo "↩ $id возвращена в To Do, замок снят"
    ;;
  release)  # только для bl-done.sh
    rm -rf "${locks:?}/${2:?}"
    ;;
  *) echo "bl-lock.sh take|who|drop" >&2; exit 1 ;;
esac
