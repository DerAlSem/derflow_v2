---
id: DF-1
title: 'Свип канона: «~/.claude как репозиторий» → ~/dev/derflow'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-09T07:42:00Z'
updated_date: '2026-11-12T19:01:00Z'
labels: []
dependencies:
  - DF-10
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
После переезда 09.11.2026 пути ~/.claude/scripts|hooks|skills остаются верными (симлинки), но фразы, где ~/.claude — git-репо канона (пушить, ворктри ~/.claude, грязное дерево ~/.claude), устарели. Кандидаты: _parallel.md, _capture.md, scripts/waiting-bite.sh (стенд считает ~/.claude репозиторием), stale-root.py. Только смена адреса, без правки решений роутера.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 grep по core/ не находит утверждений, что ~/.claude — git-репо канона
- [x] #2 waiting-bite.sh и memo-bite.sh проходят
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
12.11.2026: свип адресов сделан — _capture.md (мета-репо, карта букв C), _parallel.md:71, waiting-bite.sh (комментарий стенда; git init оставлен сознательно — waiting.py: «у ящика дома .git может не быть»), stale-root.py чист от ~/.claude. Archive-файлы помечены «на момент записи ~/.claude, с 09.11.2026 ~/dev/derflow» — история не переписана. Попутно _capture.md сжат до бюджета (124→120, canon-budget чист). AC#2 частично: memo-bite 64/0 ✅, waiting-bite 54 ❌ ПРЕДШЕСТВУЮЩЕЕ (проверено на чистом HEAD) — вынесено в DF-10, DF-1 ждёт его.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Свип адресов выполнен (12.11.2026): _capture.md (мета-репо, буква C), _parallel.md:71, waiting-bite.sh (комментарий стенда). Archive помечен «на момент записи», не переписан. AC#2: waiting-bite 227/0 после DF-10, memo-bite 64/0. Попутно: _capture.md ужат в бюджет 120.
<!-- SECTION:FINAL_SUMMARY:END -->
