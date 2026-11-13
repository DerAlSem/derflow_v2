---
id: DF-13
title: >-
  Скилл modern-web-guidance: подключить, привязать к frontend-developer, пилот
  на двух проектах
status: Done
assignee:
  - '@main'
created_date: '2026-11-13T07:01:00Z'
updated_date: '2026-11-13T07:03:00Z'
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
- [x] #3 search и retrieve отработали из установленного скилла на реальном запросе, телеметрия не уходит (DEBUG_MWG_TELEMETRY показывает отключение)
- [x] #4 legacy-scan прогнан минимум на двух проектах владельца, отчёт с проверенными находками (keepWhen/dropWhen) лежит в доке или в заметках задачи
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Пилот legacy-scan (1.0.0, DISABLE_TELEMETRY=1), 3 проекта: mprz 2 находки, propevay 3, romantsova.store 6. Проверка по keepWhen/dropWhen: mprz — обе в mocks/*.html (primeicons@7.0.0 без SRI), по правилу верны, по делу сброшены (одноразовые макеты). propevay: gallery-view.ts:51 верна (кнопка data-gal-close -> dialog.close(), заменима на command/commandfor); gallery-view.ts:83 верна (ручной light-dismiss, заменим на closedby=any с фолбэком); event-view.ts:311 — ручной light-dismiss с защитой от drag-выделения (downOnBackdrop), перед заменой прочитать guide dialog, не ясно, держит ли closedby эту защиту. romantsova.store: проверены 2 из 6 (ParamPanel.tsx:40, Workshop.tsx:194) — Enter->blur, не отправка формы, сброшены по dropWhen; остальные 4 не смотрел. Телеметрия: отключение подтверждено чтением isTelemetryEnabled (при DISABLE_TELEMETRY=1 конструктор логгера не создаёт watchdog), но не наблюдалось в рантайме (DEBUG_MWG_TELEMETRY вывода не даёт ни при включённой, ни при выключенной).

Дока не менялась: обёртка-скилл: поведение описано в самом SKILL.md, capability-доки нет
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ждёт тебя: решить, какие из находок propevay править (3 шт., см. заметки) и смотреть ли остальные 4 в romantsova.store. НЕ проверено: телеметрия выключена по коду, а не по сетевому наблюдению; /code-review не гонял (дифф — проза скилла и абзац в шапке агента); frontend-developer ещё не вызывал скилл в живой задаче — сработает ли шапка, видно только в первом реальном прогоне (по секции ### Modern Web Guidance в его ответе). Сделано: skills/modern-web-guidance — тонкая обёртка с закреплённой 1.0.0 и DISABLE_TELEMETRY=1 в каждой команде, без вендоринга 16,5 МБ; симлинки в claude, zcode, kimi-code; шапка frontend-developer требует search до веб-кода; install.sh --check чист; search/retrieve проверены. Найдено: CLI шлёт текст search-запросов в Google Clearcut — поэтому префикс обязателен; npx @latest в оригинале меняет гайды между запусками — закреплено.
<!-- SECTION:FINAL_SUMMARY:END -->
