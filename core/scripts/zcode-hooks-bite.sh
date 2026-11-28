#!/usr/bin/env bash
# Стенд укуса записей derflow в ~/.zcode/cli/config.json (DF-30): install.sh
# сверяет их с эталоном hosts/zcode/hooks.json и правит текстом внутри hooks
# (core/scripts/zcode-hooks.py).
#
#   bash core/scripts/zcode-hooks-bite.sh
#   ZCODE_HOOKS=/путь/к/хелперу bash core/scripts/zcode-hooks-bite.sh   # заглушка, мутант
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
# 🔴 ЗАМЕРЫ (28.11.2026, 32 укуса). Каждая строка — отдельный прогон:
#
#   zcode-hooks.py с правками ...................... ✅ 32 ❌  0
#   заглушка (exit 0, молчит) ...................... ✅  0 ❌ 32
#   мутация: is_derflow → True ..................... ✅ 30 ❌  2   — глава «чужая запись», оба её укуса
#   мутация: файл пересериализуется ................ ✅ 30 ❌  2   — «байты вне hooks»: правка и вставка ключа
#   мутация: --check пишет ......................... ✅ 31 ❌  1   — «--check не пишет»
#   мутация: живой файл не сверяется со схемой ..... ✅ 28 ❌  4   — глава «файл, который CLI не читает», все четыре укуса об отказе
#   мутация: не замечает пропавшей записи .......... ✅ 20 ❌ 12   — семья «записи нет», все её 12 укусов
#   мутация: не видит расхождения matcher .......... ✅ 30 ❌  2   — «расходится matcher», оба её укуса
#   мутация: не снимает лишнюю ..................... ✅ 30 ❌  2   — «лишняя запись derflow», оба её укуса
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
elif cmd == "fp":
    try:
        data = open(a[0], "rb").read()
    except OSError:
        print("нет")
    else:
        print(f"{len(data)} {os.stat(a[0]).st_mtime_ns} {hashlib.sha256(data).hexdigest()[:16]}")
PY

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
pass=0; fail=0; out=""; rc=0

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
printf '{"hooks": {"enabled": true, "events": {"SessionEnd": [{"hooks": [{"type": "command", "command": "echo x"}]}]}}}\n' > "$ROOT/badref2.json"
out="$(HOME="$H" python3 "$HOOKS" "$C" "$ROOT/badref2.json" --check 2>&1)"; rc=$?   # эталон вне схемы, напрямую
{ [ "$rc" != 0 ] && has "эталон $ROOT/badref2.json" && nohas "файл $C" && cmp -s "$C" "$ROOT/unknown.json"; }
is "эталон вне схемы: отказ раньше и вместо разбора живого файла; файл цел (DF-30.1 AC #4)" $?

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

echo "=== итог: ✅ $pass ❌ $fail ==="
[ "$fail" = 0 ]
