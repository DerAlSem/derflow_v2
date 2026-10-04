#!/bin/bash
# Сессия Claude Code на GLM (z.ai) — пилот перевёрнутой схемы, 04.10.2026.
#
# Схема: длинная сессия едет на GLM, Opus зовётся разово через consult.sh на
# решение, а не держит контекст. Замер 25.09–04.10: 78% расхода — сама сессия
# оркестратора, сабагенты — 22%. Поэтому дешевеет сессия, а не исполнители.
#
# Хост — Claude Code, а не opencode/Z Code: хуки, Agent, Skill, hand.sh и реестр
# живут здесь родными, портировать нечего (решение владельца 04.10.2026).
#
# Ловушки, увиденные на первом прогоне:
#   • `glm-5.3` Claude Code не знает — окно контекста он подставляет 200k по
#     умолчанию; счётчик ctx и порог расщепления верны, только если у GLM так же.
#   • Классификатор авто-режима тоже идёт в z.ai: решает, что пускать без
#     вопроса, GLM. Для ВДС и прода это не страховка.
#   • Коннекторы claude.ai при внешнем токене выключены (Claude Docs и пр.).
#
# Использование:  glm.sh [аргументы claude]   — интерактивная сессия
#                 glm.sh -p "…"               — headless (стенд RED/GREEN)
set -euo pipefail

# Ключ — из окружения, иначе из конфига opencode, где он уже лежит. В репо
# ключа нет и быть не должно (белый список .gitignore пропустил бы scripts/).
key="${ZAI_API_KEY:-}"
if [ -z "$key" ]; then
  key="$(python3 - <<'PY' 2>/dev/null || true
import json, os
p = os.path.expanduser("~/.config/opencode/opencode.json")
print(json.load(open(p))["provider"]["zai-glm"]["options"]["apiKey"])
PY
)"
fi
if [ -z "$key" ]; then
  echo "❌ нет ключа z.ai: ни ZAI_API_KEY, ни ~/.config/opencode/opencode.json" >&2
  exit 1
fi

export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
export ANTHROPIC_AUTH_TOKEN="$key"
unset ANTHROPIC_API_KEY
# Алиасы моделей агентов (`model: sonnet` у исполнителей) тоже уходят в GLM:
# внутри этой сессии других моделей нет, Anthropic — только через consult.sh.
export ANTHROPIC_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_OPUS_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_SONNET_MODEL="glm-5.3"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="glm-5.3-flash"
# Метка хоста: по ней hand.sh открывает расщеплённую сессию тоже на GLM, а
# consult.sh знает, что окружение надо вычистить.
export DERFLOW_HOST="glm"

exec claude "$@"
