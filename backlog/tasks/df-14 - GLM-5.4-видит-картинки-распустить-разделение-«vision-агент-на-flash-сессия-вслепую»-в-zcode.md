---
id: DF-14
title: >-
  GLM-5.4 видит картинки: распустить разделение «vision-агент на flash / сессия
  вслепую» в zcode
status: Done
assignee:
  - '@main'
created_date: '2026-11-23T07:16:51Z'
updated_date: '2026-11-23T08:27:28Z'
labels: []
dependencies: []
documentation:
  - backlog/docs/capabilities/doc-3 - Чтение-изображений-в-средах.md
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
04.10.2026 glm-5.3 в rk_bot «прочитал» скриншот psql, которого не видит: выдуманная таблица и вердикт «фискального долга нет». Слепоту закрыли разделением труда: в ztui — агент vision на GLM-5.3-Flash и абзац в слоте models; в Claude Code через glm.sh — glm-blind.py + see.sh; в opencode — внешние глаза в derflow-hooks.js. 23.11.2026 вышла GLM-5.4 с вижн, сессия ztui уже едет на ней, владелец просит разделение убрать. Задача покрывает только zcode: там модель уже видит. glm.sh и opencode остались на glm-5.3 (opencode.json: zai-glm/glm-5.3), их упор не трогаем до решения владельца о переводе.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Дока capability «Чтение изображений в средах» описывает по факту кода, какая модель что видит и где стоит упор от слепоты (zcode, Claude Code через glm.sh, opencode, kimi)
- [x] #2 Проба check-vision.py на модели сессии GLM-5.4: картинка со случайным содержимым прочитана через Read, сверка с истиной без расхождений, код 0
- [x] #3 Слот models среды zcode не называет GLM слепым и не отсылает к агенту vision; правило привязано к версии модели (5.4 читает сам, 5.3 слеп)
- [x] #4 Агента vision нет ни в hosts/zcode (агент и generated), ни среди симлинков ~/.zcode/agents
- [x] #5 ./install.sh --check выходит с «дрейфа нет», generated закоммичен вместе с источниками
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Проба check-vision.py: рендер случайной картинки, Read моделью сессии, сверка. Не видит — стоп и доклад владельцу, канон не трогать.
2. Слот hosts/zcode/slots/models.md: правило по версии модели, без агента vision.
3. Удалить hosts/zcode/agents/vision.md, пересобрать generated, снять симлинк ~/.zcode/agents/vision.md.
4. install.sh --check.
5. Дока capability по факту кода, bl-done, коммит и пуш на main.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Проба 23.11.2026, ztui, glm-5.4, core/scripts/check-vision.py: №1 — 7 из 8, серийный номер кеглем 11 px прочитан с ошибкой (S за 5); тот же файл через see.sh (glm-5.3-flash) дал ту же ошибку на той же букве; №2 и №3 — 8 из 8. Сверщик прогнан на пяти ответах: верный с вариациями пробелов, ё→е и числом вместо строки проходит; неверная буква, выдуманный статус, счёт мимо на единицу и пустой ответ падают. install.sh --check показал старый дрейф копий скиллов kimi-work (core/skills/derflow/_capture.md обновлён 23.11, docflow/SKILL.md — 14.11, копии от 12.11 и 14.10), к задаче отношения не имеет — подтянут ./install.sh --only kimi-work.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ждёт тебя: решение по двум слепым средам — Claude Code через glm.sh и opencode стоят на glm-5.3, их упор (glm-blind.py, see.sh, внешние глаза derflow-hooks.js) не тронут; при переводе на 5.4 упор сносится вместе с моделью, иначе заблокирует видящую. Исполнители и разведка в ztui остались на GLM-5.3-Flash: flash-версии 5.4 в списке моделей нет. НЕ проверено: картинка, вложенная в сообщение (проверен только Read); скриншоты двойной плотности; зум как лекарство от мелкого шрифта; /code-review не гонял. Сделано: слот models среды zcode переписан под версию модели; агент vision удалён — источник, generated и симлинк ~/.zcode/agents/vision.md; check-vision.py — проба со случайным содержимым, живущим только в пикселях; doc-3 «Чтение изображений в средах». Найдено: мелкий шрифт 11 px читается с ошибкой в букве (1 знак из 36), flash ошибается так же — регрессии от отмены обхода нет; install.sh не подчищает симлинк распущенного агента и не видит его в --check (снят руками).
<!-- SECTION:FINAL_SUMMARY:END -->
