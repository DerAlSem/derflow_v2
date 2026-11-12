---
id: DF-11
title: >-
  hand.sh: проверка омоглифов ломает кириллические буквы без двойника (hand-bite
  18/2)
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-12T19:00:00Z'
updated_date: '2026-11-12T19:08:00Z'
labels:
  - hand
  - стенд
dependencies: []
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Найдено при DF-10 (12.11.2026): hand-bite.sh красный на двух провах. 1) «Л·лото» отклоняется rc=4 «не канонная форма»: grep -E '^[[:alpha:]]·' под локалью стенда не признаёт кириллицу — буква без латинского двойника обязана проезжать. 2) Отказ по омоглифу приходит без слова «неотличим» — проверить порядок/текст в core/scripts/hand.sh (в kimi-версии текст с «неотличима» есть). Проверить и kimi-версию hand.sh на тот же класс.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 hand-bite.sh зелёный целиком
- [x] #2 kimi-версия hand.sh проверена на «Л·лото» и «Т·раскатка»
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Корень один: форма-гейт '^[[:alpha:]]·' под наследованной LC_COLLATE=C не признавал кириллицу — оба провала (и «Т·раскатка» без слова «неотличим», и отказ «Л·лото») были его срабатыванием до омоглиф-гейта. Починка: LC_ALL=en_US.UTF-8 на этот grep в обеих версиях hand.sh. Проверки: hand-bite 20/0; kimi-версия прогнана руками dry-run — «Л·лото» проезжает, «Т·раскатка» отклонена с «неотличима».
<!-- SECTION:FINAL_SUMMARY:END -->
