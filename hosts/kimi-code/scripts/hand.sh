#!/usr/bin/env bash
# Расщепление сессии Kimi Code CLI: открыть свежую в нужном каталоге, накормив
# её хендоффом.
#
# Версия hand.sh для kimi-cli (канон — derflow/_capture.md в ~/.claude,
# родственные версии: ~/.claude/scripts/hand.sh для Claude Code,
# ~/.zcode/scripts/hand.sh для ZCode). Преемник — новый таб Ghostty с
# интерактивным kimi; стартовое состояние доставляет СЕЯЛКА:
#
#   kimi -p "<имя> — прочитай <хендофф> … подтверди"   # одноходовой прогон,
#                                                      # создаёт сессию каталога
#   exec kimi -c                                       # интерактив продолжает
#                                                      # именно её
#
# У kimi нет флага «интерактив со стартовым промптом» (замер 09.11.2026,
# kimi 2.5.2 --help): -p неинтерактивен, поэтому сеялка только ЧИТАЕТ хендофф
# и подтверждает, а работает уже интерактивная сессия-продолжение.
#
#   hand.sh                      # хендофф ищется в текущем каталоге
#   hand.sh <каталог>            # ищется там
#   hand.sh <каталог> <файл>     # явный путь — ОБЯЗАТЕЛЕН там, где все сессии
#                                # сидят на одной ветке: ключ по ветке там общий
#   hand.sh -n ...               # только показать команду, не открывать таб
#
# Хендофф обязан нести шапкой две строки: «ветка:» и «имя:». Первая — КЛЮЧ, по
# ней файл и находится; вторая становится заголовком таба. Конвенция —
# derflow/_capture.md. Имя ФАЙЛА ключом не является: зови файл по-человечески,
# ключ пиши в шапку.
#
# Коды отказа: 1 нет файла · 2 несвежий · 3 чужая ветка · 4 форма имени ·
#              5 автоподбор без «ветка:» · 6 несколько хендоффов на ветку ·
#              7 нет бинаря kimi.
#
# Каталог тот же — НЕ повод не звать: короткое окно двух сессий на одном дереве
# законно, пока старый таб его больше не трогает. `/clear` — только если человек
# прямо попросил «тем же табом»; сам его не предлагай.
#
# Режим родителя (yolo и т.п.) пока НЕ наследуется: у kimi нет живого чтения
# режима чужой сессии, а флагом режим сеем только жёсткий --auto. Не seем.
set -euo pipefail

# Ветка из шапки хендоффа — ПЕРВЫМ полем, а не всей строкой: хвост в строке
# ничему не мешает, а несовпадение стоит подсунутого чужого состояния.
declared_branch() {
  grep -m1 -E '^ветка:' "$1" 2>/dev/null \
    | sed 's/^ветка:[[:space:]]*//' | awk '{print $1}' || true
}

dry=0
[ "${1:-}" = "-n" ] && { dry=1; shift; }

dir="${1:-$PWD}"
[ -d "$dir" ] || { echo "нет каталога: $dir" >&2; exit 1; }
dir="$(cd "$dir" && pwd)"

auto=0
if [ "${2:-}" ]; then
  # Второй аргумент ОБЯЗАН относиться к первому: промпт строится путём от
  # каталога, и хендофф снаружи в нём не разрешится.
  case "$2" in
    /*) hand="$2" ;;
    *)  hand="$dir/$2" ;;
  esac
  [ -f "$hand" ] || { echo "нет файла хендоффа: $hand" >&2; exit 1; }
  hand="$(cd "$(dirname "$hand")" && pwd)/$(basename "$hand")"
  case "$hand" in
    "$dir"/*) : ;;
    *) echo "❌ ХЕНДОФФ ВНЕ КАТАЛОГА: $hand" >&2
       echo "   не внутри $dir — промпт с путём не разрешится." >&2
       exit 1 ;;
  esac
else
  auto=1
  # Путь ключуется ЗАДАЧЕЙ, а не репозиторием. Порядок от уникального к общему.
  hand=""
  br="$(cd "$dir" && git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  # 1. заявка openspec — кандидат обязан сам объявить текущую ветку; объявили
  #    НЕСКОЛЬКО — отказ со списком.
  nopen=0
  if [ -z "$hand" ] && [ -n "$br" ]; then
    matches=""; nmatch=0
    while IFS= read -r c; do
      [ -f "$c" ] || continue
      nopen=$((nopen + 1))
      [ "$(declared_branch "$c")" = "$br" ] || continue
      nmatch=$((nmatch + 1)); matches="${matches}${c}
"
    done < <(find "$dir/openspec/changes" -maxdepth 2 -name HANDOFF.md 2>/dev/null | sort)
    if [ "$nmatch" -gt 1 ]; then
      echo "❌ ХЕНДОФФОВ НА ВЕТКУ «${br}» НЕСКОЛЬКО — который твой, скрипт не знает:" >&2
      printf '%s' "$matches" | sed 's|^'"$dir"'/|   |' >&2
      echo "   передай нужный вторым аргументом: hand.sh <каталог> <файл>" >&2
      exit 6
    fi
    [ "$nmatch" -eq 1 ] && hand="$(printf '%s' "$matches" | head -1)"
    if [ -z "$hand" ] && [ "$nopen" -gt 0 ]; then
      echo "ℹ️  заявочных HANDOFF.md: $nopen, ни один не объявил ветку «${br}» — ищу дальше" >&2
    fi
  fi
  # 2. по ветке, ОБЪЯВЛЕННОЙ ВНУТРИ файла, — а не по его имени.
  if [ -z "$hand" ] && [ -n "$br" ]; then
    matches=""; nmatch=0
    for c in "$dir"/.claude/handoff/*.md "$dir"/handoff/*.md; do
      [ -f "$c" ] || continue
      [ "$(declared_branch "$c")" = "$br" ] || continue
      nmatch=$((nmatch + 1)); matches="${matches}${c}
"
    done
    if [ "$nmatch" -gt 1 ]; then
      echo "❌ ХЕНДОФФОВ НА ВЕТКУ «${br}» НЕСКОЛЬКО — который твой, скрипт не знает:" >&2
      printf '%s' "$matches" | sed 's|^'"$dir"'/|   |' >&2
      echo "   передай нужный вторым аргументом: hand.sh <каталог> <файл>" >&2
      exit 6
    fi
    [ "$nmatch" -eq 1 ] && hand="$(printf '%s' "$matches" | head -1)"
  fi
  # 3. корень — совместимость со старой конвенцией, столкновению открыт
  if [ -z "$hand" ]; then
    for c in "$dir/HANDOFF.md" "$dir/ПРОДОЛЖИТЬ.md"; do
      [ -f "$c" ] && { hand="$c"
        echo "⚠️  хендофф лежит в корне — общее имя на весь репозиторий." >&2
        echo "    две сессии в одном дереве затрут его друг другу; перенеси в" >&2
        echo "    .claude/handoff/<человеческий-слаг>.md либо к артефактам заявки." >&2
        echo "    имя файла любое — ключ живёт в строке «ветка:» внутри него." >&2
        break; }
    done
  fi
fi

if [ -z "$hand" ] || [ ! -f "$hand" ]; then
  echo "хендоффа не найдено в $dir" >&2
  echo "создай HANDOFF.md — без него расщеплять нечем: состояние передаётся файлом" >&2
  exit 1
fi
hand="$(cd "$(dirname "$hand")" && pwd)/$(basename "$hand")"

# Кириллица в имени файла — предупреждение, не отказ: git печатает не-ASCII имя
# в кавычках, и `[ -f ]` на нём ложна. `backlog/` исключён (docflow: имя даёт
# Backlog.md).
case "$hand" in
  "$dir"/backlog/*) latin_check=0 ;;
  *)                latin_check=1 ;;
esac
if [ "$latin_check" = 1 ] \
   && printf '%s' "$(basename "$hand")" | LC_ALL=C grep -q '[^ -~]'; then
  echo "⚠️  имя файла хендоффа не в латинице: $(basename "$hand")" >&2
  echo "    ключ живёт в строке «ветка:», имя файла свободно —" >&2
  echo "    зови латинским слагом задачи: inbox-push-trace.md" >&2
fi

# Чужой хендофф опаснее отсутствующего: проверяем принадлежность ДО свежести.
declared="$(declared_branch "$hand")"
cur="$(cd "$dir" && git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -n "$declared" ] && [ -n "$cur" ] && [ "$declared" != "$cur" ]; then
  echo "❌ ХЕНДОФФ ОТ ДРУГОЙ ЗАДАЧИ: в нём объявлена ветка «${declared}», текущая «${cur}»." >&2
  echo "   Это чужое состояние — продолжать по нему нельзя." >&2
  exit 3
fi
if [ -z "$declared" ]; then
  if [ "$auto" = 1 ]; then
    echo "❌ ПОДОБРАННЫЙ ХЕНДОФФ НЕ ОБЪЯВЛЯЕТ ВЕТКУ — принадлежность недоказуема:" >&2
    echo "   $hand" >&2
    echo "   допиши первой строкой «ветка: ${cur:-<ветка>}» либо передай файл" >&2
    echo "   вторым аргументом: hand.sh <каталог> <файл>" >&2
    exit 5
  fi
  echo "⚠️  в хендоффе нет строки «ветка:» — принадлежность не проверяется" >&2
fi

# Несвежий хендофф хуже отсутствующего. `-uall` и `core.quotePath=false`
# обязательны — без них git схлопывает каталоги и печатает не-ASCII имена в
# кавычках.
newest="$(cd "$dir" && git -c core.quotePath=false status --porcelain -uall 2>/dev/null \
          | cut -c4- \
          | while IFS= read -r f; do [ -f "$f" ] && stat -f '%m' "$f"; done \
          | sort -rn | head -1 || true)"
if [ -n "$newest" ] && [ "$newest" -gt "$(stat -f '%m' "$hand")" ]; then
  echo "⚠️  ХЕНДОФФ СТАРШЕ ПОСЛЕДНИХ ПРАВОК — обнови его до расщепления," >&2
  echo "    иначе свежая сессия начнёт с устаревшего состояния." >&2
  echo "    $hand" >&2
  exit 2
fi

# Имя сессии — из «имя:» хендоффа; им же зовём таб.
sess="$(grep -m1 -E '^имя:' "$hand" 2>/dev/null | sed 's/^имя:[[:space:]]*//' || true)"
if [ -z "$sess" ]; then
  sess="?·${cur:-$(basename "$hand" .md)}"
  echo "⚠️  в хендоффе нет строки «имя:» — таб будет назван «${sess}»" >&2
  echo "    канон: имя: <буква проекта>·<задача>, см. derflow/_capture.md" >&2
elif ! printf '%s' "$sess" | grep -qE '^[[:alpha:]]·.+$'; then
  echo "❌ ИМЯ НЕ В КАНОННОЙ ФОРМЕ: «${sess}»" >&2
  echo "   канон: имя: <буква проекта>·<задача> — одна буква, разделитель «·»." >&2
  echo "   карта букв — derflow/_capture.md" >&2
  echo "   поправь строку «имя:» и позови снова: $hand" >&2
  exit 4
fi

# Омоглиф: кириллическая буква, чей латинский двойник НЕОТЛИЧИМ в табе.
case "$sess" in
  А·*|а·*) twin=A ;;  В·*|в·*) twin=B ;;  Е·*|е·*) twin=E ;;
  К·*|к·*) twin=K ;;  М·*|м·*) twin=M ;;  Н·*|н·*) twin=H ;;
  О·*|о·*) twin=O ;;  Р·*|р·*) twin=P ;;  С·*|с·*) twin=C ;;
  Т·*|т·*) twin=T ;;  У·*|у·*) twin=Y ;;  Х·*|х·*) twin=X ;;
  *) twin="" ;;
esac
if [ -n "$twin" ]; then
  echo "❌ ОМОГЛИФ В ИМЕНИ: «${sess}»" >&2
  echo "   первая буква кириллическая, а в табе она неотличима от латинской" >&2
  echo "   «${twin}» — и та уже может принадлежать другому проекту." >&2
  echo "   поставь латинскую букву из карты (derflow/_capture.md) и позови" >&2
  echo "   снова: $hand" >&2
  exit 4
fi

kimi_bin="$HOME/.kimi-code/bin/kimi"
[ -x "$kimi_bin" ] || { echo "❌ нет бинаря kimi: $kimi_bin" >&2
  echo "   ставится: curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash" >&2
  exit 7; }

# Сеялка ЧИТАЕТ хендофф и подтверждает — не работает: у -p один ход, и
# разрешения в нём спросить не у кого. Интерактив (kimi -c) продолжает именно
# эту сессию. Путь хендоффа — АБСОЛЮТНЫЙ: надёжен при любом cwd преемника.
seed="${sess} — прочитай ${hand}: там всё состояние и порядок шагов. Ничего не меняй: подтверди одной строкой, что состояние восстановлено."

echo "каталог: $dir"
echo "хендофф: ${hand#$dir/}"
echo "имя:     $sess"
echo "сеялка:  $seed"

# Ни ${var@Q} (нет в bash 3.2), ни printf %q (разносит UTF-8 по байтам, а промпт
# русский). Оборачиваем в одинарные кавычки, экранируя только их сами.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
q_dir="$(sq "$dir")"
q_sess="$(sq "$sess")"
q_seed="$(sq "$seed")"
q_kimi="$(sq "$kimi_bin")"

# PATH у порождённого таба ГОЛЫЙ: лончер запускается как #!/bin/zsh — не login
# и не интерактивный, профили не читаются. Отдаём ребёнку PATH РОДИТЕЛЯ.
q_path="$(sq "$PATH")"

launch_dir="${TMPDIR:-/tmp}/derflow-hand"
mkdir -p "$launch_dir"
# Launcher не удаляет сам себя — гонка. Метём по возрасту при следующем запуске.
find "$launch_dir" -name 'hand-*.sh' -type f -mtime +1 -delete 2>/dev/null || true
launcher="$launch_dir/hand-$$.sh"

cat > "$launcher" <<LAUNCHER
#!/bin/zsh
export PATH=$q_path
cd $q_dir || exit 1
# Заголовок таба — наш OSC 0 с задержкой: чем пишет kimi TUI заголовок,
# не полагаемся (замер отсутствует), паузу перекрываем сами.
( sleep 2; printf '\\033]0;%s\\007' $q_sess > /dev/tty 2>/dev/null ) &
if ! [ -x $q_kimi ]; then
  echo "❌ kimi не найден — сессия не стартует"
  echo "искали: $q_kimi"
  exec zsh -i          # держим таб открытым, иначе ошибка мигнёт и исчезнет
fi
$q_kimi -p $q_seed || echo "⚠️  сеялка не отработала — откроется пустая интерактивная сессия"
exec $q_kimi -c
LAUNCHER
chmod +x "$launcher"

if [ "$dry" = 1 ]; then
  echo "launcher: $launcher"
  sed 's/^/    /' "$launcher"
  echo "доставка: new tab в окне родителя; последний рубеж — open -a Ghostty.app"
  rm -f "$launcher"
  exit 0
fi

# Родитель опознаётся СВОИМ ТАБОМ, а не именем: hand.sh запущен ИЗ него, значит
# у процесса сессии есть tty, и запись OSC-заголовка в /dev/ttysNNN метит ровно
# тот таб. (У kimi-cli-сессии, запущенной из Ghostty, tty в предках есть.)
parent_tty=""
_pid="${CLAUDE_PID:-$$}"
for _ in 1 2 3 4 5 6 7 8; do
  case "$_pid" in ''|0|1) break ;; esac
  _t="$(ps -o tty= -p "$_pid" 2>/dev/null | tr -d ' ')"
  case "$_t" in
    ''|'??') _pid="$(ps -o ppid= -p "$_pid" 2>/dev/null | tr -d ' ')" ;;
    *) parent_tty="/dev/$_t"; break ;;
  esac
done

gh_snapshot() {
  osascript 2>/dev/null <<'AS' || true
tell application "Ghostty"
  set out to ""
  repeat with w in windows
    repeat with t in tabs of w
      set out to out & "ID:" & (id of t) & linefeed & "NM:" & (name of t) & linefeed
    end repeat
  end repeat
  return out
end tell
AS
}

# Метка временная: снимок заголовков → пометка → выбор → возврат заголовка.
picked=0
parent_win=""
if [ -n "$parent_tty" ] && [ -w "$parent_tty" ]; then
  snap="$(gh_snapshot)"
  [ -n "$snap" ] || echo "⚠️  Ghostty не отвечает по AppleScript — метку не ставлю" >&2
fi
if [ -n "$parent_tty" ] && [ -w "$parent_tty" ] && [ -n "${snap:-}" ]; then
  mark="derflow-parent-$$-${RANDOM}"
  mid=""
  for _ in 1 2 3 4 5; do
    printf '\033]0;%s\007' "$mark" > "$parent_tty" 2>/dev/null || true
    sleep 0.12
    mid="$(osascript 2>/dev/null <<AS || true
tell application "Ghostty"
  repeat with w in windows
    repeat with t in tabs of w
      if (name of t) contains "$mark" then
        select tab t
        return ((id of w) & "|" & (id of t)) as text
      end if
    end repeat
  end repeat
  return ""
end tell
AS
)"
    [ -n "$mid" ] && break
  done
  case "$mid" in *'|'*) parent_win="${mid%%|*}"; mid="${mid##*|}" ;; esac
  if [ -n "$mid" ]; then
    old="$(printf '%s\n' "$snap" | awk -v id="$mid" \
      '/^ID:/{cur=substr($0,4)} /^NM:/{if(cur==id){print substr($0,4); exit}}')"
    if [ -n "$old" ]; then
      printf '\033]0;%s\007' "$old" > "$parent_tty" 2>/dev/null || true
    else
      echo "⚠️  заголовок родителя не восстановить — снимок его не знал;" >&2
      echo "    TUI перерисует экран сам, заголовок поставит наш лончер." >&2
    fi
    picked=1
    echo "родительский таб опознан по tty ($parent_tty), окно $parent_win"
  fi
fi

# Фолбэк — опознание по имени (верно в цепочке «та же задача дальше»).
if [ "$picked" = 0 ]; then
  as_sess="$(printf '%s' "$sess" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
  hits="$(osascript 2>/dev/null <<AS || true
tell application "Ghostty"
  set foundT to {}
  set foundW to {}
  repeat with w in windows
    repeat with t in tabs of w
      if (name of t) contains "$as_sess" then
        set end of foundT to t
        set end of foundW to w
      end if
    end repeat
  end repeat
  if (count of foundT) is 1 then
    select tab (item 1 of foundT)
    return "1|" & (id of (item 1 of foundW))
  end if
  return (count of foundT) as text
end tell
AS
)"
  case "$hits" in *'|'*) parent_win="${hits##*|}"; hits="${hits%%|*}" ;; esac
  case "$hits" in
    1) echo "родительский таб «${sess}» опознан по имени, окно $parent_win" ;;
    ""|0) echo "⚠️  родителя не опознать: tty нет и таба «${sess}» нет —" >&2
          echo "    новый встанет по умолчанию, не рядом" >&2 ;;
    *) echo "⚠️  табов с именем «${sess}»: ${hits} — родитель неоднозначен," >&2
       echo "    новый встанет по умолчанию: угадывать хуже, чем не двигать фокус." >&2 ;;
  esac
fi

# Доставка НАЗЫВАЕТ окно, а не надеется на переднее.
asq() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
as_launcher="$(asq "$launcher")"
as_dir="$(asq "$dir")"

deliver() {
  osascript 2>/dev/null <<AS || true
tell application "Ghostty"
  set target to missing value
  if "$1" is "" then
    set target to front window
  else
    repeat with w in windows
      if (id of w) is "$1" then set target to w
    end repeat
  end if
  if target is missing value then return ""
  set cfg to new surface configuration
  set command of cfg to "$as_launcher"
  set initial working directory of cfg to "$as_dir"
  set wait after command of cfg to true
  set nt to new tab in target with configuration cfg
  activate window target
  select tab nt
  return (id of nt) as text
end tell
AS
}

opened="$(deliver "$parent_win")"
if [ -n "$opened" ] && [ -n "$parent_win" ]; then
  echo "таб открыт рядом с родителем: окно $parent_win, таб $opened"
elif [ -n "$opened" ]; then
  echo "⚠️  родитель не опознан — таб открыт в ПЕРЕДНЕМ окне ($opened)," >&2
  echo "    рядом с родителем он не гарантирован." >&2
else
  open -a Ghostty.app "$launcher"
  echo "⚠️  прямая доставка не отработала — отдал файл через LaunchServices." >&2
  echo "    Исход не проверяем: сессия может приехать с задержкой и новым окном." >&2
  echo "    Не увидел её рядом — считай расщепление несостоявшимся и зови снова." >&2
fi
