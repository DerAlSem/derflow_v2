---
id: DF-12
title: 'handoff-header: сторож шапки хендоффа в момент записи'
status: Done
assignee: []
created_date: '2026-11-12T20:32:00Z'
updated_date: '2026-11-12T20:32:00Z'
labels: []
dependencies: []
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Замер 12.11.2026: 45 из ~60 хендоффов по всем репо написаны без шапки «ветка:»/«имя:» — hand.sh при передаче ругается предупреждениями (таб «?·слаг», принадлежность ветке не проверена), автоподбор отказывает код 1. Правило в derflow/_capture.md есть, исполняет меньшинство сессий: текст канона не помогает. Решение — PostToolUse-хук core/hooks/handoff-header.py (Write|Edit|MultiEdit|NotebookEdit|ApplyPatch → .claude/handoff/*.md без «^ветка:»/«^имя:»): подсказка пишущей сессии в момент записи, не блокирует, не правит файл; вывод по контракту среды (ZCode additionalContext / Claude decision-block / kimi plain). Регистрация: hosts/claude/settings.json + живые ~/.claude/settings.json, ~/.zcode/cli/config.json, hosts/kimi-code/config.toml + живой ~/.kimi-code/config.toml. Стенд core/scripts/handoff-bite.sh (8/0, сломанная копия краснеет).
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Проверено: core/scripts/handoff-bite.sh — ✅ 8 ❌ 0, нарочно сломанная копия (без проверки шапки) краснеет ✅ 3 ❌ 4; ./install.sh --check — «дрейфа нет»; хук доступен живым средам по симлинку ~/.claude/hooks/handoff-header.py. Регистрации: живые ~/.zcode/cli/config.json, ~/.claude/settings.json, ~/.kimi-code/config.toml + канон hosts/claude/settings.json, hosts/kimi-code/config.toml.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Сторож шапки хендоффа: PostToolUse-хук handoff-header.py подсказывает сессии в момент записи файла в .claude/handoff/*.md без строк «ветка:»/«имя:» (замер: 45 из ~60 хендоффов по репо без шапки). Три ветки вывода по среде (ZCode additionalContext, Claude decision-block, kimi plain), fail-open. Стенд handoff-bite.sh 8/0. Риск: живой ~/.zcode/cli/config.json не под стражей install --check — правки в нём не ловятся дрейфом (как и у всех зкод-хуков).
<!-- SECTION:FINAL_SUMMARY:END -->
