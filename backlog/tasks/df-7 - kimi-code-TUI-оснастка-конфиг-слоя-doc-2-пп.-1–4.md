---
id: DF-7
title: 'kimi-code TUI: оснастка конфиг-слоя (doc-2 пп. 1–4)'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-11T04:25:00Z'
updated_date: '2026-11-11T04:42:00Z'
labels: []
dependencies: []
documentation:
  - doc-2
  - doc-1
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Разведка DF-6 (doc-2) дала 7 предложений по настройке TUI; рекомендация — исчерпать слой 1 (конфиг, $0) до любого патча. Владелец запустил работу по хендоффу C·7 «сразу, не переспрашивая» — берём рекомендованные пп. 1–4. Пп. 5–7 (патч полос и сайдбар) сюда НЕ входят: отдельное решение владельца. Контракты уже замерены: status_line.command получает JSON на stdin, первая строка stdout заменяет line 1 футера (300 мс, троттлинг 1 с, сбой → встроенный футер); кастом-тема — JSON по theme-schema.json из клона; auto_session_title=false схлопывает гонку заголовка таба до одной записи OSC 0 через ~2–3 с после аттача.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 В живом ~/.kimi-code/tui.toml задан status_line.items без tips — советы не выводятся ни в штатном, ни во fallback-футере
- [x] #2 ~/.kimi-code/statusline.sh по тестовому JSON-снапшоту печатает первой строкой «ветка · задача/хендофф · модель · контекст%», укладывается в 300 мс; сбой (нет jq/репо/хендоффа) даёт молчаливый fallback на встроенный футер; в tui.toml задан status_line.command
- [x] #3 ~/.kimi-code/themes/derflow.json валиден по theme-schema.json из клона (name, base=dark, colors #RRGGBB); в tui.toml выбрана theme = "derflow"
- [x] #4 В tui.toml auto_session_title=false; в hosts/kimi-code/scripts/hand.sh цикл перезаписи заголовка 2–40 с заменён одной записью через ~3 с, комментарии о гонке автотитула обновлены
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. statusline.sh (~/.kimi-code, вне git): ветка+задача из шапки хендоффа по «ветка:», модель и контекст% из JSON; jq <300 мс; любой сбой → exit 1 (встроенный футер). 2. tui.toml: status_line.items без tips, status_line.command=$HOME/.kimi-code/statusline.sh, theme="derflow", auto_session_title=false. 3. themes/derflow.json: base dark, фирменные primary/accent/borderFocus, валидация по theme-schema.json клона. 4. hand.sh: одна запись OSC 0 через 3 с вместо цикла 2–40 с + правка комментариев. 5. Проверки: синтетический JSON с замером времени, python-валидация темы и tui.toml, bash -n + dry-run hand.sh. 6. doc-2 дополнить состоянием, bl-done, коммит.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
statusline.sh живой: по тестовому JSON печатает «main · C·7-kimi-tui-оснастка · k3-agent · ctx 43%», тёплый прогон ~50 мс (холодный 236 мс — один раз на сессию, промах = разовый fallback). Края: не-репо, пустой stdin, битый JSON, чужая ветка — все корректны. Тема derflow.json валидна по theme-schema.json (проверка stdlib-скриптом). tui.toml: theme=derflow, status_line без tips + command, auto_session_title=false; tomllib-парс зелёный. hand.sh: dry-run на синтетическом каталоге — лончер с одной записью OSC 0 через 3 с.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ждёт тебя: /reload-tui в живой сессии (или перезапуск) — увидеть тему derflow, строку статуслайна и отсутствие tips; технические имена в session-picker — известная побочка auto_session_title=false. Сделано: doc-2 пп. 1–4. tui.toml: theme=derflow, status_line.items без tips, status_line.command=$HOME/.kimi-code/statusline.sh, auto_session_title=false. statusline.sh: «ветка · задача · модель · ctx%», задача из хендоффа/bl-lock/basename, тёплый прогон ~50 мс. Тема derflow.json (base dark, primary/borderFocus #F2A0C4, accent #7FDBE8) валидна по theme-schema.json. hand.sh: одна запись OSC 0 через 3 с вместо цикла 2–40 с. Проверено: синтетический JSON через реальный скрипт (контракт status-line-command.ts), tomllib-парс, валидация темы, bash -n + dry-run лончера, install.sh --check — дрейфа нет. НЕ проверено вживую: рендер в настоящем TUI — только /reload-tui владельцем. Найдено: locks лежат в .git/bl-locks (использовано как fallback источника задачи); хендофф C·7 обновлён под выбор пп. 5–7.
<!-- SECTION:FINAL_SUMMARY:END -->
