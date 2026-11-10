---
id: DF-6
title: 'kimi-code TUI: разведка настроек сайдбара и предложения'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-10T14:45:00Z'
updated_date: '2026-11-10T15:06:00Z'
labels: []
dependencies: []
documentation:
  - doc-2
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Разведка БЕЗ реализации: что в TUI kimi-code настраивается и какой ценой. Слои: 1) конфиг ~/.kimi-code/tui.toml (status_line items, theme, tui_mode fullscreen, notifications — ноль патча); 2) патч в клоне ~/dev/kimi-code (apps/kimi-code/src/tui/components/panes/ — activity/queue/btw/survey, chrome/, theme/; CI-гард: chalk вне theme запрещён). Вопросы: какие панели можно скрыть/переставить, есть ли автоскрытие, что из этого конфигурable без патча, какие слоты status_line доступны из коробки (mode, goal, model, tasks, environment, cwd, git, tips) и как добавить свой (command-скрипт), что стоит тема. Результат — doc в backlog/docs/capabilities/kimi-code-fork/ (дописать или соседний) + предложения владельцу с ценой каждого (конфиг / патч-строки / сложный патч). Контекст: doc-1 там же, форк DerAlSem/kimi-code, ветка derflow-hand, живой бинарь уже патченый (DF-5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Карта: что конфигурable в tui.toml без патча
- [x] #2 Карта панелей: скрытие/порядок — цена каждой правки
- [x] #3 Предложения владельцу с ценой, без реализации
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Разведка проведена по исходникам ~/dev/kimi-code (ветка derflow-hand). Ключевой факт: правого сайдбара в TUI нет — раскладка вертикальная колонка (buildLayout kimi-tui.ts:1498; fullscreen-док tui-state.ts:193). Слой конфига покрывает status_line (items + command), тему включая кастомные JSON из ~/.kimi-code/themes/, notifications (OSC 9, Ghostty в allow-list), auto_session_title, tui_mode, transcript.group. Автоскрытие панелей уже встроено (queue/activity/notify/btw/survey). Результат — doc-2 с ценой каждой правки и 7 предложениями владельцу.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Разведка без реализации. Результат — doc-2 (backlog/docs/capabilities/kimi-code-fork/): карта конфига tui.toml (status_line slots/command, темы включая кастомные JSON, notifications OSC 9, auto_session_title, tui_mode), карта панелей с ценой правок (перестановка = порядок addChild, десятки строк; удаление полосы = единицы-десятки строк; автоскрытие уже встроено; настоящий сайдбар = средний патч 50-150 строк + аудит ширин) и 7 предложений владельцу с ценой. Рекомендация: исчерпать слой конфига (пп. 1-4), сайдбар — отдельной задачей. Реализация не начиналась, живые конфиги и бинарь не тронуты. Заметки о hand.sh дописаны в хендофф.
<!-- SECTION:FINAL_SUMMARY:END -->
