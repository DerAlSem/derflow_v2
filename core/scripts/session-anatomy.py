#!/usr/bin/env python3
"""Анатомия сессий: из чего складывается длина и работает ли порог `ctx:`.

Не путать с `context-spend.py` — тот считает РАСХОД (output / cache-write /
cache-read по сессиям, проектам и дням). Этот отвечает на другой вопрос: как
сессия становится длинной и меняет ли поведение маркер, который ей об этом
говорит. Разные вопросы, разные инструменты; сводить их не надо.

  session-anatomy.py                 # анатомия за 7 дней
  session-anatomy.py --threshold     # эффект порога, с контролем на возраст
  session-anatomy.py --days 14 --threshold

Замер 04.09.2026, из-за которого это написано: 87% календарного времени сессий —
простой, то есть «длина в минутах» ложная метрика. А порог `ctx:` (хук
`hooks/context-meter.py`, живёт с 01.09) работает: на завершённых сессиях число
промптов ПОСЛЕ `‼` упало с медианы 30 (p90 98, макс 180) до медианы 3 (p90 10,
макс 13).
"""
import argparse, collections, datetime as dt, glob, json, os, re

ROOT = os.path.expanduser("~/.claude/projects")
GAP = 30 * 60                    # пауза, после которой это уже другой эпизод
HOOK_BORN = dt.datetime(2026, 9, 1, 9, 31, tzinfo=dt.timezone.utc)
FINISHED = 12 * 3600             # без активности столько — считаем завершённой
# `$b` в выводе хука — текст самой команды, а не ветка; `HEAD` — detached.
BRANCH = re.compile(r'git: ([^\s\\"$]+) ')
BAD_BRANCHES = {"HEAD"}


def parse(fp):
    """→ (prompts[], ctx_points[], branches, first, last) или None."""
    prompts, ctxs, brs = [], [], collections.Counter()
    first = last = None
    for line in open(fp, errors="ignore"):
        if '"timestamp"' not in line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        try:
            t = dt.datetime.fromisoformat(d.get("timestamp", "").replace("Z", "+00:00"))
        except ValueError:
            t = None
        if t:
            first = t if first is None else min(first, t)
            last = t if last is None else max(last, t)
        for b in BRANCH.findall(line):
            if b not in BAD_BRANCHES:
                brs[b] += 1
        if d.get("isSidechain"):          # сабагент держит свой контекст, не наш
            continue
        if d.get("type") == "user":
            c = (d.get("message") or {}).get("content")
            ok = isinstance(c, str) and c.strip()
            if isinstance(c, list):
                # настоящий промпт человека: есть текст и нет tool_result
                ok = (any(x.get("type") == "text" for x in c if isinstance(x, dict))
                      and not any(x.get("type") == "tool_result" for x in c if isinstance(x, dict)))
            if ok and t:
                prompts.append(t)
        elif d.get("type") == "assistant":
            u = (d.get("message") or {}).get("usage") or {}
            if u:
                ctxs.append((t, u.get("input_tokens", 0)
                             + u.get("cache_creation_input_tokens", 0)
                             + u.get("cache_read_input_tokens", 0)))
    if first is None or not prompts:
        return None
    return prompts, ctxs, brs, first, last


def sessions(days):
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    for fp in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        try:
            if dt.datetime.fromtimestamp(os.path.getmtime(fp), dt.timezone.utc) < cut:
                continue
        except OSError:
            continue
        r = parse(fp)
        if r:
            yield os.path.relpath(fp, ROOT).split(os.sep)[0], r


hm = lambda s: f"{int(s // 3600)}ч{int(s % 3600 // 60):02d}м"
med = lambda a: sorted(a)[len(a) // 2] if a else 0
p90 = lambda a: sorted(a)[int(len(a) * 0.9)] if a else 0


def anatomy(days):
    rows = []
    for proj, (prompts, ctxs, brs, first, last) in sessions(days):
        prompts.sort()
        gaps = [(prompts[i + 1] - prompts[i]).total_seconds() for i in range(len(prompts) - 1)]
        idle = sum(g for g in gaps if g > GAP)
        wall = (last - first).total_seconds()
        rows.append(dict(proj=proj, wall=wall, idle=idle, n=len(prompts),
                         big=sum(1 for g in gaps if g > GAP),
                         ctx=max((c for _, c in ctxs), default=0), br=len(brs)))
    rows.sort(key=lambda r: -r["wall"])
    print(f"сессий за {days} дн: {len(rows)}   (пауза >{GAP//60}м = разрыв эпизода)\n")
    print(f"{'проект':<34}{'вся':>8}{'актив':>8}{'простой':>9}{'промпт':>7}{'разрыв':>7}{'ctx':>7}{'веток':>6}")
    for r in rows[:14]:
        print(f"{r['proj'][:33]:<34}{hm(r['wall']):>8}{hm(r['wall']-r['idle']):>8}"
              f"{hm(r['idle']):>9}{r['n']:>7}{r['big']:>7}{r['ctx']//1000:>6}k{r['br']:>6}")
    W = sum(r["wall"] for r in rows) or 1
    I = sum(r["idle"] for r in rows)
    print(f"\nИТОГО: вся {hm(W)}, простой {hm(I)} = {100*I/W:.0f}%, активная {hm(W-I)}")
    print(f"сессий с разрывом >{GAP//60}м: {sum(1 for r in rows if r['big'])}/{len(rows)}")
    print(f"сессий с >1 РЕАЛЬНОЙ веткой: {sum(1 for r in rows if r['br'] > 1)}/{len(rows)}"
          "  ← «новая проблема в старой сессии», маркера на это нет")


def threshold(days):
    """Эффект порога. Контроль обязателен: сессии после хука МОЛОЖЕ, и без
    отсечки живых разница объясняется возрастом, а не механизмом."""
    now = dt.datetime.now(dt.timezone.utc)
    res = collections.defaultdict(list)
    for _, (prompts, ctxs, _, first, last) in sessions(days):
        if (now - last).total_seconds() < FINISHED:
            continue                       # ещё живая — судить рано
        ev = sorted([(t, "p", 0) for t in prompts] + [(t, "c", v) for t, v in ctxs if t],
                    key=lambda x: x[0])
        born = first >= HOOK_BORN
        for thr in (150_000, 300_000):
            hit, n = False, 0
            for _, k, v in ev:
                if k == "c" and v >= thr:
                    hit = True
                elif k == "p" and hit:
                    n += 1
            if hit:
                res[(thr, born)].append(n)
    print(f"ТОЛЬКО ЗАВЕРШЁННЫЕ СЕССИИ (нет активности {FINISHED//3600}ч+), окно {days} дн")
    print("«после порога» = сколько промптов человека пришло уже за порогом\n")
    for thr in (150_000, 300_000):
        for born in (True, False):
            a = res[(thr, born)]
            tag = "хук ctx: БЫЛ" if born else "до хука     "
            print(f"{thr//1000}k · {tag} сессий {len(a):>3} · "
                  f"медиана {med(a):>3}, p90 {p90(a):>3}, макс {max(a) if a else 0:>3}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--threshold", action="store_true", help="эффект порога с контролем на возраст")
    a = ap.parse_args()
    threshold(a.days) if a.threshold else anatomy(a.days)
