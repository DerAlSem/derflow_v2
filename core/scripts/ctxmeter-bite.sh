#!/usr/bin/env bash
# Стенд укуса context-meter.py --tool: вход PostToolUse.
#
#   bash ~/.claude/scripts/ctxmeter-bite.sh
#   METER=/путь/к/старому bash ~/.claude/scripts/ctxmeter-bite.sh
#
# Зачем в репозитории: хук на PostToolUse дёргается на КАЖДОМ вызове
# инструмента. Молча инертный он не заметен вовсе, а падающий ломает работу —
# оба отказа тихие, и оба ловятся только стендом.
# 🔴 ЗАМЕРЫ 12.09.2026 (7 укусов). Стенд, не умеющий краснеть, охраняет ничего:
#   живой context-meter.py ..................... ✅ 7  ❌ 0
#   заглушка (exit 0, молчит) .................. ✅ 0  ❌ 7
#   версия ДО правки (нет входа --tool) ........ ✅ 1  ❌ 6
# Ноль у заглушки — следствие спайки: каждое «молчит» стоит в одном утверждении
# с «а рядом говорит». Первая редакция стенда держала их порознь и давала
# заглушке ✅ 5 ❌ 3, то есть охраняла молчание, а не работу.
M="${METER:-$HOME/.claude/hooks/context-meter.py}"
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
export HOME="$ROOT/fakehome"; mkdir -p "$HOME/.claude/state"
pass=0; fail=0
is() { if [ "${2:-1}" = 0 ]; then echo "  ✅ $1"; pass=$((pass+1));
       else echo "  ❌ $1"; fail=$((fail+1)); fi; }
tr_with() {  # tr_with <контекст> → путь к транскрипту
  printf '{"type":"assistant","message":{"usage":{"input_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":%s}}}\n' "$1" > "$ROOT/t$1.jsonl"
  printf '%s' "$ROOT/t$1.jsonl"
}
run() {  # run <сессия> <транскрипт> → $out
  out="$(printf '{"session_id":"%s","transcript_path":"%s"}' "$1" "$2" | python3 "$M" --tool 2>&1)"; rc=$?
}

echo "=== порог, защёлка и живучесть — каждое отрицание спаяно с положительным ==="

# 🔴 ПРАВИЛО УКУСА. «Молчит» зелено на заглушке: она молчит всегда и везде.
# Поэтому в КАЖДОМ утверждении рядом с тишиной стоит речь, которую даёт только
# работающий хук. Замер этого правила — ниже, в шапке замеров.
LOW="$(tr_with 120000)"; HIGH="$(tr_with 420000)"

run a1 "$LOW"; lo_rc=$rc; lo_out="$out"
run a2 "$HIGH"; hi_rc=$rc; hi_out="$out"
{ [ "$lo_rc" = 0 ] && [ -z "$lo_out" ] && [ "$hi_rc" = 0 ] \
    && printf '%s' "$hi_out" | grep -q "hand.sh"; }
is "порог различает: на 120k молчит, на 420k зовёт hand.sh" $?
{ printf '%s' "$hi_out" | grep -q "420k"; }
is "…и называет РАЗМЕР, а не только призыв: совет без числа не проверяем" $?

run b1 "$HIGH"; first="$out"
run b1 "$HIGH"; second="$out"
{ printf '%s' "$first" | grep -q "hand.sh" && [ -z "$second" ]; }
is "защёлка: первый вызов сессии печатает, второй молчит — 178 повторов это фон" $?
run b2 "$HIGH"
{ printf '%s' "$out" | grep -q "hand.sh"; }
is "…но защёлка ПОСЕССИОННАЯ: соседняя сессия своё предупреждение получает" $?

# Хук висит на КАЖДОМ вызове инструмента: упавший ломает работу, болтливый
# засоряет. Обе стороны в одном утверждении — иначе заглушка зеленеет.
run c1 "$ROOT/НЕТ-ТАКОГО.jsonl"; a_rc=$rc; a_out="$out"
run c2 "$HIGH"; b_rc=$rc; b_out="$out"
{ [ "$a_rc" = 0 ] && [ -z "$a_out" ] && [ "$b_rc" = 0 ] \
    && printf '%s' "$b_out" | grep -q "hand.sh"; }
is "транскрипта нет — молчит кодом 0, а рядом на здоровом входе говорит" $?

printf 'не json вовсе\n' > "$ROOT/bad.jsonl"
run d1 "$ROOT/bad.jsonl"; a_rc=$rc; a_out="$out"
run d2 "$HIGH"; b_rc=$rc; b_out="$out"
{ [ "$a_rc" = 0 ] && [ -z "$a_out" ] && [ "$b_rc" = 0 ] \
    && printf '%s' "$b_out" | grep -q "hand.sh"; }
is "битый транскрипт — молчит кодом 0, а рядом на здоровом входе говорит" $?

a_out="$(printf 'не json' | python3 "$M" --tool 2>&1)"; a_rc=$?
run e1 "$HIGH"
{ [ "$a_rc" = 0 ] && [ -z "$a_out" ] && printf '%s' "$out" | grep -q "hand.sh"; }
is "мусор на stdin — молчит кодом 0, а рядом на здоровом входе говорит" $?

echo
echo "итог: ✅ $pass   ❌ $fail"
[ "$fail" = 0 ]
