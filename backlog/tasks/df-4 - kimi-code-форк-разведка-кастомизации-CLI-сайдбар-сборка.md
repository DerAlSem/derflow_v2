---
id: DF-4
title: 'kimi-code форк: разведка кастомизации CLI (сайдбар, сборка)'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-09T11:39:00Z'
updated_date: '2026-11-09T12:36:00Z'
labels: []
dependencies: []
documentation:
  - backlog/docs/capabilities/kimi-code-fork/doc-1 - kimi-code-форк.md
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Разведка: как пересобрать Kimi Code CLI под себя (модель та же, что у ZCode — клон + ветка с патчами). Вопросы: 1) клон github.com/MoonshotAI/kimi-code в ~/dev/kimi-code, поднять pnpm dev:cli (Node >=24.15, pnpm 10.33); 2) где живёт сайдбар/TUI-разметка (packages/pi-tui, apps/kimi-code) и насколько она патчабельна; 3) как собирается одиночный бинарь (build/release-скрипты), можно ли подменить ~/.kimi-code/bin/kimi своей сборкой; 4) что из наших патчей ZCode (ZCODE_TUI_PROMPT, --open-workspace-prompt) нужно поротировать на kimi. Результат — decision/док в backlog с планом патчей. Контекст: hosts/kimi-code/ уже подключён (коммит ad3b0bb).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Клон собирается, dev:cli стартует
- [x] #2 Найден файл/пакет сайдбара, есть оценка патчабельности
- [x] #3 Известна команда сборки бинаря и способ подмены
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Клон MoonshotAI/kimi-code в ~/dev/kimi-code; 2. Node/pnpm версии, pnpm install, поднять pnpm dev:cli и зафиксировать старт; 3. Найти сайдбар/TUI-разметку (packages/pi-tui, apps/kimi-code), оценить патчабельность по модели ZCode (клон+ветка); 4. Найти сборку одиночного бинаря и способ подмены ~/.kimi-code/bin/kimi; 5. Определить, что из патчей ZCode (ZCODE_TUI_PROMPT, --open-workspace-prompt) нужно kimi-CLI; 6. Decision-док в backlog, закрыть AC, дописать заметки о hand.sh в хендофф
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Клон в ~/dev/kimi-code (main, 2.5.2). pnpm install OK (Node 26.13/pnpm 10.33.2; PATH-node битый — братский shim kimi-desktop, workaround: /opt/homebrew/bin в PATH). dev:cli под pty стартует: trust-гейт → welcome (модель k3-agent, 2.5.2). TUI-разметка: apps/kimi-code/src/tui (chrome/panes/messages + kimi-tui.ts 5595 строк-координатор), движок packages/pi-tui. Интерактивного seed-промпта нет: -p только headless, env KIMI_TUI_* — дебаг. Подмена бинаря: SEA-сборка scripts/native (5 шагов), автообновление глушится KIMI_CODE_NO_AUTO_UPDATE=1. Homebrew node собран без SEA — для сборки нужен официальный node (взял 24.15.0 tarball в /tmp).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ждёт тебя: решить, когда делать сам патч KIMI_TUI_PROMPT (ветка в ~/dev/kimi-code) и подмену живого бинаря — подмена НЕ делалась, ~/.kimi-code/bin/kimi не тронут. Сделано: клон ~/dev/kimi-code (main, 2.5.2), pnpm install OK; dev:cli под pty доходит до welcome-экрана; SEA-сборка pnpm build:native:sea отработала (~10 с на прогретом клоне), native smoke зелёный; карта TUI (apps/kimi-code/src/tui: chrome/, panes/ — «сайдбар», kimi-tui.ts) и план патчей записаны в doc-1 (capabilities/kimi-code-fork), вердикт — decision-1. Найдено: seed-промпта интерактива в CLI нет (-p только headless) — патч KIMI_TUI_PROMPT: чтение env в конце KimiTUI.finishStartup → handleUserInput, десятки строк; homebrew-Node собран без SEA (для сборки нужен официальный tarball, проверено на v24.15.0); node-shim kimi-desktop в PATH битый — workaround /opt/homebrew/bin в PATH; staged-апдейт молча вернёт апстримный бинарь — подмене обязателен KIMI_CODE_NO_AUTO_UPDATE=1.
<!-- SECTION:FINAL_SUMMARY:END -->
