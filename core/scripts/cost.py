#!/usr/bin/env python3
"""Сколько стоила ветка: стадии, родитель против сабагентов, итог.

Зачем. Вопрос «этот веер агентов оправдан?» сейчас стоит раскопок в `usage`
руками — так было 13.09.2026 и 14.09.2026, оба раза с неверными промежуточными
выводами. Прибор отвечает одной командой и ничего не печатает в сессию.

Чем отличается от `context-meter.py` (он меряет РАЗМЕР, этот — СЧЁТ):
  • считает сабагентов. Метр их пропускает намеренно («сабагент держит свой
    контекст, не наш») — для размера верно, для денег наоборот: в замере
    14.09 сабагенты дали 44% счёта ветки;
  • суммирует по ВЕТКЕ, а не по сессии: хендофф-цепочка размазывает счёт по
    трём сессиям, и каждая по отдельности выглядит безобидно;
  • разделяет типы токенов: cache-read стоит 0.1× свежего входа и составляет
    здесь 98% — считать их одной кучей значит завысить счёт вдесятеро.

Стадии подписываются строкой announce-контракта derflow («Lane <id> → ...»):
она обязательна по канону, значит бесплатно годится ключом разнесения денег.
Сессия без анонса попадёт в отчёт как «без анонса» — пропуск строки, сейчас
ничем не наказанный, становится виден в счёте.
"""
import json, os, re, sys, glob

# Цены $/1М токенов. Источник: скилл claude-api (кэш 2026-06-24) + множители
# кэша из shared/prompt-caching.md: read = 0.1×input, write = 2×input при
# ЧАСОВОМ TTL (у сессий Claude Code он часовой; при пятиминутном было бы 1.25×).
# живёт до: смены тарифов Anthropic. Перепроверять скиллом claude-api, НЕ памятью.
PRICES = {            # input, output
    "opus":   (5.00, 25.00),
    "fable":  (10.00, 50.00),
    "mythos": (10.00, 50.00),
    "sonnet": (3.00, 15.00),
    "haiku":  (1.00, 5.00),
}
FALLBACK = "opus"
# Полоса бывает «C», «Dx · диагностика», «C (хвост заявки)» — до стрелки лежит
# что угодно, кроме перевода строки. Ранняя версия требовала одно слово и молча
# метила настоящий анонс как «без анонса»: тихая неверная подпись, не падение.
ANNOUNCE = re.compile(r"\*{0,2}Lane\s+([^\n→]{1,40}?)\s*→\s*([^—\n]{0,60})")


def family(model):
    for k in PRICES:
        if k in (model or ""):
            return k
    return FALLBACK


def price(model, u):
    inp, out = PRICES[family(model)]
    return (u.get("input_tokens", 0) / 1e6 * inp
            + u.get("cache_read_input_tokens", 0) / 1e6 * inp * 0.1
            + u.get("cache_creation_input_tokens", 0) / 1e6 * inp * 2.0
            + u.get("output_tokens", 0) / 1e6 * out)


def scan(path):
    """→ (доллары, {тип токена: число}, ходов). Подстрока до json.loads —
    приём из context-meter.py: иначе разбираем мегабайты ради двух полей."""
    d, t, turns = 0.0, {"in": 0, "cr": 0, "cw": 0, "out": 0}, 0
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return d, t, turns
    with f:
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") or {}
            u = msg.get("usage") or {}
            if not u:
                continue
            turns += 1
            d += price(msg.get("model"), u)
            t["in"] += u.get("input_tokens", 0)
            t["cr"] += u.get("cache_read_input_tokens", 0)
            t["cw"] += u.get("cache_creation_input_tokens", 0)
            t["out"] += u.get("output_tokens", 0)
    return d, t, turns


def announce(path):
    """Первая строка анонса в ТЕКСТЕ ассистента. Не в tool_result: там лежит
    сам SKILL.md с шаблоном «Lane `<id>` → `<agent>`», и он бы совпал."""
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with f:
        for line in f:
            if '"assistant"' not in line or "Lane" not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            for b in (rec.get("message") or {}).get("content") or []:
                if not (isinstance(b, dict) and b.get("type") == "text"):
                    continue
                m = ANNOUNCE.search(b.get("text", ""))
                if m:
                    lane = m.group(1).replace("`", "").strip(" *")
                    dest = m.group(2).replace("`", "").strip(" *(")
                    return f"Lane {lane} → {dest}"[:58]
    return None


def encode(p):
    """~/.claude/projects/<путь>: / . _ → -. Проверено на живых каталогах."""
    return re.sub(r"[/._]", "-", os.path.abspath(p))


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    root = os.path.expanduser(f"~/.claude/projects/{encode(target)}")
    if not os.path.isdir(root):
        print(f"нет транскриптов для {target}\n  ожидался каталог {root}")
        return 1

    rows, tot = [], [0.0, 0.0]
    for par in sorted(glob.glob(os.path.join(root, "*.jsonl"))):
        sid = os.path.basename(par)[:-6]
        pd, pt, pturns = scan(par)
        subs = glob.glob(os.path.join(root, sid, "subagents", "*.jsonl"))
        sd = 0.0
        for s in subs:                # токены сабагентов идут в ту же сводку,
            d1, t1, _ = scan(s)       # что и доллары: иначе строка «cache-read
            sd += d1                  # N M» объясняет лишь половину итога
            for k in pt:
                pt[k] += t1[k]
        if pd + sd < 0.01:
            continue
        rows.append((pd + sd, sid[:8], announce(par) or "без анонса",
                     pd, len(subs), sd, pturns, pt))
        tot[0] += pd
        tot[1] += sd

    if not rows:
        print(f"транскрипты есть, расхода нет: {root}")
        return 1
    rows.sort(reverse=True)
    whole = tot[0] + tot[1]
    print(f"{target}\n")
    print(f"{'сессия':9} {'родитель':>9} {'саб':>4} {'сабагенты':>10} "
          f"{'итого':>9}  {'доля':>5}  стадия")
    for d, sid, lane, pd, n, sd, turns, _ in rows:
        print(f"{sid:9} {'$%.0f' % pd:>9} {n:>4} {'$%.0f' % sd:>10} "
              f"{'$%.0f' % d:>9}  {d / whole * 100:>4.0f}%  {lane}")
    agg = {k: sum(r[7][k] for r in rows) for k in ("in", "cr", "cw", "out")}
    print(f"\nИТОГО ${whole:.0f}   родители ${tot[0]:.0f} · "
          f"сабагенты ${tot[1]:.0f} ({tot[1] / whole * 100:.0f}%)")
    print(f"вход: свежий {agg['in'] / 1e6:.1f}M · cache-read {agg['cr'] / 1e6:.1f}M "
          f"· cache-write {agg['cw'] / 1e6:.1f}M · выход {agg['out'] / 1e6:.2f}M")
    print(f"ходов ассистента: {sum(r[6] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
