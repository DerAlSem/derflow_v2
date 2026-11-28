---
id: DF-2
title: ztui headless не видит пользовательских скиллов ~/.zcode/skills
status: Done
assignee:
  - '@wb-df2'
created_date: '2026-11-09T07:42:00Z'
updated_date: '2026-11-28T05:23:47Z'
labels: []
dependencies: []
documentation:
  - backlog/docs/capabilities/doc-4 - install.sh-—-раскладка-по-средам.md
type: bug
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
09.11.2026: zcode -p (CLI 0.17.1 из ~/dev/ZCode) перечисляет только системные и плагинные скиллы (12). Не видит ни derflow/docflow (симлинки в ~/dev/derflow), ни docs/pdf (симлинки в ~/.claude/skills/synced, не тронуты), ни design-to-motion (настоящий каталог). Значит, причина не в переезде derflow. AGENTS.md ztui подхватывает (проверено). Проверить десктоп ZCode и интерактивный ztui; сканер — apps/zcode-cli/packages/adapters/src/skills/index.ts.

09.11.2026 (вечер, десктоп ZCode, сессия на живом dist из ~/dev/ZCode): скиллов нет и в десктопе. Сканер снят с подозрения: корень user-скиллов правильный (`~/.zcode/skills`, adapters/src/skills/roots.ts:115), симлинки-каталоги в user-руте сканер следует (`followSymbolicLinks: true` по умолчанию, adapters/src/skills/scan.ts:47; для plugin-рутов — false), frontmatter derflow проходит фильтры (name+description обязательны, description ≤1024 симв., adapters/src/skills/index.ts:20,183-215), dist свежее исходника (adapters/dist/skills/scan.js 05.11.2026, followSymbolicLinks присутствует). Вызов из рантайма есть: core/src/runtime/methods/context.ts:256 `discoverSkillsForContext` без кастомных roots. Значит, фильтр/выключатель сидит выше сканера — в слое между discoverSkills и списком скиллов в системном сообщении сессии (или в конфиге: config.json ключ `skills`/`skill.<path>.enable`, adapters/src/config/schema.ts). Кандидат для продолжения: grep потребителей `SkillLoadOutcome`/`discoverSkillsForContext` из core/src/runtime — что попадает в системный промпт. Рядом та же картина с агентами: ~/.zcode/agents/*.md (симлинки на hosts/zcode/generated/agents) в списке доступных типов не появляются — только встроенные Explore/general-purpose.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 derflow виден в ztui (-p или TUI) — или записано, где именно ztui берёт пользовательские скиллы
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
28.11.2026, сессия C·28.9-wb-ac34 — закрытие по факту, без новой правки кода. Причину нашли в день заведения и устранили тем же днём, а задача осталась в To Do: файл задачи последний раз трогали 09.11.2026 в 11:50 (2a8bd32), причину записали позже.

Что стало истинным:
- Причина (09.11.2026): в корне пользовательских скиллов лежала ссылка на файл. Сканер ZCode строит для неё путь `<файл>/SKILL.md`, `stat` даёт ENOTDIR, ошибку сканер не глотает (`adapters/src/skills/scan.ts:145`), и пустым возвращается весь корень (`index.ts:144`). Висячая ссылка корень не валит: её `stat` даёт ENOENT, а его сканер глотает.
- Фикс: `install.sh` ставит в `~/.zcode/skills` ссылки только на каталоги — `[ -d "$d" ] || continue`, коммит d4d1315 (09.11.2026), на HEAD строка 127.
- Улика критерия 1: интерактивная сессия ztui 28.11.2026 перечисляет 15 скиллов репозитория из `~/.zcode/skills` (derflow, docflow, explore-code, ru-text и остальные) и три собственных каталога вне репозитория; ссылок на файл в корне нет.
- Агенты: с 23.11.2026 сессии видят агентов-симлинков (frontend-developer, python-pro, gap-finder, system-architect, ui-ux-designer) — «не появляются» из описания устарело; что поменялось в движке, не смотрели.

НЕ проверено: headless `zcode -p` после исправления не перезапускали — критерий 1 выполнен по TUI. Как устроено теперь — doc-4, требование «в корне пользовательских скиллов ZCode лежат только каталоги»; прежний абзац BRIEF про ztui переписан.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ждёт тебя: headless `zcode -p` после исправления не перезапускали — критерий 1 выполнен по интерактивному ztui (сессия 28.11.2026 видит 15 скиллов репозитория). Риск: если `-p` по-прежнему не видит пользовательских скиллов, причина другая и это отдельная задача.

Сделано: причина найдена и устранена 09.11.2026 — `install.sh` ставит в `~/.zcode/skills` ссылки только на каталоги (d4d1315). В doc-4 записано требование «в корне пользовательских скиллов ZCode лежат только каталоги» с двумя сценариями; абзац BRIEF про ztui переписан по факту. Задача закрыта 28.11.2026: до этого стояла в To Do, потому что в день заведения её не перевели в Done.

Найдено: ссылка на файл в корне скиллов опустошает весь корень (ENOTDIR сканер не глотает), висячая — нет. Агенты-симлинки видны с 23.11.2026; причину перемены в движке не искали.
<!-- SECTION:FINAL_SUMMARY:END -->
