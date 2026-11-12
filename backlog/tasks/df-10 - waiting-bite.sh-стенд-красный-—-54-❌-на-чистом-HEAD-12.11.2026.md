---
id: DF-10
title: 'waiting-bite.sh: стенд красный — 54 ❌ на чистом HEAD (12.11.2026)'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-12T18:47:00Z'
updated_date: '2026-11-12T19:01:00Z'
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
- [x] #1 стенд waiting-bite.sh зелёный целиком
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Воспроизвести один провал (waiting.py done в стенде) руками, увидеть stderr. 2. Локализовать: стенд или waiting.py. 3. Починить, прогнать waiting-bite до зелёного. 4. Закрыть AC DF-1#2, оба таска в Done, коммиты.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Причина — не переезд, а python: read_text/write_text(newline=) появились в 3.13, а python3 в части сред — 3.12.16 (daimon runtime); под 3.15 (homebrew) всё работало, потому живые хуки не страдали. Починка: хелперы _read_keep_eol/_write_keep_eol на open(newline=""), четыре вызова переведены. waiting-bite 227/0, остальные стенды: memo 64/0, ctxmeter 7/0, toolcarry 14/0, hand 18/2 (омоглифы — DF-11).
<!-- SECTION:FINAL_SUMMARY:END -->
