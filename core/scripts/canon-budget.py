#!/usr/bin/env python3
"""Сторож канона derflow: бюджеты движков, индекс памяти, разрешимость ссылок.

Молчит, когда всё в порядке. Каждое нарушение — одна строка 🔴. Зовётся хуком
SessionStart (рядом с дельтой реестра) и человеком напрямую — вторая роль и
есть «дубль doctor» из спеки: waiting.py по охвату не трогаем.
Спека: specs/2026-09-13-derflow-rebuild-design.md §4.
"""
import os, re, sys

D = os.path.expanduser("~/.claude/skills/derflow")
MEM = os.path.expanduser(
    "~/.claude/projects/-Users-deralsem--claude/memory/MEMORY.md")
BUDGET = {"_lane-c.md": 120, "_gates.md": 100, "_capture.md": 120,
          "_ship.md": 80, "_parallel.md": 80}
MEM_BUDGET = 16 * 1024
LINK = re.compile(r'archive/([\w\-.]+\.md)')

bad = []
for f, lim in BUDGET.items():
    p = os.path.join(D, f)
    if not os.path.exists(p):
        bad.append(f"канон: нет файла {f}"); continue
    n = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
    if n > lim:
        bad.append(f"канон: {f} — {n} строк при бюджете {lim}; "
                   f"рост оплачивается сжатием или уходит в архив")
    for m in LINK.finditer(open(p, encoding="utf-8", errors="replace").read()):
        if not os.path.exists(os.path.join(D, "archive", m.group(1))):
            bad.append(f"канон: {f} ссылается на archive/{m.group(1)} — файла нет")
if os.path.exists(MEM) and os.path.getsize(MEM) > MEM_BUDGET:
    bad.append(f"память: индекс {os.path.getsize(MEM)} байт при бюджете "
               f"{MEM_BUDGET} (потолок харнесса ~24 КБ обрежет МОЛЧА) — "
               f"сжимай или вытесняй")
for line in bad:
    print("🔴 " + line)
sys.exit(1 if bad else 0)
