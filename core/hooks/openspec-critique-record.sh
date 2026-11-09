#!/usr/bin/env bash
# Отметить, что критик-слой прошёл по ТЕКУЩЕЙ редакции спеки заявки openspec.
#
# Пишет openspec/changes/<id>/.critique с хешем содержимого specs/. Любая
# последующая правка спеки делает отметку недействительной — это и есть гейт.
#
# Использование:
#   openspec-critique-record.sh <change-id> [заметка]
#   openspec-critique-record.sh <change-id> --waived "<причина отказа>"
#
# Второй режим отмечает НЕ прохождение круга, а его СНЯТИЕ решением владельца.
# Заведён потому, что гейт умел различать только «прошло» и «не отмечено», и
# заявка, по которой круг снят сознательно, не имела законного способа доехать
# до архивации — оставался лишь способ записать неправду.
#
# Причина обязательна и непустая. Это тот же урок, что и с `--yes` на
# архивации: барьер, снимаемый без названного основания, снимается рефлекторно.
set -euo pipefail

id=${1:?Укажи id заявки. Пример: openspec-critique-record.sh widget-venue-self-serve}
mode=pass
note=${2:-}
if [ "${2:-}" = "--waived" ]; then
  mode=waived
  note=${3:-}
  [ -n "$note" ] || { echo "Отказ от круга требует названной причины: openspec-critique-record.sh $id --waived \"<причина>\"" >&2; exit 1; }
fi

changes_dir=""
d=$PWD
while [ "$d" != "/" ]; do
  if [ -d "$d/openspec/changes" ]; then changes_dir="$d/openspec/changes"; break; fi
  d=$(dirname "$d")
done
[ -n "$changes_dir" ] || { echo "openspec/changes не найден вверх от $PWD" >&2; exit 1; }

specs="$changes_dir/$id/specs"
[ -d "$specs" ] || { echo "У заявки «${id}» нет specs/ — критиковать нечего" >&2; exit 1; }

# Хеш = СОДЕРЖИМОЕ спеки плюс ОТНОСИТЕЛЬНЫЕ пути внутри specs/. Абсолютный путь
# в расчёт не входит: заявка переезжает между ворктри, и с ним отметка
# переставала сходиться при неизменном тексте. Расчёт обязан совпадать с
# openspec-critique-gate.sh — это одна формула в двух файлах.
cur=$(cd "$specs" && find . -type f -name '*.md' | LC_ALL=C sort | while IFS= read -r f; do
  printf '%s ' "$f"
  shasum -a 256 "$f" | cut -d' ' -f1
done | shasum -a 256 | cut -d' ' -f1)

{
  echo "$cur"
  if [ "$mode" = waived ]; then
    echo "# критик-слой СНЯТ решением владельца по этой редакции спеки."
    echo "# Круг НЕ прогонялся. Это отказ, а не прохождение."
    echo "# причина: $note"
  else
    echo "# критик-слой отмечен пройденным по этой редакции спеки"
    [ -n "$note" ] && echo "# что: $note"
  fi
  echo "# когда: $(date '+%F %T %z')"
  echo "# Хеш выше — содержимое specs/. Правка спеки после этой отметки снова"
  echo "# закрывает гейт: изменённый текст ни критики не проходил, ни отказа."
} > "$changes_dir/$id/.critique"

if [ "$mode" = waived ]; then
  echo "Круг СНЯТ по заявке $id ($cur). Причина: $note"
else
  echo "Отмечено: $id ($cur)"
fi
