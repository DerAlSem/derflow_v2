---
id: DF-9
title: >-
  kimi-code TUI: конфигурируемые полосы (doc-2 пп. 5–6) — патч в форке
  derflow-hand
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-12T17:52:00Z'
updated_date: '2026-11-12T18:24:00Z'
labels:
  - kimi-code
  - fork
  - tui
dependencies: []
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
doc-2 пп. 5–6: выключение конкретной полосы (notify, queue) и перестановка полос — одним конфигурируемым патчем (ключи в tui.toml), а не жёсткой правкой. Места: apps/kimi-code/src/tui/components/panes/ + координатор kimi-tui.ts. Побочная цель — патч компактный, переживает ребейз на апстрим.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tui.toml умеет выключить полосу (notify/queue) без пересборки логики — проверено pnpm dev:cli под pty
- [x] #2 порядок полос задаётся конфигом, перестановка queue под btw проверена живьём
- [x] #3 SEA-сборка на официальном Node, живой бинарь подменён с бэкапом, KIMI_CODE_NO_AUTO_UPDATE учтён
- [x] #4 doc-2 пп. 5–6 отмечены сделанными, коммиты запушены (derflow + DerAlSem/kimi-code derflow-hand)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Ключи tui.toml: [panes] order/disabled (список id: activity, notify, queue, btw, survey; нормализация с warn на неизвестные, order дополняется дефолтным хвостом, disabled побеждает). 2. Монтирование по конфигу в трёх точках: buildLayout, stopUiForExit, fullscreen-док (tui-state); гейт setEnabled для notify при выключенной полосе. 3. Тесты: config.test.ts (парсинг/рендер/round-trip), create-tui-state.test.ts (док). 4. pty-проверка pnpm dev:cli: скрытие queue и перестановка queue под btw. 5. SEA-сборка на официальном Node v24 + подмена живого бинаря с бэкапом. 6. doc-2 пп. 5–6, финализация задачи.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Реализация: [panes] order/disabled в tui.toml (PANE_IDS=activity,notify,queue,btw,survey; нормализация с warn, order дополняется дефолтным хвостом, disabled побеждает). Монтаж циклом paneContainers() в buildLayout/stopUiForExit + fullscreen-док; выключенная notify гейтится в setEnabled (фокус Ctrl+N). Round-trip через currentTuiConfig/reload. Коммит форка 399102cd6 (8 файлов, +247/−22), запушен в DerAlSem/kimi-code derflow-hand.

Проверка: vitest 60/60 (config+create-tui-state, новые describe panes + док-тест); oxlint чист; pnpm dev:cli под pty (pyte-эмулятор экрана): disabled=[queue] — полосы нет на экране; order=[...,btw,queue,...] — queue под btw (строки 22–24 экрана) против дефолта queue над btw (строки 16–18) при работающем ходе; оба PASS. SEA-сборка на официальном Node v24.15.0 (tarball /tmp), native smoke passed; живой бинарь подменён rename-first, бэкап kimi.bak-derflow-hand-20261112, cmp идентичен.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
doc-2 пп. 5–6 закрыты одним конфигурируемым патчем: секция [panes] в tui.toml (order — перестановка полос между транскриптом и редактором, disabled — скрытие насовсем; стиль ключей повторяет [status_line]). Коммит 399102cd6 в DerAlSem/kimi-code derflow-hand (запушен). Проверено: vitest 60/60, oxlint чист, pnpm dev:cli под pty — disabled=[queue] скрывает полосу, order ставит queue под btw живьём. SEA-сборка на официальном Node v24.15.0, smoke passed, живой бинарь подменён с бэкапом kimi.bak-derflow-hand-20261112; KIMI_CODE_NO_AUTO_UPDATE/auto_install=false стоят. doc-2 обновлён формой ключей. Применяется на старте процесса (/reload-tui раскладку не перемонтирует). Живой tui.toml пока БЕЗ [panes] — включение конкретных полос за владельцем после живой приёмки.
<!-- SECTION:FINAL_SUMMARY:END -->
