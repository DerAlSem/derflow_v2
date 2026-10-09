#!/usr/bin/env python3
"""Квитанция консультации перед прод-промоушеном — упор хуком, а не просьбой.
Пилот glm.sh, plans/glm-pilot.md, триггер 4 («F/Ops: план до первого действия
на проде»). Ревью Opus 08.10.2026 (consult-receipt-brief.md) учтено целиком.

Только при DERFLOW_HOST=glm (метка glm.sh): в обычной сессии хук молчит.
Причина: классификатор авто-режима в GLM-сессии тоже GLM, и страховки у прода
там нет, кроме гейта из CLAUDE.md проекта, который GLM «выполняет по памяти».

PreToolUse Bash: команда трогает прод — ИСПОЛНЕНИЕ `deploy.sh` (первое слово
команды, позиция после `;`/`&`/`|`/перевода строки или аргумент интерпретатора
bash/sh/sudo/env; `bash -n` — разбор синтаксиса, не запуск; кроме `--env=demo`,
`--dry-run`, `-h`; у части репо флага нет вообще и без него выкатывается прод),
push в main/master, push тега `prod-*`, `--tags`/`--all`/
`--mirror`, голый push из ветки main — пропускается только при квитанции:
в ~/.claude/tmp/consult.jsonl есть запись, у которой
  • model == opus и среди served есть модель с «opus» в имени,
  • repo — тот же репозиторий, что у команды (для deploy: cwd/`cd`, а при
    абсолютном пути скрипта — каталог скрипта: выкат чужого репо из-под
    ~/.claude тоже гейтится),
  • head равен SHA, который уезжает: для push — HEAD, для deploy — origin/main
    (deploy.sh выкатывает origin/main, а не локальное дерево),
  • verdict == go (последняя строка ответа Opus — «ВЕРДИКТ: ПУСКАТЬ»),
  • не старше MAX_AGE.
Нет квитанции — deny с готовой командой консультации. Сам хук Opus не зовёт.

PreToolUse Write|Edit и Bash: любая попытка записать в consult.jsonl мимо
consult.sh — deny: иначе «починить» отказ проще всего дописанной строкой.

Не закрывает: (1) обёртки (`bash -c`, make), где прод-команда не видна в строке;
(2) смысловой пробел — квитанция привязана к SHA, а не к содержанию пакета:
консультация по пустяковому пакету на том же HEAD тоже даст «ПУСКАТЬ». Это
упор против забывчивости, а не против умысла; (3) subshell «( deploy.sh» с
пробелом и запуск под бктиком — от прозаического упоминания неотличимы.
Упоминание deploy.sh в аргументах чтения (grep/sed/cat) и в прозе
коммит-сообщения исполнением НЕ считается — ровно это и сужено 09.10.2026
после ложных отказов на чтении файла и коммит-сообщении.
~/.claude (канон «пушить сразу») пропускается.
"""
import datetime, json, os, re, shlex, subprocess, sys

if os.environ.get("DERFLOW_HOST") != "glm":
    sys.exit(0)

MAX_AGE = datetime.timedelta(hours=4)
LOG = os.path.expanduser("~/.claude/tmp/consult.jsonl")
CANON = os.path.realpath(os.path.expanduser("~/.claude"))

try:
    ev = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
if ev.get("hook_event_name") != "PreToolUse":
    sys.exit(0)

tool = ev.get("tool_name")
ti = ev.get("tool_input") or {}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


# --- квитанцию не подделывать ------------------------------------------------
GUARD = ("Квитанции консультации пишет только scripts/consult.sh после живого вызова "
         "Opus. Дописывать, править или подменять ~/.claude/tmp/consult.jsonl нельзя: "
         "вызови consult.sh, а при отказе скажи владельцу.")
if tool in ("Write", "Edit", "NotebookEdit"):
    if "consult.jsonl" in (ti.get("file_path") or ""):
        deny(GUARD)
    sys.exit(0)
if tool != "Bash":
    sys.exit(0)

cmd = ti.get("command") or ""
if "consult.jsonl" in cmd and "consult.sh" not in cmd:
    # чтение журнала (cat/tail/grep/jq) — можно; запись/подмена — нет
    if re.search(r">>?\s*\S*consult\.jsonl|tee\b[^|;&]*consult\.jsonl|"
                 r"\b(?:sed\s+-i|mv|cp|rm|truncate|dd)\b[^;&|]*consult\.jsonl|"
                 r"open\([^)]*consult\.jsonl[^)]*[\"']\s*[wa]", cmd):
        deny(GUARD)

# --- что считается прод-промоушеном ------------------------------------------
GIT = r"git(?:\s+(?:-[cC]\s+\S+|--[\w-]+(?:=\S+)?))*"
PUSH = re.compile(r"(?:^|[;&|(\n])\s*(" + GIT + r")\s+push\b([^;&|\n]*)")
DEPLOY_TOKEN = re.compile(r"(?<![\w./~-])(?:[~\w.$\"'/-]+/)?deploy\.sh\b")
INTERPRETER = re.compile(r"(?:sudo|nohup|env|command|exec|(?:ba|z|da|k)?sh)\b")
MAIN_REF = re.compile(r"(?:^|[\s:+])(?:refs/heads/)?(?:main|master)\b")
PROD_TAG = re.compile(r"(?:^|[\s:+])(?:refs/tags/)?prod-[\w.\-]+")
BULK = re.compile(r"(?:^|\s)--(?:tags|follow-tags|all|mirror)\b")
DEMO_ARGS = re.compile(r"--env[= ]\s*demo\b|-e\s+demo\b|--dry-run|(?:^|\s)(?:-h|--help)\b")


def git_c(prefix):
    m = re.search(r"-C\s+(\S+)", prefix)
    return m.group(1) if m else None


def resolve(p):
    base = ev.get("cwd") or os.getcwd()
    p = os.path.expanduser(p.strip("\"'"))
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))


def repo_dir(c_opt=None):
    if c_opt:
        return resolve(c_opt)
    # `cd <путь>` в начале команды важнее cwd события: выкат из ворктри.
    m = re.match(r"\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)", cmd)
    if m:
        p = resolve(shlex.split(m.group(1))[0])
        if os.path.isdir(p):
            return p
    return os.path.realpath(ev.get("cwd") or os.getcwd())


def git(d, *a):
    try:
        return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True,
                              timeout=4).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def deploy_exec():
    """[(токен deploy.sh, хвост до разделителя)] для каждого ИСПОЛНЕНИЯ скрипта.

    Исполнение: deploy.sh — первое слово команды, позиция после разделителя
    (`;`/`&`/`|`/перевод строки/«$(») или аргумент интерпретатора
    (bash/sh/sudo/env/…; флаг `-n` — разбор синтаксиса, не запуск).
    Упоминание — аргумент grep/sed/git add, проза коммит-сообщения —
    исполнением не считается."""
    hits = []
    for m in DEPLOY_TOKEN.finditer(cmd):
        line = cmd[:m.start()].rstrip(" \t").split("\n")[-1].rstrip(" \t")
        if not line or line[-1] in ';&|`' or line.endswith("$("):
            hits.append((m.group(0), re.split(r"[;&|\n]", cmd[m.end():])[0]))
            continue
        toks = line.split()
        j = len(toks)
        while j > 0 and re.fullmatch(r"-[A-Za-z]+", toks[j - 1]):
            j -= 1
        if j > 0 and INTERPRETER.fullmatch(toks[j - 1]) and "-n" not in toks[j:]:
            hits.append((m.group(0), re.split(r"[;&|\n]", cmd[m.end():])[0]))
    return hits


def touches_prod():
    """(что, каталог, режим) или None. Режим: 'push' — сверять HEAD, 'deploy' — origin/main."""
    for tok_, tail in deploy_exec():
        if not DEMO_ARGS.search(tail):
            d = repo_dir()
            if tok_.startswith("/") or tok_.startswith("~"):
                p = resolve(tok_)
                if os.path.isfile(p):
                    d = os.path.dirname(p)  # абсолютный путь: репо скрипта, не cwd
            return "deploy.sh (прод)", d, "deploy"
    for m in PUSH.finditer(cmd):
        prefix, args = m.group(1), m.group(2)
        if re.search(r"(?:^|\s)(?:-n|--dry-run)\b", args):
            continue
        d = repo_dir(git_c(prefix))
        if MAIN_REF.search(args) or PROD_TAG.search(args) or BULK.search(args):
            return "git push в main/тег prod-*", d, "push"
        pos = [a for a in args.split() if not a.startswith("-")]
        if len(pos) <= 1 or pos[1:] == ["HEAD"]:
            if git(d, "rev-parse", "--abbrev-ref", "HEAD") in ("main", "master"):
                return "git push из main", d, "push"
    return None


hit = touches_prod()
if not hit:
    sys.exit(0)
what, d, mode = hit
top = os.path.realpath(git(d, "rev-parse", "--show-toplevel") or d)
if top == CANON:
    sys.exit(0)

head = git(d, "rev-parse", "origin/main" if mode == "deploy" else "HEAD") or \
    git(d, "rev-parse", "HEAD")


def valid_receipt():
    if not head or not os.path.exists(LOG):
        return False
    now = datetime.datetime.now()
    for line in reversed(open(LOG, errors="replace").read().splitlines()[-200:]):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("model") != "opus" or r.get("error") or r.get("verdict") != "go":
            continue
        if not any("opus" in str(s) for s in (r.get("served") or [])):
            continue
        if r.get("head") != head:
            continue
        if os.path.realpath(r.get("repo") or "") != top:
            continue
        try:
            age = now - datetime.datetime.fromisoformat(r["ts"])
        except (KeyError, ValueError):
            continue
        if age <= MAX_AGE:
            return True
    return False


if valid_receipt():
    sys.exit(0)

deny(f"Прод-промоушен ({what}) в GLM-сессии идёт только с квитанцией Opus на "
     f"SHA {head[:9] or '?'}: план и диф перед выкатом смотрит Opus, а не GLM. "
     "Квитанции нет или она устарела (другой SHA, старше 4 ч, вердикт не «ПУСКАТЬ»). "
     "Сделай: собери пакет (SHA, результаты гейта, что едет, риски, миграции; в конце "
     "попроси последней строкой «ВЕРДИКТ: ПУСКАТЬ» или «ВЕРДИКТ: СТОП») и вызови "
     f"`~/.claude/scripts/consult.sh opus <пакет.md> {top}`. "
     "Вердикт СТОП — остановись и скажи владельцу, не обходи.")
