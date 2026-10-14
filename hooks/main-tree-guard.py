#!/usr/bin/env python3
"""Сторож главного дерева: в основном чекауте параллельного репо не пишут.

Репозиторий объявляет это отслеживаемым файлом `.claude/readonly-root` (каталог
`.claude/worktrees/` есть у десятка репо — признаком он не годится). В таком репо
основной чекаут — только для чтения: правки, задачи Backlog, замки и коммиты делаются из ворктри, в ствол
— через `./scripts/land.sh`.

Почему сторож, а не строка в правилах (GM-433, 14.10.2026): уборка GM-432 нашла
в корне gmb_v2 девять задач, не закоммиченных никогда, 12 непушенных коммитов и
замки на ветке develop. Живые пробы GLM-5.3 в ztui и ZCode.app обе ставили
`backlog task create` и `bl-lock.sh take` ДО `git worktree add`: «ворктри до
первой правки файла» CLI-команду правкой не считает.

Хук PreToolUse в формате Claude Code (его же понимает zcode): JSON на stdin,
код 2 + stderr = вызов отклонён. Ни при какой своей ошибке не блокирует.
"""
import json, os, re, subprocess, sys

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "ApplyPatch"}

# Команды, которые пишут состояние репо или Backlog. Чтение (git status/log/diff,
# backlog task view/list/search, bl-lock.sh who) пропускается.
BASH_WRITES = [
    (r"\bbacklog\s+(task|doc|draft|decision|milestone)\s+"
     r"(create|edit|update|archive|demote|promote|complete)\b", "запись в Backlog"),
    (r"\bbacklog\s+task\s+\S+\s+--(check-ac|append-notes|final-summary)", "запись в Backlog"),
    (r"bl-lock\.sh\s+(take|drop)\b", "замок задачи"),
    (r"bl-done\.sh\b", "закрытие задачи"),
    (r"\bgit\s+(commit|merge|rebase|cherry-pick|revert|reset|pull|am|push|switch)\b",
     "git пишет ветку"),
    (r"\bgit\s+checkout\b", "git переключает дерево"),
    (r"\bgit\s+stash\b(?!\s+(list|show))", "git stash"),
    (r"land\.sh\b", "приземление"),
]


def git(*a, cwd):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=5)
    return r.returncode, r.stdout.strip()


def main_checkout(cwd):
    """Корень основного чекаута и признак «cwd — он сам, а не ворктри»."""
    rc, top = git("rev-parse", "--show-toplevel", cwd=cwd)
    if rc:
        return None, False
    _, common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top)
    if os.path.basename(common) != ".git":
        return None, False  # голый репо или нестандартная раскладка — не наше
    main = os.path.realpath(os.path.dirname(common))
    if not os.path.isfile(os.path.join(main, ".claude", "readonly-root")):
        return None, False  # репо не объявил корень только для чтения
    return main, os.path.realpath(top) == main


def inside(path, root):
    path = os.path.realpath(path)
    return path == root or path.startswith(root + os.sep)


def patch_paths(text):
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", text or "", re.M)


def deny(main, what):
    sys.stderr.write(
        f"⛔ {main} — основной чекаут, он только для чтения ({what}).\n"
        "Правки, задачи Backlog, замки и коммиты — из ворктри, в ствол — land.sh:\n"
        f"  git -C {main} fetch -q origin develop\n"
        f"  git -C {main} worktree add .claude/worktrees/<ветка> -b <ветка> origin/develop\n"
        "  затем все команды с cwd внутри ворктри (cd .claude/worktrees/<ветка> && …),\n"
        "  задачу заводи и бери замок уже там; в develop — ./scripts/land.sh.\n")
    sys.exit(2)


def run():
    data = json.load(sys.stdin)
    tool = data.get("tool_name") or data.get("toolName") or ""
    inp = data.get("tool_input") or data.get("toolInput") or {}
    cwd = data.get("cwd") or os.getcwd()
    main, at_root = main_checkout(cwd) if os.path.isdir(cwd) else (None, False)

    if tool in WRITE_TOOLS:
        paths = [inp.get(k) for k in ("file_path", "filePath", "notebook_path", "path")]
        paths += patch_paths(inp.get("patch") or inp.get("input") or "")
        for p in filter(None, paths):
            full = os.path.expanduser(p if os.path.isabs(p) else os.path.join(cwd, p))
            d = os.path.dirname(full)
            while d and not os.path.isdir(d):
                d = os.path.dirname(d)  # файл новый — корень ищем от ближайшего каталога
            main, _ = main_checkout(d) if d else (None, False)
            if not main:
                continue
            wt = os.path.join(main, ".claude", "worktrees")
            if not inside(full, main) or inside(full, wt):
                continue
            # игнорируемое git'ом (.env, локальные пробы) — не состояние репо
            if git("check-ignore", "-q", full, cwd=main)[0] == 0:
                continue
            deny(main, f"{tool} {os.path.relpath(os.path.realpath(full), main)}")
        return

    if tool == "Bash":
        cmd = inp.get("command") or ""
        if ".claude/worktrees/" in cmd:
            return  # команда сама уходит в ворктри (cd/-C) — граница соблюдена
        # cwd хука — где стоит сессия, а не куда уходит команда: `cd <корень> && …`
        # и `git -C <корень> …` из ворктри или из-вне репо — тоже корень
        dirs = re.findall(r"(?:^|[;&|(]\s*)cd\s+[\"']?([^\s;&|\"')]+)", cmd) + \
            re.findall(r"\bgit\s+-C\s+[\"']?([^\s;&|\"')]+)", cmd)
        # команда, начатая с `cd X`, исполняется в X, а не в cwd сессии
        root = main if at_root and not re.match(r"\s*cd\s", cmd) else None
        for d in dirs:
            d = os.path.expanduser(d)
            d = d if os.path.isabs(d) else os.path.join(cwd, d)
            if os.path.isdir(d):
                m, r = main_checkout(d)
                if r:
                    root = m
        if not root:
            return
        flat = re.sub(r"\bgit\s+-C\s+\S+", "git", cmd)
        for pat, what in BASH_WRITES:
            if re.search(pat, flat):
                if what == "git переключает дерево" and re.search(r"--detach\s+origin/", flat):
                    continue  # корень держат отцепленным на origin — это его норма
                deny(root, what)


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        pass  # сломанный сторож не имеет права остановить сессию
