#!/usr/bin/env python3
"""Каждый ход сверяет канон derflow В КОНТЕКСТЕ сессии с каноном НА ДИСКЕ.

Замер v4.17 (`derflow/_capture.md`) показал устройство доставки: скилл входит в
сессию ровно один раз, а компакт не перечитывает файл, а переприкрепляет тот же
снимок. Правило, дописанное в канон сейчас, не догоняет ни одной идущей сессии,
и «перечитывай канон», положенное в сам канон, — замкнутый круг: его же и не
прочтут. Свежим бывает только то, что читают в момент нужды, поэтому сверку
делает хук, читающий диск сам, каждый ход, и вся инструкция едет В СТРОКЕ.

Два разных предиката, потому что два разных способа доставки:

* `SKILL.md` приезжает СНИМКОМ и живёт в контексте целиком — сверяется
  СОДЕРЖИМЫМ. Время здесь не годится: на каждой границе компакта аттач
  `invoked_skills` кладёт СТАРЫЙ текст со СВЕЖЕЙ отметкой, и предикат по
  времени замолчал бы ровно там, где снимок протух сильнее всего (боевое:
  сессия 135ea3d2 прожила 06→17.08 через четыре компакта на снимке v3.21);
* движки `_*.md` приезжают обычным чтением файла и в контексте не обновляются —
  сверяются ВРЕМЕНЕМ: правка на диске новее последнего съедения.

Собственная правка канона не считается устареванием: сессия, которая сама
писала файл, знает, что в нём. Отличить чтение от записи по имени инструмента
нельзя — в `~/.claude` канон правят через `Bash` не реже, чем через `Edit`, —
поэтому авторство не выясняется вовсе. Вместо него окно снисхождения: правка,
случившаяся в пределах минуты после того, как сессия трогала файл, сделана этой
же сессией. Слепое пятно в минуту не стоит ничего: дрейф, который ловим,
меряется часами и днями (медиана жизни снимка — 12 промптов, боевой случай —
десять дней).

Молчит при совпадении. Говорит только при доказанном расхождении — и говорит
о СОБЫТИИ, а не о состоянии: одна строка на одно приземление канона, а не на
каждый ход. Замер по 185 сессиям, съевшим канон: предикат по состоянию дал бы
750 строк на 3518 промптов (21%), по событию — 68 (2%) при том же наборе
пойманных сессий (46). Различающая сила не потеряна, потерян только повтор.
Отказ назван: печатать каждый ход соблазнительно тем, что непрочитанный канон
опасен и после первой строки, — но `derflow/_gates.md` называет цену прямо:
тревога, которую промотали сто раз, перестаёт читаться, и настоящая поломка
тонет в шуме.

Прошлое расхождение лежит в `~/.claude/state/<session_id>.canon.json` — файл на
сессию, поэтому сестринские сессии не топчут друг друга (тот же приём, что у
`context-meter.py`).
"""
import json, os, sys, glob, hashlib

# Каталог переопределяем ради стенда укуса: живой `~/.claude` правят несколько
# сессий разом, и мутировать настоящий канон ради проверки нельзя.
SKILLDIR = os.environ.get("CANON_DRIFT_SKILLDIR") or os.path.expanduser(
    "~/.claude/skills/derflow")
SKILL = "SKILL.md"
GRACE = 60          # с; правка в пределах минуты после касания — своя же
STATE_DIR = os.path.expanduser("~/.claude/state")
# archive/CHANGELOG.md намеренно вне канона: это история, а не правила
# поведения, и она не грузится в контекст на каждой задаче.


def canon():
    """{имя: (mtime, первая строка-заголовок, тело)} по файлам канона."""
    out = {}
    for p in glob.glob(os.path.join(SKILLDIR, "*.md")):
        name = os.path.basename(p)
        if name != SKILL and not name.startswith("_"):
            continue
        try:
            mtime = os.path.getmtime(p)
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        head = next((ln.strip() for ln in text.splitlines() if ln.startswith("# ")), None)
        if not head:
            continue
        out[name] = (mtime, head, text[text.index(head):])
    return out


# Снимок скилла — цельный текст файла. Всё, что короче, маркер лишь УПОМИНАЕТ:
# сессия, изучающая сам канон, печатает его заголовок в свой же транскрипт, и
# без порога вывод собственной диагностики опознаётся как снимок. Боевое: первый
# же прогон стенда покраснел на 747-символьном куске вывода grep.
MIN_SNAPSHOT = 5000


def snapshots(node, head, found):
    """Снимок лежит то в `message.content[].text`, то в
    `attachment.skills[].content` — обходим запись целиком, а не гадаем поле."""
    if isinstance(node, dict):
        for v in node.values():
            snapshots(v, head, found)
    elif isinstance(node, list):
        for v in node:
            snapshots(v, head, found)
    elif isinstance(node, str):
        i = node.find(head)
        if i >= 0 and len(node) - i >= MIN_SNAPSHOT:
            found.append(node[i:])


def ts(rec):
    t = rec.get("timestamp") or ""
    # 2026-08-06T18:11:34.814Z — сравниваем как строки только внутри одного
    # формата, поэтому переводим в число честно.
    try:
        import datetime
        return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan(path, files):
    """Один проход. Возвращает (последний снимок SKILL.md, {имя: время касания})."""
    heads = {name: h for name, (_, h, _) in files.items()}
    snap, seen = None, {}
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None, {}
    with f:
        for line in f:
            if "derflow" not in line:            # дешёвый пред-фильтр
                continue
            hit = [n for n, h in heads.items() if h in line]
            is_tool = '"tool_use"' in line
            paths = [n for n in files if is_tool and f"derflow/{n}" in line] if is_tool else []
            if not (hit or paths):
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            t = ts(rec)
            if t is None:
                continue
            for n in hit + paths:
                seen[n] = max(seen.get(n, 0), t)
            if SKILL in hit and "toolUseResult" not in rec:
                # результат инструмента — это ЭХО канона, а не его доставка
                found = []
                snapshots(rec, heads[SKILL], found)
                if found:
                    snap = found[-1]        # последний по порядку, а не длиннейший
    return snap, seen


def drifted(path, files):
    snap, seen = scan(path, files)
    if not seen:                                 # канон в этой сессии не звали
        return []
    out = []
    for name, (mtime, _, body) in sorted(files.items()):
        if name not in seen:
            continue
        if name == SKILL and snap is not None:
            if body not in snap:                 # снимок несёт не то, что на диске
                out.append(name + " (снимок)")
            continue
        if mtime > seen[name] + GRACE:
            out.append(name)
    return out


def signature(bad, files):
    """Отпечаток расхождения. Меняется, когда канон приземляется заново, —
    тогда строка законно повторяется."""
    parts = []
    for name in bad:
        base = name.split(" ")[0]
        mtime, _, body = files[base]
        parts.append(f"{name}:{int(mtime)}:{hashlib.sha1(body.encode()).hexdigest()[:12]}")
    return "|".join(parts)


def statefile(session):
    return os.path.join(STATE_DIR, f"{session}.canon.json")


def remembered(session):
    try:
        with open(statefile(session)) as f:
            return (json.load(f) or {}).get("sig")
    except (OSError, ValueError):
        return None


def remember(session, sig):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = statefile(session) + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"sig": sig}, f)
        os.replace(tmp, statefile(session))       # атомарно
    except OSError:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    path = payload.get("transcript_path") or ""
    if not path:
        return 0
    files = canon()
    if not files:
        return 0
    bad = drifted(path, files)
    sig = signature(bad, files)
    session = payload.get("session_id")
    if session:
        was = remembered(session)
        if sig == was:
            return 0                             # об этом расхождении уже сказали
        if sig or was is not None:
            # сессия без дрейфа файла состояния не заводит: канон не звало
            # подавляющее большинство сессий, и сорить на каждую незачем.
            # Жатву делает `context-meter.py` — он подчищает весь `state/`.
            remember(session, sig)
    if bad:
        print("⟳ канон derflow уехал на диске: " + ", ".join(bad)
              + " — перечитай эти файлы до следующего решения")
    return 0


if __name__ == "__main__":
    sys.exit(main())
