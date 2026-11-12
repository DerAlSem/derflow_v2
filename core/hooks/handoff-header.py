#!/usr/bin/env python3
"""Хендофф без шапки — предупреждение в МОМЕНТ ЗАПИСИ, а не в момент передачи.

hand.sh опознаёт хендофф по строкам шапки: «ветка:» — ключ подбора, «имя:» —
заголовок таба. Без них передача явным файлом проходит с двумя предупреждениями
(таб «?·слаг», принадлежность ветке не проверена), автоподбор — отказ код 1.
Замер 12.11.2026: 45 из ~60 хендоффов по всем репо написаны без шапки —
правило в derflow/_capture.md есть, а исполняет его меньшинство сессий, и
текст канона здесь не помогает. Момент записи — единственный, когда пишущая
сессия ещё может дописать шапку сама; hand.sh видит файл уже поздно.

PostToolUse на Write|Edit|*: файл по пути `…/.claude/handoff/*.md`, в первых
строках нет «^ветка:» или «^имя:» → подсказка той же сессии. Не блокирует
запись и не правит файл: шапка осмысленна только из рук знающего задачу.
Проверка ПОСЛЕ записи, поэтому Edit, дописывающий шапку, не ложится срабатыванием.

Вывод по контракту среды (канон паттерна — hooks/git-line.py): ZCode —
JSON {"additionalContext": …} (plain stdout движок молча выбрасывает);
Claude Code — {"decision": "block", "reason": …}, у PostToolUse это фидбек
модели на уже исполненный вызов; kimi и прочие — plain stdout (едет в
контекст). Ни при какой своей ошибке не мешает сессии.
"""
import json, os, re, subprocess, sys

HEAD_LINES = 12          # шапка обязана стоять над заголовком — глубже не ищем
HANDOFF_RE = re.compile(r"(^|/)\.claude/handoff/[^/]+\.md$")
NEED = {"ветка": re.compile(r"(?m)^ветка:[ \t]*\S"),
        "имя": re.compile(r"(?m)^имя:[ \t]*\S")}


def env_branch(d):
    try:
        p = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           cwd=d, capture_output=True, timeout=2)
        return p.stdout.decode("utf-8", "replace").strip() if not p.returncode else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def patch_paths(text):
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", text or "", re.M)


def run():
    data = json.load(sys.stdin)
    inp = data.get("tool_input") or data.get("toolInput") or {}
    cwd = data.get("cwd") or os.getcwd()
    paths = [inp.get(k) for k in ("file_path", "filePath", "notebook_path", "path")]
    paths += patch_paths(inp.get("patch") or inp.get("input") or "")
    for p in filter(None, paths):
        full = os.path.expanduser(p if os.path.isabs(p) else os.path.join(cwd, p))
        if not HANDOFF_RE.search(full) or not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                head = "".join(f.readline() for _ in range(HEAD_LINES))
        except OSError:
            continue
        miss = [k for k, rx in NEED.items() if not rx.search(head)]
        if not miss:
            return
        rel = full.split("/.claude/handoff/")[-1]
        br = env_branch(os.path.dirname(full)) or "<ветка>"
        text = (f"⚠️ Хендофф {rel} записан без шапки — hand.sh не подберёт его по ветке, "
                f"таб будет «?·{rel[:-3]}», принадлежность ветке не проверится "
                f"(нет: {', '.join(miss)}).\n"
                f"Допиши двумя строками НАД заголовком:\n"
                f"  ветка: {br}\n"
                f"  имя: <буква проекта>·<слаг задачи>\n"
                "Карта букв и форма имени — derflow/_capture.md, глава «Расщепление сессии».")
        if os.environ.get("ZCODE_SESSION_ID"):
            print(json.dumps({"additionalContext": text}, ensure_ascii=False))
        elif os.environ.get("CLAUDE_PROJECT_DIR"):
            print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
        else:
            print(text)
        return


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        pass  # сломанный сторож не имеет права остановить сессию
