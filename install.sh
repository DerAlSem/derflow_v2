#!/usr/bin/env bash
# Раскладка derflow по средам: Claude Code, ZCode/ztui, opencode,
# Kimi Code CLI (kimi-code), Kimi Work desktop (kimi-work).
#
#   ./install.sh                 # собрать hosts/*/generated и разложить симлинки
#   ./install.sh --check         # ничего не менять: дрейф сборки и живых путей, код 1 при дрейфе
#   ./install.sh --claude-dir D  # раскладывать claude-часть в D (стенд RED: CLAUDE_CONFIG_DIR)
#   ./install.sh --only claude   # одна среда: claude | zcode | opencode | kimi-code | kimi-work
#
# Правило: живой путь среды — симлинк в ЭТОТ чекаут. Реальный файл/каталог на
# месте симлинка не затирается, а уезжает в ~/backups/derflow-install-<время>/.
# settings.json Claude Code НЕ линкуется: Claude Code сам пишет в него
# (разрешения, /config), и запись по симлинку не гарантирована. Эталон —
# hosts/claude/settings.json; --check показывает расхождение, правишь руками.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
ZCODE_DIR="$HOME/.zcode"
OPENCODE_DIR="$HOME/.config/opencode"
CHECK=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --claude-dir) CLAUDE_DIR="$2"; shift ;;
    --only) ONLY="$2"; shift ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "❌ неизвестный аргумент: $1" >&2; exit 2 ;;
  esac
  shift
done
want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

BACKUP="$HOME/backups/derflow-install-$(date +%Y%m%d-%H%M%S)"
drift=0

# link <цель в репо> <живой путь>
link() {
  local target="$1" live="$2"
  [ -e "$target" ] || { echo "❌ нет цели $target" >&2; exit 3; }
  if [ -L "$live" ] && [ "$(readlink "$live")" = "$target" ]; then
    return 0
  fi
  if [ "$CHECK" = 1 ]; then
    if [ -L "$live" ]; then echo "⚠️  $live → $(readlink "$live") (ждём $target)"
    elif [ -e "$live" ]; then echo "⚠️  $live — реальный файл, не симлинк"
    else echo "⚠️  $live — нет"; fi
    drift=1; return 0
  fi
  mkdir -p "$(dirname "$live")"
  if [ -e "$live" ] || [ -L "$live" ]; then
    if [ -L "$live" ]; then
      rm "$live"
    else
      local rel="${live#$HOME/}"
      mkdir -p "$BACKUP/$(dirname "$rel")"
      mv "$live" "$BACKUP/$rel"
      echo "📦 $live → $BACKUP/$rel"
    fi
  fi
  ln -s "$target" "$live"
  echo "🔗 $live → $target"
}

# 1. Сборка. В --check — во временный каталог и сравнение с generated/.
if [ "$CHECK" = 1 ]; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  python3 "$REPO/tools/build.py" --out "$tmp"
  for h in claude zcode; do
    if ! diff -rq "$tmp/$h" "$REPO/hosts/$h/generated" >/dev/null; then
      echo "⚠️  hosts/$h/generated отстал от core/ + hosts/$h/ — прогони ./install.sh"
      diff -r "$tmp/$h" "$REPO/hosts/$h/generated" | head -20
      drift=1
    fi
  done
else
  python3 "$REPO/tools/build.py"
fi

# 2. Claude Code
if want claude; then
  for d in "$REPO"/core/skills/* "$REPO"/skills/*; do
    link "$d" "$CLAUDE_DIR/skills/$(basename "$d")"
  done
  for d in scripts hooks schemas agents; do
    link "$REPO/core/$d" "$CLAUDE_DIR/$d"
  done
  link "$REPO/waiting" "$CLAUDE_DIR/waiting"
  link "$REPO/hosts/claude/generated/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
  if [ -f "$CLAUDE_DIR/settings.json" ] && \
     ! diff -q "$CLAUDE_DIR/settings.json" "$REPO/hosts/claude/settings.json" >/dev/null; then
    echo "⚠️  settings.json расходится с hosts/claude/settings.json (не линкуется — сверь руками):"
    diff "$REPO/hosts/claude/settings.json" "$CLAUDE_DIR/settings.json" | head -20
    [ "$CHECK" = 1 ] && drift=1
  fi
fi

# 3. ZCode / ztui
if want zcode && [ -d "$ZCODE_DIR" ]; then
  for d in "$REPO"/core/skills/* "$REPO"/skills/*; do
    # рыхлый файл-симлинк в skills/ валит сканер ZCode целиком (ENOTDIR, DF-2)
    [ -d "$d" ] || continue
    link "$d" "$ZCODE_DIR/skills/$(basename "$d")"
  done
  for f in "$REPO"/hosts/zcode/generated/agents/*.md; do
    link "$f" "$ZCODE_DIR/agents/$(basename "$f")"
  done
  link "$REPO/hosts/zcode/generated/AGENTS.md" "$ZCODE_DIR/AGENTS.md"
  for f in "$REPO"/hosts/zcode/scripts/*; do
    link "$f" "$ZCODE_DIR/scripts/$(basename "$f")"
  done
  for f in "$REPO"/hosts/zcode/hooks/*; do
    link "$f" "$ZCODE_DIR/hooks/$(basename "$f")"
  done
fi

# 4. opencode
if want opencode && [ -d "$OPENCODE_DIR" ]; then
  link "$REPO/hosts/opencode/AGENTS.md" "$OPENCODE_DIR/AGENTS.md"
  for sub in plugins scripts commands; do
    for f in "$REPO"/hosts/opencode/$sub/*; do
      link "$f" "$OPENCODE_DIR/$sub/$(basename "$f")"
    done
  done
fi

if [ "$CHECK" = 1 ]; then
  [ "$drift" = 0 ] && echo "✅ дрейфа нет" || { echo "⚠️  дрейф найден"; exit 1; }
fi
