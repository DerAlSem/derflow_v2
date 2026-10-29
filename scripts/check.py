#!/usr/bin/env python3
"""check — утверждения памяти и спек против кода.

Спека говорит, что ДОЛЖНО быть истинно; память — где ошибётся следующий. Обе
называют символы и пути. Файл переименовали — и обе тихо стали ложью: git этого
не заметит, критик читает текст против текста, а `openspec validate` проверяет
форму. Здесь текст читается против КОДА.

    check.py [repo]              # по умолчанию — cwd
    check.py --selftest          # укус сторожа на фикстуре

Вторая половина — ГИГИЕНА: франтматтер памяти и вес индекса. Она отвечает не на
«врёт ли память», а на «доедет ли она»: индекс всегда загружен и при
переполнении обрезается молча.

    check.py [repo]              # по умолчанию — cwd
    check.py --selftest          # укус сторожа на фикстуре

Отчёт, а не гейт: код возврата всегда 0, читает человек. Гоняется перед
архивацией заявки и на гигиене памяти.

⚠️ Гнать ТОЛЬКО на верхушке рабочей ветки. Индекс строится по дереву на диске, и
на старом срезе живые символы читаются как отсутствующие: боевое 06.09.2026 —
основной репозиторий стоял в detached HEAD на теге пятидневной давности, отчёт
дал 78 находок, и проверенные из них (`job_run`, `record_package_sale`,
`legal_entity_player`, `per_pair`) все нашлись в `main`. Отчёт выглядит
авторитетно и врёт ровно там, где код ушёл вперёд.
"""

import argparse, os, pathlib, re, subprocess, sys, tempfile, shutil, collections

# ── формы токенов ─────────────────────────────────────────────────────────────
# Проза в бэктиках не проходит ни одну: русское слово не snake, не Camel, не путь.
TICK  = re.compile(r"`([^`\n]{2,100})`")
WIKI  = re.compile(r"\[\[([^\]\n]{1,120})\]\]")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
CAMEL = re.compile(r"^[A-Z][A-Za-z0-9]*[a-z][A-Z][A-Za-z0-9]*$")
DOTT  = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")

EXT = ("py js jsx ts tsx vue svelte html htm css scss sass sql sh bash zsh md yaml yml "
       "json toml ini cfg conf txt env mako jinja jinja2 j2 rb go rs java kt php lua tf").split()
PATHR = re.compile(r"^[\w][\w./@-]*\.(" + "|".join(EXT) + r")$")

# Каталоги, которых в дереве кода нет по смыслу: чужое, сборочное, изолированное.
SKIPDIR = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".claude",
           "dist", "build", ".next", ".nuxt", ".mypy_cache", ".pytest_cache",
           ".ruff_cache", "site-packages", ".tox", "coverage", ".idea", ".vscode"}
BINARY  = {".png",".jpg",".jpeg",".gif",".webp",".ico",".svg",".pdf",".zip",".gz",".tar",
           ".woff",".woff2",".ttf",".otf",".eot",".mp4",".mp3",".wav",".db",".sqlite",
           ".sqlite3",".pyc",".pyo",".so",".dylib",".dll",".bin",".xlsx",".docx",".psd"}
LOCKS   = {"package-lock.json","yarn.lock","poetry.lock","pnpm-lock.yaml","Pipfile.lock",
           "uv.lock","composer.lock","Cargo.lock"}
MAXSIZE = 2 * 1024 * 1024


def shape(tok):
    """Какого рода утверждение это может быть; None — проза, не проверяем.

    Путь обязан нести расширение и не начинаться со слэша. Оба условия оплачены
    живым прогоном: без первого в «пути» проваливаются URL-маршруты (`/events/:id`)
    и команды оболочки, и 13 находок превращаются в 326 — отчёт, который не читают.
    """
    if re.search(r"\s", tok): return None
    if tok.startswith(("/", "http://", "https://")): return None
    if PATHR.match(tok.removeprefix("./")): return "path"
    if DOTT.match(tok):  return "dotted"
    if SNAKE.match(tok): return "snake"
    if CAMEL.match(tok): return "camel"
    return None


def build_index(repo):
    """Один проход. Идентификаторы — ТОЛЬКО из кода.

    Markdown в индекс идентификаторов не входит намеренно: пустив его туда,
    получишь спеку, которая удовлетворяет сама себя — символ найдётся в её же
    тексте, и чекер зазеленеет на всех настоящих находках. Пути при этом берутся
    из ВСЕХ файлов, включая `openspec/**/*.md`: ссылка на `tasks.md` заявки —
    законное утверждение о дереве.
    """
    idents, paths, basenames, ncode = set(), set(), set(), 0
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIPDIR]
        for name in files:
            p = pathlib.Path(root) / name
            try: rel = p.relative_to(repo).as_posix()
            except ValueError: continue
            paths.add(rel); basenames.add(name)
            if p.suffix.lower() in BINARY or name in LOCKS or p.suffix.lower() == ".md":
                continue
            try:
                if p.stat().st_size > MAXSIZE: continue
                idents.update(IDENT.findall(p.read_text(encoding="utf-8", errors="ignore")))
                ncode += 1
            except OSError:
                continue
    return {"idents": idents, "paths": paths, "basenames": basenames, "ncode": ncode}


def main_worktree(repo):
    """Ворктри памяти не имеет: слаг берётся у ОСНОВНОГО дерева репозитория.

    `--show-toplevel` в ворктри отдаёт сам ворктри, и слаг ведёт в пустой
    каталог. `--git-common-dir` — общий на все деревья: в ворктри он указывает
    на `.git` основного, а рядом с ним и лежит то дерево. Знание проекта одно на
    репозиторий, а не на рабочую копию.
    """
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse",
                            "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            common = pathlib.Path(r.stdout.strip())
            if common.name == ".git" and common.parent.is_dir():
                return common.parent
    except OSError:
        pass
    return repo


def memory_dir(repo, override=None):
    """Каталог памяти привязан к слагу каталога: не-буквенно-цифровое → дефис."""
    if override: return pathlib.Path(override).expanduser()
    slug = re.sub(r"[^a-zA-Z0-9]", "-", str(main_worktree(repo)))
    return pathlib.Path.home() / ".claude" / "projects" / slug / "memory"


# ── гигиена памяти ────────────────────────────────────────────────────────────
# Второй вопрос, не тот же самый. Остальной чекер спрашивает «не врёт ли память»;
# здесь — «доедет ли она вообще». Индекс всегда загружен и при переполнении
# обрезается МОЛЧА: это потеря без предупреждения, поэтому мерить надо заранее.
IDX_MAX_BYTES = 25 * 1024
IDX_MAX_LINES = 200
PTR_MAX = 120                      # знаков в строке-указателе; детали живут в теле
LIVES = re.compile(r"^\s*живёт до:\s*(\S.*?)\s*$", re.M)
DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
IDXROW = re.compile(r"^\s*[-*]\s*\[[^\]]*\]\(([^)]+\.md)\)", re.M)
SUPERS = re.compile(r"^\s*supersedes:\s*(\S.*?)\s*$", re.M)


def hygiene(mem, memfiles, today=None):
    """Франтматтер и вес индекса — сводкой, а не построчно.

    Построчно здесь нельзя: «нет срока» у 99 файлов из 100 даёт 99 находок, то
    есть отчёт, который не читают. Тот же урок, что уже оплачен формой путей.
    Поимённо печатается лишь то, на что можно ДЕЙСТВОВАТЬ: истёкший срок, сирота,
    битый указатель, самая длинная строка.
    """
    import datetime
    today = today or datetime.date.today()
    # Сам индекс — не память: у него нет ни срока, ни строки о себе. Оставленный
    # в наборе, он честно печатался сиротой и завышал «без срока» на единицу.
    memfiles = [f for f in memfiles if f.name != "MEMORY.md"]
    h = {"есть": bool(memfiles), "истёк": [], "прозой": 0, "без срока": [],
         "сироты": [], "битые": [], "длинные": [], "самая длинная": None,
         "вытеснены": [], "байт": 0, "строк": 0}
    if not memfiles:
        return h

    for f in memfiles:
        try:
            head = f.read_text(encoding="utf-8")[:2000]
        except OSError:
            continue
        # Собирается ДО разбора срока: ниже стоят ранние `continue`, и запись,
        # объявившая вытеснение, но не объявившая срок, потеряла бы `supersedes`.
        for s in SUPERS.findall(head):
            h["вытеснены"].extend(n.strip().strip("`") for n in s.split(",") if n.strip())
        m = LIVES.search(head)
        if not m:
            h["без срока"].append(f.name)
            continue
        val = m.group(1)
        d = DATE.search(val)
        if not d:
            h["прозой"] += 1
            continue
        try:
            when = datetime.date(int(d.group(3)), int(d.group(2)), int(d.group(1)))
        except ValueError:
            h["прозой"] += 1
            continue
        if when < today:
            h["истёк"].append((f.name, val))

    idx = mem / "MEMORY.md"
    if not idx.is_file():
        return h
    try:
        text = idx.read_text(encoding="utf-8")
    except OSError:
        return h
    h["байт"] = len(text.encode("utf-8"))
    lines = text.splitlines()
    h["строк"] = len(lines)
    for ln in lines:
        s = ln.strip()
        if len(s) > PTR_MAX:
            h["длинные"].append(s)
    if h["длинные"]:
        h["самая длинная"] = max(h["длинные"], key=len)

    # Целостность индекса. Ручная сверка здесь уже соврала однажды: разбор
    # 01.09.2026 отчитался «битых указателей ноль», а их было шесть. После
    # массовой правки это проверяется механически или не проверяется вовсе.
    named = {t.split("/")[-1] for t in IDXROW.findall(text)}
    have = {f.name for f in memfiles}
    h["битые"] = sorted(named - have)
    # Вытесненная запись по построению НЕ в индексе: канон велит убрать её строку,
    # а тело оставить находимым. Сторож, звавший её сиротой, краснел на ПРАВИЛЬНОМ
    # состоянии — и тем учил себя игнорировать. Имя в `supersedes` — это `name`
    # записи, файл её — `<name>.md`; сводится по этому правилу, не по строке.
    h["сироты"] = sorted(have - named - {n + ".md" for n in h["вытеснены"]})
    return h


def report_hygiene(h):
    """Печатает блок и возвращает число находок, требующих действия."""
    print("\nГИГИЕНА ПАМЯТИ")
    if not h["есть"]:
        print("  — каталог памяти пуст; пусто ≠ чисто (в ворктри он пуст всегда)")
        return 0

    pct = 100 * h["байт"] // IDX_MAX_BYTES if IDX_MAX_BYTES else 0
    flag = "  ⚠️ ПОТОЛОК" if h["байт"] > IDX_MAX_BYTES else ""
    print(f"  индекс   {h['байт']} Б из {IDX_MAX_BYTES} ({pct}%), "
          f"{h['строк']} строк из {IDX_MAX_LINES}{flag}")

    nlong = len(h["длинные"])
    if nlong:
        print(f"  строки   {nlong} длиннее {PTR_MAX} знаков — "
              f"место деталей в теле файла, не в указателе")
        s = h["самая длинная"]
        print(f"           самая длинная {len(s)}: {s[:70]}…")
    else:
        print(f"  строки   все ≤{PTR_MAX} знаков")

    nno = len(h["без срока"])
    print(f"  срок     без `живёт до:` — {nno}; прозой — {h['прозой']}; "
          f"датой — {len(h['истёк'])} истёкших")
    if h["прозой"]:
        print("           прозой объявленный срок НИКТО НЕ СТОРОЖИТ — это отчёт, не гейт")
    if h["вытеснены"]:
        print(f"  вытеснено {len(h['вытеснены'])} — тело на месте, строки в индексе "
              f"нет ПО КАНОНУ: {', '.join(sorted(h['вытеснены']))}")
    for name, val in h["истёк"]:
        print(f"  ✗ {name} — срок истёк: {val}")
    for name in h["битые"]:
        print(f"  ✗ {name} — индекс называет файл, которого нет")
    for name in h["сироты"]:
        print(f"  ✗ {name} — файл есть, строки в индексе нет")

    return len(h["истёк"]) + len(h["битые"]) + len(h["сироты"])


def changes(repo):
    live, arch = set(), set()
    c = repo / "openspec" / "changes"
    if c.is_dir():
        for d in c.iterdir():
            if d.is_dir() and d.name != "archive": live.add(d.name)
        a = c / "archive"
        if a.is_dir():
            arch = {d.name for d in a.iterdir() if d.is_dir()}
    return live, arch


def verify(tok, kind, idx):
    """(ок, пояснение). Не найдено — значит в коде правда нет: индекс полон по построению."""
    if kind == "path":
        tok = tok.removeprefix("./")
        if tok in idx["paths"]:                  return True, "точно"
        if tok.split("/")[-1] in idx["basenames"]: return True, "по имени файла"
        return False, "файла нет в дереве"
    if kind == "dotted":
        segs = [s for s in tok.split(".") if len(s) > 2]
        miss = [s for s in segs if s not in idx["idents"]]
        return (not miss), ("нет: " + ", ".join(miss) if miss else "")
    return (tok in idx["idents"]), "нет в коде"


def scan(files, label, idx, mem_names, arch, findings):
    """Разбирает корпус и складывает находки в общий список."""
    for f in files:
        try: text = f.read_text(encoding="utf-8")
        except OSError: continue
        src = f"{label}: {f.parent.name if f.name == 'spec.md' else f.name}"

        for m in TICK.finditer(text):
            tok = m.group(1).strip()
            kind = shape(tok)
            if not kind: continue
            ok, why = verify(tok, kind, idx)
            if not ok:
                findings["путь" if kind == "path" else "символ"].append((tok, why, src))

        if label == "память":
            for m in WIKI.finditer(text):
                name = m.group(1).strip()
                if name not in mem_names:
                    findings["связь"].append((f"[[{name}]]", "такой памяти нет", src))

        for cid in arch:
            if re.search(r"(?<![\w-])" + re.escape(cid) + r"(?![\w-])", text):
                findings["заявка"].append((cid, "в archive/", src))


def report(repo, idx, mem, memfiles, specfiles, findings, hyg=None):
    print(f"\ncheck · {repo.name}")
    print(f"  индекс   {idx['ncode']} файлов кода, {len(idx['idents'])} идентификаторов, "
          f"{len(idx['paths'])} путей")
    if memfiles is None:
        print(f"  ПАМЯТЬ НЕ ПРОВЕРЕНА — каталога нет или он пуст: {mem}")
        print( "           пусто ≠ чисто: у проекта может не быть памяти вовсе")
    else:
        print(f"  память   {len(memfiles)} файлов")
    print(f"  спеки    {len(specfiles)} файлов")

    order = [("путь",   "ПУТИ — файла нет в дереве"),
             ("связь",  "СВЯЗИ ПАМЯТИ — битые"),
             ("заявка", "ЗАЯВКИ — названы, но заархивированы"),
             ("символ", "СИМВОЛЫ — нет в коде  ·  здесь живёт чужой словарь, читай глазами")]
    total = 0
    for key, title in order:
        rows = collections.OrderedDict()
        for tok, why, src in findings[key]:
            rows.setdefault((tok, why), []).append(src)
        print(f"\n{title} ({len(rows)})")
        if not rows:
            print("  —")
        for (tok, why), srcs in sorted(rows.items()):
            mark = "→" if key == "заявка" else "✗"
            print(f"  {mark} {tok}{('  — ' + why) if why else ''}")
            seen = sorted(set(srcs))
            print(f"      {', '.join(seen[:3])}" + (f" и ещё {len(seen)-3}" if len(seen) > 3 else ""))
        total += len(rows)
    if hyg is not None:
        total += report_hygiene(hyg)
    print(f"\nитого {total} находок\n")
    return total


def run(repo, mem_override=None, quiet=False):
    repo = pathlib.Path(repo).expanduser().resolve()
    try:
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True)
        if top.returncode == 0 and top.stdout.strip():
            repo = pathlib.Path(top.stdout.strip())
    except OSError:
        pass

    idx = build_index(repo)
    mem = memory_dir(repo, mem_override)
    memfiles = sorted(mem.glob("*.md")) if mem.is_dir() else []
    mem_names = {f.stem for f in memfiles}
    # Спеки живут в двух местах: доки capability docflow и openspec (закрыт с 24.09).
    # bl-migrate копирует spec.md в доку и оставляет оригинал: после первой правки
    # доки оригинал врёт вечно. Есть доки — читаются только они.
    caps = sorted((repo / "backlog" / "docs" / "capabilities").glob("*.md"))
    specfiles = caps or sorted((repo / "openspec" / "specs").glob("*/spec.md"))
    _, arch = changes(repo)

    findings = collections.defaultdict(list)
    scan(memfiles, "память", idx, mem_names, arch, findings)
    scan(specfiles, "спека", idx, mem_names, arch, findings)

    if quiet:
        return findings
    return report(repo, idx, mem, memfiles or None, specfiles, findings,
                  hygiene(mem, memfiles))


def selftest_worktree():
    """Укус на ворктри: слаг обязан вести в память ОСНОВНОГО дерева.

    Проверка без сети и без чужих каталогов — сравниваются только пути. Наивный
    слаг ворктри тоже вычисляется: без него зелёный ничего не доказывает, ведь
    совпадение могло бы выйти и по построению.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="check-wt-"))
    ok = True
    try:
        repo, wt = tmp / "repo", tmp / "wt"
        repo.mkdir()
        env = ["-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]
        run_git = lambda *a: subprocess.run(["git", "-C", str(repo)] + list(a),
                                            capture_output=True, text=True)
        subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, text=True)
        (repo / "f.txt").write_text("x\n")
        run_git("add", "-A"); run_git(*env, "commit", "-qm", "init")
        r = run_git("worktree", "add", "-q", str(wt), "-b", "wtbranch")
        if not wt.is_dir():
            print(f"✗ ворктри не создан: {r.stderr.strip()[:120]}"); return False

        naive = pathlib.Path.home() / ".claude" / "projects" / \
            re.sub(r"[^a-zA-Z0-9]", "-", str(wt)) / "memory"
        if memory_dir(wt) == memory_dir(repo) and memory_dir(wt) != naive:
            print("✓ ворктри: память берётся у основного дерева, не по своему слагу")
        else:
            print(f"✗ ворктри ведёт не туда: {memory_dir(wt)}"); ok = False

        # отрицательный контроль: вне git подмены быть не должно
        plain = tmp / "plain"; plain.mkdir()
        if memory_dir(plain) == pathlib.Path.home() / ".claude" / "projects" / \
                re.sub(r"[^a-zA-Z0-9]", "-", str(plain)) / "memory":
            print("✓ не-git каталог: слаг остаётся своим")
        else:
            print(f"✗ не-git каталог подменён: {memory_dir(plain)}"); ok = False

        # ручка сильнее механизма: явный --memory-dir не перебивается
        if memory_dir(wt, override=str(tmp / "explicit")) == tmp / "explicit":
            print("✓ --memory-dir перебивает механизм")
        else:
            print("✗ --memory-dir не сработал"); ok = False
    finally:
        subprocess.run(["git", "-C", str(tmp / "repo"), "worktree", "prune"],
                       capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def selftest_hygiene():
    """Гигиена проверяется отдельно: она читает франтматтер, а не код.

    Мутация здесь — дописать срок файлу, у которого его нет. Счёт обязан упасть
    ровно на единицу; сторож, зеленеющий и до и после, не охраняет ничего.
    """
    import datetime
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="check-hyg-"))
    ok = True
    try:
        memd = tmp / "memory"
        memd.mkdir(parents=True)
        (memd / "trap.md").write_text(
            "---\nname: trap\nmetadata:\n  живёт до: бессрочно — ловушка\n---\n\nтело\n")
        (memd / "rotten.md").write_text(
            "---\nname: rotten\nmetadata:\n  живёт до: до выката 01.01.2020\n---\n\nтело\n")
        (memd / "bare.md").write_text("---\nname: bare\n---\n\nтело\n")
        (memd / "orphan.md").write_text("---\nname: orphan\n---\n\nтело\n")
        # Пара «вытесненная — вытеснившая»: ровно то состояние, которое канон
        # считает ПРАВИЛЬНЫМ, а сторож до 14.09.2026 печатал сиротой.
        (memd / "old.md").write_text(
            "---\nname: old\nmetadata:\n  живёт до: до выката 01.01.2030\n---\n\nтело\n")
        (memd / "new.md").write_text(
            "---\nname: new\nsupersedes: old\nmetadata:\n"
            "  живёт до: до выката 01.01.2030\n---\n\nтело\n")
        (memd / "MEMORY.md").write_text(
            "- [Ловушка](trap.md) — коротко\n"
            "- [Протухла](rotten.md) — коротко\n"
            "- [Голая](bare.md) — " + "х" * 200 + "\n"
            "- [Сменщица](new.md) — вытеснила old\n"
            "- [Призрак](gone.md) — указатель в никуда\n")

        # Набор отдаётся ТАК ЖЕ, как его отдаёт run() — вместе с самим индексом.
        # Фикстура, отфильтровавшая его заранее, зеленела, а живой прогон печатал
        # `MEMORY.md` сиротой самому себе.
        def files():
            return sorted(memd.glob("*.md"))

        h = hygiene(memd, files(), today=datetime.date(2026, 9, 6))

        checks = [
            ("бессрочная ловушка не объявлена истёкшей", "trap.md" not in dict(h["истёк"])),
            ("протухшая дата поймана", ("rotten.md", "до выката 01.01.2020") in h["истёк"]),
            ("файл без срока посчитан", h["без срока"] == ["bare.md", "orphan.md"]),
            ("проза посчитана отдельно", h["прозой"] == 1),
            ("битый указатель пойман", h["битые"] == ["gone.md"]),
            ("сирота поймана", h["сироты"] == ["orphan.md"]),
            ("вытесненная сиротой НЕ считается", "old.md" not in h["сироты"]),
            ("вытеснение замечено поимённо", h["вытеснены"] == ["old"]),
            ("длинная строка поймана", len(h["длинные"]) == 1),
        ]
        for label, good in checks:
            print(("✓ " if good else "✗ ") + label)
            ok &= good

        # укус: дописываем срок — счёт «без срока» обязан упасть на единицу
        before = len(h["без срока"])
        (memd / "bare.md").write_text(
            "---\nname: bare\nmetadata:\n  живёт до: пока жив X\n---\n\nтело\n")
        after = len(hygiene(memd, files(), today=datetime.date(2026, 9, 6))["без срока"])
        if after == before - 1:
            print("✓ укус: дописанный срок снял ровно одну находку")
        else:
            print(f"✗ укус не сработал: было {before}, стало {after}")
            ok = False

        # второй укус: снимаем `supersedes` — вытесненная обязана СТАТЬ сиротой.
        # Без него послабление неотличимо от «сирот не ловим вовсе».
        (memd / "new.md").write_text(
            "---\nname: new\nmetadata:\n  живёт до: до выката 01.01.2030\n---\n\nтело\n")
        sir = hygiene(memd, files(), today=datetime.date(2026, 9, 6))["сироты"]
        if sir == ["old.md", "orphan.md"]:
            print("✓ укус: снятый supersedes вернул вытесненную в сироты")
        else:
            print(f"✗ укус supersedes не сработал: сироты {sir}")
            ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


# ── укус сторожа ──────────────────────────────────────────────────────────────
def selftest():
    """Оба контроля обязательны.

    Положительный ловит чекер, который не находит ничего вообще; отрицательный —
    который кричит на всё. Мутация проверяет, что сторож краснеет ИМЕННО от
    поломки того, что охраняет: живой путь ломается переименованием, и находка
    обязана появиться.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="check-selftest-"))
    ok = True
    try:
        repo, memd = tmp / "repo", tmp / "memory"
        (repo / "src").mkdir(parents=True); memd.mkdir()
        (repo / "src" / "app.py").write_text(
            "class UserDao:\n    def get_balance(self):\n        price_amount = 0\n        return price_amount\n")
        (repo / "openspec" / "specs" / "billing").mkdir(parents=True)
        (repo / "openspec" / "specs" / "billing" / "spec.md").write_text(
            "# billing\n\nСистема SHALL звать `UserDao.get_balance`, см. `src/app.py`.\n"
            "Ещё она SHALL звать `PromotionService`.\n")
        (memd / "live.md").write_text(
            "---\nname: live\n---\n\nБаланс считает `get_balance` в `src/app.py`.\n"
            "Связано: [[stale]].\n")
        (memd / "stale.md").write_text(
            "---\nname: stale\n---\n\nСмотри `src/gone.py` и `RenamedService`.\n"
            "Связано: [[never-existed]].\n")

        def toks(f):
            return {t for k in f for t, _, _ in f[k]}

        got = toks(run(repo, mem_override=memd, quiet=True))

        # положительный контроль: живое не обвиняем
        clean = {"get_balance", "src/app.py", "UserDao.get_balance", "[[stale]]"}
        false_alarm = clean & got
        if false_alarm:
            print(f"✗ ложная тревога на живом: {sorted(false_alarm)}"); ok = False
        else:
            print("✓ положительный контроль: живые символ, путь и связь не обвинены")

        # отрицательный контроль: мёртвое ловим
        must = {"src/gone.py", "RenamedService", "PromotionService", "[[never-existed]]"}
        missed = must - got
        if missed:
            print(f"✗ пропущено мёртвое: {sorted(missed)}"); ok = False
        else:
            print("✓ отрицательный контроль: мёртвые путь, символ и связь пойманы")

        # мутация: ломаем охраняемое — сторож обязан покраснеть
        (repo / "src" / "app.py").rename(repo / "src" / "app2.py")
        bitten = toks(run(repo, mem_override=memd, quiet=True))
        if "src/app.py" in bitten and "get_balance" not in bitten:
            print("✓ укус: переименование файла даёт находку по пути, символ уцелел")
        else:
            print(f"✗ укус не сработал: путь={'src/app.py' in bitten}, "
                  f"символ ложно={'get_balance' in bitten}"); ok = False

        # docflow: доки capability читаются, замороженная копия openspec молчит
        caps = repo / "backlog" / "docs" / "capabilities"
        caps.mkdir(parents=True)
        (caps / "doc-1 - billing.md").write_text("# billing\n\nЗовёт `DocOnlyGhost`.\n")
        got2 = toks(run(repo, mem_override=memd, quiet=True))
        if "DocOnlyGhost" in got2 and "PromotionService" not in got2:
            print("✓ docflow: дока capability читается, копия openspec рядом молчит")
        else:
            print(f"✗ docflow-корпус: дока читается={'DocOnlyGhost' in got2}, "
                  f"копия openspec ложно жива={'PromotionService' in got2}"); ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    ok &= selftest_worktree()
    print()
    ok &= selftest_hygiene()
    print("\nselftest:", "ЗЕЛЁНЫЙ" if ok else "КРАСНЫЙ")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=".", help="корень репозитория (по умолчанию cwd)")
    ap.add_argument("--memory-dir", help="каталог памяти, если слаг ведёт не туда")
    ap.add_argument("--selftest", action="store_true", help="укус сторожа на фикстуре")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else (run(a.repo, a.memory_dir) and 0))
