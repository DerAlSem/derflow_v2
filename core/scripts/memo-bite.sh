#!/usr/bin/env bash
# Стенд укуса memo.py: каждое утверждение вердикта ломается нарочно.
#
#   bash ~/.claude/scripts/memo-bite.sh
#   MEMO=/путь/к/сломанной/копии bash ~/.claude/scripts/memo-bite.sh
#
# Зачем в репозитории, а не в скрэтчпаде: сторож, чей стенд умирает вместе с
# сессией, второй раз дефекта не ловит. Стенд обязан УМЕТЬ КРАСНЕТЬ — задача 7
# ломает memo.py нарочно и сверяет, что стенд это видит.
#
# Проверка самого стенда 08.09.2026 — на нарочно сломанных копиях (обычный
# прогон даёт ✅ 53 ❌ 0, заглушка ✅ 0 ❌ 53):
#   без проверки хоста          → 2 ❌ («вердикт с ЧУЖОГО хоста не берётся»,
#                                  «чужой хост — гейт гнался заново») — совпало
#   без проверки грязи          → 3 ❌, все в главе «страховки», 0 в «кэш» и
#                                  «прогон» — совпало (≥3 и 0/0)
#   красный вердикт пишется как pass → 2 ❌ в главе «кэш», среди них «красный
#                                  гейт не записан — второй раз гнался заново» —
#                                  совпало (≥2, нужный укус в составе)
#   без --path-format=absolute  → 8 ❌, а не ≥2 из брифа. Расхождение объяснено:
#                                  без --path-format+.resolve() git отдаёт
#                                  ЛИТЕРАЛЬНУЮ строку ".git" из корня ЛЮБОГО
#                                  репозитория, её хэш одинаков всегда — repo_id
#                                  схлопывается в ОДНО значение для всех
#                                  репозиториев стенда, вызванных из своего
#                                  корня, и они делят один каталог вердиктов.
#                                  Оба именованных брифом укуса красны, плюс
#                                  контаминация утекает в чужой хост, s3,
#                                  forget --all и forget "" ниже по стенду —
#                                  поломка шире, чем бриф размечал, укус её
#                                  видит целиком, а не слабее ожидания
#   без сторожа записи на грязном/неотслеж. дереве → 2 ❌ («дерево снова чистое
#                                  — берётся ПЕРВЫЙ вердикт, не переписанный»,
#                                  «при неотслеживаемом конфиге вердикт не
#                                  записан ВОВСЕ») — совпало
# Числа сверять после любой правки укусов: расхождение значит, что укус ослаб
# (кроме случая --path-format — там расхождение — свойство самой поломки).
set -u
M="${MEMO:-$HOME/.claude/scripts/memo.py}"
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT"' EXIT
export MEMO_HOME="$ROOT/home"        # вердикты НЕ в живой ~/.claude
mkdir -p "$MEMO_HOME"
pass=0; fail=0; RC_FRESH=0

mk() {  # mk <имя> → печатает путь к свежему репозиторию с гейтом-счётчиком
  d="$ROOT/$1"; mkdir -p "$d"
  git -C "$d" init -q -b main .
  git -C "$d" config user.email t@t; git -C "$d" config user.name t
  # Путь к счётчику ЗАПЕКАЕТСЯ абсолютным, а не берётся от __file__: в ворктри
  # gate.py — это чекаут того же файла, и по __file__ он писал бы счётчик в
  # ворктри. Укус «вердикт переезжает между ворктри» тогда считал бы прогоны в
  # двух разных файлах и проходил зелёным, ничего не проверив.
  cat > "$d/gate.py" <<GATE
import pathlib, sys
log = pathlib.Path("$d/runs.log")
log.open("a").write("run\n")
rcf = pathlib.Path("$d/rc.txt")
sys.exit(int(rcf.read_text().strip()) if rcf.exists() else 0)
GATE
  printf '{"gate_pure": ["python3 gate.py"], "gate_version_external": []}\n' > "$d/deploy.json"
  echo x > "$d/a.txt"
  git -C "$d" add -A; git -C "$d" commit -qm init
  printf '%s' "$d"
}
runs() { [ -f "$1/runs.log" ] && wc -l < "$1/runs.log" | tr -d ' ' || echo 0; }
chk() {  # chk <ожидаемый rc> <ярлык> [<подстрока>|!<подстроки быть не должно>]
  want="$1"; label="$2"; needle="${3:-}"
  out="$(cd "$D" && python3 "$M" ${ARG:-check} 2>&1)"; rc=$?
  RC_FRESH=1
  ok=1
  [ "$rc" = "$want" ] || ok=0
  case "$needle" in
    '!'*) printf '%s' "$out" | grep -q -- "${needle#!}" && ok=0 ;;
    ?*)   printf '%s' "$out" | grep -q -- "$needle" || ok=0 ;;
  esac
  if [ "$ok" = 1 ]; then echo "  ✅ $label (rc=$rc)"; pass=$((pass+1))
  else
    case "$needle" in
      # Скобки ОБЯЗАТЕЛЬНЫ: bash 3.2 (единственный на macOS) присоединяет первый
      # байт многобайтового «»» к имени переменной, и под `set -u` это не пустая
      # строка, а обрыв всего стенда на первом же красном укусе. Замер 08.09.2026:
      # `bash -c 'set -u; n=abc; echo "[«$n»]"'` → «n<байт>: unbound variable».
      # Та же форма живёт в hand-bite.sh, где `set -u` нет и симптом другой —
      # диагностика молча выходит пустой (его комментарий от 07.09 винит в этом
      # последовательность «« + !», и это неверный диагноз той же болезни).
      '!'*) say="и НЕ должно быть «${needle#!}»" ;;
      ?*)   say="и «${needle}»" ;;
      *)    say="" ;;
    esac
    echo "  ❌ $label — ждали rc=$want ${say}, получили rc=$rc"
    echo "$out" | sed 's/^/       /'; fail=$((fail+1)); fi
  ARG=""
}
cnt() {  # cnt <ожидаемое число прогонов> <ярлык> [<ожидаемый rc последнего chk>]
  # 3-й параметр нужен ровно одному вызову: «0 прогонов» при отсутствии
  # конфига тривиально истинно и на настоящем memo, и на пустой заглушке —
  # та gate.py не запускает вообще никогда, вне зависимости от причины.
  # Замер 08.09.2026 на заглушке: без сверки rc этот укус был зелёным впустую.
  # Правило порядка: `cnt` с 3-м параметром звать ТОЛЬКО непосредственно после
  # `chk` — иначе `$rc` протухший, от чужого, более раннего вызова. До
  # 10.09.2026 это держалось СОГЛАШЕНИЕМ, то есть ничем: перестановка строк
  # молча превращала укус в сверку со случайным кодом. Теперь держится сторожем
  # RC_FRESH — `chk` его ставит, `cnt` съедает.
  got="$(runs "$D")"; ok=1
  [ "$got" = "$1" ] || ok=0
  if [ -n "${3:-}" ]; then
    if [ "${RC_FRESH:-0}" != 1 ]; then
      echo "  ❌ $2 — cnt с 3-м параметром вызван не сразу после chk: \$rc протухший"
      fail=$((fail+1)); RC_FRESH=0; return
    fi
    RC_FRESH=0
    [ "$rc" = "$3" ] || ok=0
  fi
  if [ "$ok" = 1 ]; then echo "  ✅ $2 (прогонов: $got)"; pass=$((pass+1))
  else
    echo "  ❌ $2 — ждали прогонов $1${3:+ и rc=$3}, получили прогонов $got, rc=${rc:-?}"
    fail=$((fail+1))
  fi
}

echo "=== положение в git ==="

D="$(mk ctx1)"
ARG="list"; chk 0 "list на пустом кэше печатает дерево HEAD" "дерево HEAD:"
ARG="list"; chk 0 "list на пустом кэше говорит, что вердиктов нет" "вердиктов нет"

# Главный сценарий подпроекта: две сессии = два ворктри одного репозитория.
D="$(mk ctx2)"
git -C "$D" worktree add -q "$ROOT/ctx2-wt" -b wb
id_main="$(cd "$D" && python3 "$M" list | grep '^репозиторий:')"
id_wt="$(cd "$ROOT/ctx2-wt" && python3 "$M" list | grep '^репозиторий:')"
if [ "$id_main" = "$id_wt" ] && [ -n "$id_main" ]; then
  echo "  ✅ repo-id ОДИНАКОВ в главном чекауте и в ворктри"; pass=$((pass+1))
else echo "  ❌ repo-id разошёлся: [$id_main] против [$id_wt]"; fail=$((fail+1)); fi
t_main="$(cd "$D" && python3 "$M" list | grep '^дерево HEAD:')"
t_wt="$(cd "$ROOT/ctx2-wt" && python3 "$M" list | grep '^дерево HEAD:')"
if [ "$t_main" = "$t_wt" ] && [ -n "$t_main" ]; then
  echo "  ✅ tree_sha ОДИНАКОВ в двух ворктри на одном коммите"; pass=$((pass+1))
else echo "  ❌ tree_sha разошёлся: [$t_main] против [$t_wt]"; fail=$((fail+1)); fi

# Из подкаталога — тот же repo-id. Ловит наивное сравнение строк `--git-common-dir`:
# git отдаёт оттуда «../.git», и без --path-format=absolute id был бы другим.
mkdir -p "$D/sub"
id_sub="$(cd "$D/sub" && python3 "$M" list | grep '^репозиторий:')"
# `-n` тут не украшение, а тот же сторож, что на двух укусах выше: на вконец
# сломанном memo обе переменные пусты, пустое равно пустому, и укус проходит
# зелёным, ничего не проверив. Замер 08.09.2026 на заглушке: без `-n` из девяти
# красных этот один был зелёным.
if [ "$id_sub" = "$id_main" ] && [ -n "$id_sub" ]; then
  echo "  ✅ repo-id из ПОДКАТАЛОГА тот же"; pass=$((pass+1))
else echo "  ❌ repo-id из подкаталога разошёлся: [$id_sub]"; fail=$((fail+1)); fi

# ARG="list" здесь обязателен: команды `check` в задаче 1 ещё нет, и по умолчанию
# argparse отказал бы кодом 2 по СВОЕЙ причине — укус прошёл бы зелёным впустую.
D="$ROOT/not-a-repo"; mkdir -p "$D"
ARG="list"; chk 2 "вне репозитория git — код 2, а не падение" "не репозиторий"

D="$ROOT/empty-repo"; mkdir -p "$D"; git -C "$D" init -q -b main .
ARG="list"; chk 2 "репозиторий без коммитов — код 2, дерева нет" "нет коммитов"

D="$(mk ctx3)"
echo draft > "$D/untracked.txt"
ARG="list"; chk 0 "untracked-файл дерево НЕ грязнит" "грязное:     нет"

D="$(mk ctx4)"
echo changed > "$D/a.txt"
ARG="list"; chk 0 "правка отслеживаемого файла дерево грязнит" "грязное:     да"

echo
echo "=== конфигурация и ключ ==="

# ⚠️ Здесь ТОЛЬКО те укусы, которым хватает `list`. Ошибки конфига проверяются
# через `check`, а его ещё нет: argparse отказал бы кодом 2 по своей причине, и
# укус проходил бы зелёным, ничего не проверив. Они заведены в задаче 3.

# Ключ обязан двигаться от ВНЕШНЕГО входа и не двигаться без него.
D="$(mk cfg5)"
ext="$ROOT/external.txt"; echo v1 > "$ext"
printf '{"gate_pure": ["python3 gate.py"], "gate_version_external": ["%s"]}\n' "$ext" \
  > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm ext
gv1="$(cd "$D" && python3 "$M" list | grep '^ключ gv:')"
gv1b="$(cd "$D" && python3 "$M" list | grep '^ключ gv:')"
echo v2 > "$ext"
gv2="$(cd "$D" && python3 "$M" list | grep '^ключ gv:')"
if [ "$gv1" = "$gv1b" ] && [ -n "$gv1" ]; then
  echo "  ✅ ключ УСТОЙЧИВ при неизменном внешнем входе"; pass=$((pass+1))
else echo "  ❌ ключ прыгает сам по себе: [$gv1] против [$gv1b]"; fail=$((fail+1)); fi
if [ "$gv1" != "$gv2" ]; then
  echo "  ✅ правка ВНЕШНЕГО входа двигает ключ"; pass=$((pass+1))
else echo "  ❌ внешний вход в ключ не попал: [$gv1] = [$gv2]"; fail=$((fail+1)); fi

D="$(mk cfg7)"
ARG="list"; chk 0 "list БЕЗ вердиктов всё равно печатает ключ" "ключ gv:"

# list обязан пережить отсутствие конфига: смотреть кэш надо и там, где конфига
# нет, иначе инструмент «посмотреть и сбросить» отказывает ровно там, где нужен.
D="$(mk cfg8)"; rm "$D/deploy.json"; git -C "$D" rm -q --cached deploy.json
git -C "$D" commit -qm "без конфига"
ARG="list"; chk 0 "list без конфига — не падает, а говорит об этом" "конфига нет"

# C1: два ОТСЛЕЖИВАЕМЫХ конфига с разными командами на одном дереве целятся в
# ОДИН файл вердикта (путь конфига в ключе (tree_sha, gate_version_external)
# не участвует). Мутация 08.09.2026, снявшая сверку `commands` в read_verdict:
# второй вызов брал вердикт первого и НЕ гонял gate2.py вообще — ложная зелень.
# Иголка — не код возврата (он зелёный в обоих случаях), а ФАКТ прогона: файл
# runs2.log обязан появиться только после вызова с --config alt.json.
D="$(mk c1cfg)"
cat > "$D/gate2.py" <<GATE2
import pathlib
pathlib.Path("$D/runs2.log").open("a").write("run\n")
GATE2
printf '{"gate_pure": ["python3 gate2.py"], "gate_version_external": []}\n' \
  > "$D/alt.json"
git -C "$D" add -A; git -C "$D" commit -qm altcfg

chk 0 "первый конфиг (deploy.json) гоняется и кэшируется" "гейт зелёный"
cnt 1 "гейт A (deploy.json) прогнался ровно раз" 0

ARG="check --config $D/alt.json"
chk 0 "второй конфиг (alt.json, ДРУГИЕ команды) тоже отдаёт зелёное" "гейт зелёный"
runs2="$([ -f "$D/runs2.log" ] && wc -l < "$D/runs2.log" | tr -d ' ' || echo 0)"
runsA="$(runs "$D")"
if [ "$runs2" = 1 ] && [ "$runsA" = 1 ]; then
  echo "  ✅ гейт B (alt.json) РЕАЛЬНО гонялся, а не считан из вердикта гейта A"
  pass=$((pass+1))
else
  echo "  ❌ ложная зелень C1: runs.log(A)=${runsA} (ждали 1), runs2.log(B)=${runs2} (ждали 1)"
  fail=$((fail+1))
fi

echo
echo "=== прогон ==="

# Перенесено из задачи 2: этим укусам нужна команда `check`, и только теперь она
# есть. Проверяется не код 2 сам по себе (его дал бы и argparse), а ТЕКСТ причины.
D="$(mk cfg1)"; rm "$D/deploy.json"; git -C "$D" rm -q --cached deploy.json
git -C "$D" commit -qm "без конфига"
chk 2 "нет deploy.json — код 2 с названной причиной" "не знает, что гнать"
cnt 0 "гейт при отсутствии конфига не гонялся" 2

D="$(mk cfg2)"; printf 'не json вовсе\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm broken
chk 2 "deploy.json не JSON — код 2, а не падение трейсбеком" "не JSON"

D="$(mk cfg3)"; printf '{"gate_pure": []}\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm empty
chk 2 "пустой gate_pure — код 2" "непустым списком"

D="$(mk cfg4)"; printf '{"gate_pure": "python3 gate.py"}\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm str
chk 2 "gate_pure строкой, а не списком — код 2" "непустым списком"

D="$(mk cfg6)"
printf '{"gate_pure": ["python3 gate.py"], "gate_version_external": ["%s/нет-такого"]}\n' \
  "$ROOT" > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm noext
chk 2 "нечитаемый внешний вход — код 2, а не тихий ключ из ничего" "не читается"

D="$(mk run1)"
chk 0 "зелёный гейт — код 0" "гейт зелёный"
cnt 1 "зелёный гейт гонялся ровно раз"

D="$(mk run2)"; echo 1 > "$D/rc.txt"
chk 1 "красный гейт — код 1, а НЕ 0" "гейт красный"

# Тот самый feedback_pipe_swallows_pytest_rc, только структурно: без шелла
# конвейер невозможен, поэтому код возврата некому глотать.
D="$(mk run3)"; echo 7 > "$D/rc.txt"
chk 1 "код возврата гейта не проглочен: rc=7 → memo rc=1" "кодом 7"

D="$(mk run4)"
printf '{"gate_pure": ["python3 gate.py", "python3 нет-такого.py"]}\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm two
chk 1 "вторая команда падает — общий результат красный" "гейт красный"
cnt 1 "первая команда всё же гонялась"

D="$(mk run5)"
printf '{"gate_pure": ["не-существует-такой-команды"]}\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm nocmd
chk 1 "команды нет в PATH — код 1, а не трейсбек" "не запустилась"

echo
echo "=== кэш ==="

# Укус 1 спеки: пишет один процесс, читает ДРУГОЙ — с другим pid и другой сессией.
D="$(mk c1)"
(cd "$D" && CLAUDE_CODE_SESSION_ID=aaa python3 "$M" check >/dev/null 2>&1)
out="$(cd "$D" && CLAUDE_CODE_SESSION_ID=bbb python3 "$M" check 2>&1)"; rc=$?
if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q "сессия aaa"; then
  echo "  ✅ вердикт процесса A виден процессу B и назван его сессией"; pass=$((pass+1))
else echo "  ❌ кросс-процессный вердикт не сработал (rc=$rc)"; echo "$out" | sed 's/^/       /'; fail=$((fail+1)); fi
cnt 1 "второй процесс чистую часть НЕ гонял"

# Укус 2 спеки: главный сценарий подпроекта — вердикт переезжает между ворктри.
D="$(mk c2)"
git -C "$D" worktree add -q "$ROOT/c2-wt" -b c2b
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
(cd "$ROOT/c2-wt" && python3 "$M" check >/dev/null 2>&1)
cnt 1 "вердикт из ворктри A действует в ворктри B того же репозитория"

# Укус 3 спеки: правка байта в дереве обесценивает вердикт.
D="$(mk c3)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
echo y >> "$D/a.txt"; git -C "$D" add -A; git -C "$D" commit -qm byte
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 2 "закоммиченная правка байта — вердикт не действует, гейт гнался снова"

# Укус 4 спеки: внешний вход при НЕИЗМЕННОМ дереве обесценивает вердикт.
D="$(mk c4)"
ext="$ROOT/ext4.txt"; echo v1 > "$ext"
printf '{"gate_pure": ["python3 gate.py"], "gate_version_external": ["%s"]}\n' "$ext" \
  > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm ext4
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
echo v2 > "$ext"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 2 "правка ВНЕШНЕГО входа при том же дереве — гейт гнался снова"

# Укус 5 спеки: untracked-файл кэш не ломает.
D="$(mk c5)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
echo draft > "$D/черновик.txt"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 1 "untracked-файл кэш НЕ ломает"

# Укус 6 спеки: красное не кэшируется никогда.
D="$(mk c6)"; echo 1 > "$D/rc.txt"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 2 "красный гейт не записан — второй раз гнался заново"
echo 0 > "$D/rc.txt"
chk 0 "после починки тот же sha даёт зелёное" "гейт зелёный"

echo
echo "=== страховки ==="

# Грязное дерево: tree_sha описывает HEAD, а гоняется рабочая копия. Это РАЗНЫЕ
# деревья, и вердикт по первому ничего не говорит о втором.
# Сессии ИМЕНОВАНЫ нарочно. Иголка «гейт пройден» доказывала бы только то, что
# какой-то вердикт есть, — а вопрос в том, ЧЕЙ он. Оба вердикта (законный с чистого
# дерева и незаконный с грязного) целятся в один файл по одному tree_sha и оба несут
# `pass`; отличить их можно только по имени сессии. Замер 08.09.2026: мутация,
# снявшая сторож записи, оставила стенд полностью зелёным — укус не отличал
# наличие сторожа от его отсутствия.
D="$(mk s1)"
(cd "$D" && CLAUDE_CODE_SESSION_ID=первый python3 "$M" check >/dev/null 2>&1)
echo changed > "$D/a.txt"
export CLAUDE_CODE_SESSION_ID=грязный
chk 0 "грязное дерево — гоним, а не отказываем" "кэш выключен"
cnt 2 "грязное дерево кэш НЕ использует"
git -C "$D" checkout -q -- a.txt
unset CLAUDE_CODE_SESSION_ID
chk 0 "дерево снова чистое — берётся ПЕРВЫЙ вердикт, не переписанный" "сессия первый"
cnt 2 "на грязном дереве вердикт не записывался: третьего прогона не было"

# Инвариант 2: вердикт локален. ~/.claude однажды кто-нибудь засинхронит.
D="$(mk s2)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
# Область поиска — каталог ЭТОГО репозитория. Все временные репозитории стенда
# имеют ОДИНАКОВЫЙ tree_sha (содержимое файлов совпадает), и `find | head -1` по
# всему MEMO_HOME правил бы чужой вердикт.
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
vf="$(ls "$MEMO_HOME/gate-verdicts/$rid"/*.json | head -1)"
python3 - "$vf" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["host"] = "чужая-машина"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
PY
chk 0 "вердикт с ЧУЖОГО хоста не берётся, факт напечатан" "на другом хосте"
cnt 2 "чужой хост — гейт гнался заново"

# m1: читающая половина инварианта 7. Мутация «убрать в read_verdict сверку
# result != "pass"» оставляла бы стенд полностью зелёным без этого укуса —
# ревью нашло, что кэшируется ТОЛЬКО pass, но никто не проверял, что "fail",
# положенный в кэш руками (или битым писателем), не будет ВЗЯТ read_verdict.
D="$(mk s2b)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
vf="$(ls "$MEMO_HOME/gate-verdicts/$rid"/*.json | head -1)"
python3 - "$vf" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["result"] = "fail"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
PY
chk 0 "вердикт с result=fail в кэше не берётся, гейт гонится заново" "гейт зелёный"
cnt 2 "result=fail в файле — второй прогон состоялся, кэш не взял его"

# Неотслеживаемый deploy.json: под --untracked-files=no он невидим, значит
# подмена команд гейта прошла бы мимо и грязи, и tree_sha.
D="$(mk s3)"
git -C "$D" rm -q --cached deploy.json; git -C "$D" commit -qm "конфиг вне git"
chk 0 "неотслеживаемый deploy.json — гоним, кэш выключен" "не отслеживается"
cnt 1 "прогон при выключенном кэше состоялся"
chk 0 "и во второй раз тоже гоним" "кэш выключен"
cnt 2 "неотслеживаемый конфиг кэш НЕ использует"

# Прямая проверка ФАЙЛОВОЙ СИСТЕМЫ, а не поведения. При выключенном кэше чтение
# пропускается всегда, поэтому незаконную запись через сам memo не увидеть: он
# её просто не прочтёт. Здесь вердиктов не должно появиться ни одного вовсе.
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
nv="$(ls "$MEMO_HOME/gate-verdicts/${rid}"/*.json 2>/dev/null | wc -l | tr -d ' ')"
if [ "$nv" = 0 ] && [ -n "$rid" ]; then
  echo "  ✅ при неотслеживаемом конфиге вердикт не записан ВОВСЕ"; pass=$((pass+1))
else echo "  ❌ вердиктов записано ${nv} (rid=[${rid}]), ждали 0"; fail=$((fail+1)); fi

echo
echo "=== посмотреть и сбросить ==="

# Иголка — СЕССИЯ, а не sha дерева: sha печатается строкой «дерево HEAD:» всегда,
# и укус на нём проходил бы зелёным при полностью отсутствующей таблице.
D="$(mk f1)"
(cd "$D" && CLAUDE_CODE_SESSION_ID=опознавательная python3 "$M" check >/dev/null 2>&1)
ARG="list"; chk 0 "list показывает строку записанного вердикта" "опознавательная"
ARG="list"; chk 0 "list помечает вердикт ТЕКУЩЕГО дерева стрелкой" "→"

D="$(mk f2)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
(cd "$D" && python3 "$M" forget --current >/dev/null 2>&1)
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 2 "forget --current заставляет гнать заново"

D="$(mk f3)"
ARG="forget --current"; chk 0 "forget на пустом кэше — ответ, а не ошибка" "нечего забывать"

# Голый forget без --current/--all/sha: argparse обязан отказать сам, кодом 2 по
# СВОЕЙ причине. $D неважен — разбор аргументов падает раньше, чем memo дойдёт
# до git; но chk всё равно делает `cd "$D"`, и каталог обязан существовать.
ARG="forget"; chk 2 "forget без аргументов — argparse отказывает" "required"

# forget --all: не «list ничего не печатает» (это истинно и на сломанном list —
# урок задач 1–5), а прямая проверка ФАЙЛОВОЙ СИСТЕМЫ: было два файла вердикта,
# стало ноль. На заглушке ни один check не пишет файл, rid остаётся пустым,
# before никогда не равен 2 — мутант, оставляющий файлы на месте, здесь красен.
D="$(mk f4)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
echo y >> "$D/a.txt"; git -C "$D" add -A; git -C "$D" commit -qm two
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
before="$(ls "$MEMO_HOME/gate-verdicts/${rid}"/*.json 2>/dev/null | wc -l | tr -d ' ')"
(cd "$D" && python3 "$M" forget --all >/dev/null 2>&1)
after="$(ls "$MEMO_HOME/gate-verdicts/${rid}"/*.json 2>/dev/null | wc -l | tr -d ' ')"
if [ -n "$rid" ] && [ "$before" = 2 ] && [ "$after" = 0 ]; then
  echo "  ✅ forget --all вычищает оба вердикта на файловой системе"; pass=$((pass+1))
else
  echo "  ❌ forget --all: было ${before:-?}, после ${after:-?} (rid=[$rid])"; fail=$((fail+1))
fi

# forget <sha>: точечное удаление по позиционному аргументу — третья ветка
# cmd_forget, отдельная от --current и --all. Проверка через runs.log (задача 4).
D="$(mk f5)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
sha="$(cd "$D" && git rev-parse HEAD^{tree})"
(cd "$D" && python3 "$M" forget "$sha" >/dev/null 2>&1)
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
cnt 2 "forget <sha> точечно вычищает вердикт этого дерева"

# forget "": ревью задачи 6 нашло, что пустая строка проходит мимо required-
# группы argparse (для него это не None — «аргумент подан») и глоб `*.json`
# совпадает со всем: радиус --all без --all. Проверяем ОБЕ половины — код
# возврата сам по себе не доказывает, что файлы целы. Иголка — текст отказа.
D="$(mk f6)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
echo y >> "$D/a.txt"; git -C "$D" add -A; git -C "$D" commit -qm two
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
before="$(ls "$MEMO_HOME/gate-verdicts/${rid}"/*.json 2>/dev/null | wc -l | tr -d ' ')"
out="$(cd "$D" && python3 "$M" forget "" 2>&1)"; rc=$?
after="$(ls "$MEMO_HOME/gate-verdicts/${rid}"/*.json 2>/dev/null | wc -l | tr -d ' ')"
if [ "$rc" = 2 ] && printf '%s' "$out" | grep -q "слишком короткий" \
    && [ "$before" = 2 ] && [ "$after" = 2 ]; then
  echo "  ✅ forget \"\" отказывает кодом 2 и не удаляет ни одного вердикта"; pass=$((pass+1))
else
  echo "  ❌ forget \"\": rc=$rc (ждали 2), вердиктов до=${before:-?} после=${after:-?} (ждали 2 и 2)"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# ── долги финального ревью, закрываются 10.09.2026 ───────────────────────────

# 1. git не в PATH — обещан код 2, а был трейсбек. Питон зовём абсолютным путём:
#    с пустым PATH шелл не нашёл бы и его, и укус проверял бы не то.
PY_ABS="$(command -v python3)"
D="$(mk r1)"
out="$(cd "$D" && PATH=/nonexistent-bin "$PY_ABS" "$M" check 2>&1)"; rc=$?
if [ "$rc" = 2 ] && printf '%s' "$out" | grep -q "git" \
    && ! printf '%s' "$out" | grep -q "Traceback"; then
  echo "  ✅ без git в PATH — код 2 с диагнозом, а не трейсбек"; pass=$((pass+1))
else
  echo "  ❌ без git в PATH: rc=$rc (ждали 2), трейсбек=$(printf '%s' "$out" | grep -c Traceback)"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 2. list не врёт «конфига нет», когда конфиг ЕСТЬ, а нечитаем внешний вход.
#    Широкий except SystemExit глотал die про внешний вход и печатал ложный диагноз.
D="$(mk r2)"
printf '{"gate_pure": ["python3 gate.py"], "gate_version_external": ["no-such-input.txt"]}\n' > "$D/deploy.json"
git -C "$D" add -A; git -C "$D" commit -qm ext
out="$(cd "$D" && python3 "$M" list 2>&1)"
# Обе половины. Одного «не содержит „конфига нет“» мало: на пустой заглушке это
# истинно даром — она вообще ничего не печатает. Замер 10.09.2026: без
# положительной половины укус был зелёным на заглушке, то есть не проверял ничего.
if printf '%s' "$out" | grep -q "внешний вход" \
    && ! printf '%s' "$out" | grep -q "конфига нет"; then
  echo "  ✅ нечитаемый внешний вход назван собой, а не отсутствием конфига"; pass=$((pass+1))
else
  echo "  ❌ list не назвал нечитаемый внешний вход (или соврал «конфига нет»)"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 3. Упавшая запись не оставляет осиротевший .tmp-<pid>. Ломаем os.replace,
#    подставив на место файла вердикта КАТАЛОГ.
D="$(mk r3)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
rid="$(cd "$D" && python3 "$M" list | sed -n 's/^репозиторий: \([^ ]*\).*/\1/p')"
vd="$MEMO_HOME/gate-verdicts/$rid"
vf="$(ls "$vd"/*.json 2>/dev/null | head -1)"
rm -f "$vf"; mkdir -p "$vf"
out="$(cd "$D" && python3 "$M" check 2>&1)"; rc=$?
orph="$(ls "$vd" 2>/dev/null | grep -c 'tmp-' || true)"
if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q "НЕ записан" && [ "$orph" = 0 ]; then
  echo "  ✅ упавшая запись не оставляет осиротевший .tmp"; pass=$((pass+1))
else
  echo "  ❌ осиротевший .tmp: rc=$rc (ждали 0), .tmp-файлов=$orph (ждали 0)"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 4. check — точка, где принимается решение, — обязан называть интерпретатор,
#    под которым вердикт снят. Решение Р5 обещало отпечаток только в list.
D="$(mk r4)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
out="$(cd "$D" && python3 "$M" check 2>&1)"; rc=$?
if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q "python"; then
  echo "  ✅ попадание в кэш называет интерпретатор вердикта"; pass=$((pass+1))
else
  echo "  ❌ check на кэше молчит про интерпретатор: rc=$rc"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 5. duration_s писался и не читался никем. Читает list.
D="$(mk r5)"
(cd "$D" && python3 "$M" check >/dev/null 2>&1)
out="$(cd "$D" && python3 "$M" list 2>&1)"
if printf '%s' "$out" | grep -q "длит"; then
  echo "  ✅ list показывает длительность прогона — duration_s больше не мёртв"; pass=$((pass+1))
else
  echo "  ❌ list не показывает длительность: поле duration_s пишется и не читается"
  echo "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

echo
echo "итог: ✅ $pass   ❌ $fail"
[ "$fail" = 0 ]
