#!/usr/bin/env bash
# Закрыть задачу Backlog.md. Главное правило docs-first держится здесь:
# задача не закрывается, пока «как устроено» не обновлено в backlog/docs.
# И пока не отмечены все AC и DoD и не записан --final-summary.
#
#   bl-done.sh <ID>                       закрыть (нужна правка backlog/docs)
#   bl-done.sh <ID> --no-doc "<причина>"  закрыть без правки доки, с причиной
#
# «Правка доки» = правка backlog/docs по дороге задачи: незакоммиченное
# в дереве или коммит, трогавший и файл задачи, и backlog/docs.
# (База — сама задача, не замок: его передача обнуляла отсчёт.)
set -euo pipefail

id="${1:?нужен ID задачи}"
here="$(cd "$(dirname "$0")" && pwd)"

# Файл задачи — база doc-гейта; путь в task view относительный.
task_json="$(backlog task view "$id" --json)"
task_path="$(printf '%s' "$task_json" | python3 -c '
import json, os, sys
p = json.load(sys.stdin)["task"]["path"]
print(os.path.relpath(p) if os.path.isabs(p) else p)')"

# Дока правлена по дороге задачи: грязь в дереве или общий коммит
# задачи и доков. Замок не участвует.
doc_touched() {
  git status --porcelain -- backlog/docs | grep -q . && return 0
  comm -12 <(git log -n 300 --format=%H -- "$task_path" | sort -u) \
           <(git log -n 300 --format=%H -- backlog/docs | sort -u) \
    | grep -q .
}

# Готовность самой задачи: все AC и DoD отмечены, итог записан.
# Лишний критерий не обходится флагом — его снимают --remove-ac с причиной
# в заметках, чтобы «не сделано» не закрывалось молча.
unready="$(printf '%s' "$task_json" | python3 -c '
import json, sys
t = json.load(sys.stdin)["task"]
for kind, flag in (("acceptanceCriteria", "AC"), ("definitionOfDone", "DoD")):
    for c in t.get(kind) or []:
        if not c["checked"]:
            print("   %s #%s не отмечен: %s" % (flag, c["index"], c["text"]))
if not (t.get("finalSummary") or "").strip():
    print("   пустой --final-summary (Ждёт тебя · Сделано · Найдено)")
')"
if [ -n "$unready" ]; then
  echo "❌ $id: задача не готова к закрытию." >&2
  echo "$unready" >&2
  echo "   Выполненное — --check-ac/--check-dod <n>; лишний критерий —" >&2
  echo "   --remove-ac <n> и причина в --append-notes." >&2
  exit 2
fi

if [ "${2:-}" = "--no-doc" ]; then
  why="${3:?--no-doc требует причину}"
  backlog task edit "$id" --append-notes "Дока не менялась: $why" \
    --plain >/dev/null
elif ! doc_touched; then
  echo "❌ $id: backlog/docs не менялся по дороге задачи." >&2
  echo "   Обнови doc capability, которую задача изменила," >&2
  echo "   или закрой с --no-doc \"<почему доке нечего добавить>\"." >&2
  exit 2
fi

backlog task edit "$id" -s Done --plain | head -1
bash "$here/bl-lock.sh" release "$id"
echo "✅ $id закрыта, замок снят. Не забудь коммит: задача + дока + код."
