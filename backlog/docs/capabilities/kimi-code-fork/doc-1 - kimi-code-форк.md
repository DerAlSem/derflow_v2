---
id: doc-1
title: kimi-code форк
type: guide
created_date: '2026-11-09T12:32:00Z'
updated_date: '2026-11-09T12:33:00Z'
---
# kimi-code форк

Как устроена кастомизация Kimi Code CLI под derflow. Разведка — DF-4 (09.11.2026), вердикт — decision-1. Клон: `~/dev/kimi-code` (github.com/MoonshotAI/kimi-code, MIT, main, версия 2.5.2, монорепо pnpm).

### Requirement: Рабочее окружение клона

ДОЛЖНА быть возможность поднять CLI из исходников за минуты, без правок системы.

#### Scenario: установка зависимостей

КОГДА в клоне выполняют `pnpm install` ТОГДА нужны Node ≥24.15 и pnpm 10.33 (engine-strict). На машине владельца `node` в PATH битый (shim kimi-desktop `command-process-owner/bin/node` падает с `exec: : not found`): workaround — `export PATH="/opt/homebrew/bin:$PATH"` (там node 26.13.0). `pnpm install` отрабатывает за ~70 секунд, postinstall без ошибок.

#### Scenario: запуск dev TUI

КОГДА нужен интерактив из исходников ТОГДА `pnpm dev:cli` (через `scripts/dev.mjs` → tsx + `src/main.ts`, cwd = корень монорепы). Проверено под pty (`script -q log pnpm dev:cli`): trust-гейт каталога → спиннер → welcome-экран с моделью из живого конфига `~/.kimi-code`. Быстрая проверка без pty: `pnpm dev:cli -- --version` → `2.5.2`. Конфиг и сессии dev-CLI читает те же, что и установленный бинарь.

### Requirement: Сборка и подмена нативного бинаря

ДОЛЖНА быть воспроизводимая локальная сборка SEA-бинаря и безопасная подмена живого `~/.kimi-code/bin/kimi`.

#### Scenario: сборка

КОГДА выполняют `pnpm build:native:sea` (в `apps/kimi-code`) ТОГДА пайплайн `scripts/native/build.mjs` делает 5 шагов: 01 tsdown-бандл в `main.cjs` (+ воркеры minidb/search), 02 SEA-blob, 03 postject-инъекция в копию node, 04 подпись (profile=local → adhoc), 05 verify. Выход: `apps/kimi-code/dist-native/bin/darwin-arm64/kimi` (~177 МБ). На прогретом клоне — ~10 секунд. ВАЖНО: homebrew-Node собран без SEA (`Single executable application is disabled`); нужен официальный бинарь Node (проверено: tarball v24.15.0 в /tmp, PATH-override на время сборки).

#### Scenario: проверка сборки

КОГДА бинарь собран ТОГДА `dist-native/bin/<target>/kimi --version` печатает версию пакета, а `pnpm test:native:smoke` (`scripts/native/smoke.mjs`) гоняет exec-server handshake и ssh-askpass без сети. Оба прошли на сборке из main.

#### Scenario: подмена живого CLI

КОГДА подменяют `~/.kimi-code/bin/kimi` своей сборкой ТОГДА копируют поверх собранный бинарь И обязательно ставят `KIMI_CODE_NO_AUTO_UPDATE=1` в окружение/конфиг запуска: иначе staged-обновление (`src/cli/update/native-swap.ts`) молча вернёт апстримный бинарь при очередном апдейте. `kimi upgrade` под патчем не запускают — после каждого апстрим-ребейза бинарь пересобирают и подменяют заново.

### Requirement: Точки патча TUI

ДОЛЖНА быть известна разметка TUI и минимальный шов под стартовый промпт интерактива.

#### Scenario: карта разметки

КОГДА нужен патч внешнего вида ТОГДА разметка приложения живёт в `apps/kimi-code/src/tui/`: хром — `components/chrome/` (footer.ts, welcome.ts, notify-panel.ts, dock-section.ts), правые/activity-панели («сайдбар») — `components/panes/` (activity-pane.ts, queue-pane.ts, btw-panel.ts, survey-panel.ts), сообщения транскрипта — `components/messages/`, координатор `kimi-tui.ts` (~5600 строк, делегирует в controllers/). Движок отрисовки — `packages/pi-tui` (примитивы Container/Text/HStack/Editor/Markdown), его трогать почти не нужно. Тема — `src/tui/theme/`, chalk-цвета вне темы запрещены CI-гардом.

#### Scenario: стартовый промпт интерактива (патч KIMI_TUI_PROMPT)

КОГДА hand.sh расщепляет сессию ТОГДА сейчас работает костыль: сеялка `kimi -p "<хендофф>"` (одноходовая, разрешения спросить не у кого) + `exec kimi -c` (интерактив стартует пустым и ждёт кика). В CLI нет способа посеять промпт в интерактив: `-p/--prompt` — только headless (конфликтует с --yolo/--auto/--plan), позиционных аргументов нет, из env существуют только дебаг-переменные вроде KIMI_TUI_INPUT_LATENCY. Патч: env `KIMI_TUI_PROMPT` (в стиле имён апстрима), читается в конце `KimiTUI.finishStartup()` (`src/tui/kimi-tui.ts`, ~строки 1128-1172) после старта подписки сессии; непустое значение уходит в публичный шов `this.handleUserInput(text)` (kimi-tui.ts:1550 — тот же путь, что и ввод пользователя: история, slash-диспатч, очередь). hand.sh тогда сводится к одному шагу: `KIMI_TUI_PROMPT="$(cat хендофф)" exec kimi` в новом табе — сессия сама начинает работу, разрешения спрашиваются в живом интерактиве. Аналог `--open-workspace-prompt` для десктопа не нужен: десктоп kimi — отдельный репо (code-app), здесь не патчится.

### Requirement: Модель сопровождения форка

ДОЛЖНА быть такой же, как у ZCode: клон + ветка с патчами, ребейз на апстрим.

#### Scenario: ведение патчей

КОГДА апстрим выкатывает релиз ТОГДА ветку патчей ребейзят на main, пересобирают бинарь, smoke, подменяют. Патчабельность высокая: TypeScript-исходники, чёткие границы модулей (AGENTS.md апстрима фиксирует карту), приёмов против форков нет. Цена патча KIMI_TUI_PROMPT — десятки строк в одном файле плюс чтение env; риск конфликтов при ребейзе минимальный (точка — хвост finishStartup, редко трогаемый код).
