---
id: DF-1
title: 'Свип канона: «~/.claude как репозиторий» → ~/dev/derflow'
status: To Do
assignee: []
created_date: '2026-11-09T07:42:00Z'
labels: []
dependencies: []
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
После переезда 09.11.2026 пути ~/.claude/scripts|hooks|skills остаются верными (симлинки), но фразы, где ~/.claude — git-репо канона (пушить, ворктри ~/.claude, грязное дерево ~/.claude), устарели. Кандидаты: _parallel.md, _capture.md, scripts/waiting-bite.sh (стенд считает ~/.claude репозиторием), stale-root.py. Только смена адреса, без правки решений роутера.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 grep по core/ не находит утверждений, что ~/.claude — git-репо канона
- [ ] #2 waiting-bite.sh и memo-bite.sh проходят
<!-- AC:END -->
