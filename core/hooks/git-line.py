#!/usr/bin/env python3
"""Строка состояния репозитория на каждую реплику: ветка и счёт незакоммиченного.

Раньше это был inline-echo в config.json/settings.json: plain stdout Claude Code
кладёт в контекст, а ZCode молча выбрасывает — строка доходила только до Клода.
Перенесена в скрипт с emit() по общему контракту сред (канон паттерна —
hooks/context-meter.py): plain для Claude Code, JSON additionalContext для ZCode
по ZCODE_SESSION_ID. Текст строки не менялся: «git: <ветка> · N uncommitted
file(s)».

Ветка берётся своим вызовом git, а не разбором транскрипта (урок context-meter):
в истории на месте ветки лежит ТЕКСТ соседнего хука. Не репозиторий — молчим,
как и inline-предок с его `|| true`.
"""
import json, os, subprocess, sys


def emit(text):
    """Вывод по контракту среды: Claude Code читает plain stdout, ZCode —
    только JSON с additionalContext, plain она молча выбрасывает."""
    if os.environ.get("ZCODE_SESSION_ID"):
        print(json.dumps({"additionalContext": text}, ensure_ascii=False))
    else:
        print(text)


def git(args, cwd):
    try:
        p = subprocess.run(["git", *args], cwd=cwd or None,
                           capture_output=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout.decode("utf-8", "replace").strip() if not p.returncode else ""


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    cwd = payload.get("cwd")
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if not branch:
        return 0
    count = len(git(["status", "--porcelain"], cwd).splitlines())
    emit(f"git: {branch} · {count} uncommitted file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
