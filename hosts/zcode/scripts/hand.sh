#!/usr/bin/env bash
# Расщепление сессии ZCode: открыть свежую в нужном каталоге, накормив её хендоффом.
#
# Это версия hand.sh для ZCode (канон — derflow/_capture.md в ~/.claude, родственная
# версия для Claude Code живёт в ~/.claude/scripts/hand.sh и не зависит от этой).
# Преемник — тот же клиент, что и родитель (v4.41: имя таба едет через
# ZCODE_TUI_SESSION_TITLE, режим — fallback на глобально свежую сессию для
# новых ворктри; v4.40: режим родителя — живая
# проектная настройка local_setting, fallback режим рождения, было наоборот;
# v4.38: гейт патча код 8, гейт singleton-замка код 9): сессия в терминале (ztui) имеет
# tty в предках → новый TUI-таб в Ghostty; сессия в десктоп-приложении tty не имеет
# → вкладка ТОГО ЖЕ десктопа: бинарь запускается вторично с --open-workspace
# --open-workspace-prompt (патч в клоне, docs/desktop-split-workspace-prompt.md),
# single-instance переправляет argv работающему окну. Транспорт TUI:
#
#   * промпт-константа едет через ZCODE_TUI_PROMPT (патч в клоне: tui-command.ts
#     читает и передаёт в TUI, тот сабмитит как первый ввод человека; после чтения
#     переменная из env УДАЛЯЕТСЯ — дочерним процессам сессии она не достаётся);
#   * заголовок таба ставим САМИ: TUI НИКОГДА не пишет OSC-заголовок, кроме одного
#     ПУСТОГО в момент инициализации рендера (замер 01.10.2026) — поэтому имя
#     пишется с задержкой после старта, когда пустая запись уже прошла;
#   * аутентификация — общий с приложением ~/.zcode/v2/credentials.json: сеялки
#     в клоне (seed-account-identity.mjs, seed-default-model.mjs) досеяли то, что
#     хост-приложение не пишет, а standalone-CLI ищет.
#
#   hand.sh                      # хендофф ищется в текущем каталоге
#   hand.sh <каталог>            # ищется там
#   hand.sh <каталог> <файл>     # явный путь — ОБЯЗАТЕЛЕН там, где все сессии
#                                # сидят на одной ветке: ключ по ветке там общий
#   hand.sh -n ...               # только показать команду, не открывать таб
#
# Хендофф обязан нести шапкой две строки: «ветка:» и «имя:». Первая — КЛЮЧ, по
# ней файл и находится; вторая становится заголовком таба. Конвенция —
# derflow/_capture.md.
#
# 🔴 Имя ФАЙЛА ключом не является и быть им не должно: пока ключевало имя, файл
# приходилось звать слагом ветки, и человеческое имя рождало второй файл под
# машинным. Зови файл по-человечески, ключ пиши в шапку.
#
# Коды отказа: 1 нет файла · 2 несвежий · 3 чужая ветка · 4 форма имени ·
#              5 автоподбор без «ветка:» · 6 несколько хендоффов на ветку ·
#              7 нет десктоп-бинаря (цель desktop) ·
#              8 десктоп-бинарь без патча --open-workspace-prompt ·
#              9 singleton-замок от другого хостнейма (цель desktop) ·
#              10 десктоп-промпт не ASCII (цель desktop).
#
# Каталог тот же — НЕ повод не звать (v4.16): короткое окно двух сессий на одном
# дереве законно, пока старый таб его больше не трогает. `/clear` — только если
# человек прямо попросил «тем же табом»; сам его не предлагай.
set -euo pipefail

# Ветка из шапки хендоффа — ПЕРВЫМ полем, а не всей строкой. Сверка полной
# строкой ломалась о любой хвост: боевое 06.09.2026 — «ветка: feature/X (ворктри
# …)» не совпало с «feature/X», шаг 1 промахнулся, и подбор свалился в корень.
# Быть строгим тут нечем: хвост в строке ничему не мешает, а несовпадение стоит
# подсунутого чужого состояния.
declared_branch() {
  grep -m1 -E '^ветка:' "$1" 2>/dev/null \
    | sed 's/^ветка:[[:space:]]*//' | awk '{print $1}' || true
}

dry=0
[ "${1:-}" = "-n" ] && { dry=1; shift; }

dir="${1:-$PWD}"
[ -d "$dir" ] || { echo "нет каталога: $dir" >&2; exit 1; }
dir="$(cd "$dir" && pwd)"

# Цель расщепления — КАКОЙ КЛИЕНТ преемник. Среда родителя решает автоматически
# (см. шапку); HAND_CLIENT принудительно выбирает цель руками: zcode|desktop|opencode.
# Пустое значение резолвится ПОСЛЕ определения среды родителя (ниже, за промптом).
target="${HAND_CLIENT:-}"
case "$target" in
  zcode|desktop|opencode) ;;
  *) target="" ;;
esac

auto=0
if [ "${2:-}" ]; then
  # Второй аргумент ОБЯЗАН относиться к первому: промпт строится путём от каталога,
  # и хендофф снаружи в нём не разрешится. Относительный путь считаем от каталога,
  # а не от cwd, — иначе он зависит от того, откуда позвали.
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
  # Путь ключуется ЗАДАЧЕЙ, а не репозиторием. Общее имя в корне — общий
  # изменяемый ресурс: две сессии в одном дереве затрут хендоффы друг друга, и
  # преемник уверенно продолжит чужую работу. Порядок от уникального к общему.
  hand=""
  br="$(cd "$dir" && git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  # 1. заявка openspec — уникальна по задаче, НО заявок в дереве много, и
  #    сестринские сессии держат свои. Кандидат обязан сам объявить текущую ветку;
  #    не объявил никто — молча падаем на пункт 2. Объявили НЕСКОЛЬКО — отказ со
  #    списком: побеждала бы произвольная чужая (боевое 07.09.2026, sms-gate).
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
  # 2. по ветке, ОБЪЯВЛЕННОЙ ВНУТРИ файла, — а не по его имени (боевое 06.09.2026:
  #    ключ именем заставлял звать файл слагом ветки и порождал второй файл).
  if [ -z "$hand" ] && [ -n "$br" ]; then
    matches=""; nmatch=0
    for c in "$dir"/.claude/handoff/*.md "$dir"/handoff/*.md; do
      [ -f "$c" ] || continue
      [ "$(declared_branch "$c")" = "$br" ] || continue
      nmatch=$((nmatch + 1)); matches="${matches}${c}
"
    done
    # Несколько хендоффов на одну ветку — ствол либо забытый файл: отказ со
    # списком, а не «взял первый».
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

# Имя файла не ключ (см. шапку), но и не свободно: кириллица в нём уже стоила
# молча инертного гейта свежести — git печатает не-ASCII имя как «"\320\277..."»,
# с кавычками, и `[ -f ]` на нём ложна. Дырку держит core.quotePath=false, однако
# полагаться на один флаг там, где имя выбирает человек, незачем. Предупреждение,
# не отказ. `backlog/` исключён (docflow: имя даёт Backlog.md).
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

# Чужой хендофф опаснее отсутствующего: он выглядит валидным. Проверяем
# принадлежность ДО свежести — мерить свежесть чужого файла бессмысленно.
declared="$(declared_branch "$hand")"
cur="$(cd "$dir" && git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -n "$declared" ] && [ -n "$cur" ] && [ "$declared" != "$cur" ]; then
  echo "❌ ХЕНДОФФ ОТ ДРУГОЙ ЗАДАЧИ: в нём объявлена ветка «${declared}», текущая «${cur}»." >&2
  echo "   Это чужое состояние — продолжать по нему нельзя." >&2
  exit 3
fi
# Подобранный САМ файл без строки «ветка:» — единственная дырка для чужого
# состояния: отказ, названный руками — предупреждение (выбор сделал человек).
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

# Несвежий хендофф хуже отсутствующего: следующая сессия поверит устаревшему
# тексту и переделает сделанное. Сравниваем с самым новым изменением в дереве.
# `-uall` и `core.quotePath=false` обязательны — без них git схлопывает каталоги
# и печатает не-ASCII имена в кавычках, `[ -f ]` на них ложна (замеры 05–06.09).
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

# Имя сессии. ZCode TUI заголовок терминала НЕ трогает (после инициализации), так
# что заголовок таба — целиком наш OSC 0, и имя обязано приехать из хендоффа.
sess="$(grep -m1 -E '^имя:' "$hand" 2>/dev/null | sed 's/^имя:[[:space:]]*//' || true)"
if [ -z "$sess" ]; then
  # Фолбэк нарочно тупой и заметно хуже канонического: «?» проектом притвориться
  # не может ни при каком каталоге (боевое 12.09.2026 — буква от каталога
  # выглядела штатной и крала чужой таб).
  sess="?·${br:-$(basename "$hand" .md)}"
  echo "⚠️  в хендоффе нет строки «имя:» — таб будет назван «${sess}»" >&2
  echo "    канон: имя: <буква проекта>·<задача>, см. derflow/_capture.md" >&2
# Гейт ФОРМЫ имени — отказ, не предупреждение: stderr проезжал мимо глаз (боевое
# 05.09.2026). Проверяем форму, но не букву: карта проектов живёт в каноне, копия
# здесь была бы вторым источником правды.
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

# Имя стоит В ПРОМПТЕ и заголовком ТАБА. Промпт — КОНСТАНТА, одинаковая у всех
# расщеплений. Путь хендоффа — АБСОЛЮТНЫЙ: он надёжен при любом рабочем каталоге
# преемника. В ZCode сессия сама называет себя по первому промпту — имя в нём
# продолжает работать и там.
prompt="${sess} — прочитай ${hand}: там всё состояние и порядок шагов. Продолжай."

echo "каталог: $dir"
echo "хендофф: ${hand#$dir/}"
echo "имя:     $sess"
echo "промпт:  $prompt"

# Режим родителя → преемнику. Родитель ВЫЗЫВАЕТ этот скрипт из своего хода, его
# строка в базе — самая свежая интерактивная сессия каталога (части пишутся в
# момент вызова инструмента). Окно 120с: строка старше — родителя в этом
# каталоге нет, молча дефолт, а не чужой режим.
#
# 🔴 Два хранилища режима (замер 30.10.2026, pyright-burn): session.permission
# хранит режим РОЖДЕНИЯ сессии и переключением НЕ обновляется; /mode и
# Shift+Tab пишут живой режим в проектную настройку local_setting
# (namespace=permission, key=mode) — bootstrap/src/app/session-facade.ts:604
# пишет в строку сессии только при scope="session" (группы), обычный ztui —
# в проект. Поэтому читаем СНАЧАЛА проектную настройку (живой режим),
# fallback — режим рождения из строки сессии. Без этого расщепление из
# переключённого в yolo родителя уезжало с родильным build, а флаг --mode
# глушит проектную настройку у преемника (create-app.ts:302) — и новый таб
# тонул в подтверждениях. Проектная настройка — последний переключённый режим
# каталога: при двух сессиях в разных режимах может дать сиблинговый (известная
# слабость, самокорректируется переключением родителя).
parent_mode=""
mode_src=""
zdb="$HOME/.zcode/cli/db/db.sqlite"
if [ -f "$zdb" ] && command -v sqlite3 >/dev/null 2>&1; then
  q_dir_sql="$(printf '%s' "$dir" | sed "s/'/''/g")"
  mrow="$(sqlite3 -noheader -separator '|' "$zdb" \
    "SELECT json_extract(permission,'\$.mode'), substr(title,1,60), project_id
       FROM session
      WHERE directory='$q_dir_sql' AND task_type='interactive'
        AND permission IS NOT NULL
        AND time_updated > (CAST(strftime('%s','now') AS integer)-120)*1000
      ORDER BY time_updated DESC LIMIT 1" 2>/dev/null || true)"
  # Сплит в НОВЫЙ ворктри: в целевом каталоге сессий ещё нет, а родитель
  # работает в другом (gmb_v2-корень и т.п.). hand.sh исполняется ИЗ хода
  # родителя — его строка пишется прямо сейчас, значит самая свежая
  # интерактивная сессия базы за те же 120с и есть родитель (замер 02.11:
  # constructor-settings-live и ещё три ворктри уезжали в build молча).
  if [ -z "$mrow" ]; then
    mrow="$(sqlite3 -noheader -separator '|' "$zdb" \
      "SELECT json_extract(permission,'\$.mode'), substr(title,1,60), project_id
         FROM session
        WHERE task_type='interactive'
          AND permission IS NOT NULL
          AND time_updated > (CAST(strftime('%s','now') AS integer)-120)*1000
        ORDER BY time_updated DESC LIMIT 1" 2>/dev/null || true)"
  fi
  mmode="${mrow%%|*}"
  mrest="${mrow#*|}"
  mtitle="${mrest%%|*}"
  mproj="${mrest#*|}"
  # Живой режим: проектная настройка по project_id свежей сессии-родителя.
  # Идентификатор приходят из нашей же базы, но пропускаем через белый список
  # символов — дешевле, чем верить формату на слово.
  case "$mproj" in
    ''|*[!A-Za-z0-9._-]*) : ;;
    *)
      pmode="$(sqlite3 -noheader "$zdb" \
        "SELECT json_extract(value,'\$.mode') FROM local_setting
          WHERE scope='project' AND scope_id='$mproj'
            AND namespace='permission' AND key='mode'" 2>/dev/null || true)"
      case "$pmode" in
        build|plan|edit|yolo|guarded)
          parent_mode="$pmode"; mode_src="живой, последнее переключение каталога" ;;
        *) : ;;
      esac ;;
  esac
  # Fallback: режим рождения родителя — единственная правда, если в каталоге
  # никто ни разу не переключал (например, цепочка рождена лончером с --mode).
  if [ -z "$parent_mode" ]; then
    case "$mmode" in
      build|plan|edit|yolo|guarded)
        parent_mode="$mmode"; mode_src="рождение сессии «${mtitle}»" ;;
      *) : ;;
    esac
  fi
fi
if [ -n "$parent_mode" ]; then
  echo "режим:   $parent_mode (${mode_src})"
else
  echo "режим:   по умолчанию (свежей сессии в каталоге не нашли)"
fi
# Флаг для лончера: значение отвалидировано белым списком выше, пусто — дефолт.
mode_arg=""
[ -n "$parent_mode" ] && mode_arg="--mode $parent_mode"

# Среда родителя: поднимаемся по дереву процессов до первого предка с tty.
# Терминальная сессия (ztui) tty имеет; сессия десктоп-приложения — нет: её
# процессы порождены Electron'ом без терминала. Это и решает преемника.
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

if [ -z "$target" ]; then
  if [ -n "$parent_tty" ]; then target=zcode
  else target=desktop
  fi
fi
echo "цель:    $target${HAND_CLIENT:+ (HAND_CLIENT)}"
# Ни ${var@Q} (нет в bash 3.2), ни printf %q (разносит UTF-8 по байтам, а промпт
# русский). Оборачиваем в одинарные кавычки, экранируя только их сами.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
q_dir="$(sq "$dir")"
q_prompt="$(sq "$prompt")"
q_sess="$(sq "$sess")"

# 🔴 PATH у порождённого таба ГОЛЫЙ (боевое 12.09.2026): лончер запускается как
# #!/bin/zsh — не login и не интерактивный, профили не читаются. Отдаём ребёнку
# PATH РОДИТЕЛЯ и зовём всё абсолютными путями.
q_path="$(sq "$PATH")"

# Десктоп-цель: ни Ghostty, ни node@24, ни собранный CLI не нужны — второй запуск
# бинаря приложения; работающий инстанс получает argv через second-instance.
if [ "$target" = "desktop" ]; then
  app_bin="${ZCODE_DESKTOP_BIN:-/Applications/ZCode.app/Contents/MacOS/ZCode}"
  [ -x "$app_bin" ] || { echo "❌ нет десктоп-бинаря: $app_bin" >&2
    echo "   ZCODE_DESKTOP_BIN переопределяет путь. Цель desktop требует сборки" >&2
    echo "   клона с --open-workspace-prompt (docs/desktop-split-workspace-prompt.md)." >&2
    exit 7; }
  # Гейт патча (v4.37, боевое 25.10.2026 на релизе 3.16.3): бинарь без флага
  # молча игнорирует и флаг, и промпт, а каталог расщепления уже открыт
  # родителем — рендерер просто активирует существующий таб. Вкладки и
  # сессии не будет, при этом старый скрипт уже напечатал бы «запрошена
  # вкладка», и сессия докладывала человеку, что всё работает. Проверяем
  # бандл ДО запуска и отказываем громко. grep -a по 341 МБ asar ~0.04 с.
  app_asar="${app_bin%/MacOS/*}/Resources/app.asar"
  if [ -f "$app_asar" ]; then
    if ! LC_ALL=C grep -aq 'open-workspace-prompt' "$app_asar"; then
      echo "❌ ДЕСКТОП-БИНАРЬ БЕЗ ПАТЧА --open-workspace-prompt: $app_bin" >&2
      echo "   Релиз промпт не доставит, а каталог уже открыт родителем —" >&2
      echo "   вкладки НЕ будет: приложение молча фокусирует существующий таб." >&2
      echo "   Собери десктоп из клона (beecc43b) и поставь его, либо открой" >&2
      echo "   преемника ztui-табом: HAND_CLIENT=zcode hand.sh <каталог> <файл>." >&2
      exit 8
    fi
  else
    echo "⚠️  у бинаря нет app.asar — поддержку флага не проверил: $app_bin" >&2
  fi
  # 🔴 Singleton-замок с ДРУГИМ хостнеймом = запуск НЕ переправит argv окну,
  # а ПЕРЕХВАТИТ singleton и перезапустит приложение под живыми сессиями
  # (боевое 27.10.2026: хостнейм дрейфнул .local→.lan со сменой сети;
  # hand.sh запустил бинарь, Electron счёл замок «DerMacBook.local-<pid>»
  # чужим, приложение перезапустилось на ходу — оборвало обе сессии, вкладки
  # и промпт не доставились, а перед пользователем позже открылось пустое
  # окно). Замок якорит хостнейм только на старте приложения: если держатель
  # жив, а хост не совпал — лечится перезапуском приложения, не запуском.
  lock_link="$HOME/Library/Application Support/ZCode/SingletonLock"
  if [ -L "$lock_link" ]; then
    lock_tgt="$(readlink "$lock_link" 2>/dev/null || true)"
    lock_host="$(printf '%s' "$lock_tgt" | sed -E 's/-[0-9]+$//')"
    lock_pid="$(printf '%s' "$lock_tgt" | sed -nE 's/.*-([0-9]+)$/\1/p')"
    lock_comm="$(ps -p "$lock_pid" -o comm= 2>/dev/null | tr -d ' ' || true)"
    if [ -n "$lock_host" ] && [ -n "$lock_pid" ] && [ "$lock_host" != "$(hostname)" ] \
       && printf '%s' "$lock_comm" | grep -q 'ZCode'; then
      echo "❌ SINGLETON-ЗАМОК ОТ ДРУГОГО ХОСТНЕЙМА: «${lock_host}» (pid ${lock_pid} жив)." >&2
      echo "   Хостнейм машины дрейфнул (сейчас «$(hostname)»), и запуск бинаря не" >&2
      echo "   переправит промпт окну, а молча ПЕРЕЗАПУСТИТ приложение — под живыми" >&2
      echo "   сессиями. Сначала перезапусти ZCode (Cmd+Q → открыть), потом зови" >&2
      echo "   расщепление снова." >&2
      exit 9
    fi
  fi
  # 🔴 Не-ASCII в argv УБИВАЕТ приложение (боевое 27.10 ×2 + изолированный
  # стенд): singleton-сообщение с кириллицей разбирается с ошибкой
  # "additional_data_size exceeds payload length" (форк Electron в
  # process_singleton_posix.cc), второй инстанс не получает ACK и по таймауту
  # SIGKILL'ит работающее приложение, забирая замок (Chromium kill_unresponsive).
  # Стенд 27.10: ASCII-промпт доставляется и маршрутизируется в вкладку,
  # кириллический — убивает получателя за 2 секунды. Десктоп-промпт строим
  # ASCII-only: имя таба — слаг файла хендоффа (имя файла обязано быть
  # латиницей), состояние преемник читает из хендоффа, а не из промпта.
  slug="$(printf '%s' "$(basename "$hand" .md)" | LC_ALL=C tr -cd 'A-Za-z0-9._-')"
  [ -n "$slug" ] || slug="handoff"
  dprompt="Successor session ${slug}: read the handoff at ${hand} and continue."
  if printf '%s' "$dprompt" | LC_ALL=C grep -q '[^ -~]'; then
    echo "❌ ДЕСКТОП-ПРОМПТ СОДЕРЖИТ НЕ-ASCII — такой запуск убил бы приложение." >&2
    echo "   Путь или имя хендоффа не в латинице: $hand" >&2
    echo "   Переименуй файл латинским слагом и позови снова." >&2
    exit 10
  fi
  if [ "$dry" = 1 ]; then
    echo "команда: $app_bin --open-workspace $dir --open-workspace-prompt <ASCII-промпт>"
    echo "промпт:  $dprompt"
    [ -n "$parent_mode" ] && [ "$parent_mode" != "build" ] && {
      echo "⚠️  десктоп-цель режим (${parent_mode}) пока НЕ наследует —" >&2
      echo "    бинарь не знает --mode; вкладка откроется в дефолте." >&2; }
    exit 0
  fi
  # Приложение закрыто — это холодный старт: промпт приедет по renderer-ready.
  # Сборка без патча отсечена гейтом выше (код 8) — сюда доходим только с флагом.
  # Промпт — dprompt (ASCII): кириллица в argv убивает получателя, см. блок выше.
  nohup "$app_bin" --open-workspace "$dir" --open-workspace-prompt "$dprompt" \
    >/dev/null 2>&1 &
  echo "десктоп: запрошена вкладка «${sess}» в $dir (окно приложения; ASCII-промпт «${slug}»)"
  [ -n "$parent_mode" ] && [ "$parent_mode" != "build" ] && {
    echo "⚠️  десктоп-цель режим (${parent_mode}) пока НЕ наследует —" >&2
    echo "    бинарь не знает --mode; вкладка откроется в дефолте." >&2; }
  exit 0
fi

# 🔴 Node обязан быть 24-й серии: FFI-бэкенд OpenTUI на Node 26 падает
# «usize until» (замер 01.10.2026). Путь абсолютный — brew-префикс стабилен.
node_bin="/opt/homebrew/opt/node@24/bin/node"
[ -x "$node_bin" ] || node_bin="$(command -v node 2>/dev/null || echo node)"
q_node="$(sq "$node_bin")"

# CLI — собранный бандл из клона опенсорса (ветка derflow-hand с патчем
# ZCODE_TUI_PROMPT). Путь абсолютный: таблица должна пережить любой cwd.
zcode_cli="$HOME/dev/ZCode/apps/zcode-cli/packages/cli/dist/zcode.cjs"
[ -f "$zcode_cli" ] || { echo "❌ нет собранного CLI: $zcode_cli" >&2
  echo "   собери: cd ~/dev/ZCode && apps/zcode-cli-окружение (см. README клона)" >&2
  exit 1; }
q_cli="$(sq "$zcode_cli")"

launch_dir="${TMPDIR:-/tmp}/derflow-hand"
mkdir -p "$launch_dir"
# Launcher не удаляет сам себя: удалять файл, который зачитывает исполняющая его
# оболочка, — гонка. Метём по возрасту при следующем запуске.
find "$launch_dir" -name 'hand-*.sh' -type f -mtime +1 -delete 2>/dev/null || true
launcher="$launch_dir/hand-$$.sh"

if [ "$target" = opencode ]; then
  # OpenCode: бинарник сам принимает промпт (--prompt) и каталог cwd'ом; TUI
  # пишет свой заголовок «OpenCode» на старте — наш OSC с задержкой перебивает
  # его, но фокус-событие таба может вернуть «OpenCode» (замер 03.10.2026).
  oc_bin="$(command -v opencode || echo /opt/homebrew/bin/opencode)"
  q_oc="$(sq "$oc_bin")"
  cat > "$launcher" <<LAUNCHER
#!/bin/zsh
export PATH=$q_path
cd $q_dir || exit 1
if ! [ -x $q_oc ]; then
  echo "❌ opencode не найден — сессия не стартует"
  echo "искали: $q_oc"
  exec zsh -i          # держим таб открытым, иначе ошибка мигнёт и исчезнет
fi
( sleep 2; printf '\\033]0;%s\\007' $q_sess > /dev/tty 2>/dev/null ) &
exec $q_oc --prompt $q_prompt
LAUNCHER
else
cat > "$launcher" <<LAUNCHER
#!/bin/zsh
export PATH=$q_path
cd $q_dir || exit 1
if ! [ -x $q_node ]; then
  echo "❌ node@24 не найден — сессия не стартует"
  echo "искали: $q_node"
  echo "ставится: brew install node@24"
  exec zsh -i          # держим таб открытым, иначе ошибка мигнёт и исчезнет
fi
# Заголовок таба: TUI пишет ОДИН ПУСТОЙ OSC 0 при инициализации рендера, потом не
# трогает — пишем своё имя с задержкой, когда пустая запись уже прошла.
( sleep 2; printf '\\033]0;%s\\007' $q_sess > /dev/tty 2>/dev/null ) &
# Стартовый промпт: патч в tui-command.ts сабмитит его как первый ввод; после
# чтения переменная из окружения удаляется — хукам и инструментам сессии её нет.
export ZCODE_TUI_PROMPT=$q_prompt
# Имя таба (v4.41): с 7401471 заголовок терминала следует за сессионным титулом,
# и сгенерированный моделью титул («Продолжение … по handoff») затирал OSC-запись
# ниже. Патч ZCODE_TUI_SESSION_TITLE (tui-prompt-handler.ts) ставит custom-титул
# из «имя:» хендоффа — автогенерация глушится; OSC-запись прикрывает паузу
# до подъёма app.
export ZCODE_TUI_SESSION_TITLE=$q_sess
# Режим родителя приехал флагом --mode (см. блок «Режим родителя» выше):
# без него TUI стартует в build и расщепление из yolo тонет в подтверждениях.
exec $q_node $q_cli tui $mode_arg
LAUNCHER
fi
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
# тот таб. parent_tty вычислен выше (он же выбирал цель) — здесь только Ghostty-разметка.
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
# Перезаписывается ПЕРЕД каждой попыткой чтения (окно гонки — миллисекунды).
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

# 🔴 Доставка НАЗЫВАЕТ окно, а не надеется на переднее (v4.35): `select tab`
# выбирает таб В ЕГО ОКНЕ и окно вперёд НЕ выводит, а `open -a` отдаёт документ
# ПЕРЕДНЕМУ окну. `new tab in <окно> with configuration` назначает окно явно.
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
