---
id: DF-13
title: >-
  Скилл modern-web-guidance: подключить, привязать к frontend-developer, пилот
  на двух проектах
status: In Progress
assignee:
  - '@main'
created_date: '2026-11-13T07:01:00Z'
updated_date: '2026-11-13T07:02:00Z'
labels:
  - skills
dependencies: []
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Google Chrome modern-web-guidance (npm, Apache-2.0): актуальные нативные веб-API для агентов. Подключаем тонким скиллом-обёрткой в skills/ с закреплённой версией 1.0.0 и DISABLE_TELEMETRY=1 (CLI шлёт текст search-запросов в Google Clearcut), без вендоринга пакета (16,5 МБ, derflow_v2 публичный). frontend-developer узнаёт о скилле из шапки. Затем legacy-scan на двух проектах владельца.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Скилл skills/modern-web-guidance существует, закрепляет версию 1.0.0 и во всех командах ставит DISABLE_TELEMETRY=1; install.sh раскладывает его в ~/.claude/skills
- [x] #2 Шапка frontend-developer требует search до написания веб-UI-кода и называет скилл; install.sh --check чистый, generated закоммичен
- [ ] #3 search и retrieve отработали из установленного скилла на реальном запросе, телеметрия не уходит (DEBUG_MWG_TELEMETRY показывает отключение)
- [ ] #4 legacy-scan прогнан минимум на двух проектах владельца, отчёт с проверенными находками (keepWhen/dropWhen) лежит в доке или в заметках задачи
<!-- AC:END -->
