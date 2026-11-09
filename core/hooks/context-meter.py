#!/usr/bin/env python3
"""Каждый ход показывает размер контекста сессии и два события смены задачи.

Агент не умеет самодетектить, что его контекст дорос до полумиллиона токенов:
у него нет показания. Та же болезнь, что у параллельности в `_parallel.md`, и
то же лечение — факт печатается хуком `UserPromptSubmit`, а не живёт правилом,
которое надо помнить.

Контекст = input + cache_write + cache_read последнего хода главного цикла:
именно эта сумма перечитывается на КАЖДОМ следующем ходу и составляет
основную часть счёта (замер: `~/.claude/scripts/context-spend.py`).

`ctx:` — состояние, а не событие: оно ни с чем не сравнивается. Поэтому рядом
печатаются два СОБЫТИЯ, оба машинные и даром:

1. **смена ветки** с прошлого хода — недостающий механизм правила «новая
   проблема = новая ветка И новая сессия» (`derflow/_parallel.md`);
2. **возврат после паузы в дорогой контекст** — опасен не разрыв сам по себе,
   а разрыв в большой контекст: именно тогда на старую дорогую сессию цепляют
   новую задачу.

Прошлый ход лежит в `~/.claude/state/<session_id>.json`: ветка берётся из
файла, пауза — из его mtime. Файл на сессию, поэтому сестринские сессии не
топчут друг друга.
"""
import json, os, re, subprocess, sys, time

TAIL_BYTES = 4_000_000       # хвост транскрипта; полный файл бывает сотнями МБ
WARN, LOUD = 150_000, 300_000
# Вторая полоса в сессии = граница СЕССИЙ (derflow/SKILL.md). Замер 14.09.2026:
# 137 сессий со вторым анонсом потратили ПОСЛЕ него $29k из $55,7k всего счёта,
# а по полосе второго анонса разрыв восьмикратный — A $26 и D $34 за сессию
# против B $243, C $198, Dx $309, F $679. Отсюда и список исключений.
ANNOUNCE = re.compile(r"\*{0,2}Lane\s+([^\n\u2192]{1,40}?)\s*\u2192")
STAY = ("A", "D")            # тривиальное и консультация чинятся ЗДЕСЬ
PAUSE_SEC = 2 * 3600         # ниже — перерыв, а не возврат к отложенной задаче
STALE_SEC = 30 * 86_400      # мёртвые файлы состояния
STATE_DIR = os.path.expanduser("~/.claude/state")


def tail_lines(path):
    """Хвост транскрипта строками. Отдельно от разбора: за один вызов хука он
    нужен и контексту, и детектору анонсов — читать файл дважды незачем."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
                f.readline()          # выбросить обрезанную строку
            return f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None


def lanes(lines):
    """Полосы анонсов по порядку. Только ТЕКСТ ассистента: в tool_result лежит
    сам SKILL.md с шаблоном «Lane `<id>` → `<agent>`» и совпал бы (урок cost.py).
    Сабагент отсеивается — его анонс не наш.

    Хвост в 4 МБ: у очень длинной сессии первый анонс может из него выпасть, и
    тогда детектор просто не сработает. Промолчать здесь дешевле, чем соврать.
    Проверка по корпусу 14.09.2026: детектор видит 104 перехода из 137 найденных
    полным проходом (76%), остальные срезал хвост. Это потолок, а не поломка.
    """
    out = []
    for line in lines or ():
        if '"assistant"' not in line or "Lane" not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        for b in (d.get("message") or {}).get("content") or []:
            if not (isinstance(b, dict) and b.get("type") == "text"):
                continue
            m = ANNOUNCE.search(b.get("text", ""))
            if m:
                out.append(m.group(1).replace("`", "").strip(" *"))
                break
    return out


def context_from(lines):
    for line in reversed(lines or []):
        if '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain"):      # сабагент держит свой контекст, не наш
            continue
        u = (d.get("message") or {}).get("usage") or {}
        if not u:
            continue
        return (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                + u.get("cache_read_input_tokens", 0))
    return None


def last_context(path):
    return context_from(tail_lines(path))


def current_branch(cwd):
    """Своим вызовом, а не разбором чужого вывода: в транскрипте на месте ветки
    лежит ТЕКСТ команды соседнего хука, и парсер его однажды уже съел."""
    try:
        p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=cwd or None, capture_output=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode:                  # не репозиторий / нет коммитов
        return None
    return p.stdout.decode("utf-8", "replace").strip() or None


def read_state(path):
    """Прошлый ход: (ветка, когда). Время — mtime файла, отдельного поля нет."""
    try:
        ts = os.path.getmtime(path)
    except OSError:
        return None, None
    try:
        with open(path) as f:
            return (json.load(f) or {}).get("branch"), ts
    except (OSError, ValueError):
        return None, ts


def write_state(path, branch, first_turn):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump({"branch": branch}, f)
        os.replace(tmp, path)         # атомарно: сестринские сессии не увидят полфайла
    except OSError:
        return
    if first_turn:                    # жатва раз за сессию, а не каждый ход
        reap(path)


def reap(keep):
    cutoff = time.time() - STALE_SEC
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    for name in names:
        p = os.path.join(STATE_DIR, name)
        try:
            if p != keep and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass                      # чужая сессия могла удалить его первой


def ago(sec):
    if sec < 3600:
        return f"{sec / 60:.0f}м"
    if sec < 86_400:
        return f"{sec / 3600:.0f}ч"
    return f"{sec / 86_400:.0f}д"


def loud_msg():
    """Один текст на оба входа: порог, названный дважды по-разному, — два правила."""
    return ("‼ расщепи сессию САМ: доведи хендофф до «здесь и сейчас» и позови "
            "~/.claude/scripts/hand.sh <каталог> (derflow/_capture.md)")


def lane2_msg(lane):
    return (f"‼ вторая полоса в сессии ({lane}) — она открывается НОВОЙ сессией: "
            "допиши хендофф до «здесь и сейчас» и позови "
            "~/.claude/scripts/hand.sh <каталог> [файл] (derflow/SKILL.md)")


def claim(latch):
    """Защёлка «один раз за сессию». Гонку выигрывает тот, кто создал файл."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        os.close(os.open(latch, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
    except FileExistsError:
        return False
    except OSError:
        return True                   # защёлку не поставили — лучше дважды, чем ни разу
    return True


def main_tool():
    """Вход для `PostToolUse`. Печатает РОВНО ОДИН РАЗ за сессию — каждое из двух.

    🔴 Зачем отдельный вход. `UserPromptSubmit` меряет на РЕПЛИКЕ, а дорожает
    сессия на ХОДАХ. Замер 12.09.2026, `V·хвосты слияния` (82cae91b): одна
    человеческая реплика, 404 хода, контекст 55k → 488k, cache-read 113,5M —
    и метр отработал ровно один раз, на 55k. То есть он слеп именно в том
    случае, который дороже всего: в длинном автономном прогоне. Последняя треть
    ходов там стоила 48% счёта.

    Печатается один раз, а не на каждом вызове: сказать 178 раз — это не
    громче, это фон, который перестают читать. Защёлка — отдельный файл, а не
    поле в состоянии: `write_state` перезаписывает его целиком на каждой
    реплике, и поле бы стёрлось.
    """
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    session = payload.get("session_id")
    if not session:
        return 0
    loud_latch = os.path.join(STATE_DIR, f"{session}.loud")
    lane2_latch = os.path.join(STATE_DIR, f"{session}.lane2")
    need_loud = not os.path.exists(loud_latch)
    need_lane2 = not os.path.exists(lane2_latch)
    # Дешёвая сторона вперёд: когда обе защёлки стоят, транскрипт не читается.
    if not (need_loud or need_lane2):
        return 0
    lines = tail_lines(payload.get("transcript_path") or "")

    out = []
    # Событие вперёд уровня: смена полосы — это ПЕРЕХОД, и он адресный,
    # тогда как «ctx: 384k» лишь состояние. Порог 300k тут сработать не успевает:
    # медиана контекста на втором анонсе — 182k, он ловит 27 сессий из 137.
    if need_lane2:
        seen = lanes(lines)
        # Сравнение ТОЧНОЕ по первому токену: `startswith` посчитал бы `Dx`
        # исключением по букве D, а Dx вторым анонсом — $309 за сессию.
        head = re.split(r"[\s\u00b7(,]", seen[1], maxsplit=1)[0] if len(seen) >= 2 else ""
        if len(seen) >= 2 and head not in STAY and claim(lane2_latch):
            out.append(lane2_msg(seen[1]))
    if need_loud:
        n = context_from(lines)
        if n and n >= LOUD and claim(loud_latch):
            out.append(f"ctx: {n / 1000:.0f}k {loud_msg()}")
    if out:
        print("\n".join(out))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    n = last_context(payload.get("transcript_path") or "")
    branch = current_branch(payload.get("cwd"))
    session = payload.get("session_id")

    out = []
    if n:
        msg = f"ctx: {n / 1000:.0f}k"
        if n >= LOUD:
            msg += " " + loud_msg()
        elif n >= WARN:
            msg += " ⚠ дальше каждый ход платит за этот контекст"
        out.append(msg)

    if session:
        path = os.path.join(STATE_DIR, f"{session}.json")
        prev_branch, prev_ts = read_state(path)
        if prev_branch and branch and prev_branch != branch:
            out.append(f"⚠ ветка: {prev_branch} → {branch} — другая проблема? "
                       "Тогда своя сессия (derflow/_parallel.md)")
        if prev_ts and n and n >= WARN and time.time() - prev_ts >= PAUSE_SEC:
            out.append(f"↩ возврат через {ago(time.time() - prev_ts)} в контекст "
                       f"{n / 1000:.0f}k — новую задачу лучше в свою сессию")
        write_state(path, branch, first_turn=prev_ts is None)

    if out:
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main_tool() if "--tool" in sys.argv else main())
