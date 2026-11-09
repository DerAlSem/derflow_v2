#!/usr/bin/env bash
# update-ztui.sh — подтянуть апстрим ZCode и пересобрать ztui без модели.
#
# Берёт: fetch → rebase → install (из корня) → пересборка → baseline архитектуры
# → пуш в зеркало через полный pre-push гейт (пробники прячутся в stash).
# НЕ берёт: конфликты ребейса. При конфликте — откат и отказ с одной фразой:
# дальше обновляет сессия («обнови ztui»), потому что выбор стороны конфликта
# решение по смыслу, а не механика.
#
# Запуск из любого места:  bash ~/.zcode/scripts/update-ztui.sh

set -euo pipefail

REPO="$HOME/dev/ZCode"
NODE24="/opt/homebrew/opt/node@24/bin"
# BSD mktemp не разворачивает XXXXXX с суффиксом после них: первый запуск молча
# создаёт файл с буквальным именем, каждый следующий падает с EEXIST. X — в конце.
LOG="$(mktemp /tmp/update-ztui.log.XXXXXX)"

export PATH="$NODE24:$REPO/node_modules/.bin:$PATH"
cd "$REPO"

say() { printf '%s\n' "$*"; }
die() { printf 'ОТКАЗ: %s\nПозови сессию: «обнови ztui».\n' "$*" >&2; exit 1; }

[ -d "$REPO/.git" ] || die "нет репозитория $REPO"

# Незакоммиченные правки в отслеживаемых файлах — ребейс не поедет.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  die "в репо есть незакоммиченные правки отслеживаемых файлов"
fi

say "==> fetch апстрима"
git fetch origin

BEHIND="$(git rev-list --count main..origin/main)"
if [ "$BEHIND" = "0" ]; then
  say "Нечего обновлять: локальный main уже на origin/main ($(git log -1 --format=%h))."
  exit 0
fi
say "==> пришло коммитов: $BEHIND, ребейс"

if ! git rebase origin/main 2>>"$LOG"; then
  git rebase --abort
  die "конфликт ребейса (детали: $LOG)"
fi

say "==> install из корня (0.17.0+ тянет кросс-воркспейс-зависимости)"
pnpm install --prefer-offline >>"$LOG" 2>&1

say "==> baseline архитектуры (локальные новые файлы, если появились)"
pnpm run architecture:baseline:update -- --changed >>"$LOG" 2>&1 || die "baseline:update упал (детали: $LOG)"
if [ -n "$(git status --porcelain -- .architecture-baseline.json)" ]; then
  git add .architecture-baseline.json
  git commit -m "architecture: baseline new local patch-stack files after rebase" >>"$LOG" 2>&1
fi

say "==> пересборка ztui"
(cd apps/zcode-cli && turbo run build --filter=@zcode/cli) >>"$LOG" 2>&1 \
  || die "сборка упала (детали: $LOG)"
VERSION="$(node apps/zcode-cli/packages/cli/dist/zcode.cjs version)"
say "    собрано: $VERSION"

say "==> пуш в зеркало через полный гейт (несколько минут)"
git stash push -u -m "update-ztui probes during gate" >>"$LOG" 2>&1
PUSH_CODE=0
git push --force-with-lease mirror main >>"$LOG" 2>&1 || PUSH_CODE=$?
git stash pop >>"$LOG" 2>&1

if [ "$PUSH_CODE" != "0" ]; then
  tail -5 "$LOG" >&2
  die "пуш/гейт не прошёл (детали: $LOG)"
fi

say "Готово: $VERSION, зеркало обновлено. Перезапусти вкладки ztui."
