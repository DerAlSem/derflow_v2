---
id: DF-3
title: 'Память проекта: ~/.claude → ~/dev/derflow'
status: Done
assignee:
  - '@kimi'
created_date: '2026-11-09T07:42:00Z'
updated_date: '2026-11-12T18:41:00Z'
labels: []
dependencies: []
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Авто-память Claude Code ключуется по cwd: работа над derflow теперь в ~/dev/derflow (-Users-deralsem-dev-derflow), а две записи (значки статуса, интервью по одному вопросу) и canon-budget.py смотрят в -Users-deralsem--claude/memory. Решить: скопировать записи или сделать их глобальными (они про владельца, не про репо).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 записи памяти о владельце доступны сессии в ~/dev/derflow
- [x] #2 canon-budget.py проверяет ту память, которой пользуются
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Правило интервью (один вопрос за сообщение) — строкой в core/AGENTS.md (значки там уже есть). 2. canon-budget.py: MEM — вычислять ключ памяти из cwd сессии, а не жёсткий -Users-deralsem--claude. 3. install.sh + --check, коммит. 4. Старые файлы памяти не трогаем — содержимое совпадает с каноном.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Записи памяти глобализированы через канон: значки статуса уже были в core/AGENTS.md, правило интервью (один вопрос за сообщение, 2–4 варианта) добавлено туда же — грузится во всех средах через сборку AGENTS.md. canon-budget.py больше не смотрит замороженный ключ -Users-deralsem--claude: ключ памяти вычисляется из cwd сессии. Старые файлы памяти оставлены — содержимое совпадает с каноном. install.sh + --check чисто, запушено.
<!-- SECTION:FINAL_SUMMARY:END -->
