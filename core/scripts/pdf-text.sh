#!/bin/bash
# Текст из pdf локально — без API и без poppler: PDFKit (Quartz) через JXA,
# родной для macOS. Сестра see.sh: see.sh — картинки через flash, это —
# текстовый слой pdf на месте. 07.10.2026, вижн-полоса опенкода.
#
# Скан без текстового слоя вернёт пусто — тогда пересказывать владельцу
# (вижн-путь flash для pdf не заведён).
# Использование:  pdf-text.sh <файл.pdf> [лимит-байт]
set -euo pipefail
pdf="${1:?путь к pdf}"
limit="${2:-12000}"
[ -f "$pdf" ] || { echo "❌ нет файла $pdf" >&2; exit 2; }

out=$(PDFPATH="$pdf" osascript -l JavaScript -e '
  ObjC.import("Quartz"); ObjC.import("Foundation")
  const p = $.NSProcessInfo.processInfo.environment.objectForKey("PDFPATH").js
  const d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(p))
  d.string.js' 2>/dev/null) || { echo "❌ PDFKit не прочитал (повреждённый?)" >&2; exit 1; }

[ -n "$(printf '%s' "$out" | tr -d '[:space:]')" ] || { echo "❌ текстовый слой пуст — похоже, скан: перескажет владелец" >&2; exit 1; }
printf '%s' "$out" | head -c "$limit"
echo
