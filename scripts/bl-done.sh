#!/usr/bin/env bash
# Закрыть задачу Backlog.md. Главное правило docs-first держится здесь:
# задача не закрывается, пока «как устроено» не обновлено в backlog/docs.
#
#   bl-done.sh <ID>                       закрыть (нужна правка backlog/docs)
#   bl-done.sh <ID> --no-doc "<причина>"  закрыть без правки доки, с причиной
#
# «Правка доки» = изменение под backlog/docs с момента взятия задачи:
# незакоммиченное в дереве или коммит новее замка.
set -euo pipefail

id="${1:?нужен ID задачи}"
common="$(git rev-parse --path-format=absolute --git-common-dir)"
owner="$common/bl-locks/$id/owner"
here="$(cd "$(dirname "$0")" && pwd)"

since=""
[ -f "$owner" ] && since="$(sed -n 's/^since: //p' "$owner")"

doc_touched() {
  git status --porcelain -- backlog/docs | grep -q . && return 0
  [ -n "$since" ] || return 1
  # строго ПОСЛЕ взятия: коммит в ту же секунду — ещё чужая работа
  git log -n 50 --format=%ct -- backlog/docs \
    | awk -v s="$since" '$1 > s { f = 1 } END { exit !f }'
}

if [ "${2:-}" = "--no-doc" ]; then
  why="${3:?--no-doc требует причину}"
  backlog task edit "$id" --append-notes "Дока не менялась: $why" \
    --plain >/dev/null
elif ! doc_touched; then
  echo "❌ $id: backlog/docs не менялся с момента взятия." >&2
  echo "   Обнови doc capability, которую задача изменила," >&2
  echo "   или закрой с --no-doc \"<почему доке нечего добавить>\"." >&2
  exit 2
fi

backlog task edit "$id" -s Done --plain | head -1
bash "$here/bl-lock.sh" release "$id"
echo "✅ $id закрыта, замок снят. Не забудь коммит: задача + дока + код."
