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

    bl-wake.py            хук: кэш + фоновое обновление
    bl-wake.py --now      прогнать пробы сейчас и напечатать (руками)

Скрипт исполняет пробы из файлов задач — это код из ТВОЕГО репозитория,
та же модель доверия, что у `waiting.py`.
"""
import datetime, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 20
STALE = 30 * 60
BLOCK = re.compile(r"```when\s*\n(.*?)\n```", re.S)


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


def main():
    root = sh(["git", "rev-parse", "--show-toplevel"]).stdout.strip()
    common = sh(["git", "rev-parse", "--path-format=absolute",
                 "--git-common-dir"]).stdout.strip()
    if not root or not os.path.exists(os.path.join(root, "backlog")):
        return 0
    cache = os.path.join(common, "bl-wake.cache")
    if "--now" in sys.argv or "--refresh" in sys.argv:
        lines = refresh(root)
        tmp = cache + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        os.replace(tmp, cache)
        if "--now" in sys.argv:
            print("\n".join(lines) if lines else "backlog: тихо")
        return 0
    try:
        age = time.time() - os.path.getmtime(cache)
        lines = open(cache, encoding="utf-8").read().strip()
    except OSError:
        age, lines = None, ""
    if lines:
        when = f"{int(age // 60)} мин назад" if age is not None else ""
        print(f"backlog (пробы {when}):\n{lines}")
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
