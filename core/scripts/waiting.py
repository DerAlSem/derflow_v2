#!/usr/bin/env python3
"""waiting — реестр не-сейчас-работы: строка, хранилище, пробуждение.

    waiting.py new "<заголовок>" [--global]
    waiting.py list [--all]
    waiting.py done <id> "<почему>"
    waiting.py stamp <id>
    waiting.py probe
    waiting.py taken <id> "<почему>"
    waiting.py ack <id>
    waiting.py wake
    waiting.py doctor [--install]

Строка — файл `<repo>/.claude/waiting/YYYYMMDD-NN.md` ОСНОВНОГО чекаута,
беспроектная — `~/.claude/waiting/`. У файла один писатель, и это человек:
всё машинно-производное живёт в кэше `~/.claude/waiting-cache/`.

Форма отказывает при `list`, а не при заведении: заполнить всё сразу нельзя по
построению — проба часто ещё не известна. `list` печатает недооформленные
ОТДЕЛЬНОЙ группой, печатает остальные группы целиком и возвращает 1 ПОСЛЕ
полной печати. Упасть на первой недооформленной значило бы заглушить реестр для
всех шести сессий; пропустить её — спрятать до `review_by`, то есть устроить ту
самую тишину, против которой написан весь реестр.

Коды: 0 сделано либо печатать нечего · 1 форма строки · 2 конфигурация либо
положение · 3 замок занят (не ошибка) · 4 проба не смогла спросить. Коды 3 и 4
возвращает ТОЛЬКО `probe` (Р17 плана 2-2): код `wake` читает харнесс, а не
человек, и ненулевой код хука — сообщение о сбое, не о состоянии реестра.
**Код 5 не занят:** у 1b он значит «нужно решение владельца».

Спека: ~/.claude/specs/2026-09-08-waiting-registry.md
План:  ~/.claude/plans/2026-09-11-waiting-registry-2-2.md (2-1 — предшественница)
"""

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# json, re, time и date задаче 1 не нужны — их зовут задачи 2 и 3. Импорт стоит
# здесь сразу, чтобы шапка файла не переписывалась четыре раза подряд.

# WAITING_HOME существует ради стенда укусов: без подмены дома укусы писали бы в
# живой ~/.claude/waiting и не воспроизводились бы дважды подряд. Подменяет
# разом три вещи — беспроектный ящик, кэш и файл корней.
HOME = pathlib.Path(os.environ.get("WAITING_HOME") or (pathlib.Path.home() / ".claude"))
BOX = "waiting"                  # имя каталога-ящика внутри репозитория
CACHE = HOME / "waiting-cache"
ROOTS = HOME / "waiting-roots.txt"
HOME_REPO_ID = "home"            # Р4: у ящика дома id фиксирован
DAYS_WITH_PROBE = 30             # инвариант 5: подстраховка там, где спрашивает машина
DAYS_NO_PROBE = 7                # инвариант 5: единственный датчик там, где не спрашивает никто
# Р11: число ВЫБРАНО 11.09.2026, а не временное. Основание названо вслух, потому
# что замер его не даёт: доля смен исхода (Р13 плана 2-2) меряет, как часто
# случаются события, а TTL задаёт допустимую ЗАДЕРЖКУ их обнаружения — из первого
# второе не выводится. Из «события редки» одинаково следует и «опрашивать реже»,
# и «тем важнее не проспать редкое». Выбрано из требования к дельте: она
# показывается на старте сессии и не должна быть старше часа. Цена обратной
# стороны мала и замерена — холодный круг 13,4 с.
CACHE_TTL_S = 3600
LOCK = HOME / "waiting-lock"     # замок пробы: экономия на ssh, НЕ условие корректности
RUN = CACHE / "_run.json"        # квитанция прогона (Р19): писатель — держатель замка
PROBE_TIMEOUT_S = int(os.environ.get("WAITING_PROBE_TIMEOUT_S") or 30)
LOCK_TTL_S = 900                 # 30-кратный запас над потолком пробы (Р15)
SSH_CONNECT_TIMEOUT_S = 10
STALE_UNREACHABLE_S = 86400      # «недостижима дольше суток» — дельта (укус 10)
# Р18: транспорт и его потолок подменяются ради стенда — как WAITING_HOME у 2-1.
# Стенд обязан работать без сети: иначе укус про код 255 либо не воспроизводится,
# либо стучится в живой mprz.
SSH = os.environ.get("WAITING_SSH") or "ssh"
SETTINGS = HOME / "settings.json"
TOMB = HOME / "ОТЛОЖКА.md"       # выведенный из обращения реестр-предшественник
TOMB_MAX_LINES = 25              # редирект занимает шесть строк, остальное — запас
TOMB_ANCHOR = "waiting.py list"
HOOK_ANCHOR = '"hooks": {'       # единственная строка верхнего уровня
HOOK_MARK = "waiting.py wake"    # по чему узнаём свою запись
# Матчер — Р3: `compact` не включён (длинная сессия платила бы за дельту
# многократно), `clear` включён (/clear вытирает контекст вместе с доставленной
# дельтой), `resume` включён (между смертью и возобновлением проходят часы, и
# дубль дешевле пропуска). timeout: 5 — как у соседей по файлу. $HOME
# разворачивает харнесс: соседняя запись context-meter.py работает именно так.
HOOK_BLOCK = """    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOME/.claude/scripts/waiting.py wake",
            "timeout": 5
          }
        ]
      }
    ],
"""


def die(code, msg):
    print(f"waiting: {msg}", file=sys.stderr)
    sys.exit(code)


def git(*args, cwd=None):
    # Отсутствие самого git — не «git ответил ошибкой», а «спросить некого»:
    # subprocess бросает FileNotFoundError ДО всякого кода возврата.
    try:
        p = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError) as e:
        die(2, f"git не запускается — {e}")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


@dataclass
class Box:
    """Ящик строк: каталог, его глобальный id и репозиторий-владелец."""
    dir: pathlib.Path
    repo_id: str
    repo: pathlib.Path        # None у ящика дома
    branch: str               # None у ящика дома


def repo_id_of(main):
    """Имя основного чекаута + 8 знаков sha его пути.

    Алгоритм скопирован из memo.py:context, а не вынесен в общий модуль:
    `lib/` в ~/.claude под запретом .gitignore (глоб без ведущего слэша ловит
    любой lib/ на любой глубине — 10.09.2026 так потерялся файл при коммите), а
    общий модуль ради десяти строк дороже, чем повтор с этой ссылкой. Отличие
    одно и намеренное: хэшуется путь основного чекаута, а не каталога .git —
    здесь id принадлежит ЯЩИКУ (Р4), и у ящика дома каталога .git может не быть
    вовсе.
    """
    slug = "".join(c if (c.isalnum() or c in "._-") else "-" for c in main.name)
    slug = slug.lstrip(".")[:32] or "repo"
    return f"{slug}-{hashlib.sha256(str(main).encode()).hexdigest()[:8]}"


def worktree_main(repo):
    """Основной чекаут репозитория. Ворктри → его хозяин (инвариант 6).

    --path-format=absolute обязателен: без него git отдаёт «.git» из корня,
    «../.git» из подкаталога и абсолютный путь из ворктри. На сравнении этих
    строк главный сценарий развалился бы молча (тот же промах чинил memo.py).
    """
    rc, common, _ = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=repo)
    if rc != 0:
        return pathlib.Path(repo).resolve()   # не git вовсе — каталог сам себе основной
    c = pathlib.Path(common).resolve()
    return (c.parent if c.name == ".git" else c).resolve()


def home_box():
    return Box(dir=HOME / BOX, repo_id=HOME_REPO_ID, repo=None, branch=None)


def repo_box(cwd=None):
    """Ящик для текущего положения.

    Три развилки, и каждая куплена: не репозиторий → дом; основной чекаут ЕСТЬ
    ~/.claude → дом (иначе `new` завёл бы ~/.claude/.claude/waiting/ и сделал
    существующие строки невидимыми — а изнутри ~/.claude зовут ежедневно);
    ворктри → его основной чекаут, молча и без отказа (Р9).
    """
    cwd = pathlib.Path(cwd) if cwd else pathlib.Path.cwd()
    rc, _top, _ = git("rev-parse", "--show-toplevel", cwd=cwd)
    if rc != 0:
        return home_box()
    main = worktree_main(cwd)
    if main == HOME.resolve():
        return home_box()
    rc, branch, _ = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    return Box(dir=main / ".claude" / BOX, repo_id=repo_id_of(main),
               repo=main, branch=(branch if rc == 0 else None))


def box_of_dir(d):
    """Ящик по каталогу: id принадлежит КАТАЛОГУ, а не пути, которым пришли."""
    d = pathlib.Path(d).resolve()
    if d == (HOME / BOX).resolve():
        return home_box()
    main = d.parent.parent
    return Box(dir=d, repo_id=repo_id_of(main), repo=main, branch=None)


def yaml_quote(s):
    """Плоский скаляр в кавычках. Двоеточие с пробелом внутри голого скаляра
    YAML либо ломает разбор, либо меняет смысл, поэтому кавычки не украшение.

    Перевод строки СХЛОПЫВАЕТСЯ в пробел, и это не косметика. Причина снятия —
    проза, а проза переносится строками; `done <id> "сработала\nподробности: …"`
    без этого клал в ИСПРАВНЫЙ файл человека незакрытую кавычку: разбор ломался,
    заголовок подменялся на «(без title)», причина снятия печаталась как «не
    названа», а stamp и done по этой строке дальше отказывали — починить её
    своим же инструментом становилось нельзя. Инвариант 7 в худшей форме: машина
    уничтожала и написанное человеком, и собственное надгробие.

    Схлопывание, а не экранирование в `\\n`: unescape понимает ровно две
    последовательности (`\\\\` и `\\"`), и третья потребовала бы править обе
    стороны ради входа, который в прозе ничего не значит.
    """
    flat = " ".join(s.split())
    return '"' + flat.replace("\\", "\\\\").replace('"', '\\"') + '"'


KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")


@dataclass
class Field:
    value: str
    style: str      # quoted | bare | block


def unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in '\\"':
            out.append(s[i + 1]); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def strip_comment(s):
    """Комментарий снимается ТОЛЬКО у голого скаляра.

    В кавычках и в блоке решётка — часть значения: `ripe_match: "#\\d+"` —
    законная регулярка, а не строка с комментарием.
    """
    if s.startswith("#"):
        return ""
    cut = s.find(" #")
    return (s[:cut] if cut >= 0 else s).strip()


def parse_front(text):
    """Разбор франтматтера СВОИМ парсером и с сохранением стиля.

    Своим — потому что PyYAML в системе нет (замер 10.09.2026), а тащить
    зависимость ради пятнадцати полей дороже шестидесяти строк.

    Стиль нужен сторожу: спека требует кавычек у пяти полей, а разобранное
    значение о кавычках уже не помнит.

    Возвращает (fields, error). error — причина либо None. Непарсящийся файл
    НИКОГДА не проглатывается: строка с ошибкой печатается наравне с целыми,
    иначе она исчезает беззвучно — то есть врёт в сторону тишины.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "нет франтматтера: файл не начинается с ---"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, "франтматтер не закрыт вторым ---"
    fields, i = {}, 1
    while i < end:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        m = KEY.match(raw)
        if not m:
            return fields, f"строка {i + 1}: не «ключ: значение» — {raw.strip()!r}"
        key, rest = m.group(1), m.group(2).strip()
        if key in fields:
            return fields, f"строка {i + 1}: ключ {key!r} повторяется — какое из двух значений верно, не решает никто"
        if rest == "|":
            body, i = [], i + 1
            while i < end and (not lines[i].strip() or lines[i][:1] in " \t"):
                body.append(lines[i])
                i += 1
            pad = min((len(b) - len(b.lstrip()) for b in body if b.strip()), default=0)
            fields[key] = Field("\n".join(b[pad:] for b in body).strip("\n"), "block")
            continue
        if rest.startswith('"'):
            if len(rest) < 2 or not rest.endswith('"'):
                # Предел назван вслух. Единственный конкретный образец строки
                # в спеке несёт перенос внутри кавычек, а по нему миграция 2-3
                # будет писать двенадцать строк руками; голое «не закрыта»
                # увело бы человека искать кавычку, которая закрыта — строкой
                # ниже. Продолжение плоского скаляра не поддерживается нарочно:
                # парсер свой, и многострочность у него ровно одна — блочная.
                return fields, (f"строка {i + 1}: кавычка у {key!r} не закрыта. "
                                f"Перенос внутри кавычек не поддерживается — "
                                f"свести значение в ОДНУ строку либо взять "
                                f"блочный скаляр «|», как у probe")
            fields[key] = Field(unescape(rest[1:-1]), "quoted")
        else:
            fields[key] = Field(strip_comment(rest), "bare")
        i += 1
    return fields, None


def day(v):
    """Дата или None. Принимает и поле, и строку — зовут и так, и так."""
    if v is None:
        return None
    s = v.value if isinstance(v, Field) else v
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_data(text):
    """Выкидывает ДАННЫЕ, оставляет код.

    Наивный `";" in probe` отвергает четыре живые строки нынешней отложки: у
    них многострочный SQL, и точка с запятой там — конец оператора, а не
    разделитель команд. Тело heredoc и содержимое кавычек — данные; сторож
    смотрит на то, что осталось.

    Разбор шелла здесь свой и неполный, и это сказано вслух: сторож ловит
    написанную конъюнкцию, а не выдуманную. `bash -n` тут не помог бы — он
    отвечает на вопрос о синтаксисе, а не о числе команд.
    """
    kept_lines, here, quote = [], None, None
    for raw in text.splitlines():
        if here is not None:
            if raw.strip() == here:
                here = None
            continue
        kept, i = [], 0
        while i < len(raw):
            ch = raw[i]
            if quote:
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in "'\"":
                quote = ch
                i += 1
                continue
            # Ограничитель ищется ДО снятия кавычек: в `<<'SQL'` они часть
            # маркера, и снятые первыми они оставили бы голое `<<`.
            m = HEREDOC.match(raw, i)
            if m:
                here = m.group(2)
                i = m.end()
                continue
            kept.append(ch)
            i += 1
        kept_lines.append("".join(kept))
    return kept_lines, (quote is not None or here is not None)


def conjunction(text):
    """Причина отказа либо None. Инвариант 1: одна строка — одна проба.

    Ноль конъюнкции двусмыслен: «событий нет» и «ветка кода ни разу не
    исполнялась» из него неразличимы (замер 08.09.2026, строка 15).
    """
    kept, unparsed = strip_data(text)
    if unparsed:
        # Состояние кавычки живёт МЕЖДУ строками, и незакрытая съедает весь
        # остаток пробы вместе с настоящей конъюнкцией. Пробиваемый вход:
        # `journalctl -u bot   # don't grep` первой строкой — апостроф в
        # комментарии открывает кавычку, и вторая команда исчезает бесследно.
        # Отказ здесь возвращает промах в БЕЗОПАСНУЮ сторону: ложный отказ
        # разобранной пробе человек увидит и перепишет, тихий пропуск
        # конъюнкции не увидит никто.
        return ("пробу не разобрали: кавычка либо heredoc не закрыты. Сторож "
                "неполон нарочно, и на неразобранном он отказывает, а не молчит")
    lines = [ln for ln in kept if ln.strip()]
    joined = "\n".join(lines)
    for token in ("&&", "||", ";"):
        if token in joined:
            return (f"проба несёт конъюнкцию «{token}» — одна строка, одна проба: "
                    f"ноль конъюнкции не отличить от «не исполнялось ни разу»")
    if len(lines) > 1:
        return ("проба несёт конъюнкцию: две команды в столбик — перевод строки "
                "разделяет их так же, как «;»")
    return None


COMPARISON = re.compile(r"^\s*(?:[<>]=?|[!=]=|=)\s*-?\d+(?:[.,]\d+)?\s*$")
ALWAYS = ("title", "state", "review_by", "stamped_at", "entry")
WITH_PROBE = ("host", "cwd", "probe", "ripe_match", "ripe_when", "sample")
QUOTED = ("title", "probe", "ripe_match", "ripe_when", "sample")


def faults(fields):
    """Чего не хватает форме. Пустой список — строка оформлена.

    Отказ формой, а не предупреждением (инвариант 4): строку без образца никто
    не отвергает — её просто заводят, и она становится обещанием вместо
    проверки.
    """
    out = []
    for k in ALWAYS:
        if k not in fields:
            out.append(f"нет поля {k}")
    for k in ALWAYS + WITH_PROBE:
        f = fields.get(k)
        if f is not None and not f.value.strip():
            out.append(f"поле {k} пустое — пустое поле это не «нет данных», "
                       f"а «данные были и потерялись при разборе»")
    st = fields.get("state")
    if st is not None and st.value not in ("waiting", "taken", "done"):
        out.append(f"state: {st.value!r} — состояния три: waiting, taken, done")
    if st is not None and st.value == "taken" and "taken_because" not in fields:
        out.append("state: taken без taken_because — запись без причины не "
                   "отвечает на вопрос, ради которого её хранят")
    for k in ("review_by", "stamped_at"):
        f = fields.get(k)
        if f is not None and day(f) is None:
            out.append(f"{k}: {f.value!r} — не дата вида ГГГГ-ММ-ДД")
    probe = fields.get("probe")
    if probe is None:
        out.append("нет поля probe — либо команда, либо явное none")
    elif probe.value == "none":
        # Событие бывает непроверяемым машинно (ответ поддержки, решение
        # человека). Тогда строка созревает ТОЛЬКО по сроку — и остальные поля
        # пробы обязаны быть явным none, а не забытыми.
        for k in ("host", "cwd", "ripe_match", "sample"):
            f = fields.get(k)
            if f is None or f.value != "none":
                out.append(f"probe: none, а {k} не none — спрашивать нечем, "
                           f"и полупустая проба это скрывает")
        if "ripe_when" not in fields:
            out.append("нет поля ripe_when: без пробы прозой сказано только оно")
        rb, sa = day(fields.get("review_by")), day(fields.get("stamped_at"))
        if rb and sa and (rb - sa).days > DAYS_NO_PROBE:
            out.append(
                f"probe: none при штампе +{(rb - sa).days} — срок вдвое длиннее, "
                f"чем положено единственному датчику; чинится `waiting.py stamp`")
    else:
        for k in WITH_PROBE:
            if k not in fields:
                out.append(f"нет поля {k}")
        why = conjunction(probe.value)
        if why:
            out.append(why)
        for k in ("host", "cwd"):
            f = fields.get(k)
            if f is not None and f.value in ("", "none"):
                out.append(f"{k}: none при живой пробе — фоновая проба стартует "
                           f"из неизвестного каталога и честно не найдёт путей")
        cw = fields.get("cwd")
        if cw is not None and cw.value.strip() == "~":
            # Отвергать ФОРМОЙ, а не подсказкой шаблона: подсказку читают один
            # раз при заведении, а форма спрашивает каждый раз — и попались
            # именно на этом. Ровно голая тильда: `~/dev/…` законна и раскрыть
            # её обязан приёмный шелл, отказ на неё снёс бы живые строки разом.
            out.append("cwd: ~ — голый дом раскрывает ПРИЁМНЫЙ шелл, а на "
                       "удалённом хосте дом не наш; пиши абсолютным путём")
        rm = fields.get("ripe_match")
        if rm is not None and COMPARISON.match(rm.value):
            # Р13-бис. `ripe_match` — регулярка по stdout (спека, «событие
            # наступило?»), и `>0` в ней ЛИТЕРАЛ: со счётчиком `0`, `1`, `47`
            # он не совпадает ни разу. Строка при этом оформлена, doctor
            # молчит, и сторож ждёт события, которого не сможет увидеть.
            # Поймано 12.09.2026 на rk_bot/20260911-01: сторож ухода часов ККТ
            # не мог созреть НИКОГДА.
            # Форма отказа нарочно узкая — только «знак и число целиком»:
            # регулярка законно начинается с `>` (журнальные префиксы, диффы),
            # и отказ по одному первому символу снёс бы живые строки. Проверяемо
            # одной фразой: под отказ не попадает ни одна из 34 нынешних
            # проб, а литерал, если он и правда нужен, пишется якорем — `^>0$`
            # проходит.
            out.append(f"ripe_match: {rm.value!r} — регулярка по stdout, а не "
                       f"сравнение: знак с числом ищется как ЛИТЕРАЛ и не "
                       f"совпадёт ни с одним счётчиком, то есть строка не "
                       f"созреет никогда; «больше нуля» пишется как ^[1-9]")
    for k in QUOTED:
        f = fields.get(k)
        if f is None or f.style in ("quoted", "block"):
            continue
        if k != "title" and f.value in ("none", "pending"):
            continue
        out.append(f"{k} без кавычек: двоеточие с пробелом внутри плоского "
                   f"скаляра YAML либо ломает разбор, либо меняет смысл")
    return out


def roots():
    """Корни скана. Конфиг, а не индекс.

    Отсутствующий файл с работающим умолчанием честнее заведённого файла,
    который надо вести. Файл с нулём корней — ошибка: это не «корней нет», это
    «сказали, что есть, и не назвали».
    """
    if not ROOTS.is_file():
        return [pathlib.Path.home() / "dev"]
    out = []
    for ln in ROOTS.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln:
            out.append(pathlib.Path(ln).expanduser())
    if not out:
        die(2, f"{ROOTS} есть, но не называет ни одного корня")
    return out


def boxes():
    """Каталоги-ящики. Список репозиториев НЕ ведётся — выводится глобом:
    ведённый индекс расходится с реальностью молча, скан не может.

    `~/.claude/waiting/` добавляется ОТДЕЛЬНОЙ строкой: глоб
    <root>/*/.claude/waiting по корню ~/.claude дал бы
    ~/.claude/*/.claude/waiting и не нашёл бы его вовсе.
    """
    seen, out = set(), []
    for root in roots():
        for d in sorted(root.glob(f"*/.claude/{BOX}")):
            if not d.is_dir():
                continue
            repo = d.parent.parent
            if worktree_main(repo) != repo.resolve():
                continue      # ворктри: его строки живут в основном чекауте
            r = d.resolve()
            if r not in seen:
                seen.add(r)
                out.append(r)
    h = HOME / BOX
    if h.is_dir() and h.resolve() not in seen:
        out.append(h.resolve())
    return out


@dataclass
class Row:
    box: Box
    path: pathlib.Path
    name: str
    fields: dict
    error: str
    faults: list

    @property
    def id(self):
        return f"{self.box.repo_id}/{self.name}"


def scan():
    rows = []
    for d in boxes():
        box = box_of_dir(d)
        for p in sorted(d.glob("*.md")):
            if p.name == "MIGRATION.md":
                continue      # карта старых номеров поставки 2-3 — не строка
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                rows.append(Row(box, p, p.stem, {}, f"не читается — {e}", []))
                continue
            f, err = parse_front(text)
            rows.append(Row(box, p, p.stem, f, err, [] if err else faults(f)))
    return rows


def state_of(row):
    f = row.fields.get("state")
    return f.value if f else ""


def sort_key(row):
    return (day(row.fields.get("review_by")) or date.max, row.id)


GROUPS = ("созрело", "молчит", "недостижима", "ни разу не опрошена",
          "недооформленные", "данные протухли", "взята в работу")


def cache_of(row):
    """Кэш исходов: ФАЙЛ НА СТРОКУ, писатель один.

    Общий JSON на шесть сессий воспроизвёл бы в самом реестре дефект №3, ради
    которого реестр и пишется: git конфликта не даст, правка целиком затрёт
    чужую главу молча. После разреза по файлам замок перестал быть условием
    корректности и стал экономией на ssh.

    Форма файла — КОНТРАКТ ДЛЯ ПОСТАВКИ 2-2, здесь только читается:
        {"outcome": "fired" | "silent" | "unreachable",
         "since": "ISO-8601 — начало ТЕКУЩЕЙ серии этого исхода",
         "last_run_at_ts": float,     # когда фон спрашивал в последний раз
         "last_rc": int}              # чем кончился САМ ПРОГОН, не проба
    `since` нужен водяному знаку 2-2 (квитанция ключуется исходом, а не датой)
    и в 2-1 не читается — но заводится здесь, чтобы 2-2 не выдумала второй.
    """
    p = CACHE / row.box.repo_id / f"{row.name}.json"
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Битый или отсутствующий кэш — не отказ реестра: строка честно
        # становится «ни разу не опрошена». Соврать в сторону тишины тут
        # невозможно — «не спрашивали» и есть правда о нечитаемом файле.
        return None
    return c if isinstance(c, dict) else None


def lock_mark():
    return LOCK / "owner.json"


def mark_lock(token):
    """Кладёт маркер владельца ВНУТРЬ взятого замка."""
    try:
        write_json(lock_mark(), {"token": token, "pid": os.getpid(),
                                 "at": time.time()})
        return True
    except OSError:
        return False


def lock_is_ours(token):
    """Замок всё ещё наш? Нечитаемый маркер — «не наш», и это верная сторона
    промаха: чужой замок переживёт лишние 900 с, свой — снимет TTL."""
    try:
        m = json.loads(lock_mark().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(m, dict) and m.get("token") == token


def drop_lock_dir():
    """Сносит каталог замка ВМЕСТЕ с содержимым.

    С появлением маркера каталог перестал быть пустым, а `rmdir` по непустому
    отказывает. Без сноса содержимого протухший замок не снялся бы НИКОГДА: не
    опрашивалась бы ни одна строка, и снаружи это выглядит как «все молчат».
    """
    try:
        for f in LOCK.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        LOCK.rmdir()
        return True
    except OSError:
        return False


def release_lock(token):
    """Снимает ТОЛЬКО свой замок.

    🔴 Безусловный `rmdir` снимал и ЧУЖОЙ — только что взятый тем, кто снял
    протухший: A берёт замок → замок протухает (30 недостижимых строк по 30 с
    потолка = ровно LOCK_TTL_S) → B снимает протухший и берёт свой → A доходит
    до своего finally и удаляет замок B → C входит третьим. Дальше два прогона
    пишут кэш вперемешку, и замок, который должен был быть экономией на ssh,
    перестаёт быть даже ею.
    """
    if token is None or not lock_is_ours(token):
        return False
    return drop_lock_dir()


def seen_path(row):
    return CACHE / row.box.repo_id / f"{row.name}.seen.json"


def seen_of(row):
    """Квитанция ДЕЛЬТЫ: что именно `wake` про эту строку НАПЕЧАТАЛ.

    🔴 Ради чего заведена. `wake` печатает дельту и ТУТ ЖЕ отцепляет фон —
    именно потому, что кэш устарел, то есть ровно в тот момент, когда дельту и
    читают. Пока владелец читает «недостижима» и говорит `ack`, фон успевает
    записать `fired`. Ключуясь НЫНЕШНИМ составом причин, `ack` гасил бы `fired`,
    которого не печатал никто, — и сработавшая проба, то самое событие, ради
    которого реестр существует, терялась бы молча и навсегда.

    Разрез по файлам с одним писателем сохранён: `<id>.json` пишет только
    `probe`, `<id>.seen.json` — только `wake`. Цена названа вслух: `wake`
    перестал быть только-читателем, и эта граница проверена кругом критики.

    Форма:
        {"key":   "<ack_key напечатанного состава>",
         "kinds": ["форма", "fired"],
         "at":    "ISO — когда дельта это напечатала"}
    Нечитаемая или бессоставная квитанция — как её отсутствие: `ack` гасит по
    нынешнему составу, как до починки. Соврать в сторону «ничего не печатали»
    тут безопасно, в обратную — нет.
    """
    try:
        s = json.loads(seen_path(row).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(s, dict) or not isinstance(s.get("key"), str):
        return None
    kinds = s.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        return None
    if not all(isinstance(k, str) for k in kinds):
        return None
    return s


def take_lock():
    """Замок пробы. Возвращает (взят ли, снят ли протухший, жетон владельца).

    Замок — экономия на ssh, а НЕ условие корректности: корректность держится
    разрезом кэша по файлам с одним писателем каждый. Нужен затем, чтобы шесть
    сессий, стартовавших в одну минуту, не позвали ssh шесть раз.

    Жетон отдаётся наружу, потому что снимать замок имеет право только тот, кто
    его взял, — см. release_lock.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    # Жетон, а не голый pid: номера процессов система переиспользует, и прогон,
    # стартовавший под номером давно умершего держателя, снял бы чужой замок
    # «как свой» — то есть маркер владельца не защищал бы ни от чего.
    token = f"{os.getpid()}-{time.time_ns()}-{os.urandom(4).hex()}"
    try:
        LOCK.mkdir(parents=True)
    except FileExistsError:
        pass
    else:
        return (True, False, token) if mark_lock(token) else (False, False, None)
    try:
        age = time.time() - LOCK.stat().st_mtime
    except OSError:
        return False, False, None
    if age <= LOCK_TTL_S:
        return False, False, None
    # Держатель не дожил до снятия. Проба, попросившая пароль, висит без TTY и
    # держала бы замок до его TTL — тогда не опросилась бы НИ ОДНА строка, а
    # снаружи это выглядит как «все молчат».
    if not drop_lock_dir():
        return False, False, None
    try:
        LOCK.mkdir()
    except OSError:
        return False, False, None    # успел другой: это его очередь, а не ошибка
    return (True, True, token) if mark_lock(token) else (False, False, None)


def write_json(path, obj):
    """Атомарно. Обрыв посередине оставил бы кэш нечитаемым, а нечитаемый кэш
    честно читается как «ни разу не опрошена» — то есть событие потерялось бы.
    """
    # Имя временного файла НЕСЁТ pid. С общим `<имя>.tmp` два прогона писали бы
    # в один файл: усечение вторым обрезало бы данные первого, os.replace
    # публиковал бы смесь, и cache_of честно отвечал бы «ни разу не опрошена»
    # про строку, которую спрашивали дважды. То есть замок был бы условием
    # КОРРЕКТНОСТИ, хотя спека и три докстринга подряд обещают обратное —
    # «корректность держится разрезом кэша по файлам с одним писателем».
    # Разрез даёт одного писателя на СТРОКУ, а не на временный файл.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def probeable(row):
    """Кого фон спрашивает (Р20). Четыре класса не спрашиваются никогда.

    done и taken — потому что не будят; недооформленные — потому что спрашивать
    нечем и форма уже названа дельтой; probe: none — по спеке. Довод не экономия:
    проба по строке с полупустой формой ходила бы в сеть по угаданным полям.
    """
    if row.error or row.faults:
        return False
    if state_of(row) in ("done", "taken"):
        return False
    probe = row.fields.get("probe")
    return probe is not None and probe.value != "none"


def probe_call(row):
    """Как позвать пробу. Возвращает (argv, скрипт для stdin).

    Скрипт уезжает в STDIN, а не в аргумент: иначе кавычки живой пробы пришлось
    бы экранировать дважды — для своего шелла и для удалённого, — и четыре живые
    строки с многострочным SQL сломались бы на этом молча.

    `bash -o pipefail`, а не голый bash: живые пробы это грепы по журналу через
    конвейер, и без pipefail код возврата брал бы ПОСЛЕДНЮЮ команду конвейера,
    то есть «источник ответил» подменялось бы «хвост дочитался».
    """
    cwd = row.fields["cwd"].value
    # Р21: тильду раскрывает шелл-ПРИЁМНИК — на удалённом хосте дом не наш, а
    # shlex.quote её экранирует и cd промахивается. Предел назван вслух: путь с
    # тильдой И пробелом сразу не поддержан, и отказ смещён в безопасную сторону
    # — cd не найдёт каталога, скрипт выйдет 91, исход будет unreachable с
    # названной причиной, а не тихое «молчит».
    where = cwd if cwd.startswith("~/") else shlex.quote(cwd)
    script = f"cd {where} || exit 91\n{row.fields['probe'].value}\n"
    host = row.fields["host"].value
    if host == "local":
        return ["bash", "-o", "pipefail", "-s"], script
    # BatchMode=yes обязателен: фон отцеплен, TTY у него нет, и проба,
    # попросившая пароль, повисла бы и удержала замок до его TTL.
    return [SSH, "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_S}",
            host, "bash", "-o", "pipefail", "-s"], script


def probe_one(row):
    """Три вопроса, а не один. Возвращает (исход, код ПРОБЫ, причина).

    Ни один из трёх не выводится из ответа на другой: `grep` без совпадений
    выходит кодом 1, а живые пробы — это грепы по журналу (14 в нынешнем
    реестре). Вывести исход из одного кода значило бы присылать ложную тревогу
    по честно молчащей строке на каждом из шести стартов, и дельту перестали бы
    читать за неделю. Тот же результат, что у лжи в сторону тишины, только с
    другой стороны.
    """
    argv, script = probe_call(row)
    try:
        # errors="replace": живые пробы — грепы по журналу, а в журнале бывает
        # один битый байт. Строгий разбор бросил бы UnicodeDecodeError, которого
        # нет ни в одном except ниже, и прогон умер бы на этой строке молча.
        p = subprocess.run(argv, input=script, capture_output=True, text=True,
                           errors="replace", timeout=PROBE_TIMEOUT_S)
    except (FileNotFoundError, PermissionError) as e:
        return "unreachable", 127, f"нечем спросить — {e}"
    except subprocess.TimeoutExpired:
        return "unreachable", 124, f"потолок пробы {PROBE_TIMEOUT_S} с исчерпан"
    if p.returncode == 255:
        return "unreachable", 255, "транспорт отказал (ssh: 255)"
    if p.returncode == 91:
        return "unreachable", 91, f"cwd не нашёлся: {row.fields['cwd'].value}"
    if p.returncode != 0:
        return "unreachable", p.returncode, f"проба вышла кодом {p.returncode}"
    try:
        rx = re.compile(row.fields["ripe_match"].value)
    except re.error as e:
        # Громкая сторона: непонятая регулярка — это «не смогли спросить», а не
        # «событие не наступило». Проглотить её тихо значит соврать в тишину.
        return "unreachable", 1, f"ripe_match не компилируется — {e}"
    return ("fired" if rx.search(p.stdout) else "silent"), 0, ""


def write_cache(row, outcome, probe_rc, note):
    """Кэш строки: исход, начало серии, два кода и ДВА СЧЁТЧИКА ЗАМЕРА (Р13).

    🔴 `last_rc` — код ПРОГОНА, `probe_rc` — код ПРОБЫ. Классификатор читает
    `last_rc != 0` как поломку реестра; положить туда код упавшей пробы значит
    отправить каждую недостижимую строку в «данные протухли» вместо
    «недостижима» — то есть сломать инвариант 3 там, где он и охраняется.
    Рука делает это сама: поле называется «rc», проба вернула «rc».
    """
    old = cache_of(row) or {}
    # 🔴 Первый прогон — НАЧАЛО наблюдения, а не наблюдение: прежнего исхода не
    # было, и менять было нечего. Засчитывать его сменой значит завышать долю
    # смен ровно на одну штуку с КАЖДОЙ заведённой строки — сдвиг растёт с
    # числом строк, а не со временем, и замер тем лживее, чем больше реестр.
    # Замерено 11.09 на живом кэше: 39 «смен» при 33 строках, настоящих 6.
    first = "outcome" not in old
    same = old.get("outcome") == outcome
    now_iso = datetime.now().isoformat(timespec="seconds")
    c = {
        "outcome": outcome,
        # Начало ТЕКУЩЕЙ серии этого исхода — ключ водяного знака (Р9). Та же
        # серия продолжается — `since` не двигается; сменился исход — новая.
        "since": (old.get("since") or now_iso) if same else now_iso,
        "last_run_at_ts": time.time(),
        "last_rc": 0,            # прогон состоялся, чем бы ни кончилась проба
        "probe_rc": probe_rc,
        "note": note,
        "same_truth_runs": int(old.get("same_truth_runs") or 0)
                           + (0 if first else (1 if same else 0)),
        "changed_runs": int(old.get("changed_runs") or 0)
                        + (0 if first or same else 1),
    }
    p = CACHE / row.box.repo_id / f"{row.name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, c)


def cmd_probe(a):
    """Фоновый опрос. Не актор (инвариант 8): ничего не решает и не чинит.

    Код 3 — замок занят, и это НЕ ошибка. Код 4 — хоть одна строка не смогла
    спросить; он отделён от 0 намеренно, иначе возвращается ровно тот дефект,
    ради которого написан инвариант 3.
    """
    ok, broken, token = take_lock()
    if not ok:
        print("замок занят — фоновая проба уже идёт")
        return 3
    started = datetime.now().isoformat(timespec="seconds")
    bad = 0
    try:
        rows = [r for r in scan() if probeable(r)]
        for row in rows:
            try:
                outcome, probe_rc, note = probe_one(row)
                write_cache(row, outcome, probe_rc, note)
            except Exception as e:
                # Одна строка не смеет уносить ВЕСЬ прогон. Без этого отказ на
                # первой же строке оставлял бы последующие неопрошенными и не
                # писал бы квитанцию прогона — «не смогла спросить» у одной
                # превращалось бы в «не спрашивали» у всех остальных, то есть в
                # конфляцию инварианта 3 там, где он и охраняется. Фон отцеплен,
                # stderr в /dev/null: трейсбека не увидел бы никто.
                outcome, probe_rc, note = "unreachable", 1, f"проба сорвалась — {e}"
                try:
                    write_cache(row, outcome, probe_rc, note)
                except OSError:
                    pass
            if outcome == "unreachable":
                bad += 1
            print(f"{row.id}: {outcome}" + (f" — {note}" if note else ""))
        write_json(RUN, {
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at_ts": time.time(),
            "rows": len(rows),
            "unreachable": bad,
            "stale_lock_broken": broken,
        })
    finally:
        # Снимаем ТОЛЬКО свой замок — почему именно так, см. release_lock.
        release_lock(token)
    if broken:
        print("снят протухший замок пробы — предыдущий прогон не дожил до конца")
    return 4 if bad else 0


def detach_probe():
    """Старт сессии не ждёт ssh НИКОГДА (укус 17).

    start_new_session=True обязателен: иначе дочерний процесс умрёт вместе с
    группой сессии, и проба, начатая на старте, не доживёт до записи кэша.
    Потоки в /dev/null — всё, что фон говорит, живёт в кэше и в квитанции
    прогона, а не в чьём-то stdout.
    """
    try:
        subprocess.Popen(
            [sys.executable, str(pathlib.Path(__file__).resolve()), "probe"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass        # не вышло отцепить — это не повод ронять старт сессии


def registry_broken(now, watching=True):
    """Молчание реестра — само событие. Возвращает текст или None.

    `watching` — есть ли в реестре хоть одна строка, которую фон обязан
    спрашивать. Если нет (все `probe: none`, `taken` либо `done` — после
    миграции это норма), фон не зовётся вовсе и квитанция прогона стареет сама
    собой. Без этой развилки каждый старт любой сессии получал бы «реестр
    молчит» НАВСЕГДА, погасить это нечем, и единственная строка, которой
    позволено нарушить «пустая дельта пуста», обесценилась бы первой же неделей.

    Если проба падает при старте, кэш просто перестаёт обновляться: исходы
    остаются прежними, дельта пуста, `list` печатает вчерашнюю правду. Молчащий
    реестр неотличим от пустого, а пустой — нормальное состояние, поэтому
    тревогу не поднимет никто.

    🔴 Своего ОТСУТСТВИЯ `wake` обнаружить не может: если запись хука пропала из
    settings.json (а файл правят 4–6 сессий), его просто никто не зовёт. Этот
    класс закрывает только `doctor`, и потому он отдельная команда для человека.

    Это ЕДИНСТВЕННАЯ строка, которой позволено нарушить «пустая дельта пуста».
    """
    try:
        run = json.loads(RUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None     # прогонов не было вовсе — это старт, а не поломка
    if run.get("stale_lock_broken"):
        return ("предыдущий фоновый прогон не дожил до конца — замок снимали "
                "протухшим; исходы могли остаться вчерашними")
    ts = run.get("finished_at_ts")
    if not isinstance(ts, (int, float)):
        return "квитанция фонового прогона без времени — фон писал её сломанным"
    if watching and now - ts > 3 * CACHE_TTL_S:
        return (f"фоновая проба не отчитывалась {int((now - ts) / 3600)} ч — "
                f"реестр печатает вчерашнюю правду")
    return None


def why_line(kind, key, row, c):
    """Причина одной строкой. Класс назван словами, а не кодом."""
    if kind == "форма":
        why = [row.error] if row.error else row.faults
        return "форма не сходится: " + "; ".join(why)
    if kind == "fired":
        return (f"проба СРАБОТАЛА (серия с {key}) — "
                f"{field_or(row, 'ripe_when', 'решение прозой не названо')}")
    if kind == "unreachable":
        note = (c or {}).get("note") or ""
        return f"недостижима с {key}, дольше суток" + (f" — {note}" if note else "")
    tail = ("" if field_or(row, "probe", "") != "none"
            else " — машинной пробы нет, срок единственный датчик")
    return f"срок пересмотра {key} прошёл{tail}"


def names_repo(text, repo):
    r"""Называет ли `entry` этот репозиторий. Сверяется ПУТЬ, а не имя.

    Голое имя репозиторий не локализует (тот же довод, что в display_path):
    корней скана бывает несколько, и одноимённые каталоги под разными корнями —
    ровно тот класс, ради которого идентификатор сделан глобальным. Формы две,
    потому что `entry` пишется через display_path (`~/dev/gmb_v2`), но правится
    и руками.

    Граница `(?![\w.-])` пропускает `/`: `~/dev/gmb_v2/.claude/…` этот
    репозиторий называет, а `~/dev/gmb` перед `_v2` — уже нет.
    """
    for pth in {display_path(repo), str(repo)}:
        if re.search(re.escape(pth) + r"(?![\w.-])", text):
            return True
    return False


def here_box():
    """Ящик текущего каталога — для ПОРЯДКА печати дельты, не для отбора.

    Каталог берётся у процесса: хук стартует в каталоге сессии. Проверяемо
    соседним UserPromptSubmit-хуком — он зовёт голый `git rev-parse` и печатает
    ветку, а `~` не репозиторий вовсе, значит стартовал он не в `~`.

    Отказ git — не повод остаться без дельты: None значит «порядок прежний», а
    не «дельта пустая» (Р16).
    """
    try:
        return repo_box()
    except Exception:
        return None


def close_to(row, here):
    """Строка «своя» текущему каталогу — по ящику ЛИБО по entry.

    Одного ящика мало, и это замерено: у `gmb_v2` проектный ящик недоступен
    (основной чекаут отцеплен нарочно, main держит ворктри deploy-main), и 13
    его строк живут в ящике дома. Порядок по одному ящику отрезал бы от сессии
    ровно то, что к её проекту и относится.
    """
    if here is None:
        return False
    if row.box.repo_id == here.repo_id:
        return True
    if here.repo is None:
        return False
    f = row.fields.get("entry")
    return bool(f) and names_repo(f.value, here.repo)


def wake():
    """Дельта на старте сессии. Собирается В ПАМЯТИ и печатается одним куском.

    🔑 Вывод хука уходит в КОНТЕКСТ АССИСТЕНТА, а не на экран человека
    (проверено 08.09.2026). Значит «печатает» — неверное слово: хук КЛАДЁТ
    дельту в контекст, а вынести её на экран обязан ассистент, и это сказано
    строкой в самом выводе. Иначе созревшая строка будет прочитана и не названа.

    Р16: печать одним куском в конце. По ходу — и исключение на середине
    оставило бы в контексте половину дельты, неотличимую от полной.
    """
    today = datetime.now().date()
    now = time.time()
    items, stale, watching, receipts = [], False, False, []
    for row in scan():
        c = cache_of(row)
        kinds = reasons(row, c, today, now)
        printed = bool(kinds) and unacked(row, kinds)
        if printed:
            items.append((row, kinds, c))
        receipts.append((row, kinds if printed else None))
        if probeable(row):
            watching = True
            ts = (c or {}).get("last_run_at_ts")
            if not isinstance(ts, (int, float)) or now - ts > CACHE_TTL_S:
                stale = True
    # 🔴 Квитанция дельты обслуживается для ВСЕХ строк и ДО раннего возврата.
    # Напечатанной — кладём; НЕ напечатанной — сносим, и вторая половина ничуть
    # не менее важна первой. Квитанция, которой следующая дельта не подтвердила,
    # описывает печать позавчерашнего дня; оставленная лежать, она заглушила бы
    # будущее событие ровно так же, как неизрасходованная после `ack`. Поймано
    # укусом, а не чтением кода: стенд от этого КРАСНЕЛ ЧЕРЕЗ РАЗ — девять чисел
    # таблицы разошлись, и разбор расхождения вывел сюда.
    #
    # Отказ глотается целиком: по Р16 `wake` не имеет права упасть, а упавший
    # здесь оставил бы контекст вообще без дельты. `except Exception` тут
    # безопасен — ни одна из этих строк не зовёт die(), чей SystemExit мимо него
    # и проехал бы (Ruling 10). Зачем всё это — см. seen_of.
    for row, kinds in receipts:
        try:
            p = seen_path(row)
            if kinds is None:
                p.unlink(missing_ok=True)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            write_json(p, {"key": ack_key(kinds),
                           "kinds": sorted({k for k, _ in kinds}),
                           "at": datetime.now().isoformat(timespec="seconds")})
        except Exception:
            pass
    broken = registry_broken(now, watching)
    if stale:
        detach_probe()
    if not items and not broken:
        # 🔴 Ноль байт. Не «событий нет», не пустая строка, не заголовок без
        # содержимого: требование стоит токенов на каждом из шести стартов.
        return 0
    lines = ["РЕЕСТР НЕ-СЕЙЧАС-РАБОТЫ — дельта на старте сессии."]
    if broken:
        lines.append(f"🔴 реестр молчит: {broken}")
    # ПОРЯДОК, а не отбор. Дельта глобальна по построению — хук в
    # ~/.claude/settings.json стартует в любом проекте, — и это верно: строка
    # ждёт СОБЫТИЯ, а не твоего захода в её каталог. Спрятать чужое значило бы
    # вернуть ровно ту потерю, против которой реестр и заведён. Но шесть
    # созревших строк чужих репозиториев в каждой сессии — налог на внимание, и
    # платится он порядком дешевле, чем слепотой.
    here = here_box()
    near, far = [], []
    for it in items:
        (near if close_to(it[0], here) else far).append(it)
    # Заголовки печатаются, только когда есть что различать: над единственной
    # группой заголовок не добавляет ни бита, а дельта стоит токенов на каждом
    # старте любой сессии. Молчаливая перестановка при этом хуже отсутствия
    # порядка — читатель не знает, почему список такой, и примет верх за всё.
    where = (f"этот репозиторий: {here.repo.name}" if here and here.repo
             else "ящик дома (~/.claude)")
    if near and far:
        groups = [(f"  — {where} —", near), ("  — другие ящики —", far)]
    elif far:
        groups = [("  — здесь созревшего нет; другие ящики —", far)]
    else:
        groups = [(None, near)]
    for head, group in groups:
        if head:
            lines.append(head)
        for row, kinds, c in sorted(group, key=lambda it: sort_key(it[0])):
            lines.append(f"  {row.id}  {field_or(row, 'title', '(без title)')}")
            for kind, key in kinds:
                lines.append(f"      • {why_line(kind, key, row, c)}")
    lines.append("Это лежит в контексте, а НЕ на экране человека: назови дельту "
                 "вслух своими словами. Неназванная созревшая строка потеряна.")
    lines.append("`ack`, `taken` и `done` зовутся ТОЛЬКО по прямой просьбе "
                 "владельца: ассистент, погасивший дельту сам, уничтожает "
                 "строку при ненаступившей отработке.")
    print("\n".join(lines))
    return 0


def cmd_wake(a):
    """Хук не имеет права уронить старт сессии: падение = НОЛЬ ВЫВОДА.

    Радиус глобальный — старт ЛЮБОЙ сессии в любом проекте. Поэтому наружу
    всегда нуль и поэтому ловится всё: сломанный кэш, уехавший корень, чужой
    файл в ящике. Ни одно из этого не стоит отказа старта.
    """
    # stderr уводится в никуда на время прогона. Одного кода 0 мало: `die()`
    # успевает НАПЕЧАТАТЬ причину до того, как бросит SystemExit, и требование
    # спеки «падение = ноль ВЫВОДА» нарушается вторым потоком, а не первым.
    # Поймано укусом, а не чтением кода: первая редакция починки давала код 0 и
    # строку на stderr. Дельта идёт в stdout и уходит наружу как прежде.
    saved, sys.stderr = sys.stderr, open(os.devnull, "w", encoding="utf-8")
    try:
        return wake()
    except (Exception, SystemExit):
        # 🔴 SystemExit НЕ наследник Exception — он от BaseException. Голый
        # `except Exception` пропускал наружу ровно тот класс, ради которого
        # написан: die() бросает SystemExit, и путь wake → scan → boxes →
        # roots() → die(2) выводил хук кодом 2 с текстом на stderr НА КАЖДОМ
        # старте любой сессии. Вход не экзотический: файл корней, где все строки
        # закомментированы, — штатное конфигурационное состояние, и стенд сам
        # его строит. Второй такой путь — git вне PATH у процесса хука.
        # KeyboardInterrupt намеренно НЕ ловится: прерывание человеком не отказ.
        return 0
    finally:
        sys.stderr.close()
        sys.stderr = saved


def tomb_state():
    """Надгробие не растёт. Возвращает (текст, ok) по образцу hook_state().

    Дописку в конец выведенного файла предотвратить НЕЛЬЗЯ: сессия, помнящая
    ОТЛОЖКА.md по своему стартовому контексту, допишет туда молча и уедет — её
    правило лежит в CLAUDE.md, а он грузится один раз на старте. Предотвратить
    нельзя, увидеть можно, и это вся задача сторожа.

    Четыре состояния, и три из них — поломка. Зелёное одно: файл на месте,
    редирект в нём, длина в пределах потолка.
    """
    try:
        lines = TOMB.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        # Не «всё хорошо»: редирект и есть то единственное, чем останавливаются
        # живые сессии. Сессия, не нашедшая файла, заведёт отложку заново.
        return ("надгробие ПРОПАЛО: ОТЛОЖКА.md удалён — сессия, не нашедшая "
                "файла, заведёт отложку заново с чистого листа", False)
    except OSError as e:
        return (f"надгробие не прочиталось — {e}", False)
    if TOMB_ANCHOR not in "\n".join(lines):
        return (f"надгробие НЕ ПОСТАВЛЕНО: в ОТЛОЖКА.md нет «{TOMB_ANCHOR}» — "
                f"файл всё ещё источник правды", False)
    if len(lines) > TOMB_MAX_LINES:
        return (f"надгробие ВЫРОСЛО: {len(lines)} строк при потолке "
                f"{TOMB_MAX_LINES} — кто-то дописал в выведенный файл", False)
    return (f"надгробие цело: {len(lines)} строк, редирект на месте", True)


def hook_state():
    """Жива ли запись хука. Возвращает (текст, здорово ли).

    🔴 Судим РАЗБОРОМ, а не грепом по тексту. Подстрока «waiting.py wake» живёт
    и в `permissions.allow` (такие записи в этом файле уже есть), и во ВТОРОМ
    одноимённом ключе `SessionStart`, который разбор молча выбрасывает. Зелёный
    `doctor` при мёртвом хуке — это «молчащий реестр неотличим от пустого»,
    воспроизведённое в самом стороже, а `doctor` тут единственный сторож:
    своего отсутствия дельта не видит по построению.

    Читаем разбором, ПИШЕМ по-прежнему по якорю: инвариант 7 про запись.
    """
    try:
        raw = SETTINGS.read_text(encoding="utf-8")
    except OSError as e:
        return f"настройки не читаются — {e}", False
    try:
        d = json.loads(raw)
    except ValueError as e:
        return (f"настройки не разбираются как JSON ({e}) — харнесс игнорирует "
                f"файл ЦЕЛИКОМ, и ни одного хука сейчас нет"), False
    blocks = d.get("hooks", {}).get("SessionStart") or [] if isinstance(d, dict) else []
    live = any(HOOK_MARK in (h.get("command") or "")
               for b in blocks if isinstance(b, dict)
               for h in (b.get("hooks") or []) if isinstance(h, dict))
    if live:
        return "запись хука SessionStart на месте", True
    if HOOK_MARK in raw:
        return ("команда wake в настройках упомянута, но НЕ в живом блоке "
                "SessionStart — хук не зовётся никем, а греп по файлу сказал бы "
                "«на месте». Разобрать руками, куда она попала"), False
    return ("записи хука SessionStart НЕТ — реестр не будит никого, и молчащий "
            "реестр неотличим от пустого. Поставить: waiting.py doctor --install"), False


def install_hook():
    """Текстовая вставка ПО ЯКОРЮ (Р5). Никогда json.load → json.dump.

    Сериализация переписала бы файл целиком и затёрла главу сестринской сессии
    молча, без конфликта git, — то есть воспроизвела бы в собственном инструменте
    дефект №3 из «Задачи» спеки, ради которого реестр и пишется. Здесь
    вставляется одна строка после якоря; всё остальное остаётся байт в байт.

    Якорь не единственный — ОТКАЗ, а не вставка наугад: так же отказывает
    hand.sh на нескольких хендоффах ветки, потому что угадать хуже, чем не
    двигаться.
    """
    try:
        raw = SETTINGS.read_text(encoding="utf-8", newline="")
    except OSError as e:
        die(2, f"настройки не читаются — {e}")
    if HOOK_MARK in raw:
        print("запись хука уже на месте — ничего не меняю")
        return 0
    if '"SessionStart"' in raw:
        # Вставка первым ключом после якоря дала бы ВТОРОЙ одноимённый ключ, а
        # разбор оставляет последний: наш хук молча не работал бы, и doctor
        # по-прежнему говорил бы «на месте». Это тот самый дефект №3 из «Задачи»
        # спеки — затирание чужой главы, только не байтами, а дублем ключа.
        die(2, f"в {SETTINGS} уже есть ключ SessionStart, а нашей записи в нём "
               f"нет. Вставлять нельзя: два одноимённых ключа — это молча "
               f"выключенный хук. Вписать команду руками в СУЩЕСТВУЮЩИЙ блок:\n"
               f'            "command": "python3 $HOME/.claude/scripts/waiting.py wake",')
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
    hits = [i for i, ln in enumerate(lines) if ln.strip() == HOOK_ANCHOR]
    if len(hits) != 1:
        die(2, f"якорь {HOOK_ANCHOR!r} в {SETTINGS} найден {len(hits)} раз — "
               f"вставлять наугад нельзя. Вставить руками сразу после него:\n"
               f"{HOOK_BLOCK}")
    at = hits[0] + 1
    lines[at:at] = HOOK_BLOCK.rstrip("\n").split("\n")
    tmp = SETTINGS.with_name(f"{SETTINGS.name}.{os.getpid()}.tmp")   # pid: файл правят 4–6 сессий
    tmp.write_text(eol.join(lines), encoding="utf-8", newline="")
    os.replace(tmp, SETTINGS)
    print(f"запись хука вставлена в {SETTINGS} — по якорю, чужие ключи не тронуты")
    print("Проверить: новая сессия, и дельта обязана прийти в её контекст.")
    return 0


def cmd_doctor(a):
    """Жив ли механизм. Молчащий реестр неотличим от пустого.

    Отдельная команда для ЧЕЛОВЕКА, а не хук: единственный класс, который не
    виден изнутри дельты, — это отсутствие самой дельты. Поэтому первой строкой
    называется запись хука, а не состояние кэша.

    Возвращает 2 (конфигурация) при любой найденной поломке. До Задачи 5 это
    штатное состояние поставки: записи хука ещё нет, и doctor честно кричит.
    """
    if a.install:
        return install_hook()
    now = time.time()
    bad = 0
    text, ok = hook_state()
    print(("✅ " if ok else "🔴 ") + text)
    bad += 0 if ok else 1
    text, ok = tomb_state()
    print(("✅ " if ok else "🔴 ") + text)
    bad += 0 if ok else 1
    broken = registry_broken(now, any(probeable(r) for r in scan()))
    if broken:
        print(f"🔴 {broken}")
        bad += 1
    else:
        try:
            run = json.loads(RUN.read_text(encoding="utf-8"))
            print(f"✅ фон отчитался {run.get('finished_at')}: строк "
                  f"{run.get('rows')}, недостижимых {run.get('unreachable')}")
        except (OSError, ValueError):
            print("· фоновых прогонов ещё не было — это не поломка, это старт")
    if LOCK.is_dir():
        try:
            age = int(now - LOCK.stat().st_mtime)
        except OSError:
            age = -1
        print(f"· замок пробы занят {age} с (TTL {LOCK_TTL_S})")
    same = changed = 0
    for p in (sorted(CACHE.glob("*/*.json")) if CACHE.is_dir() else []):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        same += int(c.get("same_truth_runs") or 0)
        changed += int(c.get("changed_runs") or 0)
    total = same + changed
    if total:
        # Замер TTL (Р13): число выбирается наблюдением, а не оценкой.
        print(f"замер TTL (CACHE_TTL_S={CACHE_TTL_S}): прогонов {total}, "
              f"та же правда {same}, смена исхода {changed} — "
              f"{100 * changed // total}% смен")
        # 🔴 Прежняя подпись гласила «частое „то же самое“ значит TTL тесен» —
        # она принимала частоту событий за допустимую задержку. Число выбрано
        # решением с названным основанием, и подпись обязана это говорить,
        # иначе вывод учит выводу, который из него не следует.
        print("Это частота смен в мире, а НЕ довод о TTL: число выбрано "
              "требованием к дельте (на старте не старше часа).")
    else:
        print("замер TTL: прогонов ещё нет — числу не на чем выбраться")
    return 2 if bad else 0


def vanished(rows):
    """Пропажа из скана — событие, и печатается она ОДИН раз.

    Репозиторий уехал за корни, переименован или удалён — его строки перестают
    находиться, list печатает меньше, и никто не считает сколько. Кэш помнит
    виденные id и потому врать не может; ведённый список репозиториев — может.

    Зовётся со ВСЕМИ строками скана, включая снятые: иначе `done` выглядела бы
    пропажей и гасила бы собственный кэш при каждом list.
    """
    if not CACHE.is_dir():
        return
    live = {(r.box.repo_id, r.name) for r in rows}
    for d in sorted(CACHE.glob("*")):
        if not d.is_dir():
            continue
        # Следов у строки ДВА — `<id>.json` от probe и `<id>.seen.json` от wake, —
        # и оба принадлежат ОДНОМУ id. Голый `p.stem` давал у квитанции стем
        # `<id>.seen`, которого в live нет никогда: живая строка объявлялась
        # пропавшей, а квитанция гасилась вместе с фантомом. Замер 11.09 — по
        # двенадцать таких строк на прогоне, и настоящая пропажа, ради которой
        # эта функция и написана, тонула среди них. Собираем следы по имени
        # СТРОКИ, и тогда пропажа называется один раз, а забывается целиком.
        gone = {}
        for p in sorted(d.glob("*.json")):
            name = p.name[:-len(".seen.json")] if p.name.endswith(".seen.json") else p.stem
            if (d.name, name) in live:
                continue
            gone.setdefault(name, []).append(p)
        for name, traces in sorted(gone.items()):
            print(f"строка {d.name}/{name} пропала из скана — кэш о ней забыт")
            for p in traces:
                try:
                    p.unlink()
                except OSError:
                    pass


def resolve(arg, rows):
    """Голый NN принимается, ТОЛЬКО если разрешается однозначно.

    Два `20260908-01` в один день — норма, а не редкость: NN атомарен внутри
    каталога, а каталогов столько, сколько репозиториев. Угадать хуже, чем не
    двигаться: так же отказывает hand.sh кодом 6 на нескольких хендоффах ветки.
    """
    hits = [r for r in rows if (r.id == arg if "/" in arg else r.name == arg)]
    if not hits:
        die(2, f"нет строки {arg}. Что есть — `waiting.py list --all`")
    if len(hits) > 1:
        cands = "\n".join(f"  {r.id}  {r.path}" for r in sorted(hits, key=lambda r: r.id))
        die(2, f"id {arg} неоднозначен — строк с таким именем {len(hits)}:\n{cands}\n"
               f"Назвать полный: <repo-id>/{arg}")
    return hits[0]


def set_fields(path, pairs):
    """Правка франтматтера ПО КЛЮЧУ: своё меняем, чужое не трогаем.

    Перезаписью целиком нельзя — у файла один писатель, человек (инвариант 7), и
    его комментарии, порядок полей и тело обязаны пережить машинную правку. Та
    же дисциплина, что для файлов ~/.claude вообще: read-modify-write по якорю.

    Блочные скаляры не правятся никогда — ни `probe`, ни что-либо ещё
    многострочное: подмена одной строки оставила бы осиротевший отступ.
    """
    # split("\n"), а не splitlines(): последний делит ещё и по U+2028, NEL,
    # U+000C и U+001C, и вставленный из PDF символ после машинной правки стал
    # бы настоящим переводом строки в теле, написанном человеком.
    # newline="" обязателен: без него текстовый режим транслирует \r\n в \n ещё
    # до нас, и любая проверка «а был ли CRLF» отвечает «не было» ВСЕГДА. Своя
    # починка без этого была бы пустой — поймано укусом, а не чтением кода.
    raw = path.read_text(encoding="utf-8", newline="")
    # Окончание строк СОХРАНЯЕТСЯ. Иначе файл с CRLF после любой машинной правки
    # переписывался бы в LF целиком, и диффом это выглядело бы как «изменены все
    # строки» — правка по ключу перестала бы отличаться от перезаписи, то есть
    # инвариант 7 соблюдался бы только на словах. Хуже того, до этого правка
    # была ЧАСТИЧНОЙ: непереписанные строки хранили \r, а переписанная его
    # теряла, и файл уезжал в смешанные окончания.
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    end = None
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
    if end is None:
        die(1, f"{path}: франтматтер не закрыт — машина в такой файл не пишет")
    left = dict(pairs)
    for i in range(1, end):
        m = KEY.match(lines[i])
        if m and m.group(1) in left:
            # Хвостовой комментарий человека переживает правку. Спека приводит
            # его в СВОЁМ образце строки («review_by: … # машиной: +30»), а
            # докстринг обещает сохранность прямо; до починки stamp и done
            # стирали его молча, и в диффе это выглядело обычной правкой поля.
            old = m.group(2)
            mc = None if old.strip().startswith(('"', "'", "|", ">")) \
                else re.search(r"(\s+#.*)$", old)
            tail = mc.group(1) if mc else ""
            lines[i] = f"{m.group(1)}: {left.pop(m.group(1))}{tail}"
    for k, v in left.items():
        lines.insert(end, f"{k}: {v}")
        end += 1
    # Запись атомарная: write_text усекает файл ДО записи, и обрыв посередине
    # оставил бы от строки, купленной боем, половину — без резервной копии.
    # Имя временного файла НЕСЁТ pid — тот же класс, что починен в write_json и
    # install_hook. Писатели здесь — команды, которые зовёт человек, поэтому окно
    # уже; но класс тот же, а цена промаха выше: это файл ЧЕЛОВЕКА, а не кэш.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(eol.join(lines) + eol, encoding="utf-8", newline="")
    os.replace(tmp, path)


def field_or(row, key, default):
    f = row.fields.get(key)
    return f.value if f is not None else default


def iso_ts(s):
    try:
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return None


def faults_digest(row):
    """Отпечаток СОСТАВА причин брака — ключ квитанции класса «форма» (Р9).

    У формы нет начала серии во времени: она не событие, а состояние. Ключом
    служит сам набор причин. Сменился набор — квитанция сброшена, строка снова в
    дельте; иначе `ack` гасил бы и НОВУЮ дыру, появившуюся после квитанции.
    """
    why = [row.error] if row.error else sorted(row.faults)
    return hashlib.sha256("\n".join(why).encode("utf-8")).hexdigest()[:8]


def reasons(row, c, today, now):
    """Почему строка в дельте. Список пар (класс, ключ); пусто — не в дельте.

    Классов может быть несколько разом, и `ack` гасит их ВСЕ (Р11). `silent` в
    дельту не идёт никогда: честно молчащая проба и есть нормальное ожидание, а
    тревога по ней — та же ложь, что и молчание, только с другой стороны.
    """
    out = []
    # 🔴 Форма РАНЬШЕ состояния — тот же порядок, что в classify, и по той же
    # причине (Р8: недооформленная взятая строка громче, чем взятая). У
    # НЕПАРСЯЩЕЙСЯ он вдобавок единственно возможный: её `state` прочитан из
    # полей, набранных ДО ошибки, и «снята» из такого файла недостоверна.
    # Обратный порядок прятал строку, сломанную руками уже после `taken`, из
    # дельты НАВСЕГДА — при том что спека требует печатать непарсящуюся ВСЕГДА,
    # а починить её может только человек, которому про неё никто не скажет.
    if row.error or row.faults:
        out.append(("форма", faults_digest(row)))
    if state_of(row) in ("done", "taken"):
        return out          # исхода и срока у снятой и взятой не спрашиваем
    if c is not None:
        outcome, since = c.get("outcome"), (c.get("since") or "")
        if outcome == "fired":
            out.append(("fired", since))
        elif outcome == "unreachable":
            began = iso_ts(since)
            # Дольше суток (укус 10). Свежая недостижимость — это ssh, который
            # мигнул; дельта на каждый мигающий ssh обесценила бы дельту.
            if began is not None and now - began > STALE_UNREACHABLE_S:
                out.append(("unreachable", since))
    rb = day(row.fields.get("review_by"))
    if rb is not None and rb <= today:
        out.append(("срок", rb.isoformat()))
    return out


def ack_key(kinds):
    """Ключ квитанции — отпечаток ВСЕГО нынешнего состава причин, кроме срока.

    Квитанция гасит состояние, а не отдельную причину (Р11): любое изменение
    состава — новый исход вместо прежнего, добавившаяся дыра формы — даёт другой
    ключ, и строка снова в дельте. «Переход unreachable → fired печатается»
    выполняется отсюда даром.

    Срок в ключ НЕ входит: его гасит пере-штамп `review_by`, и следующее
    созревание по сроку — это следующая дата, сама себе ключ. Включи его — и
    пере-штамп сразу после квитанции изменил бы состав, то есть строка печаталась
    бы снова тем же вечером.
    """
    body = "\n".join(f"{k}={s}" for k, s in sorted(kinds) if k != "срок")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


def unacked(row, kinds):
    """Есть ли среди причин хоть одна НЕОТРАБОТАННАЯ."""
    if not kinds:
        return False
    if any(k == "срок" for k, _ in kinds):
        # Срок снова прошёл — значит это новое созревание, а не то же самое:
        # квитанция по сроку выражается пере-штампом, и он бы его отодвинул.
        return True
    a = row.fields.get("acked_key")
    return not (a is not None and a.value == ack_key(kinds))


def cmd_done(a):
    row = resolve(a.id, scan())
    if row.error:
        # Тот же сторож, что у stamp. Закрывающий --- на месте, а кавычка внутри
        # не закрыта — set_fields найдёт ограду и запишет в файл, которого разбор
        # не понял. Машина не правит непонятое: у файла один писатель, человек,
        # и починить франтматтер обязан он.
        die(1, f"{row.id}: франтматтер не разбирается ({row.error}) — "
               f"машина в такой файл не пишет; почини форму и повтори")
    if not a.because.strip():
        die(1, "надгробие без причины смерти не отвечает на вопрос, ради которого "
               "его хранят: «сработала» и «линия закрыта» — разные исходы")
    set_fields(row.path, [
        ("state", "done"),
        ("closed_at", datetime.now().date().isoformat()),
        ("closed_because", yaml_quote(a.because)),
    ])
    print(f"снята: {row.id} — {a.because}")
    return 0


def cmd_stamp(a):
    """Пере-вывести review_by по НЫНЕШНЕМУ полю probe.

    Существует ради строк, у которых проба выяснилась после заведения: `new`
    штампует +30, а строка становится `probe: none` позже. `ack` для этого не
    годится — он пишет acked_outcome, то есть утверждает, что строку посмотрели
    по существу. Здесь не посмотрели, здесь переклеили срок.
    """
    row = resolve(a.id, scan())
    if row.error:
        die(1, f"{row.id}: франтматтер не разбирается ({row.error}) — "
               f"срок машина в такой файл не пишет")
    probe = row.fields.get("probe")
    days = DAYS_NO_PROBE if (probe is not None and probe.value == "none") else DAYS_WITH_PROBE
    today = datetime.now().date()
    when = today + timedelta(days=days)
    set_fields(row.path, [("review_by", when.isoformat()), ("stamped_at", today.isoformat())])
    why = ("машинной пробы нет, срок — единственный датчик" if days == DAYS_NO_PROBE
           else "проба есть, срок — подстраховка")
    print(f"{row.id}: пересмотр {when} (+{days} — {why})")
    return 0


def cmd_taken(a):
    """Работа началась и НЕ кончилась (решение владельца 11.09.2026).

    `ack` («видел, ждём дальше») этого не описывает, `done` («ждать кончили»)
    лжёт о завершённости. Строка в `taken` не будит и в дельту не идёт, но из
    `list` не исчезает: работа видна, пока не закрыта.

    Р23: `done`-строка принимается. Это исправление ошибочного закрытия, а не
    воскрешение, и надгробие при переводе СОХРАНЯЕТСЯ — его писал человек своим
    словом, а стереть значит спрятать, что строку однажды закрыли.
    """
    row = resolve(a.id, scan())
    if row.error:
        die(1, f"{row.id}: франтматтер не разбирается ({row.error}) — "
               f"машина в такой файл не пишет; почини форму и повтори")
    if not a.because.strip():
        die(1, "запись без причины не отвечает на вопрос, ради которого её "
               "хранят: чем именно началась работа и по какому событию")
    set_fields(row.path, [
        ("state", "taken"),
        ("taken_at", datetime.now().date().isoformat()),
        ("taken_because", yaml_quote(a.because)),
    ])
    print(f"взята в работу: {row.id} — {a.because}")
    return 0


def cmd_ack(a):
    """Квитанция: гасит ВСЕ нынешние причины созревания разом (Р11).

    🔴 Квитанцию ставит ВЛАДЕЛЕЦ, не ассистент. Существует полностью
    «корректный» прогон, где ассистент прочитал дельту, не назвал её человеку и
    погасил — строка исчезает навсегда при ненаступившей отработке. Механически
    это не удержать (сторож дороже сторожимого), поэтому правило сказано вслух
    и повторяется в выводе `wake`.
    """
    row = resolve(a.id, scan())
    if row.error:
        # Непарсящаяся строка гасится только руками: машина не пишет в то, чего
        # не разобрала (инвариант 7). Она будет в дельте каждый старт — это
        # самый громкий класс, и починить его может только человек.
        die(1, f"{row.id}: франтматтер не разбирается ({row.error}) — "
               f"квитанцию машина в такой файл не пишет; почини форму")
    today = datetime.now().date()
    # 🔴 Гасим то, что дельта НАПЕЧАТАЛА, а не то, что в реестре сейчас. Между
    # печатью и словом «ack» фон успевает сменить исход — и именно тогда, когда
    # кэш устарел, то есть в тот же момент, когда дельту и читают. Квитанции нет
    # (дельта эту строку не печатала, либо файл нечитаем) — работаем по нынешнему
    # составу, ровно как до починки. Подробности и форма — в seen_of.
    seen = seen_of(row)
    if seen is None:
        kinds = reasons(row, cache_of(row), today, time.time())
        closed, key = sorted({k for k, _ in kinds}), ack_key(kinds)
    else:
        closed, key = sorted(set(seen["kinds"])), seen["key"]
        kinds = closed
    if not kinds:
        print(f"{row.id}: гасить нечего — строка в дельту не идёт")
        return 0
    pairs = []
    if "срок" in closed:
        probe = row.fields.get("probe")
        days = (DAYS_NO_PROBE if probe is not None and probe.value == "none"
                else DAYS_WITH_PROBE)
        when = today + timedelta(days=days)
        pairs += [("review_by", when.isoformat()), ("stamped_at", today.isoformat())]
    pairs += [("acked_at", today.isoformat()),
              ("acked_outcome", "+".join(closed)),
              ("acked_key", key)]
    set_fields(row.path, pairs)
    if seen is not None:
        # Квитанция дельты израсходована. Оставленная, она заглушила бы БУДУЩЕЕ
        # событие: следующий `ack` погасил бы по ключу позавчерашней печати.
        try:
            seen_path(row).unlink()
        except OSError:
            pass
    print(f"{row.id}: квитанция — закрыто «{'+'.join(closed)}»")
    if "срок" in closed:
        print(f"  срок пересмотра переклеен на {pairs[0][1]}")
    return 0


def classify(row, today, now):
    """Группа строки. Созрелость ВЫЧИСЛЯЕТСЯ (инвариант 2), не хранится.

    Порядок развилок — не вкусовой:
    форма → срок → есть ли кэш → свеж ли он → что он говорит.
    Срок раньше кэша, потому что review_by и есть страховка на случай, когда
    проба врёт в сторону тишины; кэш раньше исхода, потому что «не спрашивали»
    и «спросили, пусто» — разные ответы (инвариант 3).
    """
    if row.error or row.faults:
        return "недооформленные"
    if state_of(row) == "taken":
        # Р8: своя группа, последняя в порядке печати. Печатать её в вычисленной
        # группе значило бы поставить строку с прошедшим сроком в «созрело» — то
        # есть просить действия по работе, которая уже идёт. Форма проверяется
        # РАНЬШЕ: недооформленная взятая строка громче, чем взятая.
        return "взята в работу"
    rb = day(row.fields.get("review_by"))
    if rb is not None and rb <= today:
        return "созрело"
    c = cache_of(row)
    if c is None:
        return "ни разу не опрошена"
    ts = c.get("last_run_at_ts")
    if c.get("last_rc") not in (0, None) or not isinstance(ts, (int, float)) \
            or now - ts > 3 * CACHE_TTL_S:
        # Молчащий реестр неотличим от пустого, а пустой — нормальное
        # состояние, поэтому тревогу не поднимет никто. Отсюда отдельная группа.
        return "данные протухли"
    outcome = c.get("outcome")
    if outcome == "fired":
        return "созрело"
    # Умолчание — ГРОМКАЯ сторона. «Ни разу не опрошена» здесь означало бы,
    # что про строку, которую спрашивали и получили ответ, реестр говорит «не
    # спрашивали» — ровно конфляция, помеченная инвариантом 3. Форма кэша
    # объявлена контрактом для 2-2 здесь, и умолчание она унаследует.
    return {"silent": "молчит", "unreachable": "недостижима"}.get(
        outcome, "данные протухли")


def line_of(row, group):
    title = row.fields.get("title")
    head = f"  {row.id}  {title.value if title else '(без title)'}"
    marks = []
    rb = row.fields.get("review_by")
    if rb is not None:
        marks.append(f"пересмотр {rb.value}")
    probe = row.fields.get("probe")
    if probe is not None and probe.value == "none":
        marks.append("машинной пробы нет, созреет только сроком")
    sample = row.fields.get("sample")
    if sample is not None and sample.value == "pending":
        marks.append("образца нет, отрицательный ответ ничего не доказывает")
    entry = row.fields.get("entry")
    if entry is not None and entry.value != "none":
        marks.append(entry.value)
    if state_of(row) == "done":
        why = row.fields.get("closed_because")
        marks.insert(0, "снята: " + (why.value if why else "причина не названа"))
    if state_of(row) == "taken":
        why = row.fields.get("taken_because")
        marks.insert(0, "взята в работу: " +
                     (why.value if why else "причина не названа"))
        # Р23: строка, закрытая по ошибке и переведённая в taken, СОХРАНЯЕТ
        # надгробие. Стереть его значило бы спрятать, что строку однажды
        # закрыли, — а писал его человек своим словом.
        was = row.fields.get("closed_at")
        if was is not None:
            marks.append(f"закрывалась {was.value}, закрытие отменено")
    out = [head + (("   [" + " · ".join(marks) + "]") if marks else "")]
    if group == "недооформленные":
        for why in ([row.error] if row.error else row.faults):
            out.append(f"      ⚠ {why}")
        out.append(f"      файл: {row.path}")
    return "\n".join(out)


def cmd_list(a):
    today = datetime.now().date()
    now = time.time()
    rows = scan()
    buckets = {g: [] for g in GROUPS}
    for r in rows:
        if state_of(r) == "done" and not a.all:
            continue
        buckets[classify(r, today, now)].append(r)
    printed = 0
    for g in GROUPS:
        rs = sorted(buckets[g], key=sort_key)
        if not rs:
            continue
        print(f"— {g} ({len(rs)}) —")
        for r in rs:
            print(line_of(r, g))
        printed += len(rs)
    if printed == 0:
        print("реестр пуст")
    vanished(rows)      # со ВСЕМИ строками, включая снятые
    # Код 1 возвращается ПОСЛЕ полной печати. Упасть на первой недооформленной
    # значило бы заглушить вывод реестра для всех шести сессий; пропустить её —
    # спрятать до review_by, то есть устроить ту самую тишину.
    return 1 if buckets["недооформленные"] else 0


def display_path(p):
    """Путь репозитория для entry (Р13) — путь ВСЕГДА, `~` только как сокращение.

    Голое имя репозиторий не локализует: корней скана может быть несколько, и
    одноимённые каталоги под разными корнями — тот самый класс, ради которого
    идентификатор сделан глобальным. Спека приводит единственный конкретный
    образец entry — с путём: `~/dev/rk_bot · main`. Формат один и не зависит от
    места: промежуточный вариант «под домом путь, вне дома имя» отвергнут — два
    формата в одном поле хуже любого одного, а путь вне дома в боевом случае не
    встречается никогда (корень по умолчанию, Р7, — единственный `~/dev`).
    """
    # Обе стороны РАЗРЕШАЮТСЯ. Путь репозитория приходит из worktree_main уже
    # разрешённым, а Path.home() отдаёт HOME как есть: на macOS это /var/... и
    # /private/var/... — сравнение проваливалось, и `~` не подставлялось вовсе.
    # В бою промах тихий: корень ~/dev не через симлинк, и ветка молчала бы до
    # первого дома за симлинком. Поймано укусом «entry сокращает дом до ~».
    p = pathlib.Path(p).resolve()
    try:
        return "~/" + str(p.relative_to(pathlib.Path.home().resolve()))
    except ValueError:
        return str(p)


def claim_name(d, today):
    """Атомарный захват имени. O_EXCL — единственное, что различает два `new` в
    одну секунду: проверка exists() перед записью проигрывает гонку молча.

    Имя обязано остаться формы YYYYMMDD-NN (инвариант 9): дописать pid значит
    пройти укус и сломать ссылочный идентификатор, на который смотрят хендоффы,
    память и сестринские сессии.
    """
    stem = today.strftime("%Y%m%d")
    for n in range(1, 100):
        path = d / f"{stem}-{n:02d}.md"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            continue
        os.close(fd)
        return path.stem
    die(2, f"в {d} за {stem} уже 99 строк — сотую заводить нечем: "
           f"форма имени YYYYMMDD-NN двузначна и не расширяется")


TEMPLATE = """---
title: {title}
state: waiting
review_by: {review_by}
stamped_at: {stamped_at}
entry: {entry}
---

<!-- Дозаполнить. Пока полей нет, строка висит в группе «недооформленные».
Подсказка нарочно с отступом: без него греп по началу строки не отличит её от
настоящего поля, и укус «new не придумывает probe» проходил бы впустую.

  host: local            local | имя хоста | none при probe: none
  cwd: ~/dev/…           каталог, из которого проба запускается; none при probe: none
  probe: |               ОДНА команда, без && и ; ; либо строкой `probe: none`
    …
  ripe_match: "…"        регулярка по stdout пробы; none при probe: none
  ripe_when: "…"         ТО САМОЕ решение прозой, а не его окрестность
  sample: "…"            наблюдение, где проба показала ОБА исхода; либо pending;
                         none при probe: none — образец пробы без пробы это обещание

Если машинной пробы нет — поставить `probe: none` и позвать
`waiting.py stamp {name}`: срок станет +7 дней, потому что без пробы он
остаётся единственным датчиком. -->

Тело: что наблюдалось, чем куплено, что делать по созревании.
"""


def cmd_new(a):
    box = home_box() if a.global_box else repo_box()
    box.dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date()
    name = claim_name(box.dir, today)
    entry = yaml_quote(f"{display_path(box.repo)} · {box.branch or '?'}") if box.repo else "none"
    path = box.dir / f"{name}.md"
    path.write_text(TEMPLATE.format(
        title=yaml_quote(a.title),
        review_by=(today + timedelta(days=DAYS_WITH_PROBE)).isoformat(),
        stamped_at=today.isoformat(),
        entry=entry,
        name=name,
    ), encoding="utf-8")
    print(f"заведена: {box.repo_id}/{name}")
    print(f"файл:     {path}")
    print("дозаполнить: host · cwd · probe · ripe_match · ripe_when · sample.")
    print("Пока их нет, list держит строку в «недооформленных» и возвращает 1.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="waiting", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="завести строку")
    p_new.add_argument("title", help="заголовок строки, по-русски")
    # dest обязателен: `global` — ключевое слово Python, a.global не разбирается.
    p_new.add_argument("--global", dest="global_box", action="store_true",
                       help="строка без проекта — в ~/.claude/waiting/")
    p_new.set_defaults(fn=cmd_new)

    p_list = sub.add_parser("list", help="что ждёт события снаружи")
    p_list.add_argument("--all", action="store_true", help="показать и снятые строки")
    p_list.set_defaults(fn=cmd_list)

    p_done = sub.add_parser("done", help="снять строку")
    p_done.add_argument("id", help="<repo-id>/YYYYMMDD-NN либо голый YYYYMMDD-NN")
    p_done.add_argument("because", help="почему снята — обязательно")
    p_done.set_defaults(fn=cmd_done)

    p_stamp = sub.add_parser("stamp", help="пере-вывести срок по нынешней probe")
    p_stamp.add_argument("id", help="<repo-id>/YYYYMMDD-NN либо голый YYYYMMDD-NN")
    p_stamp.set_defaults(fn=cmd_stamp)

    p_probe = sub.add_parser("probe", help="опросить строки (зовётся фоном)")
    p_probe.set_defaults(fn=cmd_probe)

    p_taken = sub.add_parser("taken", help="работа началась и не кончилась")
    p_taken.add_argument("id", help="<repo-id>/YYYYMMDD-NN либо голый YYYYMMDD-NN")
    p_taken.add_argument("because", help="чем началась работа — обязательно")
    p_taken.set_defaults(fn=cmd_taken)

    p_ack = sub.add_parser("ack", help="квитанция: видел, ждём дальше")
    p_ack.add_argument("id", help="<repo-id>/YYYYMMDD-NN либо голый YYYYMMDD-NN")
    p_ack.set_defaults(fn=cmd_ack)

    p_wake = sub.add_parser("wake", help="дельта в контекст (зовётся хуком)")
    p_wake.set_defaults(fn=cmd_wake)

    p_doctor = sub.add_parser("doctor", help="жив ли механизм реестра")
    p_doctor.add_argument("--install", action="store_true",
                          help="поставить запись хука SessionStart по якорю")
    p_doctor.set_defaults(fn=cmd_doctor)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
