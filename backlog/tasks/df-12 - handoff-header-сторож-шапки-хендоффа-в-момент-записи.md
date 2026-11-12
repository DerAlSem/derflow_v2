---
id: DF-12
title: 'handoff-header: сторож шапки хендоффа в момент записи'
status: To Do
assignee: []
created_date: '2026-11-12T20:32:00Z'
labels: []
dependencies: []
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Замер 12.11.2026: 45 из ~60 хендоффов по всем репо написаны без шапки «ветка:»/«имя:» — hand.sh при передаче ругается предупреждениями (таб «?·слаг», принадлежность ветке не проверена), автоподбор отказывает код 1. Правило в derflow/_capture.md есть, исполняет меньшинство сессий: текст канона не помогает. Решение — PostToolUse-хук core/hooks/handoff-header.py (Write|Edit|MultiEdit|NotebookEdit|ApplyPatch → .claude/handoff/*.md без «^ветка:»/«^имя:»): подсказка пишущей сессии в момент записи, не блокирует, не правит файл; вывод по контракту среды (ZCode additionalContext / Claude decision-block / kimi plain). Регистрация: hosts/claude/settings.json + живые ~/.claude/settings.json, ~/.zcode/cli/config.json, hosts/kimi-code/config.toml + живой ~/.kimi-code/config.toml. Стенд core/scripts/handoff-bite.sh (8/0, сломанная копия краснеет).
<!-- SECTION:DESCRIPTION:END -->
