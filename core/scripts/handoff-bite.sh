#!/usr/bin/env bash
# Стенд укуса handoff-header.py: хендофф без шапки ловится в момент записи.
#
#   bash core/scripts/handoff-bite.sh            # из корня ~/dev/derflow
#   HOOK=/путь/к/сломанной/копии bash core/scripts/handoff-bite.sh
#
# Зачем в репозитории: сторож, чей стенд умирает вместе с сессией, второй раз
# дефекта не ловит. Стенд обязан УМЕТЬ КРАСНЕТЬ: в конце копия хука ломается
# нарочно (выкусывается проверка «имя:») и стенд обязан увидеть поломку —
# без неё зелёный прогон ничего не доказывает.
#
# Проверка самого стенда 12.11.2026: сломанная копия даёт ❌ в задачах 1–3
# (предупреждение не печатается), обычный прогон — ✅ 8 ❌ 0.

HOOK="${HOOK:-$(cd "$(dirname "$0")/.." && pwd)/hooks/handoff-header.py}"
ok=0; bad=0
pass() { ok=$((ok+1)); printf '✅ %s\n' "$*"; }
fail() { bad=$((bad+1)); printf '❌ %s\n' "$*"; }

run() { # run «ENV=…» payload → stdout хука
  # -u: стенд сам живёт в ZCode/Claude-сессии — их env не должен выбирать ветку
  env -u ZCODE_SESSION_ID -u CLAUDE_PROJECT_DIR $1 python3 "$HOOK" <<<"$2" 2>/dev/null
}

# tmp-репо с веткой main и хендофф-каталогом
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
git -C "$T" init -q -b main
# без коммита rev-parse HEAD падает («ambiguous») — ветка не резолвится
git -C "$T" -c user.email=bite@t -c user.name=bite commit -q --allow-empty -m init
mkdir -p "$T/.claude/handoff" "$T/docs"

printf '# Задача\nтело\n' > "$T/.claude/handoff/bare.md"
P_BARE='{"tool_name":"Write","tool_input":{"file_path":"'"$T/.claude/handoff/bare.md"'"},"cwd":"'"$T"'"}'

out="$(run 'CLAUDE_PROJECT_DIR=1' "$P_BARE")"
case "$out" in *'"decision"'*:*'"block"'*|*'"decision":"block"'*)
  case "$out" in *ветка:*) pass "claude: decision block с подсказкой";;
    *) fail "claude: block есть, подсказки нет: ${out:0:120}";; esac;;
  *) fail "claude: ждали decision block, получили: ${out:0:120}";; esac

out="$(run 'ZCODE_SESSION_ID=s1' "$P_BARE")"
case "$out" in *additionalContext*ветка:*) pass "zcode: JSON additionalContext";;
  *) fail "zcode: ждали additionalContext, получили: ${out:0:120}";; esac

out="$(run 'PATH__none=1' "$P_BARE")"
case "$out" in '{*'*) fail "kimi: ждали plain, получили JSON: ${out:0:120}";;
  *ветка:*) pass "kimi: plain-подсказка";;
  *) fail "kimi: ждали plain-подсказку, получили: ${out:0:120}";; esac

out="$(run 'CLAUDE_PROJECT_DIR=1' "$P_BARE")"
case "$out" in *'ветка: main'*) pass "ветка репо подставлена: «ветка: main»";;
  *) fail "ждали «ветка: main» в подсказке: ${out:0:120}";; esac

printf 'ветка: main\nимя: R·слаг\n\n# Задача\n' > "$T/.claude/handoff/dressed.md"
out="$(run 'CLAUDE_PROJECT_DIR=1' \
  '{"tool_name":"Edit","tool_input":{"file_path":"'"$T/.claude/handoff/dressed.md"'"},"cwd":"'"$T"'"}')"
[ -z "$out" ] && pass "шапка на месте — молчание" || fail "лишнее срабатывание: ${out:0:120}"

printf '# Заметки\n' > "$T/docs/notes.md"
out="$(run 'CLAUDE_PROJECT_DIR=1' \
  '{"tool_name":"Write","tool_input":{"file_path":"'"$T/docs/notes.md"'"},"cwd":"'"$T"'"}')"
[ -z "$out" ] && pass "вне .claude/handoff — молчание" || fail "сработал на не-хендоффе: ${out:0:120}"

out="$(echo 'не json' | env -u ZCODE_SESSION_ID CLAUDE_PROJECT_DIR=1 python3 "$HOOK" 2>/dev/null; echo "rc=$?")"
case "$out" in rc=0) pass "мусорный stdin: exit 0 молча";;
  *) fail "мусорный stdin уронил сторож: $out";; esac

# Укус: стенд обязан краснеть на нарочно сломанной копии (молчит всегда)
if [ -n "${HANDOFF_BITE_RECURSE:-}" ]; then
  printf 'handoff-bite: ✅ %d ❌ %d\n' "$ok" "$bad"
  [ "$bad" -eq 0 ]
  exit
fi
B="$T/broken.py"
sed 's/if not rx.search(head)\]/if False]/' "$HOOK" > "$B"
chmod +x "$B"
sub="$(HANDOFF_BITE_RECURSE=1 HOOK="$B" bash "$0" 2>/dev/null | tail -1)"
case "$sub" in
  *'❌ 0') fail "УКУС НЕ ВИДЕН: сломанная копия прошла стенд зелёно — стенд слеп";;
  *'❌ '*) pass "сломанная копия краснеет стендом: ${sub#handoff-bite: }";;
  *) fail "стенд на сломанной копии умер без итога: ${sub:0:80}";;
esac

printf 'handoff-bite: ✅ %d ❌ %d\n' "$ok" "$bad"
[ "$bad" -eq 0 ]
