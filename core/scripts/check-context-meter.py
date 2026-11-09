#!/usr/bin/env python3
"""Сторож детектора второго анонса в `hooks/context-meter.py`.

Молчит только целиком зелёным; каждая проба печатает строку. Зовётся руками
после правки метра — бегунка тестов в этом репозитории нет.

Пробы держат три ловушки, на которых детектор ломается молча: `Dx` против `D`
(startswith посчитал бы Dx исключением по букве D, а это $309 за сессию),
анонс САБАГЕНТА (не наша полоса) и шаблон «Lane <id> → <agent>» из tool_result
— в нём лежит сам SKILL.md, и наивный греп совпадает на нём.
"""
import json, os, subprocess, sys, tempfile
H = os.path.expanduser("~/.claude/hooks/context-meter.py")
SD = os.path.expanduser("~/.claude/state")

def turn(text=None, usage=None, sidechain=False, role="assistant"):
    rec = {"type": role, "isSidechain": sidechain,
           "message": {"model": "claude-opus-5", "content": [], "usage": usage or {}}}
    if text: rec["message"]["content"] = [{"type": "text", "text": text}]
    return json.dumps(rec, ensure_ascii=False)

def run(records, sid):
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    open(path, "w", encoding="utf-8").write("\n".join(records) + "\n")
    p = subprocess.run([sys.executable, H, "--tool"], input=json.dumps(
        {"session_id": sid, "transcript_path": path, "cwd": "/tmp"}),
        capture_output=True, text=True)
    os.unlink(path)
    return p.stdout.strip()

U = {"input_tokens": 10, "cache_read_input_tokens": 50_000}
cases = [
 ("две полосы, вторая B — стреляет",
  [turn("Lane Dx → debugging — потому что", U), turn("Lane B → сам — потому что", U)], True),
 ("две полосы, вторая A — молчит",
  [turn("Lane Dx → debugging — потому что", U), turn("Lane A → сам — потому что", U)], False),
 ("две полосы, вторая D · консультация — молчит",
  [turn("Lane Dx → x — потому что", U), turn("Lane D · консультация → system-architect — потому что", U)], False),
 ("две полосы, вторая Dx — СТРЕЛЯЕТ (не путать с D)",
  [turn("Lane B → сам — потому что", U), turn("Lane Dx · диагностика → x — потому что", U)], True),
 ("одна полоса — молчит",
  [turn("Lane C → openspec — потому что", U)], False),
 ("вторая полоса у САБАГЕНТА — молчит",
  [turn("Lane C → openspec — потому что", U),
   turn("Lane B → сам — потому что", U, sidechain=True)], False),
 ("шаблон из tool_result не считается",
  [turn("Lane C → openspec — потому что", U),
   json.dumps({"type":"user","message":{"content":[{"type":"tool_result",
     "content":"> **Lane `<id>` → `<agent/skill>` — потому что**"}]}}, ensure_ascii=False)], False),
]
ok = True
for name, recs, expect in cases:
    sid = "t-" + name[:8].replace(" ", "")
    for suf in (".loud", ".lane2"):
        f = os.path.join(SD, sid + suf)
        if os.path.exists(f): os.unlink(f)
    got = "вторая полоса" in run(recs, sid)
    mark = "ок" if got == expect else "ПРОВАЛ"
    if got != expect: ok = False
    print(f"  {mark:6} {name}")

# защёлка: второй вызов молчит
sid = "t-latch"
for suf in (".loud", ".lane2"):
    f = os.path.join(SD, sid + suf)
    if os.path.exists(f): os.unlink(f)
recs = [turn("Lane Dx → x — потому что", U), turn("Lane C → openspec — потому что", U)]
a, b = run(recs, sid), run(recs, sid)
mark = "ок" if ("вторая полоса" in a and b == "") else "ПРОВАЛ"
if mark == "ПРОВАЛ": ok = False
print(f"  {mark:6} защёлка: печатает один раз за сессию")

# громкий порог по-прежнему работает
sid = "t-loud"
for suf in (".loud", ".lane2"):
    f = os.path.join(SD, sid + suf)
    if os.path.exists(f): os.unlink(f)
out = run([turn("что-то", {"input_tokens": 10, "cache_read_input_tokens": 400_000})], sid)
mark = "ок" if "‼ расщепи сессию САМ" in out else "ПРОВАЛ"
if mark == "ПРОВАЛ": ok = False
print(f"  {mark:6} порог 300k не сломан")
for suf in (".loud", ".lane2"):
    for sid in ("t-latch", "t-loud"):
        f = os.path.join(SD, sid + suf)
        if os.path.exists(f): os.unlink(f)
print("\nИТОГ:", "всё зелено" if ok else "ЕСТЬ ПРОВАЛЫ")
sys.exit(0 if ok else 1)
