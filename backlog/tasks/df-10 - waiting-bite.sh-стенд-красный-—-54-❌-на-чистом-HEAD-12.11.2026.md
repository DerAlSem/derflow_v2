---
id: DF-10
title: 'waiting-bite.sh: стенд красный — 54 ❌ на чистом HEAD (12.11.2026)'
status: To Do
assignee: []
created_date: '2026-11-12T18:47:00Z'
labels:
  - waiting
  - стенд
dependencies: []
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Найдено при DF-1: core/scripts/waiting-bite.sh даёт 173✅/54❌ и на чистом HEAD, и с правками DF-1 — поломка предшествующая. Первые провалы: done/ack waiting.py в стенде возвращают rc=1 («полный id снимает строку», «done ставит closed_at», «done требует причину смерти» и далее). Живой waiting.py в хуках работает — подозрение на сам стенд после переезда 09.11. Начать с одного провала руками в стенде.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 стенд waiting-bite.sh зелёный целиком
<!-- AC:END -->
