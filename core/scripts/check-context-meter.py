#!/usr/bin/env python3
"""Сторож детектора второго анонса в `hooks/context-meter.py`.

    python3 core/scripts/check-context-meter.py     # хук того же чекаута, что и стенд
    METER=/путь/к/копии python3 core/scripts/check-context-meter.py

Молчит только целиком зелёным; каждая проба печатает строку. Зовётся руками
после правки метра — бегунка тестов в этом репозитории нет.

Пробы держат три ловушки, на которых детектор ломается молча: `Dx` против `D`
(startswith посчитал бы Dx исключением по букве D, а это $309 за сессию),
анонс САБАГЕНТА (не наша полоса) и шаблон «Lane <id> → <agent>» из tool_result
— в нём лежит сам SKILL.md, и наивный греп совпадает на нём.

🔴 «Молчит» не стоит одно (25.11.2026, DF-22): на заглушке были зелёны все пять
таких проб. Каждой в том же прогоне добавлен ход контекстом 400k — хук обязан
сказать о пороге и промолчать о второй полосе.

🔴 Замеры после правки (25.11.2026, DF-22, 10 проб). Живой из ворктри — в шелле
ztui, в чистой среде и с подложенным ZCODE_SESSION_ID — ✅ 10 ❌ 0, выводы
равны. METER= заглушки — ✅ 0 ❌ 10 (до правки ✅ 5 ❌ 4). METER= хука с
выключенным детектором — ✅ 6 ❌ 4: пробы 1 и 4, защёлка и укус про файл. Мутации
копии: возвращённый путь через ~/.claude и вызов мимо H — по ✅ 9 ❌ 1, ровно
укус про файл; снятый env.pop в run() — из ztui ✅ 9 ❌ 1 (проба про порог), из
чистой среды ✅ 10 ❌ 0. Сломанный хук ворктри: из ворктри ✅ 6 ❌ 4.
"""
import json, os, re, subprocess, sys, tempfile

# 🔴 Испытываемый файл — ИЗ СВОЕГО ЧЕКАУТА: от __file__ физическим путём; хук
# лежит уровнем выше (стенд — в core/scripts, хук — в core/hooks). METER=
# подменяет его копией. Прежний путь, ~/.claude/hooks/context-meter.py, — симлинк
# на КОРЕНЬ: стенд, пущенный из ворктри, гонял живой хук корня, был зелёным на
# любой правке ворктри и молчал о ней (25.11.2026, DF-22).
HERE = os.path.dirname(os.path.realpath(__file__))
OWN = os.path.join(os.path.dirname(HERE), "hooks", "context-meter.py")
H = os.environ.get("METER") or OWN
NAMED = "METER" in os.environ
SD = os.path.expanduser("~/.claude/state")

# 🔴 Статическая половина укуса про файл — стенд читает свой текст без
# комментариев: каждое упоминание интерпретатора в списке (`sys.executable`,
# `"python3"`) ведёт сразу на H либо на опцию — программа не из файла ("-", "-c").
# Сравнить H с его же определением — тавтология: вызов мимо переменной оставил
# бы живую половину зелёной, а первая строка называла бы «свой» файл. Пределы:
# строковая форма запуска и список, собранный раньше вызова, не видны; текст
# внутри строк читается как код — ложное красное громкое.
def bypass():
    with open(os.path.realpath(__file__), encoding="utf-8") as f:
        code = "\n".join(line.split("#", 1)[0] for line in f)
    for m in re.finditer(r'''(sys\.executable|["']python3?["'])(\s*,\s*([^\s,\]\)]+))?''', code):
        arg = m.group(3)
        if arg is None or (arg != "H" and not arg.startswith("-")):
            return f"запуск мимо переменной пути: {m.group(0).strip()}"
    return ""
byp = bypass()

# Первая строка прогона: по одному логу видно, какой файл и в каком чекауте
# проверен. Без METER= это файл того же чекаута, что и стенд, с METER= — копия.
print(f"испытываемый файл: {H} — {'по METER=' if NAMED else 'тот же чекаут, что и стенд'}\n")

ok = True; good_n = 0; bad_n = 0
def judge(name, good):
    global ok, good_n, bad_n
    if not good: ok = False
    good_n += good; bad_n += not good
    print(f"  {'✅' if good else '❌'} {name}")

def turn(text=None, usage=None, sidechain=False, role="assistant"):
    rec = {"type": role, "isSidechain": sidechain,
           "message": {"model": "claude-opus-5", "content": [], "usage": usage or {}}}
    if text: rec["message"]["content"] = [{"type": "text", "text": text}]
    return json.dumps(rec, ensure_ascii=False)

def run(records, sid):
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd)
    open(path, "w", encoding="utf-8").write("\n".join(records) + "\n")
    # ZCODE_SESSION_ID снимается при каждом запуске: по нему хук переходит на
    # контракт ZCode — JSON и пороги 130k/170k. Для хука правильно, для стенда —
    # чужой приказ: проба про порог написана про контракт Claude Code (300k).
    env = dict(os.environ); env.pop("ZCODE_SESSION_ID", None)
    p = subprocess.run([sys.executable, H, "--tool"], input=json.dumps(
        {"session_id": sid, "transcript_path": path, "cwd": "/tmp"}),
        capture_output=True, text=True, env=env)
    os.unlink(path)
    return p.stdout.strip()

def unhook(sid):   # защёлки пробы — в живом ~/.claude/state, снимаются до и после
    for suf in (".loud", ".lane2"):
        f = os.path.join(SD, sid + suf)
        if os.path.exists(f): os.unlink(f)

U = {"input_tokens": 10, "cache_read_input_tokens": 50_000}
LOUD = {"input_tokens": 10, "cache_read_input_tokens": 400_000}   # выше 300k обоих контрактов
SPEAK = "вторая полоса"
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
sids = []
for n, (name, recs, expect) in enumerate(cases):
    sid = "t-" + name[:8].replace(" ", ""); sids.append(sid)
    unhook(sid)
    # «Молчит» — с положительной половиной: тот же прогон говорит о пороге.
    out = run(recs if expect else recs + [turn("что-то", LOUD)], sid)
    got = SPEAK in out
    judge(name, got == expect and (expect or "‼ расщепи сессию САМ" in out))
    if n == 0: first = got

# 🔴 Какой файл здесь проверяется. Из ворктри стенд гонял живой хук КОРНЯ и был
# зелёным на любой правке ворктри (25.11.2026, DF-22). Живая половина: путь —
# файл своего чекаута либо назван METER=, и он же дал первый выстрел — заглушке
# здесь зеленеть нечего. Статическая — у определения H: вызов мимо переменной
# виден только по тексту стенда.
if first and not byp and (NAMED or H == OWN):
    judge("🔴 испытываемый файл — тот же чекаут, что и стенд (или назван METER=), и он же дал первый выстрел", True)
else:
    print(f"  ❌ 🔴 испытываемый файл: {H} — вне своего чекаута, запуск мимо переменной пути или первый выстрел не получен"
          f"{'; ' + byp if byp else ''}")
    ok = False; bad_n += 1

# защёлка: второй вызов молчит
sid = "t-latch"; unhook(sid)
recs = [turn("Lane Dx → x — потому что", U), turn("Lane C → openspec — потому что", U)]
a, b = run(recs, sid), run(recs, sid)
judge("защёлка: печатает один раз за сессию", SPEAK in a and b == "")

# громкий порог по-прежнему работает — и в контракте Claude Code: вывод зовёт
# ~/.claude/scripts/hand.sh, и ни одна строка не начинается с «{» (JSON —
# контракт ZCode, в него хук переходит по ZCODE_SESSION_ID).
sid = "t-loud"; unhook(sid)
out = run([turn("что-то", LOUD)], sid)
judge("порог 300k не сломан, вывод — контракт Claude Code",
      "‼ расщепи сессию САМ" in out and ".claude/scripts/hand.sh" in out
      and not any(line.startswith("{") for line in out.splitlines()))
for sid in sids + ["t-latch", "t-loud"]: unhook(sid)
print(f"\nитог: ✅ {good_n} ❌ {bad_n}")
sys.exit(0 if ok else 1)
