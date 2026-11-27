#!/usr/bin/env python3
"""Что созрело в колонке Backlog. Хук SessionStart проекта и ручной вызов.

Задача статуса Backlog несёт в описании «почему не сейчас» и, по желанию,
блок пробы:

    ```when
    host: mprz            # local по умолчанию; иначе ssh-хост
    cwd: /home/deralsem   # по умолчанию корень репозитория (для local)
    match: pay_for_event  # необязательно: регэксп по выводу пробы
    ---
    journalctl -u bot-gmp --since today
    ```

Созрело — проба вышла с 0 (и вывод совпал с match, если он задан).
Срок пересмотра — поле Due Date задачи: наступил → строка в выводе, даже
без пробы. Молчит, когда сказать нечего: на старте сессии каждая строка
должна что-то значить, иначе вывод перестанут читать.

Пробы бывают по ssh и медленные, поэтому хук их НЕ ждёт: печатает итог
прошлого прогона из кэша (в общем git-каталоге, виден всем ворктри) и
отцепляет свежий прогон в фон, если кэшу больше 30 минут.

    bl-wake.py                   хук: кэш + фоновое обновление
    bl-wake.py --overdue         то же, 📂 построчно
    bl-wake.py --now             прогнать пробы сейчас и напечатать (руками)
    bl-wake.py --now --overdue   прогнать и напечатать всё

Форма (с 27.11.2026, DF-29): 🟢 и ⚪ — по строке и вперёд; 📂 — наступивший
срок пересмотра (имя категории: в кэше эти строки под 📅), состояние, а не
переход (в кэше gmb_v2 на 27.11.2026 — 79 📂 против 14 🟢), поэтому одной
строкой счёта по месяцам. Кэш хранит список целиком, форма применяется
при печати.

Контракты сред: Claude Code читает plain stdout, ZCode — только JSON
{"additionalContext": …}, plain выбрасывает молча (обёртка emit(), канон
паттерна — context-meter.py:emit). JSON — только в режиме хука: ручные
ключи читает терминал, ему plain всегда. Печатается один раз: две печати
ZCode не довезёт.

Регистрация: Claude Code — проектный .claude/settings.json (docflow/setup.md,
шаг 5); ZCode проектный слой хуков не читает (zcode-cli 0.18.0) — запись
глобальная, ~/.zcode/cli/config.json → hooks.events.SessionStart, руками.
Вне docflow-репо (нет backlog/) хук молчит сам, потому глобальная запись
безвредна. Стенд — bl-wake-bite.sh, обёртку держит check-hook-emit.py.

Скрипт исполняет пробы из файлов задач — это код из ТВОЕГО репозитория,
та же модель доверия, что у `waiting.py`.
"""
import datetime, json, os, re, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 20
STALE = 30 * 60
BLOCK = re.compile(r"```when\s*\n(.*?)\n```", re.S)
DUE = re.compile(r"\(был (\d{4})-(\d{2})-(\d{2})\)\s*$")
MONTHS = ("январь февраль март апрель май июнь июль август "
          "сентябрь октябрь ноябрь декабрь").split()


def sh(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True,
                          errors="replace", **kw)


def backlog_json(*args):
    p = sh(["backlog", *args, "--json"])
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def parse_block(text):
    m = BLOCK.search(text or "")
    if not m:
        return None
    head, _, script = m.group(1).partition("\n---\n")
    if not script:
        return None
    f = {}
    for line in head.splitlines():
        # комментарий — только через два пробела: `#` бывает в самом match
        # (re.escape превращает его в `\#`), и срезать по нему нельзя
        line = re.sub(r"\s{2,}#.*$", "", line).strip()
        if ":" in line:
            k, v = line.split(":", 1)
            f[k.strip()] = v.strip()
    f["script"] = script
    return f


def probe(f, root):
    host = f.get("host", "local")
    cwd = f.get("cwd") or (root if host == "local" else "~")
    where = cwd if cwd.startswith("~") else f"'{cwd}'"
    script = f"cd {where} || exit 91\n{f['script']}\n"
    argv = ["bash", "-o", "pipefail", "-s"]
    if host != "local":
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                host, *argv]
    try:
        p = sh(argv, input=script, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "unreachable", f"потолок {TIMEOUT} с"
    except OSError as e:
        return "unreachable", f"нечем спросить: {e.strerror}"
    if p.returncode in (91, 255, 127):
        why = {91: f"нет cwd {cwd}", 255: "ssh отказал", 127: "нет команды"}
        return "unreachable", why[p.returncode]
    if p.returncode != 0:
        return "quiet", ""
    pat = f.get("match")
    try:
        if pat and not re.search(pat, p.stdout):
            return "quiet", ""
    except re.error as e:
        return "unreachable", f"плохой match: {e}"
    hit = ""
    if pat:
        hit = next((l for l in p.stdout.splitlines() if re.search(pat, l)), "")
    return "ripe", hit[:120]


def check(t, root, today):
    try:
        return _check(t, root, today)
    except Exception as e:  # одна кривая задача не роняет весь прогон
        return f"⚪ проба не дошла {t.get('id')} · {type(e).__name__}: {e}"


def _check(t, root, today):
    tid, title = t["id"], t["title"]
    full = backlog_json("task", "view", tid) or {}
    task = full.get("task", full)
    f = parse_block(task.get("description", ""))
    if f:
        state, note = probe(f, root)
        if state == "ripe":
            return f"🟢 созрело {tid} · {title}" + (f" · {note}" if note else "")
        if state == "unreachable":
            return f"⚪ проба не дошла {tid} · {note}"
    due = t.get("dueDate")
    if due and due <= today:
        return f"📅 срок пересмотра {tid} · {title} (был {due})"
    return None


def refresh(root):
    lst = backlog_json("task", "list", "--status", "Backlog") or {}
    today = datetime.date.today().isoformat()
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda t: check(t, root, today), lst.get("tasks", [])))
    return [r for r in res if r]


def emit(text, zcode):
    """Вывод по контракту среды: Claude Code читает plain stdout, ZCode — только
    JSON с additionalContext, plain она молча выбрасывает (канон паттерна —
    hooks/context-meter.py:emit, замер 09.11.2026)."""
    if zcode:
        print(json.dumps({"additionalContext": text}, ensure_ascii=False))
    else:
        print(text)


def summary(due):
    """📂 одной строкой: сколько сроков наступило, с какого по какой, по месяцам;
    дата не разобралась — ведро «без даты»."""
    found = [DUE.search(l) for l in due]
    got = [m.groups() for m in found if m and 1 <= int(m[2]) <= 12]
    span = "–".join(f"{d}.{m}" for _, m, d in (min(got), max(got))) if got else "без дат"
    by = Counter(int(m) for _, m, _ in got)
    months = " · ".join(f"{MONTHS[k - 1]} {n}" for k, n in sorted(by.items()))
    if len(got) < len(due):
        months += f" · без даты {len(due) - len(got)}"
    return (f"📅 наступивших сроков пересмотра {len(due)} ({span}): {months}; "
            "построчно — bl-wake.py --overdue")


def show(lines, full):
    """Форма вывода: 🟢 вперёд, ⚪ за ними в порядке кэша, 📂 — одной строкой
    счёта; full — список целиком, как хранится в кэше."""
    if full:
        return list(lines)
    due = [l for l in lines if l.startswith("📅")]
    ripe = [l for l in lines if l.startswith("🟢")]
    rest = [l for l in lines if not l.startswith(("📅", "🟢"))]
    return ripe + rest + ([summary(due)] if due else [])


def main():
    root = sh(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    common = sh(["git", "rev-parse", "--path-format=absolute",
                 "--git-common-dir"]).stdout.strip()
    if not root or not os.path.exists(os.path.join(root, "backlog")):
        return 0
    cache = os.path.join(common, "bl-wake.cache")
    full = "--overdue" in sys.argv
    if "--now" in sys.argv or "--refresh" in sys.argv:
        lines = refresh(root)
        tmp = cache + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        os.replace(tmp, cache)
        if "--now" in sys.argv:
            emit("\n".join(show(lines, full)) or "backlog: тихо", False)
        return 0
    try:
        age = time.time() - os.path.getmtime(cache)
        lines = open(cache, encoding="utf-8").read().strip()
    except OSError:
        age, lines = None, ""
    if lines:
        when = f"{int(age // 60)} мин назад" if age is not None else ""
        text = "\n".join([f"backlog (пробы {when}):",
                          *show(lines.splitlines(), full)])
        emit(text, bool(os.environ.get("ZCODE_SESSION_ID")))
    if age is None or age > STALE:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--refresh"],
                         cwd=root, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # хук старта не имеет права ронять сессию
        print(f"bl-wake: {e}", file=sys.stderr)
        sys.exit(0)
