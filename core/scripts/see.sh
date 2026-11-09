#!/bin/bash
# Глаза для GLM-сессии: картинка → текст через glm-5.3-flash (z.ai). Пилот
# glm.sh, 04.10.2026.
#
# Зачем: glm-5.3 только текстовая модель, картинку не видит. Боевое 04.10.2026,
# rk_bot: скриншот вывода psql, в рассуждении «I can't see the image… let me
# assume I can see it» — и выдуманная таблица с вердиктом «✅ фискального долга
# нет». Поэтому слепота закрывается инструментом и хуком (hooks/glm-blind.py),
# а не просьбой «не выдумывай».
#
# flash сверен на скриншоте с известным текстом: дословно, без додумываний.
# Лимиты Claude не тратит — та же подписка z.ai.
#
# Использование:  see.sh <картинка> [вопрос]
# Без вопроса — дословная транскрипция текста плюс описание того, что не текст.
set -euo pipefail

img="${1:?путь к картинке}"
ask="${2:-Перепиши дословно весь текст на изображении, сохраняя строки и столбцы таблиц. Затем коротко опиши то, что не текст (схемы, графики, цвета-статусы). Ничего не додумывай: нечитаемое помечай [?].}"
[ -f "$img" ] || { echo "❌ нет файла $img" >&2; exit 2; }

python3 - "$img" "$ask" <<'PY'
import base64, json, mimetypes, os, sys, urllib.request
img, ask = sys.argv[1:3]
key = os.environ.get("ZAI_API_KEY") or json.load(open(os.path.expanduser(
    "~/.config/opencode/opencode.json")))["provider"]["zai-glm"]["options"]["apiKey"]
mime = mimetypes.guess_type(img)[0] or "image/png"
data = base64.b64encode(open(img, "rb").read()).decode()
body = {"model": "glm-5.3-flash", "messages": [{"role": "user", "content": [
    {"type": "text", "text": ask},
    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]}]}
req = urllib.request.Request(
    "https://api.z.ai/api/coding/paas/v4/chat/completions",
    json.dumps(body).encode(),
    {"Content-Type": "application/json", "Authorization": "Bearer " + key})
try:
    r = json.load(urllib.request.urlopen(req, timeout=180))
except Exception as e:
    print(f"❌ see.sh: z.ai не ответил ({e}). Картинку НЕ видел — попроси текстом.")
    sys.exit(1)
print(f"[see.sh · glm-5.3-flash · {os.path.basename(img)}]")
print(r["choices"][0]["message"]["content"])
PY
