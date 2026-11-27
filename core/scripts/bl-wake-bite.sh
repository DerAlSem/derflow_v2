#!/usr/bin/env bash
# Стенд укуса bl-wake.py: будильник отложки docflow — форма вывода, контракт
# ZCode, дисциплина кэша (DF-29).
#
#   bash core/scripts/bl-wake-bite.sh
#   BLWAKE=/путь/к/копии bash core/scripts/bl-wake-bite.sh
#
# Испытывается bl-wake.py из того же чекаута, что и стенд (файл и стенд — в
# core/scripts): запуск из ворктри гоняет файл ворктри, из корня — файл корня.
# BLWAKE= подменяет его копией.
#
# Зачем в репозитории: хук молчит вне docflow-репо и в обоих контрактах среды
# выходит нулём — сломанный неотличим от «сказать нечего». В gmb_v2 так и было:
# 14 🟢 лежали в кэше, а владелец в ztui их не видел (27.11.2026).
# 🔴 ПРАВИЛО УКУСА — как в шапке waiting-bite.sh: отрицательное не стоит одно,
# искомое не встречается ни в фикстуре, ни в путях стенда, заглушка обязана
# дать ✅ 0. Действуют и здесь; третья проверка встроена — сломанные копии
# стенд делает сам, в конце прогона.
# 🔴 ЗАМЕРЫ (27.11.2026, 19 укусов). Каждая строка — отдельный прогон, шелл ztui:
#
#   bl-wake.py до правки (3bd4d09)   . ✅ 9 ❌ 10   — слеп к форме и к JSON
#   bl-wake.py после правки          . ✅ 19 ❌ 0   — подпроходы того же файла:
#       заглушка ✅ 0 ❌ 9 · копия без JSON ✅ 6 ❌ 3 · копия «кэш целиком» ✅ 7 ❌ 2
#
# Разбирать расхождения с числами, а не переписывать молча. Ожидание «копия без
# JSON краснеет ровно одним» было вписано до замера и опровергнуто им.
#
# Красные у старого (10): 🟢 и ⚪ — по строке и вперёд, 📂 — ни одной построчно (всего 4 строки) · строка счёта одна: 79, разбивка по месяцам, диапазон дат, зовёт --overdue · контракт ZCode: под ZCODE_SESSION_ID — ровно один JSON, нагрузка байт-в-байт равна plain, 🟢 внутри · вне docflow-репо молчит и на контракте ZCode (даже не {}), а на кэше отдаёт JSON · пустой кэш: молчит в обоих контрактах, а непустой рядом говорит · пробы живые: 🟢 с находкой, ⚪ «нет cwd», 📂 — строкой счёта; тихая (exit 3) не звучит · кэш хранит список целиком, а хук на нём печатает строку счёта · живой кэш на контракте ZCode: один JSON с той же нагрузкой · копия без JSON-обёртки краснеет ровно тремя — контракт ZCode и две спайки на нём · копия, печатающая кэш целиком, краснеет ровно двумя — строка счёта 📂
set -u
HERE="$(cd -P "$(dirname "$0")" && pwd)"      # физический core/scripts: ~/.claude/scripts — симлинк
W="${BLWAKE:-$HERE/bl-wake.py}"
# 🔴 Статическая половина укуса про файл (форма DF-21, 24.11.2026). Стенд читает
# свой текст: КАЖДЫЙ запуск интерпретатора идёт через "$W" либо читает программу
# из stdin (`python3 -`). Сравнить переменную с её же определением — тавтология:
# стенд, все вызовы которого уведены в другое дерево, оставил бы живую половину
# зелёной, а первая строка называла бы «свой» файл. Комментарии не считаются;
# красный — первый аргумент интерпретатора, похожий на путь или переменную, либо
# голое имя испытуемого. Себя не прочитал (source, `bash -s <`, `bash -c`): $0 —
# не этот файл, красный: тогда файл выбирает каталог запуска. Пределы: путь
# после слова интерпретатора в текстовой строке — громкое ложное красное; тело
# `python3 - <<…` не читается.
self="$0"; bypass="не прочитал свой текст: $0"
[ "$self" = "${BASH_SOURCE[0]:-}" ] && [ -r "$self" ] && bypass="$(sed 's/^/ /' "$self" \
  | grep -vE '^[[:space:]]*#' \
  | grep -oE '.(python3?|bash|sh)[[:space:]]+("[^"]*"|[^[:space:]]+)' \
  | grep -E '^[^[:alnum:]_./"-]' | sed -E 's/^.(python3?|bash|sh)[[:space:]]+//' \
  | grep -vxF -e '"$W"' -e '-' \
  | grep -E -e '^[^[:alnum:][:space:]]' -e '/' -e '^bl-wake\.py$')"
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
pass=0; fail=0; out=""; rc=0; hit=0; json_ok=1
is() {  # is <ярлык> <0 если утверждение верно>
  if [ "${2:-1}" = 0 ]; then echo "  ✅ $1"; pass=$((pass+1))
  else echo "  ❌ $1 — rc=$rc, строк: $(printf '%s\n' "$out" | wc -l | tr -d ' '), первая: $(printf '%s\n' "$out" | head -1)"
       fail=$((fail+1)); fi
}

# 🔴 ZCODE_SESSION_ID снимается при КАЖДОМ запуске bl-wake.py — в обёртке, а не
# unset наверху стенда: иммунитет проверяется укусом изнутри (переменную
# подкладывают перед вызовом), а unset сверху изнутри не поймать. По
# ZCODE_SESSION_ID хук печатает JSON вместо plain; для хука это правильно, для
# plain-прогон стенда — чужой приказ. Контракт ZCode гоняет вторая обёртка.
blw()  { env -u ZCODE_SESSION_ID python3 "$W" "$@"; }
blwz() { ZCODE_SESSION_ID=t-bite python3 "$W" "$@"; }
run() {  # run <каталог> [аргументы bl-wake.py…] → $out, $rc
  local d="$1"; shift
  out="$(cd "$d" && blw "$@" 2>"$ROOT/err")"; rc=$?
}
ln_()   { printf '%s\n' "$out" | sed -n "$1p"; }                 # ln_ <номер> — строка вывода
has()   { printf '%s' "$out" | grep -qF -- "$1"; }
n_start() { printf '%s\n' "$out" | grep -c "^$1"; }
same_json() {  # → 0, когда $ROOT/zcode.txt — ровно один JSON с нагрузкой $ROOT/plain.txt
  A="$ROOT/plain.txt" B="$ROOT/zcode.txt" python3 - <<'PY'
import json, os
try:
    doc = json.loads(open(os.environ["B"], encoding="utf-8").read())
except ValueError:
    raise SystemExit(1)
plain = open(os.environ["A"], encoding="utf-8").read().strip()
raise SystemExit(0 if isinstance(doc, dict) and list(doc) == ["additionalContext"]
                 and doc["additionalContext"] == plain else 1)
PY
}
ago() {  # ago <минут назад> <файл> — время изменения фикстуры; одинаково на BSD и GNU
  MIN="$1" P="$2" python3 - <<'PY'
import os, time
t = time.time() - int(os.environ["MIN"]) * 60
os.utime(os.environ["P"], (t, t))
PY
}
wait_changed() {  # wait_changed <файл> <эталон> → 0, когда файл перестал равняться эталону (до 15 с)
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    cmp -s "$1" "$2" || return 0
    sleep 1
  done
  return 1
}
wait_exists() {  # wait_exists <файл> → 0, когда файл появился (до 15 с)
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    [ -f "$1" ] && return 0
    sleep 1
  done
  return 1
}

suite() {  # suite fast|slow — укусы на файле $W; медленные (фон и живой backlog) — только slow
  local F C N NG E G i m d
  hit=0; json_ok=1                     # подпроход наследует счёт основного прохода — сброс
  F="$ROOT/fixture"; mkdir -p "$F/backlog"; git -C "$F" init -q
  C="$F/.git/bl-wake.cache"
  # 79 📂 (сентябрь 8, октябрь 51, ноябрь 20 — числа кэша gmb_v2 от 27.11.2026),
  # ⚪ в середине, 🟢 в конце: порядок кэша не порядок вывода.
  : > "$C"
  for i in $(seq 1 79); do
    if [ "$i" -le 8 ]; then m="2026-09"; d=$((10 + i))
    elif [ "$i" -le 59 ]; then m="2026-10"; d=$(( (i - 9) % 28 + 1 ))
    else m="2026-11"; d=$((i - 59)); fi
    [ "$i" = 40 ] && printf '⚪ проба не дошла FX-901 · потолок 20 с\n' >> "$C"
    printf '📅 срок пересмотра FX-%03d · Поправка %d (был %s-%02d)\n' "$i" "$i" "$m" "$d" >> "$C"
  done
  printf '🟢 созрело FX-900 · Оплата одиночной ссылки пробила чек сама · маяк-зелёный-щит\n' >> "$C"

  if [ "${1:-}" != slow ]; then   # медленный проход не повторяет быстрый: счёт один
  echo "=== форма вывода: 🟢 и ⚪ по строке, 📂 — строкой счёта ==="

  run "$F"; a_rc=$rc; a_out="$out"
  { [ "$a_rc" = 0 ] && [ "$(printf '%s\n' "$a_out" | wc -l | tr -d ' ')" = 4 ] \
    && [ "$(printf '%s\n' "$a_out" | sed -n 2p | grep -c '^🟢')" = 1 ] \
    && printf '%s\n' "$a_out" | sed -n 2p | grep -qF 'маяк-зелёный-щит' \
    && [ "$(printf '%s\n' "$a_out" | sed -n 3p | grep -c '^⚪')" = 1 ] \
    && printf '%s\n' "$a_out" | sed -n 3p | grep -qF 'FX-901' \
    && [ "$(printf '%s\n' "$a_out" | grep -c '^📅 срок пересмотра')" = 0 ]; }
  is "🟢 и ⚪ — по строке и вперёд, 📂 — ни одной построчно (всего 4 строки)" $?
  out="$a_out"
  { [ "$a_rc" = 0 ] && ln_ 4 | grep -q '^📅 наступивших сроков пересмотра 79 (' \
    && has '11.09–20.11' && has 'сентябрь 8 · октябрь 51 · ноябрь 20' && has 'bl-wake.py --overdue'; }
  is "строка счёта одна: 79, разбивка по месяцам, диапазон дат, зовёт --overdue" $?
  [ "$(printf '%s' "$a_out" | grep -c 'маяк-зелёный-щит')" -ge 1 ] && hit=1

  run "$F" --overdue
  { [ "$rc" = 0 ] && [ "$(n_start '📅 срок пересмотра')" = 79 ] && [ "$(n_start '📅 наступивших')" = 0 ] \
    && has 'маяк-зелёный-щит' && has 'FX-901'; }
  is "--overdue: тот же кэш построчно — 79 📂, 🟢 и ⚪ на месте, строки счёта нет" $?

  echo "=== контракты сред ==="

  printf '%s' "$a_out" > "$ROOT/plain.txt"
  out="$(cd "$F" && blwz 2>"$ROOT/err")"; rc=$?
  printf '%s\n' "$out" > "$ROOT/zcode.txt"
  same_json; json_ok=$?
  { [ "$rc" = 0 ] && [ "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" = 1 ] && [ "$(n_start '{')" = 1 ] \
    && [ "$json_ok" = 0 ] && [ "$(grep -c 'маяк-зелёный-щит' "$ROOT/plain.txt")" -ge 1 ]; }
  is "контракт ZCode: под ZCODE_SESSION_ID — ровно один JSON, нагрузка байт-в-байт равна plain, 🟢 внутри" $?

  out="$(cd "$F" && ZCODE_SESSION_ID=x blw --overdue 2>"$ROOT/err")"; rc=$?
  { [ "$rc" = 0 ] && [ "$(n_start '{')" = 0 ] && [ "$(n_start '📅 срок пересмотра')" = 79 ]; }
  is "ручной ключ читает терминал: под ZCODE_SESSION_ID --overdue остаётся plain" $?

  out="$(cd "$F" && ZCODE_SESSION_ID=x blw 2>"$ROOT/err")"; rc=$?
  { [ "$rc" = 0 ] && [ "$(n_start '{')" = 0 ] && has 'маяк-зелёный-щит'; }
  is "подложенный снаружи ZCODE_SESSION_ID не переводит plain-прогон стенда на JSON" $?

  N="$ROOT/nobacklog"; mkdir -p "$N"; git -C "$N" init -q
  printf '🟢 созрело FX-999 · чужой-кэш-маяк\n' > "$N/.git/bl-wake.cache"
  NG="$ROOT/nogit"; mkdir -p "$NG"
  run "$N"; b_rc=$rc; b_out="$out"
  out="$(cd "$N" && blwz 2>"$ROOT/err")"; c_out="$out"
  run "$NG"; d_rc=$rc; d_out="$out"
  { [ "$b_rc" = 0 ] && [ -z "$b_out" ] && [ "$d_rc" = 0 ] && [ -z "$d_out" ] && [ "$hit" = 1 ]; }
  is "вне docflow-репо (без backlog/, без git) молчит кодом 0, а рядом на кэше говорит" $?
  { [ -z "$c_out" ] && [ "$json_ok" = 0 ]; }
  is "вне docflow-репо молчит и на контракте ZCode (даже не {}), а на кэше отдаёт JSON" $?

  E="$ROOT/empty"; mkdir -p "$E/backlog"; git -C "$E" init -q; : > "$E/.git/bl-wake.cache"
  run "$E"; e_rc=$rc; e_out="$out"
  out="$(cd "$E" && blwz 2>"$ROOT/err")"; g_out="$out"
  { [ "$e_rc" = 0 ] && [ -z "$e_out" ] && [ -z "$g_out" ] && [ "$json_ok" = 0 ]; }
  is "пустой кэш: молчит в обоих контрактах, а непустой рядом говорит" $?

  fi
  [ "${1:-}" = fast ] && return 0

  echo "=== дисциплина кэша: свежий не тронут, старый и пропавший — пробы в фон ==="

  cp "$C" "$ROOT/cache.copy"; ago 20 "$C"
  run "$F"; h_rc=$rc; h_out="$out"
  sleep 2
  { [ "$h_rc" = 0 ] && has 'пробы 20 мин назад' && cmp -s "$C" "$ROOT/cache.copy"; }
  is "кэш 20 минут назад: шапка называет возраст, перезаписи нет (порог 30)" $?

  ago 40 "$C"
  run "$F"
  { [ "$rc" = 0 ] && has 'пробы 40 мин назад' && wait_changed "$C" "$ROOT/cache.copy"; }
  is "кэш старше 30 минут: шапка честна, и пробы уходят в фон — кэш перезаписан" $?

  rm "$C"
  run "$F"; m_rc=$rc; m_out="$out"
  { [ "$m_rc" = 0 ] && [ -z "$m_out" ] && [ -n "$h_out" ] && wait_exists "$C"; }
  is "кэша нет: молчит кодом 0, а фон его создаёт — рядом непустой говорит" $?

  echo "=== живой backlog: пробы → кэш → форма ==="

  G="$ROOT/live"; mkdir -p "$G"
  git -C "$G" init -q
  # 🔴 init и create — только внутри фикстуры: без cd они пишут в backlog/ и
  # CLAUDE.md того чекаута, откуда пущен стенд (27.11.2026: четыре задачи DF-30–33
  # очутились в ворктри, а config.yml и CLAUDE.md — правлены).
  (cd "$G" && backlog init "Стенд" --defaults --integration-mode cli --agent-instructions claude --task-prefix FX) \
    >"$ROOT/init.log" 2>&1 || echo "  🔴 backlog init отказал: $(head -c 200 "$ROOT/init.log")"
  # docflow: колонка Backlog — четвёртая (setup.md, шаг 3); init --defaults её не ставит
  { grep -v '^statuses:' "$G/backlog/config.yml"; printf 'statuses: ["Backlog", "To Do", "In Progress", "Done"]\n'; } \
    > "$G/backlog/config.new" && mv "$G/backlog/config.new" "$G/backlog/config.yml"
  mkt() {  # mkt <заголовок> <шапка-блока> <тело-пробы> <due>
    (cd "$G" && backlog task create "$1" -s Backlog --plain \
      -d '```when'$'\n'"$2"$'\n'"---"$'\n'"$3"$'\n```'$'\n'"почему не сейчас" ${4:+--due-date "$4"}) \
      >"$ROOT/create.log" 2>&1 || echo "  🔴 backlog task create «$1» отказал: $(head -c 200 "$ROOT/create.log")"
  }
  mkt "Зрелая проба" "match: маяк-живой-рок" "echo маяк-живой-рок; exit 0" ""
  mkt "Тихая проба" "" "exit 3" ""
  mkt "Недостижимая" "cwd: /no/such/dir-bite" "echo маяк-живой-рок" ""
  mkt "Срок прошёл" "" "" 2026-09-26
  run "$G" --now
  { [ "$rc" = 0 ] && [ "$(n_start '🟢')" = 1 ] && has 'маяк-живой-рок' && [ "$(n_start '⚪')" = 1 ] \
    && has 'нет cwd' && [ "$(n_start '📅 срок пересмотра')" = 0 ] && [ "$(n_start '📅 наступивших сроков пересмотра 1 (')" = 1 ]; }
  is "пробы живые: 🟢 с находкой, ⚪ «нет cwd», 📂 — строкой счёта; тихая (exit 3) не звучит" $?
  run "$G"
  { [ "$rc" = 0 ] && [ "$(grep -c '^📅 срок пересмотра' "$G/.git/bl-wake.cache")" = 1 ] \
    && [ "$(n_start '📅 наступивших сроков пересмотра 1 (')" = 1 ]; }
  is "кэш хранит список целиком, а хук на нём печатает строку счёта" $?
  printf '%s' "$out" > "$ROOT/plain.txt"
  out="$(cd "$G" && blwz 2>"$ROOT/err")"; rc=$?
  printf '%s\n' "$out" > "$ROOT/zcode.txt"
  same_json; live_json=$?
  { [ "$rc" = 0 ] && [ "$live_json" = 0 ] && [ "$(grep -c 'маяк-живой-рок' "$ROOT/plain.txt")" -ge 1 ]; }
  is "живой кэш на контракте ZCode: один JSON с той же нагрузкой" $?
}

# Первая строка прогона: по одному логу видно, какой файл и в каком чекауте
# проверен. Без BLWAKE= это файл того же чекаута, что и стенд, с BLWAKE= —
# названная копия.
if [ -n "${BLWAKE:-}" ]; then how="по BLWAKE="; else how="рядом со стендом"; fi
echo "испытываемый файл: $W — $how"
echo

suite fast; NF=$((pass + fail))
# 🔴 Какой файл здесь проверяется. Спаяно с положительной половиной: строку счёта
# и 🟢 из кэша принёс именно этот файл — заглушке здесь зеленеть нечего.
# Статическая половина — у определения W: запуск мимо "$W" виден только по
# тексту стенда, по выводу его не отличить.
[ -z "$bypass" ] || echo "  🔴 запуск мимо переменной пути: $bypass"
{ [ "$W" = "${BLWAKE:-$HERE/bl-wake.py}" ] && [ -z "$bypass" ] && [ "$hit" = 1 ]; }
is "🔴 испытываемый файл — рядом со стендом (или назван BLWAKE=), и он же принёс 🟢 из кэша" $?

suite slow

echo "=== стенд умеет краснеть: нарочно сломанные копии ==="

# Подпроход — та же suite fast в подоболочке с подменённым $W; счёт читаем по
# строкам вывода. Копии — sed от живого файла: якорь не найден, и копия равна
# живому — тогда подпроход зелёный, и укус краснеет сам.
subcount() { printf '%s\n' "$sub" | grep -c "^  $1"; }   # subcount ✅|❌
sed 's/^    if zcode:/    if False:/' "$W" > "$ROOT/plain-only.py"
sed 's/^    if full:/    if True:/' "$W" > "$ROOT/dump.py"
: > "$ROOT/stub.py"
sub="$(W="$ROOT/plain-only.py" suite fast)"
# Ровно три, не один: укусы «вне docflow-репо молчит» и «пустой кэш» не стоят
# на одном отрицании — каждый спаян с «на кэше отдаёт JSON», и для копии, которая
# JSON не отдаёт нигде, спайка ложная. Замер 27.11.2026: ✅ 6 ❌ 3.
{ [ "$(subcount ❌)" = 3 ] && [ "$(subcount ✅)" = $((NF - 3)) ] && printf '%s\n' "$sub" | grep -q '❌ контракт ZCode:'; }
is "копия без JSON-обёртки краснеет ровно тремя — контракт ZCode и две спайки на нём" $?
sub="$(W="$ROOT/dump.py" suite fast)"
{ [ "$(subcount ❌)" = 2 ] && [ "$(subcount ✅)" = $((NF - 2)) ] && printf '%s\n' "$sub" | grep -q '❌ 🟢 и ⚪ — по строке'; }
is "копия, печатающая кэш целиком, краснеет ровно двумя — строка счёта 📂" $?
sub="$(W="$ROOT/stub.py" suite fast)"
{ [ "$(subcount ❌)" = "$NF" ] && [ "$(subcount ✅)" = 0 ]; }
is "заглушка (пустой файл, exit 0) даёт ✅ 0 ❌ $NF — ни один укус не стоит на одном отрицании" $?

echo
echo "итог: ✅ $pass   ❌ $fail"
[ "$fail" = 0 ]
