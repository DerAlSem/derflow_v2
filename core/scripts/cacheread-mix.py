#!/usr/bin/env python3
r"""Из ЧЕГО состоит чтение кэша: содержимое файлов, разговор, вывод инструментов, канон.

Сосед `context-spend.py` отвечает «сколько» (77% расхода — cache-read). Этот
отвечает «чего именно», потому что от ответа зависит, стоит ли резать большие
файлы: если файлы в переотправке — единицы процентов, рефакторинг ради токенов
затевать не за чем.

Метод. Префикс запроса — это ровно цепочка предков по `parentUuid`. Обходим
дерево в глубину, на входе в узел прибавляем его размер к бегущей сумме по
категориям, на выходе вычитаем. В узле, открывающем новый `requestId`,
бегущая сумма И ЕСТЬ состав префикса этого запроса — складываем её в итог.
Сумма по всем запросам тогда сходится с Σ(input + cache_write + cache_read),
и расхождение — это статический префикс (системный промпт, определения
инструментов, CLAUDE.md, память) плюс ошибка оценки.

⚠️ Дедупликация обязательна: на один `requestId` в транскрипте ~1,88 записи
(блок мышления, блок текста, блок вызова — каждый своей строкой, `usage`
продублирована). Складывать построчно — завысить вдвое.

Размер в токенах оценивается по письменности (латиница ~3,7 знака на токен,
кириллица ~2,3) и потом нормируется на измеренный итог, так что абсолютные
числа честные, а относительные не врут в пользу прозы.
"""
import argparse, collections, glob, json, os, re, sys, datetime as dt

ROOT = os.path.expanduser("~/.claude/projects")

READ_BASH = re.compile(r'(?:^|[|;&(]\s*)(cat|head|tail|bat|less|more)\s|sed\s+-n', re.M)
WRITE_BASH = re.compile(r'<<\s*[\'"]?\w*EOF|<<\s*[\'"]?PY|>\s*[~/.\w]|>>\s*[~/.\w]')
CODE_PATH = re.compile(r'[\w./~-]*[\w-]+\.(?:py|ts|tsx|js|vue|md|json|sh|css|html|yml|yaml|sql|txt)\b')
CANON_PATH = re.compile(r'/\.claude/(skills|plugins)/|derflow|superpowers')

def sizes(s):
    """(знаков, токенов-оценка) для строки."""
    n = len(s)
    b = len(s.encode("utf-8", "replace"))
    cyr = max(0, b - n)          # двухбайтные ~ кириллица
    asc = max(0, n - cyr)
    return n, asc / 3.7 + cyr / 2.3

# Картинка стоит ~(ш×в)/750 токенов, обычно 1–2 тыс. В транскрипте она лежит
# base64-строкой на сотни килобайт. Считать её знаками — завысить в 300 раз;
# именно на этом первый прогон выдал «браузер съел 10% лимитов».
IMG_TOKENS = 1500.0

def _walk(x, acc):
    """acc = [знаков, токенов]; base64-картинки снимаются с посимвольного счёта."""
    if isinstance(x, str):
        a, b = sizes(x); acc[0] += a; acc[1] += b
    elif isinstance(x, dict):
        src = x.get("source")
        if isinstance(src, dict) and src.get("data"):
            acc[1] += IMG_TOKENS; acc[2] += 1
            for k, v in x.items():
                if k != "source": _walk(v, acc)
            return
        if x.get("type") == "base64" and x.get("data"):
            acc[1] += IMG_TOKENS; acc[2] += 1
            return
        for v in x.values(): _walk(v, acc)
    elif isinstance(x, list):
        for v in x: _walk(v, acc)

def measure(x):
    acc = [0, 0.0, 0]; _walk(x, acc)
    return acc[0], acc[1]

def fine_of(name, inp, cat):
    n = name or "?"
    if cat in ("файлы", "файлы(bash)", "bash", "канон", "правки"):
        if n == "Bash":
            cmd = str((inp or {}).get("command", "")) if isinstance(inp, dict) else ""
            m = CODE_PATH.search(cmd)
            if m: return f"{cat}:{m.group(0)[-60:]}"
            head = re.sub(r"\s+", " ", cmd.strip())[:40]
            return f"{cat}:{head}"
        fp = ""
        if isinstance(inp, dict):
            fp = str(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or "")
        return f"{cat}:{fp[-60:]}" if fp else f"{cat}:{n}"
    return f"{cat}:{n}"


def tool_cat(name, inp):
    n = name or "?"
    fp = ""
    if isinstance(inp, dict):
        fp = str(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or "")
    if n in ("Read", "NotebookRead"):
        return "канон" if CANON_PATH.search(fp) else "файлы"
    if n == "Skill": return "канон"
    if n in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return "канон" if CANON_PATH.search(fp) else "правки"
    if n in ("Grep", "Glob", "LS"): return "поиск"
    if n in ("Task", "Agent"): return "субагенты"
    if n in ("WebFetch", "WebSearch"): return "веб"
    if n == "Bash":
        cmd = str((inp or {}).get("command", "")) if isinstance(inp, dict) else ""
        if CANON_PATH.search(cmd): return "канон"
        # гетеродок и перенаправление — это ЗАПИСЬ: текст файла едет во входе вызова
        if WRITE_BASH.search(cmd): return "правки"
        return "файлы(bash)" if READ_BASH.search(cmd) else "bash"
    if n.startswith("mcp__"): return "mcp"
    if n in ("TodoWrite", "ExitPlanMode", "EnterPlanMode"): return "служебное"
    return "прочие-инструменты"

CATS = ["файлы", "файлы(bash)", "bash", "канон", "поиск", "субагенты", "веб",
        "mcp", "правки", "служебное", "прочие-инструменты",
        "мышление", "ответы", "человек", "хуки/вложения", "картинки"]

def node_payload(r, id2name, id2inp):
    """[(категория, знаков, токенов)] для одной записи транскрипта."""
    out = []
    t = r.get("type")
    a = r.get("attachment")
    if isinstance(a, dict):
        c, tk = measure(a)
        out.append(("хуки/вложения", "хуки/вложения:" + str(a.get("type")), c, tk))
    msg = r.get("message") or {}
    ct = msg.get("content")
    if isinstance(ct, str):
        c, tk = sizes(ct)
        k = "человек" if t == "user" else "ответы"
        out.append((k, k, c, tk))
    elif isinstance(ct, list):
        for b in ct:
            if not isinstance(b, dict): continue
            bt = b.get("type")
            if bt == "thinking":
                c, tk = measure(b.get("thinking") or "")
                out.append(("мышление", "мышление", c, tk))
            elif bt == "text":
                c, tk = measure(b.get("text") or "")
                k = "человек" if t == "user" else "ответы"
                out.append((k, k, c, tk))
            elif bt == "tool_use":
                cat = tool_cat(b.get("name"), b.get("input"))
                c, tk = measure(b.get("input"))
                # вход вызова: у Edit/Write это и есть новый текст файла
                out.append((cat, fine_of(b.get("name"), b.get("input"), cat), c, tk))
            elif bt == "tool_result":
                nm = id2name.get(b.get("tool_use_id"))
                ip = id2inp.get(b.get("tool_use_id"))
                cat = tool_cat(nm, ip)
                c, tk = measure(b.get("content"))
                out.append((cat, fine_of(nm, ip, cat), c, tk))
            elif bt == "image":
                c, tk = measure(b)
                out.append(("картинки", "картинки", c, tk))   # грубая оценка
    return out

def walk(path, tot_ch, tot_tk, acc, fcat):
    """acc: [запросов, Σ(in+cw+cr), список статических оценок]"""
    nodes, kids, roots = {}, collections.defaultdict(list), []
    id2name, id2inp = {}, {}
    orphan_att = collections.defaultdict(list)
    raw = []
    for line in open(path, encoding="utf-8", errors="replace"):
        try: r = json.loads(line)
        except Exception: continue
        raw.append(r)
        msg = r.get("message") or {}
        ct = msg.get("content")
        if isinstance(ct, list):
            for b in ct:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    id2name[b.get("id")] = b.get("name")
                    id2inp[b.get("id")] = b.get("input")
    for r in raw:
        u = r.get("uuid")
        if not u:
            if isinstance(r.get("attachment"), dict):
                orphan_att[r.get("parentUuid")].append(r)
            continue
        nodes[u] = r
    for u, r in nodes.items():
        p = r.get("parentUuid")
        (kids[p] if p in nodes else roots).append(u)
    payload = {}
    for u, r in nodes.items():
        pl = node_payload(r, id2name, id2inp)
        for extra in orphan_att.get(u, []):
            pl += node_payload(extra, id2name, id2inp)
        payload[u] = pl

    running_ch = collections.Counter(); running_tk = collections.Counter()
    for root in roots:
        stack = [(root, False, None)]
        rid_path = []          # requestId предков, чтобы не считать себя
        while stack:
            u, done, _ = stack.pop()
            r = nodes[u]
            if done:
                for cat, fine, c, t in payload[u]:
                    running_ch[fine] -= c; running_tk[fine] -= t; fcat[fine] = cat
                if rid_path and rid_path[-1][0] == u: rid_path.pop()
                continue
            rid = r.get("requestId") if r.get("type") == "assistant" else None
            new_req = bool(rid) and (not rid_path or rid_path[-1][1] != rid)
            if new_req:
                acc[0] += 1
                usg = (r.get("message") or {}).get("usage") or {}
                acc[1] += ((usg.get("input_tokens") or 0)
                           + (usg.get("cache_creation_input_tokens") or 0)
                           + (usg.get("cache_read_input_tokens") or 0))
                for cat in running_ch:
                    tot_ch[cat] += running_ch[cat]; tot_tk[cat] += running_tk[cat]
                if len(rid_path) == 0:
                    acc[2].append(((usg.get("input_tokens") or 0)
                                   + (usg.get("cache_creation_input_tokens") or 0)
                                   + (usg.get("cache_read_input_tokens") or 0),
                                   sum(running_tk.values())))
            for cat, fine, c, t in payload[u]:
                running_ch[fine] += c; running_tk[fine] += t; fcat[fine] = cat
            if rid: rid_path.append((u, rid))
            stack.append((u, True, None))
            for k in kids.get(u, []): stack.append((k, False, None))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--project", default=None, help="подстрока каталога проекта")
    ap.add_argument("--dump", default=None, help="выгрузить все тонкие метки в CSV")
    ap.add_argument("--top", type=int, default=0, help="показать N крупнейших источников поимённо")
    a = ap.parse_args()
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).timestamp()
    tot_ch = collections.Counter(); tot_tk = collections.Counter()
    acc = [0, 0, []]
    fcat = {}
    files = 0
    for p in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(p) < cut: continue
        except OSError: continue
        if a.project and a.project not in p: continue
        files += 1
        try: walk(p, tot_ch, tot_tk, acc, fcat)
        except Exception as e: print(f"! {p}: {e}", file=sys.stderr)

    nreq, actual, firsts = acc
    est = sum(tot_tk.values())
    # статический префикс: у первого запроса сессии префикс = статика + первый промпт
    stat = sorted(max(0, x - y) for x, y in firsts) if firsts else [0]
    static = stat[len(stat)//2] if stat else 0
    static_total = static * nreq
    dyn_actual = max(1, actual - static_total)
    k = dyn_actual / est if est else 1.0

    print(f"файлов транскриптов: {files}   запросов (дедуп): {nreq:,}   дней: {a.days}")
    print(f"Σ(input+cache_write+cache_read) = {actual/1e6:,.0f} M токенов — это и есть весь префиксный расход")
    print(f"статический префикс на запрос ≈ {static:,} токенов (медиана по первым запросам сессий)"
          f" → {static_total/1e6:,.0f} M ({static_total/max(1,actual)*100:.1f}%)")
    print(f"динамика (история сессии): {dyn_actual/1e6:,.0f} M ({dyn_actual/max(1,actual)*100:.1f}%)"
          f"   калибровка оценки ×{k:.2f}")
    print()
    print(f"{'категория':22} {'M токенов':>11} {'% динамики':>11} {'% всего':>9}")
    print("-" * 58)
    bycat = collections.Counter()
    for fine, v in tot_tk.items(): bycat[fcat.get(fine, "?")] += v
    rows = sorted(bycat.items(), key=lambda kv: -kv[1])
    for cat, tk in rows:
        v = tk * k
        if v / 1e6 < 0.5: continue
        print(f"{cat:22} {v/1e6:11,.0f} {v/dyn_actual*100:10.1f}% {v/actual*100:8.1f}%")
    if a.top:
        print()
        print(f"КРУПНЕЙШИЕ ИСТОЧНИКИ ПОИМЁННО (top {a.top}):")
        for fine, v in sorted(tot_tk.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {v*k/1e6:8,.1f} M {v*k/actual*100:5.2f}%  {fine[:96]}")
    if a.dump:
        with open(a.dump, "w", encoding="utf-8") as fh:
            fh.write("cat\tfine\tMtok\tpct_all\n")
            for fine, v in sorted(tot_tk.items(), key=lambda kv: -kv[1]):
                fh.write(f"{fcat.get(fine,'?')}\t{fine}\t{v*k/1e6:.3f}\t{v*k/actual*100:.4f}\n")
        print(f"\nвыгружено метками: {len(tot_tk)} → {a.dump}")
    fam = {"файлы": ["файлы", "файлы(bash)"], "канон": ["канон"],
           "разговор": ["человек", "ответы", "мышление"],
           "инструменты-прочее": ["bash", "поиск", "субагенты", "веб", "mcp",
                                  "правки", "служебное", "прочие-инструменты",
                                  "хуки/вложения", "картинки"]}
    print()
    print("СВОДКА ПО СЕМЕЙСТВАМ (доля всего префиксного расхода):")
    for name, cs in fam.items():
        v = sum(bycat[c] for c in cs) * k
        print(f"  {name:20} {v/1e6:8,.0f} M   {v/actual*100:5.1f}%")
    print(f"  {'статический префикс':20} {static_total/1e6:8,.0f} M   {static_total/actual*100:5.1f}%")

main()
