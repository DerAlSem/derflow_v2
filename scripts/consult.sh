#!/bin/bash
# Разовый вызов модели Anthropic из GLM-сессии — пилот перевёрнутой схемы,
# 04.10.2026 (см. glm.sh).
#
# Opus не держит сессию: получает пакет (вопрос, варианты, выдержки, пути) и
# отдаёт вердикт. Читать репо может, писать — нет. Sonnet — тем же путём, для
# механической проверки работы GLM.
#
# Использование:  consult.sh <opus|sonnet> <файл-пакета> [каталог-репо] [ходов]
# Вывод: ответ модели, затем строка расхода. Каждый вызов дописывается в
# ~/.claude/tmp/consult.jsonl — это и есть замер пилота: сколько лимита
# съедает одна консультация.
set -euo pipefail

model="${1:?модель: opus|sonnet}"
brief="${2:?файл-пакет с вопросом}"
dir="${3:-$PWD}"
turns="${4:-15}"

case "$model" in opus|sonnet) ;; *) echo "❌ модель: opus|sonnet" >&2; exit 2;; esac
[ -f "$brief" ] || { echo "❌ нет файла $brief" >&2; exit 2; }

# Вычистить GLM-окружение: без этого вызов уйдёт в z.ai и «Opus» ответит GLM.
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_MODEL
unset ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL
unset ANTHROPIC_DEFAULT_HAIKU_MODEL DERFLOW_HOST
# Вызов из живой сессии помечается дочерним и глушит транскрипт — см. hand.sh.
unset CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDE_CODE_ENTRYPOINT

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

cd "$dir"
claude -p --model "$model" --max-turns "$turns" --output-format json \
  --allowedTools "Read Grep Glob Bash(git log:*) Bash(git show:*) Bash(git diff:*)" \
  --disallowedTools "Edit Write NotebookEdit Agent" \
  < "$brief" > "$out" 2>/dev/null || true

python3 - "$out" "$model" "$dir" "$brief" <<'PY'
import json, os, sys, datetime
out, model, d, brief = sys.argv[1:5]
raw = open(out, errors="replace").read()
try:
    r = json.loads(raw[raw.index("{"):])
except ValueError:
    print("❌ consult: ответ не разобран\n" + raw[-1500:])
    sys.exit(1)
print(r.get("result") or "❌ пустой ответ")
u = r.get("usage") or {}
mods = list((r.get("modelUsage") or {}).keys())
line = {
    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    "model": model, "served": mods, "repo": d, "brief": os.path.basename(brief),
    "turns": r.get("num_turns"), "usd_api": round(r.get("total_cost_usd") or 0, 4),
    "in": u.get("input_tokens", 0), "cache_read": u.get("cache_read_input_tokens", 0),
    "cache_write": u.get("cache_creation_input_tokens", 0),
    "out": u.get("output_tokens", 0), "error": r.get("is_error"),
}
log = os.path.expanduser("~/.claude/tmp/consult.jsonl")
os.makedirs(os.path.dirname(log), exist_ok=True)
open(log, "a").write(json.dumps(line, ensure_ascii=False) + "\n")
print(f"\n— consult {model} ({','.join(mods)}): {line['turns']} ходов, "
      f"${line['usd_api']} по ценам API, вход {line['in']}+кэш {line['cache_read']}, "
      f"выход {line['out']}")
PY
