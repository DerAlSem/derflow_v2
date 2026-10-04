#!/usr/bin/env python3
"""Слепота GLM-сессии — упор хуком, а не просьбой. Пилот glm.sh, 04.10.2026.

glm-5.3 картинок не видит. Боевое 04.10.2026, rk_bot: скриншот вывода psql →
«let me assume I can see it» → выдуманная таблица и «✅ фискального долга нет».
Модель, которая уже решила додумать, просьбу «не додумывай» тоже додумает.

Два события, оба — только при DERFLOW_HOST=glm (метка glm.sh); в обычной
сессии хук молчит и выходит сразу:
  UserPromptSubmit — в сообщении есть картинка → в контекст: «не видишь, вот
                     пути, зови see.sh, без его вывода картинку не описывай»;
  PreToolUse Read  — чтение картинки отклоняется с той же подсказкой
                     (скриншоты shot.mjs, файлы из репо).
"""
import glob, json, os, sys

if os.environ.get("DERFLOW_HOST") != "glm":
    sys.exit(0)

IMG = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
SEE = "~/.claude/scripts/see.sh"

try:
    ev = json.load(sys.stdin)
except ValueError:
    sys.exit(0)

name = ev.get("hook_event_name")

if name == "UserPromptSubmit":
    if "[Image" not in (ev.get("prompt") or ""):
        sys.exit(0)
    # Вставленные картинки Claude Code кладёт в <tmp>/claude-<uid>/<проект>/<сессия>/images/.
    sid = ev.get("session_id") or "?"
    # /tmp на macOS — симлинк на /private/tmp: без realpath каждая картинка дважды.
    paths = sorted(
        {os.path.realpath(p) for p in glob.glob(f"/private/tmp/claude-*/*/{sid}/images/*")
         + glob.glob(f"/tmp/claude-*/*/{sid}/images/*")},
        key=os.path.getmtime)
    where = "\n".join(f"  {SEE} {p}" for p in paths[-5:]) or \
        "  (путь не найден — попроси владельца прислать текстом)"
    print("🔴 В сообщении картинка, а ты (glm-5.3) изображений НЕ видишь. "
          "Не описывай и не интерпретируй её по догадке. Прочитай через:\n"
          f"{where}\n"
          "Нет вывода see.sh — скажи «картинку не вижу» и попроси текст.")
    sys.exit(0)

if name == "PreToolUse" and ev.get("tool_name") == "Read":
    p = (ev.get("tool_input") or {}).get("file_path") or ""
    if p.lower().endswith(IMG):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason":
                f"glm-5.3 изображений не видит — Read отдаст картинку вслепую. "
                f"Прочитай её текстом: {SEE} {p} [вопрос]",
        }}, ensure_ascii=False))
    sys.exit(0)
