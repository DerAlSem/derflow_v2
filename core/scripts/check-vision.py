#!/usr/bin/env python3
"""Проба зрения модели сессии: случайная картинка → Read → сверка с истиной.

    check-vision.py new              # рендерит пробу: печатает путь к png и схему ответа
    check-vision.py check <каталог>  # сверяет answer.json с истиной; код 0 = видит

Зачем: 04.10.2026 glm-5.3 «прочитал» скриншот psql, которого не видит, и выдал
выдуманную таблицу с вердиктом «✅ фискального долга нет» — слепоту закрыли
разделением «картинки через flash». С 23.11.2026 сессия ZCode едет на glm-5.4
и читает картинки сама. «Вижу на скрине» — факт этой пробы, а не слово о новой
модели: сессия сменила модель — прогони заново. Содержимое случайно и после
рендера живёт только в пикселях (истина — truth.json, html удаляется):
угадать или вычитать из файла нельзя.
"""
import argparse, html, json, secrets, subprocess, sys, tempfile, unicodedata
from pathlib import Path

SHOT = Path.home() / ".claude" / "scripts" / "shot.mjs"
DIGITS = "0123456789"
ALNUM = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # без 0/O, 1/I/L — омоглифы
CONS, VOW = "bdfgklmnprstvz", "aeiou"
STATUSES = {"Оплачен": "#15803d", "Возврат": "#1d4ed8", "Ошибка": "#b91c1c", "Ждёт": "#b45309"}
TERM_ST = ("paid", "pending", "failed", "refunded")
COLORS = {"зелёный": "#16a34a", "красный": "#dc2626", "синий": "#2563eb",
          "фиолетовый": "#7c3aed", "оранжевый": "#ea580c"}
KINDS = ("круг", "квадрат")
FIELDS = ("title", "rows", "toast", "term", "term_footer", "shapes", "kind", "serial")

SCHEMA = """Прочитай картинку САМ (Read) и запиши ответ в {d}/answer.json; truth.json не открывать.
{{
  "title": "<код после «Панель платежей ·»>",
  "rows": [["<контрагент>", "<сумма>", "<статус>"], ...],   # таблица, сверху вниз
  "toast": "<красная строка дословно>",
  "term": [["<id>", "<status>", "<amount>"], ...],           # тёмный блок, сверху вниз
  "term_footer": "<последняя строка тёмного блока>",
  "shapes": {{"<цвет>": <сколько фигур этого цвета>}},       # только цвета, которые есть
  "kind": {{"<цвет>": "круг" или "квадрат"}},
  "serial": "<серийный номер: мелкая строка под фигурами, без подписи>"
}}
Цвета называй из набора: зелёный, красный, синий, фиолетовый, оранжевый.
Затем: python3 {me} check {d}"""


def rnd(n, abc):
    return "".join(secrets.choice(abc) for _ in range(n))


def content():
    names = []
    while len(names) < 3:
        w = "".join(secrets.choice(CONS) + secrets.choice(VOW) for _ in range(3)).capitalize()
        if w not in names:
            names.append(w)
    pick = secrets.SystemRandom().sample
    colors = pick(sorted(COLORS), 3)
    return {
        "title": rnd(5, ALNUM),
        "rows": [[n, f"{secrets.randbelow(90000) + 1000:,}".replace(",", " ") + "," + rnd(2, DIGITS), s]
                 for n, s in zip(names, pick(sorted(STATUSES), 3))],
        "toast": "Ошибка ERR-" + rnd(4, DIGITS) + ": платёж " + rnd(8, DIGITS + "abcdef")
                 + " отклонён шлюзом",
        "term": [[str(secrets.randbelow(9000) + 1000), secrets.choice(TERM_ST),
                  f"{secrets.randbelow(900) + 100}." + rnd(2, DIGITS)] for _ in range(3)],
        "term_footer": "(3 rows)",
        "shapes": {c: secrets.randbelow(3) + 1 for c in colors},
        "kind": {c: secrets.choice(KINDS) for c in colors},
        "serial": "SN-" + rnd(4, ALNUM) + "-" + rnd(4, ALNUM),
    }


def page(t):
    rows = "".join(
        '<tr><td>%s</td><td style="white-space:nowrap">%s</td>'
        '<td><span class="badge" style="background:%s">%s</span></td></tr>'
        % (n, a, STATUSES[s], s) for n, a, s in t["rows"])
    # Тёмный блок — как вывод psql: та самая плотная моноширинная таблица
    term = [" id   | status   |  amount", "------+----------+--------"]
    term += [" %-5s| %-9s| %7s" % (i, st, am) for i, st, am in t["term"]]
    term.append(t["term_footer"])
    shapes = ""
    for c in secrets.SystemRandom().sample(list(t["shapes"]), 3):
        kind = "c" if t["kind"][c] == KINDS[0] else "s"
        shapes += ('<span class="grp">' + '<i class="%s" style="background:%s"></i>'
                   % (kind, COLORS[c]) * t["shapes"][c] + "</span>")
    title, toast, serial = html.escape(t["title"]), html.escape(t["toast"]), html.escape(t["serial"])
    return f"""<!doctype html><meta charset="utf-8"><style>
body{{margin:0;width:1100px;height:640px;background:#eef1f5;color:#111827;
font:15px/1.45 -apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}}
.win{{margin:18px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;overflow:hidden}}
.bar{{display:flex;justify-content:space-between;padding:10px 16px;background:#1e293b;color:#f8fafc;font-weight:600}}
th,td{{padding:7px 16px;text-align:left;border-bottom:1px solid #e5e7eb}}
th{{background:#f8fafc;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#475569}}
.badge{{display:inline-block;padding:1px 9px;border-radius:999px;color:#fff;font-size:12px;font-weight:600}}
.toast{{margin:14px 16px;padding:10px 14px;border-radius:8px;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;font-size:14px}}
pre{{margin:0 16px;padding:12px;background:#0f172a;color:#e2e8f0;border-radius:8px;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace}}
.grp{{display:inline-block;margin:14px 16px 6px}}
i{{display:inline-block;width:22px;height:22px;margin-right:6px}}
.c{{border-radius:50%}}
.small{{padding:6px 16px 14px;font-size:11px;color:#6b7280}}
</style>
<div class="win">
<div class="bar"><span>Панель платежей · {title}</span><span>export</span></div>
<table style="width:100%;border-collapse:collapse">
<tr><th>Контрагент</th><th>Сумма</th><th>Статус</th></tr>{rows}</table>
<div class="toast">{toast}</div>
<pre>{html.escape(chr(10).join(term))}</pre>
<div>{shapes}</div>
<div class="small">Серийный номер: {serial}</div>
</div>"""


def render(d, t):
    src, png = d / "page.html", d / "probe.png"
    src.write_text(page(t), encoding="utf-8")
    try:
        p = subprocess.run(["node", str(SHOT), src.as_uri(), str(png), "--size", "1100x640"],
                           capture_output=True, text=True, timeout=120)
    finally:
        src.unlink()  # содержимое остаётся только в пикселях
    if p.returncode or not png.is_file():
        sys.exit("❌ рендер не удался: " + (p.stderr or p.stdout).strip()[:400])


def fold(s):
    return " ".join(unicodedata.normalize("NFKC", str(s)).replace("Ё", "Е").replace("ё", "е").split())


def norm(v):
    if isinstance(v, dict):
        return {fold(k).lower(): norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return fold(int(v)) if float(v).is_integer() else fold(v)
    return fold(v)


def check(d):
    try:
        truth = json.loads((d / "truth.json").read_text(encoding="utf-8"))
        answer = json.loads((d / "answer.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit("❌ " + str(e).replace(str(d), "<проба>")[:300])
    if not isinstance(answer, dict):
        sys.exit("❌ answer.json должен быть объектом по схеме из `new`")
    bad = [k for k in FIELDS if norm(answer.get(k)) != norm(truth.get(k))]
    for k in FIELDS:
        print(f"  {'FAIL' if k in bad else 'ok  '} {k}")
    for k in bad:
        print(f"    {k}: ждали {json.dumps(truth[k], ensure_ascii=False)}"
              f" — получено {json.dumps(answer.get(k), ensure_ascii=False)}")
    if bad:
        sys.exit(f"❌ не сошлось {len(bad)} из {len(FIELDS)} полей: {', '.join(bad)}")
    print(f"✅ все {len(FIELDS)} полей сошлись — читающий видит картинку")


def main():
    ap = argparse.ArgumentParser(description="Проба зрения модели сессии.")
    ap.add_argument("cmd", choices=("new", "check"))
    ap.add_argument("dir", nargs="?", help="каталог пробы (для check)")
    a = ap.parse_args()
    if a.cmd == "new":
        d = Path(tempfile.mkdtemp(prefix="derflow-vision-"))
        t = content()
        render(d, t)
        truth = d / "truth.json"
        truth.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
        truth.chmod(0o600)
        print(f"Картинка: {d / 'probe.png'}")
        print(SCHEMA.format(me=Path(__file__).resolve(), d=d))
        return
    if not a.dir:
        ap.error("check нужен каталог пробы, напечатанный командой new")
    check(Path(a.dir))


if __name__ == "__main__":
    main()
