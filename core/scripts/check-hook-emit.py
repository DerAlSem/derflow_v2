#!/usr/bin/env python3
"""Сторож JSON-обёртки вывода хуков (контракт ZCode, 09.11.2026).

ZCode выбрасывает plain stdout хука молча — в контекст идёт только
{"additionalContext": …}. Обёртку ставит emit() в каждом хуке по
ZCODE_SESSION_ID (канон паттерна — hooks/context-meter.py). Зовётся руками
после правки хуков, как check-context-meter.py: бегунки тестов в репо нет.

Каждая проба гонит хук ДВАЖДЫ на одинаковых входах: без ZCODE_SESSION_ID
(контракт Claude Code — plain) и с ним (контракт ZCode — ровно один JSON).
Равенство полезной нагрузки — главное условие: текст сообщения проверяют
свои сторожа, здесь проверяется только проводка.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timedelta

SC = os.path.dirname(os.path.realpath(__file__))
HOOKS = os.path.join(os.path.dirname(SC), "hooks")
SD = os.path.expanduser("~/.claude/state")
PY = sys.executable
ok = True


def mark(name, good):
    global ok
    if not good:
        ok = False
    print(f"  {'ок' if good else 'ПРОВАЛ':6} {name}")


def run(script, payload, env_extra, cwd=None, args=()):
    """Один вызов хука. Возвращает (stdout, код возврата)."""
    env = dict(os.environ)
    env.pop("ZCODE_SESSION_ID", None)
    env.update(env_extra)
    p = subprocess.run([PY, script, *args], input=json.dumps(payload),
                       capture_output=True, text=True, env=env, cwd=cwd, timeout=60)
    return p.stdout, p.returncode


def both_ways(name, script, payload, env_extra=None, cwd=None, args=(),
              allow_empty=False, absent=None):
    """Хук в двух контрактах. Пустой plain — только при allow_empty; непустой —
    zcode-режим обязан быть РОВНО ОДНОЙ строкой JSON с той же полезной
    нагрузкой. absent — чего в plain быть не должно (ловит «зелёный» прогон,
    говорящий лишнее)."""
    plain, rc_p = run(script, payload, env_extra or {}, cwd, args)
    # Свой session_id на второй контракт: защёлки «уже сказали» (у canon-drift)
    # и квитанции дельты гасили бы второй прогон первого — это не проводка.
    pay_z = dict(payload)
    if isinstance(pay_z.get("session_id"), str):
        pay_z["session_id"] += "-z"
    zout, rc_z = run(script, pay_z, {**(env_extra or {}), "ZCODE_SESSION_ID": "t-emit"},
                     cwd, args)
    good = rc_p == rc_z and (absent is None or absent not in plain)
    if plain == "":
        good = good and zout == "" and allow_empty
    else:
        try:
            doc = json.loads(zout)
            good = good and list(doc) == ["additionalContext"] \
                and doc["additionalContext"] == plain.strip() \
                and zout.count("\n") <= 1
        except ValueError:
            good = False
    mark(name, good)
    if not good:
        print(f"        plain: {plain[:120]!r}\n        zcode: {zout[:120]!r}")


tmp = tempfile.mkdtemp(prefix="chk-emit-")
try:
    # --- canon-budget: перерасход и зелёный канон ----------------------------
    D = os.path.join(tmp, "canon")
    os.makedirs(D)
    for f in "_lane-c.md", "_gates.md", "_capture.md", "_ship.md", "_parallel.md":
        open(os.path.join(D, f), "w").write("# h\n" + "x\n" * 200)
    # absent="канон:": память — глобальный индекс, фикстурой не подменить, и её
    # строка (если есть) в равенстве участвует, а на «канон молчит» не мешает.
    both_ways("canon-budget: перерасход — один JSON со всеми 🔴",
              os.path.join(SC, "canon-budget.py"), {}, {"CANON_BUDGET_DIR": D})
    for f in os.listdir(D):
        open(os.path.join(D, f), "w").write("# h\n")
    both_ways("canon-budget: зелёный канон — без канон-строк, JSON равен plain",
              os.path.join(SC, "canon-budget.py"), {}, {"CANON_BUDGET_DIR": D},
              allow_empty=True, absent="канон:")

    # --- canon-drift: движок на диске новее касания в транскрипте -------------
    D2 = os.path.join(tmp, "drift")
    os.makedirs(D2)
    open(os.path.join(D2, "SKILL.md"), "w").write("# derflow — роутер\n")
    gates = os.path.join(D2, "_gates.md")
    open(gates, "w").write("# derflow · гейты\n")
    fd, transcript = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    old = (datetime.now() - timedelta(hours=2)).isoformat()
    rec = {"type": "assistant", "timestamp": old, "message": {"content": [
        {"type": "tool_use", "input": {"file_path": "/x/derflow/_gates.md"}}]}}
    open(transcript, "w", encoding="utf-8").write(json.dumps(rec) + "\n")
    os.utime(gates)          # правка «случилась» после касания — дрейф
    both_ways("canon-drift: дрейф — JSON",
              os.path.join(HOOKS, "canon-drift.py"),
              {"session_id": "t-emit-drift", "transcript_path": transcript},
              {"CANON_DRIFT_SKILLDIR": D2})
    os.utime(gates, (time.time() - 7200, time.time() - 7200))   # касание свежее правки
    both_ways("canon-drift: совпадает — молчит в обоих",
              os.path.join(HOOKS, "canon-drift.py"),
              {"session_id": "t-emit-drift2", "transcript_path": transcript},
              {"CANON_DRIFT_SKILLDIR": D2}, allow_empty=True)
    os.unlink(transcript)

    # --- waiting wake: созревшая строка на стендовом доме ---------------------
    W = os.path.join(tmp, "waiting")
    repo = os.path.join(W, "dev", "repo1")
    box = os.path.join(repo, ".claude", "waiting")
    os.makedirs(box)
    subprocess.run(["git", "init", "-q", repo], check=True)
    open(os.path.join(W, "waiting-roots.txt"), "w").write(os.path.join(W, "dev") + "\n")
    open(os.path.join(box, "20261101-01.md"), "w", encoding="utf-8").write(
        "---\n"
        "title: \"стендовая строка ради проверки обёртки\"\n"
        "state: waiting\n"
        "review_by: 2026-11-05\n"
        "stamped_at: 2026-11-01\n"
        "entry: none\n"
        "host: none\n"
        "cwd: none\n"
        "probe: none\n"
        "ripe_match: none\n"
        "ripe_when: \"никогда — строка стендовая\"\n"
        "sample: none\n"
        "---\n\nСтенд check-hook-emit.\n")
    # cwd=repo в ОБОИХ прогонах: с ним порядок «этот репозиторий» один и тот же
    # в plain (cwd процесса) и в zcode (ZCODE_PROJECT_DIR) — иначе равенство
    # текстов ломалось бы на различии заголовков, а не на проводке.
    both_ways("waiting wake: дельта — JSON, порядок «этот репозиторий»",
              os.path.join(SC, "waiting.py"), {}, {"WAITING_HOME": W,
              "ZCODE_PROJECT_DIR": repo}, cwd=repo, args=("wake",),
              absent="другие ящики")

    # --- stale-root: падение сторожа и не-git каталог -------------------------
    nowhere = tempfile.mkdtemp(prefix="chk-emit-nowhere-")
    shutil.rmtree(nowhere)
    both_ways("stale-root: падение — JSON с 🔴",
              os.path.join(SC, "stale-root.py"), {"cwd": nowhere})
    both_ways("stale-root: не git — молчит в обоих",
              os.path.join(SC, "stale-root.py"), {"cwd": tmp}, allow_empty=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    for f in os.listdir(SD) if os.path.isdir(SD) else []:
        if f.startswith("t-emit-"):
            try:
                os.unlink(os.path.join(SD, f))
            except OSError:
                pass

print("\nИТОГ:", "всё зелено" if ok else "ЕСТЬ ПРОВАЛЫ")
sys.exit(0 if ok else 1)
