#!/usr/bin/env bash
# Стенд укуса install.sh: --check видит висячие симлинки на исчезнувшее из
# репо (DF-16).
#
#   bash core/scripts/install-bite.sh
#   INSTALL=/путь/к/install.sh bash core/scripts/install-bite.sh
#
# Зачем в репозитории, а не в скрэтчпаде, и три правила укуса (отрицательное
# спаяно с положительным; искомое не встречается в фикстуре и путях стенда;
# заглушка обязана краснеть) — в шапке waiting-bite.sh. Действуют и здесь.
#
# Контур — поддельный HOME: install.sh берёт из него все живые каталоги разом,
# и укус идёт по тем местам, где 23.11.2026 оставались мёртвые ссылки:
# ~/.zcode/{agents,scripts,hooks}, ~/.config/opencode/plugins. Интерфейс
# стенда из задачи (--claude-dir --only claude) закрыт отдельной главой.
#
# 🔴 install-режим нужен, чтобы разложить чистый дом, а он пересобирает
# hosts/*/generated в репозитории install.sh. Сборка детерминирована, дереву
# ничего не должно достаться — последний укус сверяет дерево до и после.
#
# 🔴 ЗАМЕРЫ (24.11.2026, 16 укусов). Каждая строка — отдельный прогон:
#
#   install.sh с правкой .................... ✅ 16 ❌ 0
#   install.sh до правки (b3a5093) .......... ✅  8 ❌ 8   — слеп к висячим
#   заглушка (echo «дрейфа нет»; exit 0) .... ✅  4 ❌ 12
#   мутация: убран признак «свой» ........... ✅ 13 ❌ 3   — AC #3
#   мутация: --check снимает сам ............ ✅ 10 ❌ 6   — AC #5
#   мутация: не печатает команду снятия ..... ✅ 10 ❌ 6   — AC #6
#
# Восемь зелёных у старого — не зоркость, а пары: каждый такой укус несёт
# положительную половину («install разложил», «пропажу управляемой видит»),
# которую даёт любой работающий install.sh. Расхождение с числами после
# правки укусов разбирать, а не переписывать молча.
#
# Оснастка та же: run гоняет install.sh и кладёт вывод в $out, код в $rc;
# has/nohas смотрят $out; is печатает вердикт. Идиома вызова:
#   run --check
#   { [ "$rc" = 0 ] && has "дрейфа нет"; }; is "ярлык укуса" $?
set -u
HERE="$(cd -P "$(dirname "$0")" && pwd)"      # физический core/scripts: ~/.claude/scripts — симлинк
I="${INSTALL:-$(cd -P "$HERE/../.." && pwd)/install.sh}"
IREPO="$(cd "$(dirname "$I")" && pwd)"         # тем же выражением, каким install.sh находит REPO
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT" 2>/dev/null || true' EXIT
H="$ROOT/home"                                 # живые каталоги — только в поддельном доме
mkdir -p "$H/.claude" "$H/.zcode" "$H/.config/opencode" "$H/.kimi-code"   # линкуется лишь в существующие
# settings.json не линкуется: без него сверка hooks падает ещё в install-режиме.
cp "$IREPO/hosts/claude/settings.json" "$H/.claude/settings.json"
# config.json ztui — то же (DF-30): без файла install откажет; эталон записей равен сам себе.
mkdir -p "$H/.zcode/cli"; cp "$IREPO/hosts/zcode/hooks.json" "$H/.zcode/cli/config.json"
before="$(git -C "$IREPO" status --porcelain 2>/dev/null)"
pass=0; fail=0; out=""; rc=0
G=ghostlink                                    # имя фикстур: файла с ним в репо нет и быть не должно

run() {  # run <аргументы install.sh…> → $out, $rc
  out="$(HOME="$H" bash "$I" "$@" 2>&1)"; rc=$?
}
has()   { printf '%s' "$out" | grep -qF -- "$1"; }
nohas() { ! printf '%s' "$out" | grep -qF -- "$1"; }
is() {  # is <ярлык> <0 если утверждение верно>
  if [ "${2:-1}" = 0 ]; then echo "  ✅ $1"; pass=$((pass+1))
  else
    echo "  ❌ $1 — rc=$rc"
    printf '%s\n' "$out" | sed 's/^/       /' | head -40
    fail=$((fail+1))
  fi
}
ghost() {  # ghost <живой путь> <цель-призрак> — ссылка в никуда
  # Каталог заводит фикстура, а не проверяемый: иначе у заглушки укус падает
  # от отсутствующего каталога, а не от слепоты.
  mkdir -p "$(dirname "$1")"; ln -s "$IREPO/$2" "$1"
}
unghost() {  # исполняет команды снятия из вывода; путь — только внутри стенда
  local list one
  list="$(printf '%s\n' "$out" | sed -n 's/^ *rm //p')"
  [ -n "$list" ] || return 1
  while read -r one; do
    case "${one/\~/$H}" in "$H/"*) ;; *) return 1 ;; esac
  done <<< "$list"
  while read -r one; do HOME="$H" bash -c "rm $one"; done <<< "$list"
}

echo "=== чистый дом ==="

run
{ [ "$rc" = 0 ] && [ -e "$H/.zcode/AGENTS.md" ] && [ -e "$H/.config/opencode/AGENTS.md" ] \
  && [ -e "$H/.kimi-code/AGENTS.md" ] && [ -e "$H/.claude/CLAUDE.md" ]; }
is "install разложил ссылки во все четыре среды поддельного дома" $?
run --check
{ [ "$rc" = 0 ] && has "дрейфа нет"; }
is "чистый дом: «дрейфа нет», код 0 (AC #2)" $?

echo "=== свой висячий ==="

ghost "$H/.claude/skills/$G-skill" "core/skills/$G-skill"
run --check
{ [ "$rc" = 1 ] && has "дрейф найден" && has "$H/.claude/skills/$G-skill" \
  && has "$IREPO/core/skills/$G-skill"; }
is "ссылка на исчезнувшее из репо: путь и цель напечатаны, код 1 (AC #1)" $?
{ [ -L "$H/.claude/skills/$G-skill" ] && unghost && [ ! -L "$H/.claude/skills/$G-skill" ] \
  && [ -e "$H/.claude/skills/derflow" ]; }
is "--check сам не снял, а команда из его вывода снимает ровно эту ссылку (AC #5, AC #6)" $?
run --check
{ [ "$rc" = 0 ] && has "дрейфа нет"; }
is "после снятия: «дрейфа нет», код 0 — красным был ровно он (AC #2)" $?

echo "=== чужой висячий не дрейф ==="

# Как девять живых на 23.11.2026: Claude Sync, цель исчезла, к репо отношения нет.
mkdir -p "$H/.zcode/skills"
ln -s "$H/.claude/skills/synced/fe0c6cc2-gone/morning" "$H/.zcode/skills/morning"
ghost "$H/.zcode/agents/$G-agent.md" "hosts/zcode/generated/agents/$G-agent.md"
run --check
{ [ "$rc" = 1 ] && has "agents/$G-agent.md" && nohas "fe0c6cc2-gone" \
  && nohas "zcode/skills/morning"; }
is "свой назван, чужой (цель вне репо) не напечатан и дрейфом не стал (AC #3)" $?
{ unghost && [ -L "$H/.zcode/skills/morning" ] && [ ! -e "$H/.zcode/skills/morning" ]; }
is "команда снятия не задела чужой симлинк" $?
rm "$H/.zcode/AGENTS.md"                      # управляемую ссылку снимает стенд
run --check
{ [ "$rc" = 1 ] && has "AGENTS.md — нет" && nohas "zcode/skills/morning"; }
is "рядом с чужим --check жив: пропажу управляемой видит, чужого не называет (AC #3)" $?
run
run --check
{ [ "$rc" = 0 ] && has "дрейфа нет" && [ -L "$H/.zcode/skills/morning" ]; }
is "чужой висячий на месте: «дрейфа нет», код 0 (AC #3)" $?

echo "=== мёртвые ссылки 23.11.2026 — по одной в каждой среде ==="

ghost "$H/.zcode/scripts/$G.sh"                "core/scripts/$G.sh"
ghost "$H/.zcode/hooks/$G.py"                  "core/hooks/$G.py"
ghost "$H/.config/opencode/plugins/$G.js"     "hosts/opencode/plugins/$G.js"
ghost "$H/.kimi-code/agents/$G.md"             "hosts/kimi-code/generated/agents/$G.md"
ghost "$H/.claude/hooks-gone"                  "core/hooks-gone"   # одиночные ссылки: каталог скана — сам ~/.claude
run --check
{ [ "$rc" = 1 ] && has "scripts/$G.sh" && has "hooks/$G.py" && has "plugins/$G.js" \
  && has "agents/$G.md" && has ".claude/hooks-gone" \
  && [ "$(printf '%s\n' "$out" | sed -n 's/^ *rm //p' | wc -l | tr -d ' ')" = 5 ]; }
is "поимённо все пять, и пять команд снятия: zcode scripts и hooks, opencode plugins, kimi-code, корень ~/.claude (AC #1, AC #6)" $?

echo "=== install-режим не снимает ==="

rm "$H/.zcode/AGENTS.md"                      # управляемую ссылку снимает стенд
run
{ [ "$rc" = 0 ] && [ -L "$H/.zcode/AGENTS.md" ] && [ -L "$H/.zcode/scripts/$G.sh" ] \
  && [ -L "$H/.claude/hooks-gone" ] && [ -L "$H/.kimi-code/agents/$G.md" ]; }
is "install вернул управляемую ссылку на место, а висячие не тронул (AC #5)" $?
run --check
{ [ "$rc" = 1 ] && has "scripts/$G.sh" && has ".claude/hooks-gone"; }
is "после install висячие на месте — --check всё ещё их видит (AC #5)" $?

echo "=== стенд --claude-dir видит только себя ==="

S="$H/claude stand"                           # пробел в пути: команда снятия обязана пережить копирование
mkdir -p "$S"; cp "$IREPO/hosts/claude/settings.json" "$S/settings.json"
run --only claude --claude-dir "$S"
{ [ "$rc" = 0 ] && [ -L "$S/CLAUDE.md" ]; }
is "стенд разложен: одна среда, другой каталог" $?
ghost "$S/skills/$G-stand" "core/skills/$G-stand"
run --check --only claude --claude-dir "$S"
{ [ "$rc" = 1 ] && has "$S/skills/$G-stand" && has "дрейф найден" \
  && nohas "$H/.claude/" && nohas ".zcode/" && nohas "opencode/" && nohas ".kimi-code/"; }
is "стенд назвал своего и не заглянул ни в ~/.claude дома, ни в другие среды (AC #1, AC #3)" $?
{ unghost && [ ! -L "$S/skills/$G-stand" ] && [ -L "$S/CLAUDE.md" ]; }
is "команда снятия с пробелом в пути исполняется и снимает ровно одну ссылку (AC #6)" $?

echo "=== стенд не пачкает репозиторий ==="

{ [ "$before" = "$(git -C "$IREPO" status --porcelain 2>/dev/null)" ]; }
is "дерево репозитория после стенда — какое было" $?

echo "=== итог: ✅ $pass ❌ $fail ==="
[ "$fail" = 0 ]
