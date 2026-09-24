#!/usr/bin/env bash
# Переключение профилей Claude Code: живой всегда ~/.claude, спящие —
# ~/.claude-<имя>. Меняются переименованием каталогов, поэтому все зашитые
# пути (~/.claude/scripts, state, projects) остаются верными в обоих профилях.
#
#   cc-profile              # какой профиль живой
#   cc-profile v1 | v2      # переключить (все сессии claude закрыты)
#   cc-profile memory       # перенести память проектов из v1 в живой v2
#   cc-profile install      # положить себя в ~/.local/bin/cc-profile
#
# Профиль опознаётся по origin: derflow_v2 → v2, иначе v1.
set -euo pipefail

LIVE="$HOME/.claude"

# Скрипт живёт внутри переименовываемого каталога — исполняемся из копии.
if [ -z "${CC_PROFILE_COPY:-}" ] && [ "${1:-}" != "install" ]; then
  tmp="$(mktemp "${TMPDIR:-/tmp}/cc-profile.XXXXXX")"
  cp "$0" "$tmp"
  CC_PROFILE_COPY=1 exec bash "$tmp" "$@"
fi

which_profile() {
  local url
  url="$(git -C "$1" remote get-url origin 2>/dev/null || true)"
  case "$url" in *derflow_v2*) echo v2 ;; *) echo v1 ;; esac
}

running() {  # мост Claude in Chrome (--chrome-native-host) — не сессия
  ps -axo args= | grep -E '(^|/)claude( |$)' \
    | grep -v -e '--chrome-native' -e 'grep' | grep -q .
}

cmd="${1:-status}"
case "$cmd" in
  status)
    [ -d "$LIVE" ] || { echo "нет $LIVE"; exit 1; }
    echo "живой: $(which_profile "$LIVE")"
    for d in "$HOME"/.claude-*; do
      [ -d "$d" ] && echo "спит:  $(basename "$d")"
    done
    ;;
  v1|v2)
    cur="$(which_profile "$LIVE")"
    [ "$cur" = "$cmd" ] && { echo "уже $cmd"; exit 0; }
    [ -d "$HOME/.claude-$cmd" ] || { echo "нет ~/.claude-$cmd" >&2; exit 1; }
    [ -e "$HOME/.claude-$cur" ] && {
      echo "~/.claude-$cur уже существует — разберись руками" >&2; exit 1; }
    if running; then
      echo "закрой все сессии claude, потом повтори" >&2; exit 2
    fi
    mv "$LIVE" "$HOME/.claude-$cur"
    mv "$HOME/.claude-$cmd" "$LIVE"
    echo "живой: $cmd (был $cur → ~/.claude-$cur)"
    ;;
  memory)
    [ "$(which_profile "$LIVE")" = v2 ] || { echo "живой не v2" >&2; exit 1; }
    src="$HOME/.claude-v1/projects"
    [ -d "$src" ] || { echo "нет $src" >&2; exit 1; }
    n=0
    for m in "$src"/*/memory; do
      [ -d "$m" ] || continue
      slug="$(basename "$(dirname "$m")")"
      dst="$LIVE/projects/$slug/memory"
      [ -e "$dst" ] && { echo "пропуск (уже есть): $slug"; continue; }
      mkdir -p "$LIVE/projects/$slug"
      cp -R "$m" "$dst"
      n=$((n + 1))
    done
    echo "перенесено каталогов памяти: $n (транскрипты не трогались)"
    ;;
  install)
    mkdir -p "$HOME/.local/bin"
    cp "$0" "$HOME/.local/bin/cc-profile"
    chmod +x "$HOME/.local/bin/cc-profile"
    echo "готово: ~/.local/bin/cc-profile"
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
      echo "добавь ~/.local/bin в PATH (~/.zshrc)";; esac
    ;;
  *) echo "cc-profile [status|v1|v2|memory|install]" >&2; exit 1 ;;
esac
