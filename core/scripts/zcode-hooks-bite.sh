#!/usr/bin/env bash
# Стенд укуса записей derflow в ~/.zcode/cli/config.json (DF-30): install.sh
# сверяет их с эталоном hosts/zcode/hooks.json и правит текстом внутри hooks
# (core/scripts/zcode-hooks.py).
#
#   bash core/scripts/zcode-hooks-bite.sh
#   ZCODE_HOOKS=/путь/к/хелперу bash core/scripts/zcode-hooks-bite.sh   # заглушка, мутант
#   ZCODE_SCHEMA_GUARD=/путь/к/сторожу bash core/scripts/zcode-hooks-bite.sh   # заглушка, мутант сторожа
#
# Зачем в репозитории, а не в скрэтчпаде, и три правила укуса (отрицательное
# спаяно с положительным; искомое не встречается в фикстуре и путях стенда;
# заглушка обязана краснеть) — в шапке waiting-bite.sh. Действуют и здесь.
# «Файл не тронут» само по себе зелёно и заглушке, поэтому каждый укус несёт
# половину, которую даёт только настоящий хелпер: «файл изменился как ждём»
# или флаг changed («стенд за прогон правил файл стенда»).
#
# Контур — поддельный HOME и ключ --zcode-dir <стенд>: install.sh правит файл
# стенда S/cli/config.json. Приманка — H/.zcode/cli/config.json с другим
# содержимым: туда install.sh пошёл бы без --zcode-dir. Живой ~/.zcode/cli/
# config.json стенд не открывает: снимает его отпечаток (байты, mtime) до и
# после. Фикстуры — эталон с мутацией, ключ plugins в них отформатирован
# не так, как пишет CLI: пересериализация всего файла это выдаст.
#
# Сторож схемы CLI — глава «схема CLI». Хелпер судит файл по EVENTS и трём
# правилам, а схема CLI живёт в бандлах и меняется без этого репозитория.
# Сторож schema.py (каталог стенда) читает каждый объект events живого бандла
# — dist клона и десктопного Resources/glm/zcode.cjs, каждый сам по себе — и
# сверяет с EVENTS хелпера: EVENTS читает из него как данные, кодом не пользуется.
# Расхождение — «CLI обновился — правь EVENTS и CLI_SCHEMA». Бандла нет —
# «пропущено», в зачёт не идёт (⏭ в итоговой строке). Пути бандлов — свои
# переменные ZCODE_SCHEMA_ZTUI и ZCODE_SCHEMA_DESKTOP.
#
# 🔴 ЗАМЕРЫ (28.11.2026, 43 укуса). Каждая строка — отдельный прогон:
#
#   zcode-hooks.py с правками ...................... ✅ 43 ❌  0
#   заглушка (exit 0, молчит) ...................... ✅  0 ❌ 43
#   мутация: is_derflow → True ..................... ✅ 41 ❌  2   — глава «чужая запись», оба её укуса
#   мутация: файл пересериализуется ................ ✅ 41 ❌  2   — «байты вне hooks»: правка и вставка ключа
#   мутация: --check пишет ......................... ✅ 42 ❌  1   — «--check не пишет»
#   мутация: живой файл не сверяется со схемой ..... ✅ 39 ❌  4   — глава «файл, который CLI не читает», все четыре укуса об отказе
#   мутация: не замечает пропавшей записи .......... ✅ 31 ❌ 12   — семья «записи нет», все её 12 укусов
#   мутация: не видит расхождения matcher .......... ✅ 41 ❌  2   — «расходится matcher», оба её укуса
#   мутация: не снимает лишнюю ..................... ✅ 41 ❌  2   — «лишняя запись derflow», оба её укуса
#   заглушка сторожа (exit 0, молчит) .............. ✅ 32 ❌ 11   — глава «схема CLI», все 11 укусов
#   мутация: сторож не видит расхождений ........... ✅ 37 ❌  6   — шесть укусов главы «схема CLI» о расхождениях
#   мутация: сторож всегда видит расхождение ....... ✅ 33 ❌ 10   — глава «схема CLI» без укуса о нечитаемом источнике
#   мутация: EVENTS с лишним SessionEnd ............ ✅ 35 ❌  8   — четыре равенства и «лишнее событие» главы «схема CLI», три укуса об отказе по чужому событию
#
# Расхождение с числами после правки укусов или хелпера разбирать, а не
# переписывать молча.
#
# Оснастка та же, что в install-bite.sh: run гоняет install.sh и кладёт вывод
# в $out, код в $rc; has/nohas смотрят $out; is печатает вердикт. Разборы
# JSON — fx.py (каталог стенда): своих проверок у bash нет, а кодом хелпера
# стенд не пользуется — он под испытанием.
set -u
HERE="$(cd -P "$(dirname "$0")" && pwd)"      # физический core/scripts: ~/.claude/scripts — симлинк
IREPO="$(cd -P "$HERE/../.." && pwd)"
I="$IREPO/install.sh"
HOOKS="${ZCODE_HOOKS:-$IREPO/core/scripts/zcode-hooks.py}"
REF="$IREPO/hosts/zcode/hooks.json"
ROOT="$(mktemp -d)"; trap 'rm -rf "$ROOT" 2>/dev/null || true' EXIT
H="$ROOT/home"                                 # живые каталоги — только в поддельном доме
S="$H/zcode stand"                             # пробел в пути
C="$S/cli/config.json"                         # файл стенда: его и правит install.sh
DECOY="$H/.zcode/cli/config.json"              # приманка
LIVE="$HOME/.zcode/cli/config.json"            # живой: только отпечаток
ZTUI_BUNDLE="${ZCODE_SCHEMA_ZTUI:-$HOME/dev/ZCode/apps/zcode-cli/packages/cli/dist/zcode.cjs}"
DESKTOP_BUNDLE="${ZCODE_SCHEMA_DESKTOP:-/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs}"
GUARD="${ZCODE_SCHEMA_GUARD:-$ROOT/schema.py}"   # сторож схемы CLI: подмена — заглушка, мутант
mkdir -p "$S/cli" "$H/.zcode/cli"
echo "испытуемый файл: $HOOKS"

cat > "$ROOT/fx.py" <<'PY'
"""Фикстуры и разборы стенда: fx.py <команда> …; код 0 — верно, 1 — нет."""
import copy
import hashlib
import json
import os
import sys

sys.excepthook = lambda *_: sys.exit(1)               # ошибка разбора — просто код 1
ref = json.load(open(sys.argv[2]))["hooks"] if len(sys.argv) > 2 else None
OURS = ("/.claude/scripts/", "/.claude/hooks/", "/.zcode/hooks/")
FOREIGN_UP = "echo stand-foreign-up"
FOREIGN_PT = "echo stand-foreign-pt"
FOREIGN_END = "echo stand-foreign-end"
# plugins не так, как пишет CLI: отступ 4, лишние пробелы
PLUGINS = ('{\n  "plugins": {\n      "enabledPlugins": {\n'
           '    "computer-use@zcode-plugins-official": true,\n'
           '        "pdf@zcode-plugins-official":   false\n      }\n  },\n')


def drop(records, name):
    records[:] = [r for r in records if name not in r["command"]]


def fixture(kind):
    h = copy.deepcopy(ref)
    ev = h["events"]
    ss, ups, pt, stop = (ev["SessionStart"][0]["hooks"], ev["UserPromptSubmit"][0]["hooks"],
                         ev["PreToolUse"], ev["Stop"][0]["hooks"])
    if kind == "clean" or kind == "nokey":
        pass
    elif kind == "missing":
        drop(ss, "bl-wake")
    elif kind == "matcher":                       # matcher слота SessionStart
        ev["SessionStart"][0]["matcher"] = "startup"   # слот с четырьмя записями
    elif kind == "extra":
        stop.append({"type": "command", "command": "$HOME/.claude/hooks/stand-ghost-gate.sh",
                     "timeout": 5})
    elif kind == "foreign":                       # чужие в двух слотах + нет одной нашей
        drop(ss, "bl-wake")
        ups.append({"type": "command", "command": FOREIGN_UP, "timeout": 3})
        pt[1]["hooks"].append({"type": "command", "command": FOREIGN_PT, "async": True})
    elif kind == "unknown":                     # событие вне семи имён: CLI не читает весь файл
        ev["SessionEnd"] = [{"hooks": [{"type": "command", "command": FOREIGN_END}]}]
    elif kind == "slotkey":                     # в слоте ключ вне matcher и hooks
        ev["Stop"][0]["stand-extra"] = "note"
    elif kind == "empty":                       # у слота пустой список hooks
        ev["Stop"].append({"matcher": "Bash", "hooks": []})
    elif kind == "off":                         # выключатель: иначе всё как в эталоне
        h["enabled"] = False
    elif kind == "decoy":
        drop(ss, "canon-budget")
    else:
        sys.exit(f"неизвестная фикстура {kind}")
    if kind == "nokey":
        return PLUGINS + '  "theme": "dark"\n}\n'
    return PLUGINS + '  "hooks": ' + json.dumps(h, indent=2, ensure_ascii=False).replace("\n", "\n  ") + "\n}\n"


CLI_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
              "PostToolUse", "PostToolUseFailure", "Stop")   # семь имён схемы CLI: своя копия стенда
TS_HEAD = """// Фикстура стенда: схема хуков — как adapters/src/config/schema.ts клона.
import { z } from "zod";

export const HookConfigSchema = z.object({
  type: z.literal("command"),
  command: z.string(),
});

// слот: matcher и список записей
const hookMatcherSchema = z.object({
  matcher: z.string().optional(),
  // hooks: z.array(HookConfigSchema) — комментарий, не ключ
  hooks: z.array(HookConfigSchema).min(1),
}).strict();

export const HooksSchema = z.object({
  events: z.object({
"""


def schema_source(kind):
    """Источник схемы: ts — читаемый исходник, один слой; иначе минифицированный
    бандл из трёх слоёв (первый без strict-слота, как в живых), расхождение — в
    последнем слое; none — объекта events нет."""
    names = list(CLI_EVENTS)
    if kind == "ts":
        rows = "".join("    %s: z.array(hookMatcherSchema),\n" % n for n in names)
        return TS_HEAD + rows + "    // SessionEnd: z.array(hookMatcherSchema) — комментарий\n" \
            "  }).strict(),\n  enabled: z.boolean().optional(),\n}).strict();\n"
    if kind == "none":
        return 'const a=1;export const Other=d.object({name:d.string(),hooks:d.array(X)});\n'
    out = []
    for i in (1, 2, 3):
        last = i == 3
        ev = [n for n in names if not (last and kind == "missing" and n == "Stop")]
        if last and kind == "extra":
            ev.append("SessionEnd")
        strict = not (kind == "alllax" or i == 1)
        matcher = ("matcher:d.string().transform(e=>e||void 0).optional()," if i > 1
                   else "matcher:d.string().optional(),")
        keys = "description:d.string().optional()," if last and kind == "slotkey" else ""
        at_least = ".min(2)" if last and kind == "min2" else ".min(1)"
        note = "// hooks: d.array(Z) — комментарий, не ключ\n" if i == 2 else ""
        out.append('S%d=d.object({%s%s%shooks:d.array(d.discriminatedUnion("type",[T%da,T%db]))%s})%s,' % (
            i, note, matcher, keys, i, i, at_least, ".strict()" if strict else ""))
        out.append("E%d=d.object({events:d.object({%s})%s,enabled:d.boolean().optional()}).strict()," % (
            i, "".join("%s:d.array(S%d)," % (n, i) for n in ev),
            "" if last and kind == "lax" else ".strict()"))
    return "".join(out)



def is_ours(record):
    return any(p in record.get("command", "") for p in OURS)


def stripped(hooks):
    """hooks без чужих записей (пустые слоты и события сняты)."""
    events = {}
    for event, slots in hooks["events"].items():
        kept = []
        for slot in slots:
            records = [r for r in slot["hooks"] if is_ours(r)]
            if records:
                kept.append({**slot, "hooks": records})
        if kept:
            events[event] = kept
    return {**hooks, "events": events}


def members(text):
    """Члены корня → список сырых значений (как в тексте)."""
    dec = json.JSONDecoder()

    def ws(i):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i
    i = ws(ws(0) + 1)
    out = {}
    while text[i] != "}":
        key, i = dec.raw_decode(text, i)
        i = ws(i)
        assert text[i] == ":"
        i = ws(i + 1)
        _, end = dec.raw_decode(text, i)
        out.setdefault(key, []).append(text[i:end])
        i = ws(end)
        if text[i] == ",":
            i = ws(i + 1)
    return out


cmd, a = sys.argv[1], sys.argv[3:]
if cmd == "mk":
    open(a[1], "w").write(fixture(a[0]))
    os.chmod(a[1], 0o600)
elif cmd == "hooks-eq-ref":
    sys.exit(0 if json.load(open(a[0])).get("hooks") == ref else 1)
elif cmd == "derflow-eq-ref":
    sys.exit(0 if stripped(json.load(open(a[0])).get("hooks")) == ref else 1)
elif cmd == "members-same":
    x, y = members(open(a[0]).read()), members(open(a[1]).read())
    sys.exit(0 if all(y.get(k) == v for k, v in x.items() if k != "hooks") else 1)
elif cmd == "foreign-in-place":
    ev = json.load(open(a[0])).get("hooks")["events"]
    theirs = [r for s in (sl for e in ev.values() for sl in e) for r in s["hooks"] if not is_ours(r)]
    ok = (ev["UserPromptSubmit"][0]["hooks"][-1]["command"] == FOREIGN_UP
          and ev["PreToolUse"][1]["hooks"][-1] == {"type": "command", "command": FOREIGN_PT, "async": True}
          and len(theirs) == 2)
    sys.exit(0 if ok else 1)
elif cmd == "enabled-off":
    sys.exit(0 if json.load(open(a[0])).get("hooks", {}).get("enabled") is False else 1)
elif cmd == "mode":
    sys.exit(0 if os.path.exists(a[0]) and oct(os.stat(a[0]).st_mode & 0o777) == "0o600" else 1)
elif cmd == "schema":                     # источник схемы CLI для сторожа: <вид> <файл>
    open(a[1], "w", encoding="utf-8").write(schema_source(a[0]))
elif cmd == "fp":
    try:
        data = open(a[0], "rb").read()
    except OSError:
        print("нет")
    else:
        print(f"{len(data)} {os.stat(a[0]).st_mtime_ns} {hashlib.sha256(data).hexdigest()[:16]}")
PY

# Сторож схемы CLI — его читает глава «схема CLI»; подмена — ZCODE_SCHEMA_GUARD.
cat > "$ROOT/schema.py" <<'SCHEMA'
#!/usr/bin/env python3
"""Сторож схемы CLI: EVENTS хелпера и три его правила против объекта events источника.

    schema.py <хелпер> <имя>=<путь> [<имя>=<путь>…]

Слой — один объект events источника; слот ищется в том же слое и раньше своего
events (короткие имена в минифицированном коде повторяются). Код 0 — в каждом
слое каждого источника события ровно EVENTS хелпера, events strict, ключи слота
matcher и hooks, hooks с min(1), и есть strict-слот; 1 — расхождение; 2 — хелпер
не объявляет EVENTS либо схема источника не читается.
"""
import importlib.util
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True     # не мусорить __pycache__ рядом с хелпером
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ALERT = "CLI обновился — правь EVENTS и CLI_SCHEMA"
SLOT_KEYS = ("matcher", "hooks")
CHAIN = rb"[\w$]+(?:\s*\.\s*[\w$.]+){0,6}"
OPEN, CLOSE = {0x7B: 0x7D, 0x28: 0x29, 0x5B: 0x5D}, {0x7D, 0x29, 0x5D}
BACK = 20000                       # слот определён не дальше этого от своего events


def close(data, open_at):
    """Индекс скобки, парной к data[open_at]; строки и комментарии // пропущены."""
    stack = [OPEN[data[open_at]]]
    i, n = open_at + 1, len(data)
    while i < n and stack:
        c = data[i]
        if c in (0x22, 0x27):                       # " или '
            i += 1
            while i < n and data[i] != c:
                i += 2 if data[i] == 0x5C else 1
        elif c == 0x2F and i + 1 < n and data[i + 1] == 0x2F:   # //
            i = data.find(b"\n", i)
            if i < 0:
                return -1
        elif c in OPEN:
            stack.append(OPEN[c])
        elif c in CLOSE:
            stack.pop()
        i += 1
    return i - 1 if not stack else -1


def no_comments(data):
    """Байты //-комментариев — пробелами; строки учтены."""
    out = bytearray(data)
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c in (0x22, 0x27):
            i += 1
            while i < n and data[i] != c:
                i += 2 if data[i] == 0x5C else 1
        elif c == 0x2F and i + 1 < n and data[i + 1] == 0x2F:
            j = data.find(b"\n", i)
            j = n if j < 0 else j
            out[i:j] = b" " * (j - i)
            i = j
        i += 1
    return bytes(out)


def literal(data, at):
    """(Объект от { до }, до 40 байт после его закрывающей скобки) — по { в позиции at."""
    end = close(data, at)
    if end <= at:
        raise ValueError("скобка объекта не закрылась")
    tail = end + 1
    if tail < len(data) and data[tail] == 0x29:     # ) обёртки .object( … )
        tail += 1
    return data[at:end + 1], data[tail:tail + 41]


def top_keys(lit):
    """Ключи объекта на верхнем уровне (строки пропущены)."""
    out, depth, i, n = [], 0, 1, len(lit) - 1
    while i < n:
        c = lit[i]
        if c in (0x22, 0x27):
            i += 1
            while i < n and lit[i] != c:
                i += 2 if lit[i] == 0x5C else 1
        elif c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif depth == 0:
            m = re.match(rb"(\w+)\s*:", lit[i:])
            if m and (i == 1 or lit[i - 1] in (0x20, 0x2C, 0x0A, 0x09)):
                out.append(m.group(1).decode("ascii", "replace"))
                i += m.end() - 1
        i += 1
    return out


def layer(data, m):
    """Слой схемы по совпадению `events: … .object({`; слот — раньше, в том же слое."""
    lit, after = literal(data, m.end() - 1)
    pairs = re.findall(rb"(\w+)\s*:\s*" + CHAIN + rb"\s*\.array\(\s*([\w$]+)\s*\)", no_comments(lit))
    idents = sorted({i for _, i in pairs})
    if not idents:
        raise ValueError("под events нет ни одного списка слотов")
    if len(idents) != 1:
        raise ValueError("события описаны разными слотами: " + ", ".join(i.decode("ascii", "replace") for i in idents))
    ident = idents[0]
    lo = max(0, m.start() - BACK)
    defs = list(re.finditer(rb"(?<![\w$.])" + re.escape(ident) + rb"\s*=\s*" + CHAIN + rb"\s*\.object\(\{",
                            data[lo:m.start()]))
    if not defs:
        raise ValueError("слот %s не определён раньше своего events" % ident.decode("ascii", "replace"))
    slit, safter = literal(data, lo + defs[-1].end() - 1)
    slit = no_comments(slit)
    hooks = re.search(rb"\bhooks\s*:\s*" + CHAIN + rb"\s*\.array\(", slit)
    at_least = None
    if hooks:
        e = close(slit, hooks.end() - 1)
        if e <= 0:
            raise ValueError("список hooks в слоте не закрыт")
        mm = re.match(rb"\s*\.min\((\d+)\)", slit[e + 1:e + 21])
        nonempty = slit[e + 1:e + 14].lstrip().startswith(b".nonempty()")
        at_least = mm.group(1).decode() if mm else "1" if nonempty else None
    return {
        "at": m.start(),
        "events": [k.decode("ascii", "replace") for k, _ in pairs],
        "events.strict": bool(re.match(rb"\s*\.strict\(\)", after)),
        "slot.strict": bool(re.match(rb"\s*\.strict\(\)", safter)),
        "slot.keys": top_keys(slit),
        "hooks.min": at_least,
    }


def layer_faults(s, events):
    """Чем слой расходится с событиями и правилами хелпера."""
    out = []
    extra = [k for k in s["events"] if k not in events]
    gone = [e for e in events if e not in s["events"]]
    if extra:
        out.append("в схеме есть, в EVENTS нет: " + ", ".join(extra))
    if gone:
        out.append("в EVENTS есть, в схеме нет: " + ", ".join(gone))
    if sorted(s["slot.keys"]) != sorted(SLOT_KEYS):
        out.append("ключи слота не matcher и hooks: " + ", ".join(s["slot.keys"]))
    if s["hooks.min"] != "1":
        out.append("у hooks минимум не 1: " + ("min(%s)" % s["hooks.min"] if s["hooks.min"] else "минимума нет"))
    if not s["events.strict"]:
        out.append("events не strict: чужое событие CLI срежет молча")
    return out


def source_faults(layers, events):
    """Расхождения источника — (номер слоя, 0 — весь источник; строка)."""
    faults = [(n, f) for n, s in enumerate(layers, 1) for f in layer_faults(s, events)]
    if not any(s["slot.strict"] for s in layers):
        faults.append((0, "ни в одном слое слот не strict: лишний ключ слота CLI срежет молча"))
    return faults


def plural(n, one, few, many):
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def check(name, path, events, version):
    """(строки, код) по одному источнику."""
    head = name + ":"
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        return ["%s схема не читается — %s" % (head, e.strerror)], 2
    layers = []
    for m in re.finditer(rb"(?<![\w$.])events\s*:\s*" + CHAIN + rb"\s*\.object\(\{", data):
        try:
            layers.append(layer(data, m))
        except ValueError as e:
            return ["%s схема не читается — объект events не разобран: %s" % (head, e)], 2
    if not layers:
        return ["%s схема не читается — объекта events не нашёл" % head], 2
    lines = ["%s слой %d/%d @%d — %d %s, events %s, слот %s, hooks min(%s)" % (
        head, n, len(layers), s["at"], len(s["events"]), plural(len(s["events"]), "событие", "события", "событий"),
        "strict" if s["events.strict"] else "не strict", "strict" if s["slot.strict"] else "не strict",
        s["hooks.min"] or "нет") for n, s in enumerate(layers, 1)]
    faults = source_faults(layers, events)
    if faults:
        lines += ["%s %s — %s: %s" % (head, "слой %d/%d" % (n, len(layers)) if n else "весь источник", ALERT, f)
                  for n, f in faults]
        return lines, 1
    lines.append("%s равна — %d %s, в каждом EVENTS хелпера (%d %s), схема CLI %s" % (
        head, len(layers), plural(len(layers), "слой", "слоя", "слоёв"),
        len(events), plural(len(events), "имя", "имени", "имён"), version))
    return lines, 0


def main(argv):
    if len(argv) < 2:
        print("использование: schema.py <хелпер> <имя>=<путь> [<имя>=<путь>…]")
        return 2
    helper, sources = argv[0], argv[1:]
    try:
        spec = importlib.util.spec_from_file_location("zcode_hooks", helper)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        events = tuple(mod.EVENTS)
    except (Exception, SystemExit) as e:            # заглушка хелпера выходит на импорте
        print("хелпер %s не объявляет EVENTS — %s: %s" % (helper, type(e).__name__, e))
        return 2
    version = getattr(mod, "CLI_SCHEMA", "не объявлена")
    code = 0
    for arg in sources:
        name, _, path = arg.partition("=")
        lines, c = check(name, path, events, version)
        print("\n".join(lines))
        code = max(code, c)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:                          # падение сторожа не должно выглядеть вердиктом
        print("сторож упал — %s: %s" % (type(e).__name__, e))
        sys.exit(2)
SCHEMA

fx()    { python3 "$ROOT/fx.py" "$1" "$REF" "${@:2}"; }
fixture() { fx mk "$1" "$2"; }                   # fixture <вид> <файл>
run() {  # run <аргументы install.sh…> → $out, $rc; всегда поддельный HOME и стенд
  out="$(HOME="$H" ZCODE_HOOKS="$HOOKS" bash "$I" --only zcode --zcode-dir "$S" "$@" 2>&1)"; rc=$?
}
has()   { printf '%s' "$out" | grep -qF -- "$1"; }
nohas() { ! printf '%s' "$out" | grep -qF -- "$1"; }
cnt()   { printf '%s\n' "$out" | grep -c -E "^ +$1 +"; }   # строки метки: «нет», «иная», «лишняя»
nbak()  { local n=0 f; for f in "$C".bak-*; do [ -e "$f" ] && n=$((n+1)); done; echo "$n"; }
ntmp()  { local n=0 f; for f in "$C".*tmp; do [ -e "$f" ] && n=$((n+1)); done; echo "$n"; }
is() {  # is <ярлык> <0 если утверждение верно>
  if [ "${2:-1}" = 0 ]; then echo "  ✅ $1"; pass=$((pass+1))
  else
    echo "  ❌ $1 — rc=$rc"
    printf '%s\n' "$out" | sed 's/^/       /' | head -40
    fail=$((fail+1))
  fi
}
changed=0                                       # стенд правил файл стенда — для спаивания ниже
moved() { cmp -s "$1" "$C" || changed=1; }      # moved <снимок до записи>
again() { fixture "$1" "$C"; rm -f "$C".bak-*; }  # install начинает со своей фикстуры

before="$(git -C "$IREPO" status --porcelain 2>/dev/null)"
live0="$(fx fp "$LIVE")"
pass=0; fail=0; skip=0; out=""; rc=0

echo "=== штатный файл ==="

fixture clean "$C"; cp -p "$C" "$ROOT/clean.json"
run
{ [ "$rc" = 0 ] && cmp -s "$C" "$ROOT/clean.json" && [ "$(nbak)" = 0 ] && has "равны"; }
is "install не меняет ни байта, копии нет (AC #5)" $?
run --check; c0="$rc"; has "дрейфа нет"; h0=$?
fixture missing "$C"
run --check
{ [ "$c0" = 0 ] && [ "$h0" = 0 ] && [ "$rc" = 1 ] && [ "$(cnt нет)" = 1 ]; }
is "штатный: «дрейфа нет», код 0; снятая запись — ровно одна строка «нет», код 1 (AC #3)" $?

echo "=== --check не пишет ==="

fixture missing "$ROOT/missing.json"; cp -p "$ROOT/missing.json" "$C"   # снимок — из фикстуры, не после --check
run --check
{ [ "$rc" = 1 ] && cmp -s "$C" "$ROOT/missing.json" && [ "$(nbak)" = 0 ]; }
is "--check при дрейфе не пишет: файл байт в байт прежний, копии нет (AC #3)" $?

echo "=== нет одной записи ==="

again missing
run; moved "$ROOT/missing.json"
{ [ "$rc" = 0 ] && [ "$(nbak)" = 1 ] && cmp -s "$C".bak-* "$ROOT/missing.json" \
  && fx mode "$C".bak-* && fx mode "$C" && fx hooks-eq-ref "$C"; }
is "install добавил: копия одна с прежними байтами и 0600, результат 0600 и равен эталону (AC #4)" $?
{ ! cmp -s "$C" "$ROOT/missing.json" && fx members-same "$ROOT/missing.json" "$C"; }
is "файл изменился, а байты вне значения hooks (plugins, скобки корня) прежние (AC #4)" $?
cp -p "$C" "$ROOT/after.json"
run
{ [ "$rc" = 0 ] && cmp -s "$C" "$ROOT/after.json" && [ "$(nbak)" = 1 ]; }
is "второй install — ни байта и новой копии нет (AC #5)" $?
run --check
{ [ "$rc" = 0 ] && has "дрейфа нет" && fx hooks-eq-ref "$C"; }
is "после install: «дрейфа нет», код 0 — красным был ровно derflow (AC #3)" $?

echo "=== расходится matcher ==="

fixture matcher "$C"
run --check
{ [ "$rc" = 1 ] && [ "$(cnt иная)" = 4 ] && [ "$(printf '%s\n' "$out" | grep -c -E '^ +иная +.*matcher:')" = 4 ]; }
is "matcher слота расходится: четыре его записи — четыре «иная … matcher …», код 1 (AC #3)" $?
again matcher; cp -p "$C" "$ROOT/matcher.json"
run; moved "$ROOT/matcher.json"
{ [ "$rc" = 0 ] && fx hooks-eq-ref "$C"; }
is "install привёл matcher к эталону (AC #4)" $?

echo "=== лишняя запись derflow ==="

fixture extra "$C"
run --check
{ [ "$rc" = 1 ] && [ "$(cnt лишняя)" = 1 ] && has "stand-ghost-gate.sh" && [ "$(cnt нет)" = 0 ]; }
is "одна «лишняя», она названа, код 1 (AC #3)" $?
again extra; cp -p "$C" "$ROOT/extra.json"
run; moved "$ROOT/extra.json"
{ [ "$rc" = 0 ] && fx hooks-eq-ref "$C" && ! grep -q "stand-ghost-gate" "$C"; }
is "install снял лишнюю (AC #4)" $?

echo "=== нет ключа hooks ==="

fixture nokey "$C"; cp -p "$C" "$ROOT/nokey.json"
run --check
{ [ "$rc" = 1 ] && [ "$(cnt нет)" = 13 ]; }
is "13 «нет», код 1 (AC #3)" $?
again nokey
run; moved "$ROOT/nokey.json"
{ [ "$rc" = 0 ] && fx hooks-eq-ref "$C" && fx members-same "$ROOT/nokey.json" "$C"; }
is "ключ hooks вставлен, записи равны эталону; plugins и theme байт в байт (AC #4)" $?

echo "=== чужая запись в hooks ==="

fixture foreign "$C"; cp -p "$C" "$ROOT/foreign.json"
run --check
{ [ "$rc" = 1 ] && [ "$(cnt нет)" = 1 ] && [ "$(cnt лишняя)" = 0 ] && nohas "stand-foreign"; }
is "чужая не дрейф и не печатается; видна ровно наша недостающая (AC #3, AC #4)" $?
again foreign
run; moved "$ROOT/foreign.json"
{ [ "$rc" = 0 ] && fx derflow-eq-ref "$C" && fx foreign-in-place "$C" && nohas "stand-foreign"; }
is "после install чужие на месте в прежнем порядке, наши равны эталону, чужое не напечатано (AC #4)" $?

echo "=== файл, который CLI не читает ==="

# Схема CLI строже эталона: чужое событие, лишний ключ слота, пустой hooks —
# и CLI читает весь файл пустым. Отказ обязан назвать место и не тронуть файл;
# «не тронут» и заглушке зелёно, поэтому каждый укус спаян с «названо».
again unknown; cp -p "$C" "$ROOT/unknown.json"; f="$(fx fp "$C")"
run --check
{ [ "$rc" != 0 ] && has "SessionEnd" && has "по схеме CLI" && has "без хуков и плагинов" \
  && has "install её не трогает" && cmp -s "$C" "$ROOT/unknown.json" && [ "$(nbak)" = 0 ]; }
is "событие вне семи имён: --check называет его, схему и цену, код не 0, файл байт в байт (DF-30.1 AC #1, #3)" $?
run
{ [ "$rc" != 0 ] && has "SessionEnd" && [ "$(fx fp "$C")" = "$f" ] && [ "$(nbak)" = 0 ] && [ "$(ntmp)" = 0 ]; }
is "событие вне семи имён: install отказывает, файл и mtime прежние, копии нет (DF-30.1 AC #1)" $?
again slotkey; cp -p "$C" "$ROOT/slotkey.json"
run --check
{ [ "$rc" != 0 ] && has "Stop [без matcher], слот 1" && has "«stand-extra»" \
  && cmp -s "$C" "$ROOT/slotkey.json" && [ "$(nbak)" = 0 ]; }
is "лишний ключ слота: --check называет слот и ключ, код не 0, файл цел (DF-30.1 AC #2, #3)" $?
again empty; cp -p "$C" "$ROOT/empty.json"; f="$(fx fp "$C")"
run
{ [ "$rc" != 0 ] && has "Stop [Bash], слот 2" && has "список hooks пуст" \
  && [ "$(fx fp "$C")" = "$f" ] && [ "$(nbak)" = 0 ]; }
is "пустой hooks у слота: install отказывает, называет слот, файл и mtime прежние, копии нет (DF-30.1 AC #2)" $?
again unknown; cp -p "$C" "$ROOT/unknown.json"
# Нарушение в эталоне одно — событие вне EVENTS, запись derflow. С «echo x» отказ
# держит правило «не команда derflow», и хелпер с кривым EVENTS укус проходит.
printf '{"hooks": {"enabled": true, "events": {"SessionEnd": [{"hooks": [{"type": "command", "command": "$HOME/.claude/hooks/stand-schema-end.sh"}]}]}}}\n' > "$ROOT/badref2.json"
out="$(HOME="$H" python3 "$HOOKS" "$C" "$ROOT/badref2.json" --check 2>&1)"; rc=$?   # эталон вне схемы, напрямую
{ [ "$rc" != 0 ] && has "эталон $ROOT/badref2.json" && nohas "файл $C" && cmp -s "$C" "$ROOT/unknown.json"; }
is "эталон вне схемы: отказ раньше и вместо разбора живого файла; файл цел (DF-30.1 AC #4)" $?

echo "=== схема CLI ==="

# Хелпер судит файл по EVENTS и трём правилам — а схема CLI живёт в бандлах и
# меняется без этого репозитория. Сторож schema.py (каталог стенда) читает
# каждый объект events источника и сверяет с хелпером: событие из EVENTS —
# равенство множеств и events strict; «в слоте только matcher и hooks» — ключи
# слота и strict-слот хотя бы в одном слое; «hooks непуст» — min(1). Живые
# бандлы — оба контура, каждый сам по себе; фикстуры — расхождение в третьем
# слое, чтобы сторож судил каждый слой, а не первый попавшийся. «Не тронут»
# тут не при чём: каждый укус держит то, что даёт только настоящий сторож с
# настоящим хелпером — «равна» с EVENTS хелпера или названное место расхождения.
guard() {  # guard <имя> <путь> <ярлык> [все строки]: источник против EVENTS хелпера; нет пути — «пропущено»
  if [ ! -e "$2" ]; then echo "  ⏭ $1: пропущено — нет $2"; skip=$((skip+1)); return; fi
  out="$(python3 "$GUARD" "$HOOKS" "$1=$2" 2>&1)"; rc=$?
  if [ -n "${4:-}" ]; then printf '%s\n' "$out" | sed 's/^/       /'
  else printf '%s\n' "$out" | tail -1 | sed 's/^/       /'; fi
  { [ "$rc" = 0 ] && has "равна"; }
  is "$3" $?
}
guardout() {  # guardout <имя> <файл> → $out, $rc: вердикт сторожа без счёта
  out="$(python3 "$GUARD" "$HOOKS" "$1=$2" 2>&1)"; rc=$?
}
skipself() {  # «пропущено» — вне зачёта: счётчики локальные, итога не меняет
  local pass=0 fail=0 skip=0
  guard самопроверка-пропуска "$ROOT/no-such-bundle.cjs" x
  [ "$skip" = 1 ] && [ "$pass" = 0 ] && [ "$fail" = 0 ]
}
ALERT="CLI обновился — правь EVENTS и CLI_SCHEMA"

fx schema ts "$ROOT/s-ts.ts"
for k in eq extra missing slotkey min2 lax alllax none; do fx schema "$k" "$ROOT/s-$k.js"; done

guard ts "$ROOT/s-ts.ts" "фикстура, читаемый исходник: один слой равен EVENTS хелпера"
guard eq "$ROOT/s-eq.js" "фикстура, минифицированный бандл: три слоя равны EVENTS, первый — без strict-слота"
guard ztui "$ZTUI_BUNDLE" "dist ztui: каждый слой схемы равен EVENTS хелпера (DF-35 AC #1)" все
guard desktop "$DESKTOP_BUNDLE" "десктопный бандл: каждый слой схемы равен EVENTS хелпера (DF-35 AC #1)" все
guardout extra "$ROOT/s-extra.js"
{ [ "$rc" = 1 ] && has "extra: слой 3/3 — $ALERT: в схеме есть, в EVENTS нет: SessionEnd"; }
is "лишнее событие в третьем слое: названы слой и событие, что править, код 1 (DF-35 AC #2)" $?
guardout missing "$ROOT/s-missing.js"
{ [ "$rc" = 1 ] && has "missing: слой 3/3 — $ALERT: в EVENTS есть, в схеме нет: Stop"; }
is "отсутствующее событие в третьем слое: названы слой и событие, код 1 (DF-35 AC #2)" $?
guardout slotkey "$ROOT/s-slotkey.js"
{ [ "$rc" = 1 ] && has "slotkey: слой 3/3 — $ALERT: ключи слота не matcher и hooks: matcher, description, hooks"; }
is "лишний ключ слота в третьем слое: названы слой и ключи, код 1 (DF-35 AC #2)" $?
guardout min2 "$ROOT/s-min2.js"
{ [ "$rc" = 1 ] && has "min2: слой 3/3 — $ALERT: у hooks минимум не 1: min(2)"; }
is "hooks с min(2) в третьем слое: названы слой и минимум, код 1 (DF-35 AC #2)" $?
guardout lax "$ROOT/s-lax.js"
{ [ "$rc" = 1 ] && has "lax: слой 3/3 — $ALERT: events не strict"; }
is "events не strict в третьем слое: назван слой, код 1 (DF-35 AC #2)" $?
guardout alllax "$ROOT/s-alllax.js"
{ [ "$rc" = 1 ] && has "alllax: весь источник — $ALERT: ни в одном слое слот не strict"; }
is "ни одного strict-слота: названо, код 1 (DF-35 AC #2)" $?
guardout none "$ROOT/s-none.js"
{ [ "$rc" = 2 ] && has "none: схема не читается — объекта events не нашёл"; }
is "источник без объекта events: «схема не читается», код 2 (DF-35 AC #3)" $?
skipself || { echo "  ❌ отсутствующий источник пошёл в зачёт, а не «пропущено»"; fail=$((fail+1)); }

echo "=== выключатель ==="

# hooks.enabled = false: CLI не зовёт ни один хук. install.sh выключатель не
# трогает — обе печати обязаны сказать, как включить; это даёт только хелпер.
again off; cp -p "$C" "$ROOT/off.json"; f="$(fx fp "$C")"
run --check
{ [ "$rc" = 1 ] && has "выключено" && has "hooks.enabled: true" && cmp -s "$C" "$ROOT/off.json" && [ "$(nbak)" = 0 ]; }
is "hooks.enabled = false: --check печатает «выключено» и как включить, код 1, файл не пишет (DF-30.1 AC #5)" $?
run
{ [ "$rc" = 0 ] && has "не зовёт ни один хук" && has "hooks.enabled: true" && has "ничего не меняю" \
  && [ "$(fx fp "$C")" = "$f" ] && [ "$(nbak)" = 0 ] && fx enabled-off "$C"; }
is "hooks.enabled = false: install предупреждает и говорит, как включить; не пишет, код 0, выключатель на месте (DF-30.1 AC #5)" $?

echo "=== отказы ==="

rm -f "$C".bak-*
fixture missing "$C"; rm "$C"
run
{ [ "$rc" != 0 ] && has "не читается" && [ ! -e "$C" ] && [ "$(nbak)" = 0 ]; }
is "нет файла: код не 0, причина названа, файла не появилось (AC #6)" $?
fixture missing "$C"; f="$(fx fp "$C")"; chmod 000 "$C"
run; chmod 600 "$C"
{ [ "$rc" != 0 ] && has "не читается" && [ "$(fx fp "$C")" = "$f" ] && [ "$(nbak)" = 0 ]; }
is "chmod 000: код не 0, причина названа, файл цел (AC #6)" $?
printf '{"hooks": {,}\n' > "$C"; cp -p "$C" "$ROOT/bad.json"
run
{ [ "$rc" != 0 ] && has "не разбирается" && cmp -s "$C" "$ROOT/bad.json" && [ "$(nbak)" = 0 ] && [ "$(ntmp)" = 0 ]; }
is "кривой JSON: код не 0, причина названа, файл цел (AC #6)" $?
printf '{"hooks": {"events": {}}, "hooks": {"events": {}}}\n' > "$C"; cp -p "$C" "$ROOT/twice.json"
run
{ [ "$rc" != 0 ] && has "больше одного раза" && cmp -s "$C" "$ROOT/twice.json" && [ "$(nbak)" = 0 ]; }
is "ключ hooks в корне дважды (якорь не единственный): код не 0, файл цел (AC #6)" $?
fixture missing "$C"; cp -p "$C" "$ROOT/missing.json"; printf '{"hooks": {\n' > "$ROOT/badref.json"
out="$(HOME="$H" python3 "$HOOKS" "$C" "$ROOT/badref.json" 2>&1)"; rc=$?   # эталон у install.sh свой — напрямую
{ [ "$rc" != 0 ] && has "эталон" && cmp -s "$C" "$ROOT/missing.json" && [ "$(nbak)" = 0 ]; }
is "эталон кривой (напрямую): код не 0, причина названа, файл цел (AC #6)" $?

echo "=== стенд --zcode-dir видит только себя ==="

fixture decoy "$DECOY"; df="$(fx fp "$DECOY")"
fixture missing "$C"; cp -p "$C" "$ROOT/missing.json"
run; moved "$ROOT/missing.json"
{ [ "$rc" = 0 ] && ! cmp -s "$C" "$ROOT/missing.json" && fx hooks-eq-ref "$C" \
  && [ "$(fx fp "$DECOY")" = "$df" ] && fx mode "$DECOY"; }
is "файл стенда правится; приманка H/.zcode/cli/config.json — байты и mtime прежние (AC #7)" $?
run --check; c1="$rc"; has "дрейфа нет"; h1=$?
fixture missing "$C"
run --check
{ [ "$c1" = 0 ] && [ "$h1" = 0 ] && [ "$rc" = 1 ] && [ "$(cnt нет)" = 1 ] && [ "$(fx fp "$DECOY")" = "$df" ]; }
is "--check смотрит в стенд: чисто — код 0, приманка с дрейфом не видна; снятая в стенде — код 1 (AC #7)" $?
out="$(HOME="$H" bash "$I" --help 2>&1)"; rc=$?
{ [ "$rc" = 0 ] && has "--zcode-dir" && [ "$changed" = 1 ]; }
is "--help называет --zcode-dir (стенд за прогон правил файл стенда)" $?

echo "=== стенд не пачкает ==="

{ [ "$before" = "$(git -C "$IREPO" status --porcelain 2>/dev/null)" ] && [ "$changed" = 1 ]; }
is "дерево репозитория после стенда — какое было" $?
{ [ "$(fx fp "$LIVE")" = "$live0" ] && [ "$changed" = 1 ]; }
is "живой ~/.zcode/cli/config.json — байты и mtime прежние" $?

skipnote=""; [ "$skip" -gt 0 ] && skipnote=" ⏭ $skip"   # пропуск — только когда был
echo "=== итог: ✅ $pass ❌ $fail$skipnote ==="
[ "$fail" = 0 ]
