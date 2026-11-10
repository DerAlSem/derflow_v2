---
id: DF-5
title: 'kimi-code: патч KIMI_TUI_PROMPT + подмена живого бинаря'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-10T10:12:00Z'
updated_date: '2026-11-10T12:42:00Z'
labels: []
dependencies: []
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Реализация по doc-1 (backlog/docs/capabilities/kimi-code-fork): env KIMI_TUI_PROMPT в конце KimiTUI.finishStartup (apps/kimi-code/src/tui/kimi-tui.ts ~1128-1172), непустое значение → this.handleUserInput(text) (тот же шов, что ввод пользователя). Работа в ~/dev/kimi-code, ветка derflow-hand. Сборка: pnpm build:native:sea в apps/kimi-code — НУЖЕН официальный Node (homebrew собран без SEA; tarball v24.15.0, PATH-override на время сборки), потом pnpm test:native:smoke. Подмена: cp собранного поверх ~/.kimi-code/bin/kimi + KIMI_CODE_NO_AUTO_UPDATE=1 (иначе staged-апдейт молча вернёт апстрим) — экспорт в launcher hand.sh, в доке отметить для ручных запусков. После патча hand.sh сводится к одному шагу: KIMI_TUI_PROMPT=... exec kimi — обновить hosts/kimi-code/scripts/hand.sh и слот slots/hand.md (кик-ритуал уходит), прогнать install.sh и --check. Проверки: новый tab по hand.sh стартует и СРАЗУ работает по хендоффу, заголовок таба = имя из хендоффа, kimi --version = наша сборка. Побочное: node в PATH битый (shim kimi-desktop) — везде PATH=/opt/homebrew/bin первым.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Патч в ветке derflow-hand, SEA собран, smoke зелёный
- [x] #2 Живой kimi подменён, авто-апдейт заблокирован, hand.sh одношаговый
- [x] #3 Слот hand обновлён, install.sh --check чистый, таб стартует с работой сразу
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. В ~/dev/kimi-code ветка derflow-hand: патч KIMI_TUI_PROMPT в конце KimiTUI.finishStartup() → this.handleUserInput(text). 2. Проверка без сборки: pnpm dev:cli под pty с KIMI_TUI_PROMPT — сессия сама начинает ход. 3. Сборка SEA на официальном Node v24.15.0 (PATH-override), pnpm test:native:smoke. 4. Бэкап kimi.bak-2.5.2, подмена ~/.kimi-code/bin/kimi, KIMI_CODE_NO_AUTO_UPDATE=1 в hand.sh + отметка в doc-1. 5. hand.sh в один шаг (KIMI_TUI_PROMPT=… exec kimi), обновить slots/hand.md и эхо-строки. 6. ./install.sh + --check; приёмка живьём: расщепление в /tmp-фикстуре без кика, заголовок таба = имя хендоффа. 7. Мелкие коммиты; DF-5 закрыть по task-finalization, заметки в хендофф. Во всех шагах PATH=/opt/homebrew/bin первым.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
10.11: патч 6 строк в хвосте finishStartup (коммит 397cf3248 в клоне, derflow-hand); typecheck+oxlint чисто. pty-проверка dev:cli: ход сам, ответ «ок». SEA 9с на Node v24.15.0 tarball, smoke зелёный. Подмена rename-first, cmp идентичен, бэкап kimi.bak-2.5.2. Живая приёмка в /tmp-фикстуре: преемник прочитал хендофф и ответил без кика (wire.jsonl), заголовок таба «T·6-приёмка» — автотитул проиграл лончеру. install.sh --check чист.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Реализован патч env KIMI_TUI_PROMPT (конец KimiTUI.finishStartup → handleUserInput, тот же шов что ввод пользователя) в клоне ~/dev/kimi-code, ветка derflow-hand; SEA-бинарь собран официальным Node v24.15.0, smoke зелёный, живой ~/.kimi-code/bin/kimi подменён (бэкап kimi.bak-2.5.2). hand.sh сведён к одному шагу KIMI_TUI_PROMPT=… exec kimi с экспортом KIMI_CODE_NO_AUTO_UPDATE=1 и повторной записью заголовка таба; слот hand.md, BRIEF.md и doc-1 обновлены, install.sh --check чист. Проверки: pty-прогон dev:cli — ход без ввода; живая приёмка расщеплением в /tmp-фикстуре — преемник начал работу без кика, заголовок таба = имя хендоффа. Риски/хвосты: tui.toml [upgrade] auto_install=true — ручные запуски вне hand.sh не защищены от staged-апдейта (решение владельца, отмечено в doc-1); ветка derflow-hand не пушилась — форка на GitHub нет.
<!-- SECTION:FINAL_SUMMARY:END -->
