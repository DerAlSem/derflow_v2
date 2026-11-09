---
id: DF-2
title: ztui headless не видит пользовательских скиллов ~/.zcode/skills
status: To Do
assignee: []
created_date: '2026-11-09T07:42:00Z'
labels: []
dependencies: []
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
09.11.2026: zcode -p (CLI 0.17.1 из ~/dev/ZCode) перечисляет только системные и плагинные скиллы (12). Не видит ни derflow/docflow (симлинки в ~/dev/derflow), ни docs/pdf (симлинки в ~/.claude/skills/synced, не тронуты), ни design-to-motion (настоящий каталог). Значит, причина не в переезде derflow. AGENTS.md ztui подхватывает (проверено). Проверить десктоп ZCode и интерактивный ztui; сканер — apps/zcode-cli/packages/adapters/src/skills/index.ts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 derflow виден в ztui (-p или TUI) — или записано, где именно ztui берёт пользовательские скиллы
<!-- AC:END -->
