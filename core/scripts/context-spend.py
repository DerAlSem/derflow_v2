#!/usr/bin/env python3
"""Куда уходят токены Claude Code — замер по локальным транскриптам.

Считает не «сколько написано», а полную структуру расхода: output,
cache-write и cache-read. Последний обычно доминирует, потому что каждый
ход перечитывает весь накопленный контекст сессии.

  ~/.claude/scripts/context-spend.py                 # 7 дней, сводка
  ~/.claude/scripts/context-spend.py --days 1
  ~/.claude/scripts/context-spend.py --sessions 20   # самые дорогие сессии
"""
import argparse, collections, datetime, glob, json, os, sys

# Прайс Opus-класса, $/M токенов. Нужен только чтобы ранжировать статьи
# расхода между собой — с формулой недельного лимита он не совпадает.
PRICE = {"out": 75.0, "cw": 18.75, "cr": 1.50, "in": 15.0}
ROOT = os.path.expanduser("~/.claude/projects")


def human(n):
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= div:
            return f"{n/div:.1f}{unit}"
    return str(n)


def collect(days):
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    z = lambda: [0, 0, 0, 0, 0]  # in, out, cache_write, cache_read, msgs
    tot, by_side, by_proj, by_day, by_sess = z(), collections.defaultdict(z), \
        collections.defaultdict(z), collections.defaultdict(z), collections.defaultdict(z)
    ctx_main = []
    for fp in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        try:
            if datetime.datetime.fromtimestamp(os.path.getmtime(fp), datetime.timezone.utc) < cut:
                continue
        except OSError:
            continue
        proj = os.path.relpath(fp, ROOT).split(os.sep)[0]
        with open(fp, errors="ignore") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                day = ""
                ts = d.get("timestamp", "")
                if ts:
                    try:
                        t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if t < cut:
                            continue
                        day = t.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                u = (d.get("message") or {}).get("usage") or {}
                if not u:
                    continue
                v = (u.get("input_tokens", 0), u.get("output_tokens", 0),
                     u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0), 1)
                side = "sub" if d.get("isSidechain") else "main"
                for bucket in (tot, by_side[side], by_proj[proj], by_sess[(proj, os.path.basename(fp)[:8])],
                               by_day[day] if day else z()):
                    for i, x in enumerate(v):
                        bucket[i] += x
                if side == "main":
                    ctx_main.append(v[0] + v[2] + v[3])
    return tot, by_side, by_proj, by_day, by_sess, ctx_main


def cost(b):
    return (b[0] * PRICE["in"] + b[1] * PRICE["out"] + b[2] * PRICE["cw"] + b[3] * PRICE["cr"]) / 1e6


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--projects", type=int, default=10)
    ap.add_argument("--sessions", type=int, default=0, help="показать N самых дорогих сессий")
    a = ap.parse_args()

    tot, by_side, by_proj, by_day, by_sess, ctx = collect(a.days)
    if not tot[4]:
        print(f"Нет данных за {a.days} дн. в {ROOT}", file=sys.stderr)
        return 1
    total_cost = cost(tot)

    print(f"=== расход за {a.days} дн. ({tot[4]:,} ходов) ===")
    for label, key in (("output", 1), ("cache-write", 2), ("cache-read", 3)):
        c = tot[key] * PRICE[{1: "out", 2: "cw", 3: "cr"}[key]] / 1e6
        print(f"  {label:12} {human(tot[key]):>8}  ≈ ${c:9,.0f}  {c/total_cost:5.1%} счёта")
    print(f"  {'ИТОГО':12} {'':>8}  ≈ ${total_cost:9,.0f}")

    print("\n=== главный цикл против сабагентов ===")
    for side in ("main", "sub"):
        b = by_side.get(side)
        if not b:
            continue
        print(f"  {side:5} out={human(b[1]):>7} ({b[1]/max(tot[1],1):5.1%})  "
              f"cacheR={human(b[3]):>7} ({b[3]/max(tot[3],1):5.1%})  ходов={b[4]:,}")

    if ctx:
        ctx.sort()
        q = lambda f: ctx[min(len(ctx) - 1, int(len(ctx) * f))]
        print(f"\n=== контекст на ход главного цикла ===\n"
              f"  медиана={human(q(.5))}  p75={human(q(.75))}  p90={human(q(.9))}  max={human(ctx[-1])}")
        print("  ↑ это множитель на КАЖДЫЙ последующий ход сессии — главный рычаг счёта")

    print(f"\n=== проекты (топ-{a.projects}) ===")
    for p, b in sorted(by_proj.items(), key=lambda x: -cost(x[1]))[:a.projects]:
        print(f"  {p[:48]:48} ≈ ${cost(b):8,.0f}  {cost(b)/total_cost:5.1%}  ходов={b[4]:,}")

    if by_day:
        print("\n=== по дням ===")
        for d in sorted(by_day):
            b = by_day[d]
            print(f"  {d}  ≈ ${cost(b):8,.0f}  out={human(b[1]):>7}  cacheR={human(b[3]):>7}")

    if a.sessions:
        print(f"\n=== самые дорогие сессии (топ-{a.sessions}) ===")
        for (p, sid), b in sorted(by_sess.items(), key=lambda x: -cost(x[1]))[:a.sessions]:
            print(f"  {p[:38]:38} {sid}  ≈ ${cost(b):8,.0f}  ходов={b[4]:5,}  cacheR={human(b[3]):>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
