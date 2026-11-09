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

09.11.2026 (вечер, десктоп ZCode, сессия на живом dist из ~/dev/ZCode): скиллов нет и в десктопе. Сканер снят с подозрения: корень user-скиллов правильный (`~/.zcode/skills`, adapters/src/skills/roots.ts:115), симлинки-каталоги в user-руте сканер следует (`followSymbolicLinks: true` по умолчанию, adapters/src/skills/scan.ts:47; для plugin-рутов — false), frontmatter derflow проходит фильтры (name+description обязательны, description ≤1024 симв., adapters/src/skills/index.ts:20,183-215), dist свежее исходника (adapters/dist/skills/scan.js 05.11.2026, followSymbolicLinks присутствует). Вызов из рантайма есть: core/src/runtime/methods/context.ts:256 `discoverSkillsForContext` без кастомных roots. Значит, фильтр/выключатель сидит выше сканера — в слое между discoverSkills и списком скиллов в системном сообщении сессии (или в конфиге: config.json ключ `skills`/`skill.<path>.enable`, adapters/src/config/schema.ts). Кандидат для продолжения: grep потребителей `SkillLoadOutcome`/`discoverSkillsForContext` из core/src/runtime — что попадает в системный промпт. Рядом та же картина с агентами: ~/.zcode/agents/*.md (симлинки на hosts/zcode/generated/agents) в списке доступных типов не появляются — только встроенные Explore/general-purpose.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 derflow виден в ztui (-p или TUI) — или записано, где именно ztui берёт пользовательские скиллы
<!-- AC:END -->
