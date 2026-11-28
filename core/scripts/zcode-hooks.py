#!/usr/bin/env python3
"""Хуки derflow в ~/.zcode/cli/config.json: сверка и приведение к эталону.

Файл живой для всех ztui-сессий всех проектов, вне git, и CLI сам
перезаписывает его целиком (JSON.stringify(value, null, 2) + "\\n",
временный файл + rename, режим 0600). Поэтому:

    судим РАЗБОРОМ JSON, пишем ТЕКСТОМ — меняются байты только внутри
    значения ключа `hooks`, всё до и после промежутка остаётся как было
    (прецедент — waiting.py:install_hook);
    чужие записи не печатаются, дрейфом не считаются и сохраняются
    в прежнем порядке;
    любой отказ безопаснее правки наугад: не понял форму — не пишу.

    hooks, не проходящий схему CLI (событие вне семи, лишний ключ слота,
    пустой список записей), — отказ в обоих режимах: CLI читает такой файл
    пустым целиком, без хуков и плагинов;
Чья запись derflow: хотя бы один токен команды (по пробельным) после
раскрытия `$HOME`/`~` начинается с ~/.claude/scripts/, ~/.claude/hooks/
или ~/.zcode/hooks/ — это каталоги, которые раскладывает install.sh.

    zcode-hooks.py <config.json> <hooks.json>          привести к эталону
    zcode-hooks.py <config.json> <hooks.json> --check  только сверка

Коды: 0 — равны или приведены; 1 — дрейф (только с --check); 2 — отказ,
ничего не написано, причина на stderr. Метки строк фиксированной ширины —
их ищут grep-ом. Эталон — hosts/zcode/hooks.json (DF-30).
"""
from __future__ import annotations

import datetime
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Iterator, NamedTuple

USAGE = "использование: zcode-hooks.py <config.json> <hooks.json> [--check]"

NONE = object()  # поля нет в объекте

# schema.ts: events строго этих семь, слот — только matcher и hooks (минимум одна
# запись); лишнее там CLI отвергает вместе со всем пользовательским файлом
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
          "PostToolUse", "PostToolUseFailure", "Stop")
CLI_SCHEMA = "0.18.x"  # исходники, по которым сверены EVENTS и форма слота

Slot = tuple["str | None", list[dict[str, Any]], dict[str, Any]]  # (matcher, записи, сам слот)
Model = dict[str, list[Slot]]  # событие -> слоты в порядке файла


class Refuse(Exception):
    """Отказ (код 2): причина готова к печати, ничего не написано."""


class Dup(Exception):
    """Одноимённый ключ в одном объекте: разбор молча оставил бы последний."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(2)


def _pairs_strict(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for key, val in pairs:
        if key in d:
            raise Dup(key)
        d[key] = val
    return d


DEC = json.JSONDecoder()
STRICT = json.JSONDecoder(object_pairs_hook=_pairs_strict)


def _no_constant(name: str) -> Any:
    raise ValueError(f"константа {name} — не JSON")


DOC = json.JSONDecoder(parse_constant=_no_constant)


def strict_decode(text: str, what: str) -> Any:
    """Разбор всего текста так, как его читает CLI: NaN, Infinity и мусор в хвосте — отказ."""
    try:
        return DOC.decode(text)
    except ValueError as e:
        raise Refuse(f"{what} не разбирается как JSON — {e}") from e


class Member(NamedTuple):
    """Член корневого объекта: ключ, промежуток значения в тексте, значение."""

    key: str
    start: int
    end: int
    value: Any


def _ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def root_members(text: str, where: str) -> tuple[list[Member], int, int]:
    """Члены корневого объекта с промежутками значений — без регулярных.

    Возвращает (члены, индекс открывающей `{`, индекс закрывающей `}`).
    Внутри `hooks` одноимённый ключ — отказ; прочее разбирается как его
    читает сам CLI: последний побеждает.
    """
    i = _ws(text, 0)
    if i >= len(text) or text[i] != "{":
        raise Refuse(f"{where}: корень — не объект")
    opened = i
    i = _ws(text, i + 1)
    out: list[Member] = []
    if i < len(text) and text[i] == "}":
        return out, opened, i
    while True:
        i = _ws(text, i)
        strict = False
        try:
            if i >= len(text) or text[i] != '"':
                raise ValueError("ожидался ключ")
            key, i = DEC.raw_decode(text, i)
            i = _ws(text, i)
            if i >= len(text) or text[i] != ":":
                raise ValueError("ожидалось двоеточие")
            i = _ws(text, i + 1)
            start = i
            strict = key == "hooks"
            val, end = (STRICT if strict else DEC).raw_decode(text, i)
        except Dup as e:
            if strict:
                raise Refuse(f"{where}: одноимённый ключ «{e.key}» внутри hooks") from e
            raise Refuse(f"{where}: JSON не разбирается — ключ «{e.key}» дважды") from e
        except ValueError as e:
            raise Refuse(f"{where}: JSON не разбирается — {e}") from e
        out.append(Member(key, start, end, val))
        i = _ws(text, end)
        if i < len(text) and text[i] == ",":
            i += 1
            continue
        if i < len(text) and text[i] == "}":
            return out, opened, i
        raise Refuse(f"{where}: JSON не разбирается — после «{key}» нет запятой "
                     f"или закрывающей скобки")


def read_text(path: Path, what: str) -> str:
    try:
        data = path.read_bytes()
    except OSError as e:
        raise Refuse(f"{what} {path} не читается — {e.strerror or e}") from e
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Refuse(f"{what} {path} не UTF-8 — {e}") from e


def is_derflow(command: Any) -> bool:
    """Команда зовёт скрипт из каталогов, которые раскладывает install.sh."""
    if not isinstance(command, str):
        return False
    home = os.path.expanduser("~")
    prefixes = tuple(home + p for p in ("/.claude/scripts/", "/.claude/hooks/", "/.zcode/hooks/"))

    def expand(tok: str) -> str:
        if tok.startswith("$HOME"):
            return home + tok[5:]
        if tok.startswith("~"):
            return home + tok[1:]
        return tok

    return any(expand(tok).startswith(prefixes) for tok in command.split())


def to_model(hooks: Any, where: str, *, reference: bool = False) -> Model:
    """hooks -> {событие: [(matcher, записи)]}; не той формы — отказ."""
    if not isinstance(hooks, dict):
        raise Refuse(f"{where}: hooks — не объект")
    events = hooks.get("events", {})
    if not isinstance(events, dict):
        raise Refuse(f"{where}: hooks.events — не объект")
    model: Model = {}
    for event, slots in events.items():
        if not isinstance(slots, list):
            raise Refuse(f"{where}: hooks.events.{event} — не список")
        if reference and event not in EVENTS:
            raise Refuse(f"{where}: событие {event} CLI не знает — такой ключ events "
                         f"отвергает вместе со всем файлом")
        parsed: list[Slot] = []
        for slot in slots:
            if not isinstance(slot, dict) or not isinstance(slot.get("hooks"), list):
                raise Refuse(f"{where}: слот события {event} не той формы")
            if reference and (set(slot) - {"matcher", "hooks"} or not slot["hooks"]):
                raise Refuse(f"{where}: слот события {event} эталона — только matcher и hooks,"
                             f" записей не меньше одной: иначе CLI отвергает весь файл")
            matcher = slot.get("matcher")
            if matcher is not None and not isinstance(matcher, str):
                raise Refuse(f"{where}: matcher слота события {event} — не строка")
            if matcher == "":
                matcher = None  # CLI читает пустую строку как «без matcher»
            records = slot["hooks"]
            if any(not isinstance(r, dict) for r in records):
                raise Refuse(f"{where}: запись события {event} не той формы")
            if reference and any(not isinstance(r.get("command"), str) for r in records):
                raise Refuse(f"{where}: запись события {event} без строкового command")
            if reference and any(r.get("type") not in ("command", "process")
                                 or not is_derflow(r["command"]) for r in records):
                raise Refuse(f"{where}: запись события {event} эталона — не команда derflow "
                             f"(type command или process, скрипт из каталогов install.sh)")
            parsed.append((matcher, records, slot))
        model[event] = parsed
    return model


class Rec(NamedTuple):
    event: str
    matcher: str | None
    record: dict[str, Any]


def flatten(model: Model) -> Iterator[Rec]:
    for event, slots in model.items():
        for matcher, records, _ in slots:
            for record in records:
                yield Rec(event, matcher, record)


def foreign(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if not is_derflow(r.get("command"))]


def others(slot: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in slot.items() if k not in ("matcher", "hooks")}


def foreign_shape(model: Model) -> dict[str, list[tuple[dict[str, Any], list[dict[str, Any]]]]]:
    """Чужое по событиям: (прочие ключи слота, чужие записи) слотов с чужими записями,
    в порядке файла."""
    out: dict[str, list[tuple[dict[str, Any], list[dict[str, Any]]]]] = {}
    for event, slots in model.items():
        rows = [(others(slot), foreign(records)) for _, records, slot in slots]
        if any(rest for _, rest in rows):
            out[event] = [row for row in rows if row[1]]
    return out


def fmt(val: Any) -> str:
    if val is NONE:
        return "нет"
    if isinstance(val, str):
        return f"«{val}»"
    if isinstance(val, bool):
        return "true" if val else "false"
    if val is None:
        return "null"
    if isinstance(val, (int, float)):
        return str(val)
    return json.dumps(val, ensure_ascii=False, separators=(",", ":"))


def where(event: str, matcher: str | None) -> str:
    return f"{event} [{matcher if matcher is not None else 'без matcher'}]"


def field_diff(a: dict[str, Any], b: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Чем a (файл) отличается от b (эталон); поля только с одной стороны тоже."""
    keys = list(a) + [k for k in b if k not in a]
    return [(k, a.get(k, NONE), b.get(k, NONE)) for k in keys if a.get(k, NONE) != b.get(k, NONE)]


def schema_faults(model: Model) -> list[str]:
    """Где hooks не проходит схему CLI — по месту, в порядке файла.

    Те же три правила, что reference=True держит с эталона: событие из EVENTS,
    в слоте только matcher и hooks, список hooks непуст.
    """
    out: list[str] = []
    for event, slots in model.items():
        if event not in EVENTS:
            out.append(f"событие {event} — вне схемы, CLI его не знает")
        for n, (matcher, records, slot) in enumerate(slots, 1):
            place = f"событие {where(event, matcher)}, слот {n}"
            extra = [k for k in slot if k not in ("matcher", "hooks")]
            if extra:
                out.append(f"{place} — лишний ключ " + ", ".join(f"«{k}»" for k in extra))
            if not records:
                out.append(f"{place} — список hooks пуст")
    return out


def analyze(refm: Model, filem: Model) -> tuple[list[str], list[str]]:
    """Строки сверки «нет / иная / лишняя» и парные им строки правок."""
    lines: list[str] = []
    edits: list[str] = []
    ours = [f for f in flatten(filem) if is_derflow(f.record.get("command"))]
    used: set[int] = set()

    for r in flatten(refm):
        cmd = r.record["command"]
        loc = where(r.event, r.matcher)
        same = [f for f in ours if f.event == r.event and f.matcher == r.matcher
                and f.record.get("command") == cmd]
        hit = next((f for f in same if f.record == r.record), None)
        if hit is not None:
            used.add(id(hit.record))
            continue
        if same:
            hit, diff = same[0], field_diff(same[0].record, r.record)
        else:
            hit = next((f for f in ours if id(f.record) not in used and f.event == r.event
                        and f.record.get("command") == cmd), None)
            if hit is None:
                lines.append(f"    нет     {loc} · {cmd}")
                edits.append(f"🔧 добавлена: {loc} · {cmd}")
                continue
            diff = [("matcher", hit.matcher, r.matcher)] + field_diff(hit.record, r.record)
        used.add(id(hit.record))
        lines.append(f"    иная    {loc} · {cmd} — " + "; ".join(
            f"{k}: в файле {fmt(a)}, в эталоне {fmt(b)}" for k, a, b in diff))
        edits.append(f"🔧 исправлена: {loc} · {cmd} — " + "; ".join(
            f"{k}: было {fmt(a)}, стало {fmt(b)}" for k, a, b in diff))

    for f in ours:
        if id(f.record) not in used:
            loc = where(f.event, f.matcher)
            lines.append(f"    лишняя  {loc} · {f.record.get('command')}")
            edits.append(f"🔧 снята:    {loc} · {f.record.get('command')}")
    return lines, edits


def build(refm: Model, base: dict[str, Any], filem: Model) -> dict[str, Any]:
    """Новый объект hooks: порядок событий и слотов — файла, записи derflow — эталона.

    Записи эталона встают в первый слот файла с тем же matcher, вперёд чужих
    записей этого слота; слоты эталона, которых в файле нет, — в конец события,
    новые события — в конец events. Слот файла берётся как есть, из чужого слота
    уходят только записи derflow; без записей слот снимается — пустым он ломает
    файл для CLI. base — прежний hooks файла (его прочие ключи, включая enabled,
    как были); когда ключа не было — эталон целиком.
    """
    events: dict[str, list[dict[str, Any]]] = {}
    for event in list(filem) + [e for e in refm if e not in filem]:
        left = dict(enumerate(refm.get(event, [])))  # слоты эталона, ещё не занятые
        out: list[dict[str, Any]] = []
        for matcher, records, slot in filem.get(event, []):
            rest = foreign(records)
            hit = next((i for i, (m, _, _) in left.items() if m == matcher), None)
            if hit is None:
                if rest:
                    out.append({**slot, "hooks": rest})
                continue
            ref_records = left.pop(hit)[1]
            out.append({**slot, "hooks": ref_records + rest})
        out += [slot for _, _, slot in left.values()]
        if out:
            events[event] = out
    new: dict[str, Any] = {}
    for key, val in base.items():
        new[key] = events if key == "events" else val
    if "events" in base:
        return new
    new["events"] = events
    return new


def _layout(text: str, opened: int) -> tuple[int, str]:
    """(единица отступа по первой вложенной строке, EOL файла)."""
    nested = [ln for ln in text[opened:].split("\n")[1:] if ln.strip() and not ln.lstrip().startswith("}")]
    unit = next((len(ln) - len(ln.lstrip(" \t")) for ln in nested), 2)
    return unit, ("\r\n" if "\r\n" in text else "\n")


def _render(hooks: dict[str, Any], unit: int, eol: str, inline: bool) -> str:
    if inline:
        return json.dumps(hooks, ensure_ascii=False, separators=(",", ":"))
    pad = " " * unit
    return (eol + pad).join(json.dumps(hooks, ensure_ascii=False, indent=unit).split("\n"))


def splice(text: str, members: list[Member], close: int, opened: int,
           hooks: dict[str, Any]) -> tuple[str, str, str]:
    """Новый текст + (прежние байты до промежутка, после него) для проверки."""
    unit, eol = _layout(text, opened)
    found = [m for m in members if m.key == "hooks"]
    if len(found) > 1:
        raise Refuse("ключ hooks в корне встречается больше одного раза")
    if found:
        m = found[0]
        inline = "\n" not in text[m.start:m.end] and "\r" not in text[m.start:m.end]
        return (text[:m.start] + _render(hooks, unit, eol, inline) + text[m.end:],
                text[:m.start], text[m.end:])
    root_inline = "\n" not in text[opened:close] and "\r" not in text[opened:close]
    body = '"hooks": ' + _render(hooks, unit, eol, root_inline)
    pad = " " * unit
    if not members:
        head = text[:opened + 1] + ("" if root_inline else eol + pad)
        return head + body + text[opened + 1:], head, text[opened + 1:]
    cut = members[-1].end
    head = text[:cut] + (", " if root_inline else "," + eol + pad)
    return head + body + text[cut:], head, text[cut:]


def check_post(text: str, new_text: str, old_head: str, old_tail: str, new_hooks: dict[str, Any],
               live: Path, filem: Model, refm: Model) -> None:
    def fail(what: str) -> None:
        raise Refuse(f"внутренняя проверка не прошла ({what}) — {live} не тронут")

    try:
        strict_decode(new_text, str(live))
        members, _, _ = root_members(new_text, str(live))
    except Refuse as e:
        raise Refuse(f"внутренняя проверка не прошла (новый текст не разбирается: {e})") from e
    spans = [m for m in members if m.key == "hooks"]
    if len(spans) != 1:
        fail("hooks в новом тексте не единственный")
    span = spans[0]
    head, tail = new_text[:span.start], new_text[span.end:]
    if not (head.startswith(old_head) and tail.endswith(old_tail)):
        fail("байты за пределами значения hooks изменились")
    old_doc = json.loads(text)
    new_doc = json.loads(new_text)
    if {k: v for k, v in old_doc.items() if k != "hooks"} != {k: v for k, v in new_doc.items() if k != "hooks"}:
        fail("прочие корневые ключи изменились")
    if new_doc["hooks"] != new_hooks:
        fail("hooks нового текста не равен построенному")
    newm = to_model(new_doc["hooks"], str(live))
    if foreign_shape(filem) != foreign_shape(newm):
        fail("чужие записи или прочие ключи их слотов изменились")
    if analyze(refm, newm)[0]:
        fail("после записи сверка с эталоном не пуста")


def _write(path: Path, data: bytes, mode: int, *, exclusive: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, mode)
    try:
        os.fchmod(fd, mode)
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _drop(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def replace_file(live: Path, data: bytes, new_data: bytes) -> Path:
    """Копия прежнего, временный файл, сверка на ходу, rename. Возвращает копию."""
    try:
        mode = stat.S_IMODE(os.stat(live).st_mode)
    except OSError as e:
        raise Refuse(f"{live} не читается — {e.strerror or e}") from e
    bak = Path(f"{live}.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    if bak.exists():
        bak = Path(f"{bak}-{os.getpid()}")
    if bak.exists():
        raise Refuse(f"имя копии {bak} занято — ничего не написано")
    tmp = Path(f"{live}.{os.getpid()}.tmp")
    try:
        _write(tmp, new_data, mode, exclusive=False)
        short = tmp.read_bytes() != new_data
    except OSError as e:
        _drop(tmp)
        raise Refuse(f"не записать рядом с {live} — {e.strerror or e}") from e
    if short:
        _drop(tmp)
        raise Refuse(f"временный файл записался не целиком — {live} не тронут")
    try:
        _write(bak, data, mode, exclusive=True)
    except OSError as e:
        _drop(tmp)
        raise Refuse(f"не записать рядом с {live} — {e.strerror or e}") from e
    try:
        if live.read_bytes() != data:
            raise Refuse(f"{live} изменился на ходу — ничего не написано")
        os.replace(tmp, live)
    except OSError as e:
        _drop(tmp)
        _drop(bak)
        raise Refuse(f"не записать рядом с {live} — {e.strerror or e}") from e
    except Refuse:
        _drop(tmp)
        _drop(bak)
        raise
    return bak


def run(live: Path, ref_path: Path, check: bool) -> int:
    text = read_text(live, "файл")
    strict_decode(text, f"файл {live}")
    members, opened, close = root_members(text, str(live))
    if sum(m.key == "hooks" for m in members) > 1:
        raise Refuse(f"ключ hooks в корне {live} встречается больше одного раза")
    ref_text = read_text(ref_path, "эталон")
    try:
        ref_doc = json.loads(ref_text, object_pairs_hook=_pairs_strict, parse_constant=_no_constant)
    except Dup as e:
        raise Refuse(f"эталон {ref_path}: ключ «{e.key}» дважды") from e
    except ValueError as e:
        raise Refuse(f"эталон {ref_path} не разбирается — {e}") from e
    if (not isinstance(ref_doc, dict) or not isinstance(ref_doc.get("hooks"), dict)
            or not isinstance(ref_doc["hooks"].get("events"), dict)):
        raise Refuse(f"эталон {ref_path}: нет hooks.events или не той формы")
    refm = to_model(ref_doc["hooks"], f"эталон {ref_path}", reference=True)
    keys = [(r.event, r.matcher, r.record["command"]) for r in flatten(refm)]
    if len(set(keys)) != len(keys):
        raise Refuse(f"эталон {ref_path}: дубль ключа записи (событие, matcher, command)")

    for event, slots in refm.items():  # иначе dict по matcher глотает первый слот
        seen = [m for m, _, _ in slots]
        if len(set(seen)) != len(seen):
            raise Refuse(f"эталон {ref_path}: в событии {event} два слота с одним matcher")
    had_hooks = any(m.key == "hooks" for m in members)
    old_hooks = members[[m.key for m in members].index("hooks")].value if had_hooks else {}
    filem = to_model(old_hooks, str(live)) if had_hooks else {}
    faults = schema_faults(filem)
    if faults:  # файл непригоден для CLI независимо от записей derflow
        raise Refuse(f"файл {live} не проходит по схеме CLI {CLI_SCHEMA} — CLI читает весь "
                     "пользовательский файл как пустой: без хуков и плагинов; это не запись "
                     "derflow, install её не трогает:\n" + "\n".join(f"    {one}" for one in faults))
    new_hooks = build(refm, old_hooks if had_hooks else ref_doc["hooks"], filem)
    lines, edits = analyze(refm, filem)
    switch = ""
    if had_hooks and old_hooks.get("enabled") is not True:  # CLI: включено только `=== true`
        switch = "hooks.enabled " + ("нет в файле" if "enabled" not in old_hooks
                                     else f"= {fmt(old_hooks['enabled'])}")

    if check:
        if lines:
            print(f"⚠️  hooks в {live} расходятся с {ref_path}:")
            print("\n".join(lines))
        if switch:
            print(f"    выключено {switch} — ztui не зовёт ни один хук; включить — руками:"
                  " hooks.enabled: true; install.sh выключатель не трогает")
        return 1 if lines or switch else 0
    if switch:
        print(f"⚠️  {switch} в {live} — ztui не зовёт ни один хук; включить — руками:"
              " hooks.enabled: true; install.sh выключатель не трогает")
    if not lines and had_hooks:  # иначе check молчит, а install пишет
        print(f"✅ hooks в {live} равны {ref_path} — ничего не меняю")
        return 0
    new_text, old_head, old_tail = splice(text, members, close, opened, new_hooks)
    check_post(text, new_text, old_head, old_tail, new_hooks, live, filem, refm)
    data = text.encode("utf-8")
    bak = replace_file(live, data, new_text.encode("utf-8"))
    if edits:
        print("\n".join(edits))
    print(f"📦 прежний файл: {bak}")
    return 0


def main(argv: list[str]) -> int:
    rest = [a for a in argv[1:] if a != "--check"]
    if len(rest) != 2 or any(a.startswith("-") for a in rest):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        return run(Path(rest[0]), Path(rest[1]), "--check" in argv[1:])
    except Refuse as e:
        _die(str(e))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
