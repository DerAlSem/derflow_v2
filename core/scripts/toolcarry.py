#!/usr/bin/env python3
r"""Сколько вывода инструментов реально уезжает дальше по сессии.

Замерено 12.09.2026 по 1382 транскриптам (2,1 ГБ): вывод Bash — 100,7 млн
знаков, и в СЛЕДУЮЩИЙ ход ассистента из него уезжает 2,9%, а за всю сессию —
28,5%. Больше половины вызовов (55,8%) не всплывают потом нигде.

**Мерило — текстовый перенос, а не польза, и путать их нельзя.** Строка вывода
считается уехавшей, если несёт токен (≥4 знаков), которого нет в тексте самой
команды, который до этого вывода в сессии не встречался ВООБЩЕ и который потом
всплывает в ходе ассистента. Молчаливое решение сюда не попадает: ход, прочитавший
движок на 12 тыс. знаков и попросивший следующие 240 строк, даёт перенос ноль, а
прочитанное кормит всю полосу. Поэтому число — НИЖНЯЯ граница.

Рядом держится мягкий счёт (любой токен, не только новый) — он верхняя граница и
раздут совпадениями частых слов. Врозь каждый врёт в свою сторону; смысл имеет
только вилка.

Два режима:
  отчёт  — разрезы по инструментам, по объёму вывода и по росту сессии;
  --probe — один вердикт для реестра отложки (см. `waiting/`).

⚠️ Разрез «по росту сессии» без окна ВРЁТ: у позднего вызова меньше сессии
впереди, и токену просто негде всплыть. Усечение справа выглядит деградацией.
Поэтому `--window` отбрасывает вызовы, которым до конца сессии осталось меньше
окна, и считает перенос только внутри него.
"""
import argparse, bisect, collections, json, os, re, sys

TOK = re.compile(r'[A-Za-z0-9_Ѐ-ӿ][A-Za-z0-9_./\-Ѐ-ӿ]{3,}')
CD = re.compile(r'^\s*cd\s+\S+\s*(&&|;)\s*')
PROJECTS = os.path.expanduser('~/.claude/projects')
BUCKETS = [0, 25, 50, 100, 200, 400, 800, 1600, 10 ** 9]


def toks(s):
    return {m.group(0).lower() for m in TOK.finditer(s)}


def cmd_head(c):
    """Первое СОДЕРЖАТЕЛЬНОЕ слово команды: `cd ~/x && git log` — это git, не cd.

    Без снятия префикса разбивка отдавала 59% знаков корпуса команде `cd` и не
    объясняла ничего: переход стоит почти у каждой команды этого репозитория.
    """
    c = (c or '').strip()
    for _ in range(4):
        c2 = CD.sub('', c)
        if c2 == c:
            break
        c = c2
    w = re.sub(r'^\W+', '', c).split()
    return w[0].split('/')[-1] if w else '?'


def res_text(b):
    c = b.get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return '\n'.join(x.get('text', '') for x in c if isinstance(x, dict))
    return ''


def entry_text(d):
    c = d.get('message', {}).get('content', [])
    if isinstance(c, str):
        return c
    parts = []
    for b in (c if isinstance(c, list) else []):
        if not isinstance(b, dict):
            continue
        t = b.get('type')
        if t == 'text':
            parts.append(b.get('text', ''))
        elif t == 'thinking':
            parts.append(b.get('thinking', ''))
        elif t == 'tool_use':
            parts.append(json.dumps(b.get('input', {}), ensure_ascii=False))
        elif t == 'tool_result':
            parts.append(res_text(b))
    return '\n'.join(parts)


class Acc:
    def __init__(self):
        self.tool = collections.defaultdict(collections.Counter)
        self.ctx = collections.defaultdict(collections.Counter)
        self.size = collections.defaultdict(collections.Counter)
        self.head = collections.defaultdict(collections.Counter)
        self.pos = collections.Counter()
        self.tot = collections.Counter()


def bucket(n):
    k = n // 1000
    for i in range(len(BUCKETS) - 1):
        if BUCKETS[i] <= k < BUCKETS[i + 1]:
            return i
    return len(BUCKETS) - 2


def size_bucket(n):
    for i, hi in enumerate((500, 2000, 10000)):
        if n <= hi:
            return i
    return 3


def scan(path, acc, window=0, only=None):
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            entries = [json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        acc.tot['bad'] += 1
        return
    acc.tot['files'] += 1

    texts = [entry_text(d) for d in entries]
    ctx = [0] * (len(entries) + 1)
    for i, t in enumerate(texts):
        ctx[i + 1] = ctx[i] + len(t)
    total = ctx[-1]

    # ход ассистента = все его записи ПОДРЯД до записи пользователя. Взять первую
    # запись за ход значило мерить пустоту: транскрипт режет ход на несколько
    # записей, и первая часто несёт пустой текстовый блок. Первая редакция замера
    # дала на этом 89,6% «нулевого переноса» — цифру круглую и целиком ложную.
    turn_text, turn_pos, turn_before = [], [], {}
    cur, open_at = [], None
    done = 0
    for i, d in enumerate(entries):
        turn_before[i] = done
        if d.get('type') == 'assistant':
            if open_at is None:
                open_at = ctx[i]
            cur.append(texts[i])
        elif open_at is not None:
            turn_text.append('\n'.join(cur))
            turn_pos.append(open_at)
            cur, open_at = [], None
            done += 1
            turn_before[i] = done
    if open_at is not None:
        turn_text.append('\n'.join(cur))
        turn_pos.append(open_at)

    where = collections.defaultdict(list)
    for k, t in enumerate(turn_text):
        for tok in toks(t):
            where[tok].append(k)
    first_seen = {}
    for i in range(len(entries)):
        k = turn_before[i]
        for tok in toks(texts[i]):
            if tok not in first_seen:
                first_seen[tok] = k

    tu = {}
    for d in entries:
        if d.get('type') == 'assistant':
            for b in (d.get('message', {}).get('content') or []):
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    tu[b['id']] = (b.get('name'), b.get('input', {}))

    for i, d in enumerate(entries):
        if d.get('type') != 'user':
            continue
        if window and total - ctx[i] < window:
            continue
        for b in (d.get('message', {}).get('content') or []):
            if not (isinstance(b, dict) and b.get('type') == 'tool_result'):
                continue
            meta = tu.get(b.get('tool_use_id'))
            if meta is None:
                continue
            name, inp = meta
            if only and name != only:
                continue
            out = res_text(b)
            if not out:
                continue
            k = turn_before[i]
            if k >= len(turn_text):
                continue
            limit = ctx[i] + window if window else None
            ct = toks(json.dumps(inp, ensure_ascii=False))
            strict = nxt = soft = 0
            lines = out.split('\n')
            for li, ln in enumerate(lines):
                lt = toks(ln) - ct
                if not lt:
                    continue
                s_first = n_any = None
                for tok in lt:
                    idxs = where.get(tok)
                    if not idxs:
                        continue
                    p = bisect.bisect_left(idxs, k)
                    if p >= len(idxs):
                        continue
                    if limit is not None and turn_pos[idxs[p]] > limit:
                        continue
                    n_any = idxs[p] if n_any is None else min(n_any, idxs[p])
                    if first_seen.get(tok, -1) >= k:
                        s_first = idxs[p] if s_first is None else min(s_first, idxs[p])
                n = len(ln) + 1
                if n_any is not None:
                    soft += n
                if s_first is not None:
                    strict += n
                    if s_first == k:
                        nxt += n
                        acc.pos[min(li // 10, 20)] += n
            for agg, key in ((acc.tool, name), (acc.ctx, bucket(ctx[i])),
                             (acc.size, size_bucket(len(out)))):
                e = agg[key]
                e['calls'] += 1
                e['chars'] += len(out)
                e['strict'] += strict
                e['next'] += nxt
                e['soft'] += soft
                if strict == 0:
                    e['dead'] += 1
            if name == 'Bash':
                e = acc.head[cmd_head(inp.get('command'))]
                e['calls'] += 1
                e['chars'] += len(out)
                e['strict'] += strict
            acc.tot['calls'] += 1
            acc.tot['chars'] += len(out)
            acc.tot['strict'] += strict
            acc.tot['next'] += nxt
            acc.tot['soft'] += soft
            if strict == 0:
                acc.tot['dead'] += 1


def files(root, recent=0, max_mb=0):
    out = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.jsonl'):
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if max_mb and st.st_size > max_mb * 1048576:
                    continue
                out.append((st.st_mtime, p))
    out.sort(reverse=True)
    if recent:
        out = out[:recent]
    return [p for _, p in out]


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def report(acc, window):
    t = acc.tot
    c = t['chars']
    print(f"файлов {t['files']} (нечитаемых {t['bad']}) · вызовов {t['calls']:,} · знаков вывода {c:,}")
    if window:
        print(f"окно {window:,} знаков вперёд; вызовы с меньшим остатком сессии отброшены")
    print(f"\nперенос: строгий (новое) {pct(t['strict'], c):.1f}%   мягкий (любой токен) {pct(t['soft'], c):.1f}%"
          f"   в следующий ход {pct(t['next'], c):.1f}%")
    print(f"вызовов, чей вывод не всплыл нигде: {t['dead']:,} ({pct(t['dead'], t['calls']):.1f}%)")

    print(f"\n{'инструмент':<34}{'вызовов':>9}{'знаков':>14}{'строгий':>9}{'в след.':>9}{'мёртвых':>9}")
    for name, e in sorted(acc.tool.items(), key=lambda kv: -kv[1]['chars'])[:12]:
        print(f"{name[:33]:<34}{e['calls']:>9,}{e['chars']:>14,}{pct(e['strict'], e['chars']):>8.1f}%"
              f"{pct(e['next'], e['chars']):>8.1f}%{pct(e['dead'], e['calls']):>8.0f}%")

    print(f"\n{'объём вывода':<34}{'вызовов':>9}{'знаков':>14}{'строгий':>9}{'':>9}{'мёртвых':>9}")
    for i, lab in enumerate(('до 500', '500–2000', '2000–10000', 'свыше 10000')):
        e = acc.size.get(i)
        if e:
            print(f"{lab:<34}{e['calls']:>9,}{e['chars']:>14,}{pct(e['strict'], e['chars']):>8.1f}%"
                  f"{'':>9}{pct(e['dead'], e['calls']):>8.0f}%")

    print(f"\n{'объём сессии до вызова':<34}{'вызовов':>9}{'знаков':>14}{'строгий':>9}{'в след.':>9}{'мёртвых':>9}")
    for i in range(len(BUCKETS) - 1):
        e = acc.ctx.get(i)
        if not e:
            continue
        lo, hi = BUCKETS[i], BUCKETS[i + 1]
        lab = f"{lo}k–{hi}k" if hi < 10 ** 8 else f"{lo}k и дальше"
        print(f"{lab:<34}{e['calls']:>9,}{e['chars']:>14,}{pct(e['strict'], e['chars']):>8.1f}%"
              f"{pct(e['next'], e['chars']):>8.1f}%{pct(e['dead'], e['calls']):>8.0f}%")

    tot = sum(acc.pos.values())
    if tot:
        print("\nгде сидит перенос в следующий ход (позиция строки в выводе):")
        acc_n = 0
        for bk in sorted(acc.pos):
            acc_n += acc.pos[bk]
            lab = f"строки {bk * 10}–{bk * 10 + 9}" if bk < 20 else "строки 200 и дальше"
            print(f"  {lab:<24}{pct(acc.pos[bk], tot):5.1f}%   накоплено {pct(acc_n, tot):5.1f}%")

    if acc.head:
        print(f"\n{'команда Bash':<34}{'вызовов':>9}{'знаков':>14}{'строгий':>9}")
        for h, e in sorted(acc.head.items(), key=lambda kv: -kv[1]['chars'])[:10]:
            print(f"{h[:33]:<34}{e['calls']:>9,}{e['chars']:>14,}{pct(e['strict'], e['chars']):>8.1f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('root', nargs='?', default=PROJECTS)
    ap.add_argument('--window', type=int, default=0,
                    help='окно переноса в знаках; 0 — до конца сессии (разрез по росту сессии тогда врёт)')
    ap.add_argument('--recent', type=int, default=0, help='только N свежайших транскриптов')
    ap.add_argument('--max-mb', type=int, default=0, help='пропускать транскрипты крупнее, МБ')
    ap.add_argument('--tool', default=None, help='только этот инструмент')
    ap.add_argument('--probe', action='store_true', help='вердикт для реестра отложки')
    ap.add_argument('--baseline', type=float, default=55.8,
                    help='база доли мёртвых вызовов Bash, %% (замер 12.09.2026)')
    ap.add_argument('--tolerance', type=float, default=10.0, help='допуск в процентных пунктах')
    ap.add_argument('--min-calls', type=int, default=300, help='ниже этого числа вызовов проба НЕ отвечает')
    a = ap.parse_args()

    acc = Acc()
    only = 'Bash' if a.probe else a.tool
    for p in files(a.root, a.recent, a.max_mb):
        scan(p, acc, a.window, only)

    if not a.probe:
        report(acc, a.window)
        return 0

    # Мало данных — это «не смогли спросить», а не «событие не наступило».
    # Напечатать здесь «держится» значило бы соврать в тишину: реестр записал бы
    # молчание там, где ответа не было вовсе.
    n = acc.tot['calls']
    if n < a.min_calls:
        print(f"вызовов всего {n}, порог {a.min_calls} — отвечать не на чем", file=sys.stderr)
        return 2
    dead = pct(acc.tot['dead'], n)
    drift = dead - a.baseline
    verdict = 'КАРТИНА-ИЗМЕНИЛАСЬ' if abs(drift) > a.tolerance else 'КАРТИНА-ДЕРЖИТСЯ'
    print(f"{verdict} мёртвых {dead:.1f}% при базе {a.baseline:.1f}% "
          f"(снос {drift:+.1f} п.п., допуск ±{a.tolerance:.0f}), вызовов {n}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
