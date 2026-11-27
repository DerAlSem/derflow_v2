---
id: DF-30
title: 'install.sh: управление регистрацией zcode-хуков (~/.zcode/cli/config.json)'
status: To Do
assignee: []
created_date: '2026-11-27T18:48:41Z'
labels:
  - хук
dependencies: []
documentation:
  - .claude/handoff/bl-hooks-manage.md
type: feature
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Слово владельца 27.11.2026 ≈21:35 МСК, дословно: «форма будильника - в целом норм., управление надо заводить, давай с этим снятием ворктри что-то решим.» Средняя часть — эта задача. Родитель — DF-29 (закрыта, a866dc0): её итог вынесла «регистрация zcode-хуков живёт только в `~/.zcode/cli/config.json`: вне git, `install.sh` её не собирает» вопросом к владельцу, он ответил «заводить». Источник — хендофф `.claude/handoff/bl-wake-tails.md`.

Зачем. ztui (zcode-cli 0.18.0-2) берёт команды хуков только из `~/.zcode/cli/config.json` и плагинов, проектный `.claude/settings` среда не читает. Файл один на все проекты и все ztui-сессии, вне git. Каждая новая запись — правка руками живого JSON с режимом 0600: так вставлены waiting wake, canon-budget, stale-root и 27.11.2026 bl-wake (в DF-29 размер, режим и побайтовое равенство сверяли руками). Из репо регистрацию не восстановить ни на новой машине, ни после переустановки; дрейф файла никто не видит.

Инвентаризация 27.11.2026, 21:40 МСК. Файл 0600, 3390 Б, верхние ключи `hooks` и `plugins`; `hooks.enabled: true`; 13 команд в семи группах, все — скрипты derflow:

- SessionStart, matcher `startup|resume|clear`: `waiting.py wake`, `canon-budget.py`, `stale-root.py`, `bl-wake.py` (`core/scripts`);
- UserPromptSubmit: `git-line.py`, `context-meter.py`, `canon-drift.py` (`core/hooks`), `tariff-meter.py` (`hosts/zcode/hooks`);
- PreToolUse: `main-tree-guard.py` (matcher `Edit|Write|ApplyPatch|Bash`), `openspec-critique-gate.sh` (matcher `Skill|Bash|Task|Agent`);
- PostToolUse: `context-meter.py --tool`, `handoff-header.py` (matcher `Write|Edit|MultiEdit|NotebookEdit|ApplyPatch`);
- Stop: `openspec-reap-gate.sh`.

Чужих записей в `hooks` нет; ключ `plugins` — не derflow. Набор отличается от эталона Claude Code `hosts/claude/settings.json`: там нет bl-wake, tariff-meter, main-tree-guard и openspec-гейтов, зато есть consult-receipt; схема другая (`hooks.events` против `hooks.<событие>`). Эталон для zcode нужен свой, переиспользовать эталон Claude нельзя.

Норма «config.json НЕ под install.sh» записана как состояние среды, без причины: de3792a (09.11.2026), `hosts/BRIEF.md:43`; повторена в doc-8 (строка 73), `core/skills/docflow/setup.md` (шаг 5) и докстринге `core/scripts/bl-wake.py` (строки 41–45). Прецеденты в репо:

- `install.sh` с `settings.json` Claude Code: не линкуется, эталон в репо (`hosts/claude/settings.json`), сверяется только `hooks`, правит человек; `config.toml` kimi-code не трогается — там ключ провайдера.
- `waiting.py doctor --install` (doc-5): запись хука в `~/.claude/settings.json` вставляется текстом по единственному якорю, остальное байт в байт, замена через временный файл — файл правят несколько сессий разом, сериализация `json.load → json.dump` затёрла бы чужое молча. Сверка при этом идёт разбором JSON, а не поиском по тексту: подстрока команды живёт и в `permissions.allow`. Предел: `doctor` читает только `~/.claude/settings.json` и про config.json не знает.

Слово владельца норму отменяет; объём управления выбирает он — это первый критерий.

Главный риск. Файл живой для всех ztui-сессий всех проектов: сломанный `hooks` — без хуков везде, отката в git нет. По хендоффу DF-29 CLI сам перезаписывает файл (команды плагинов; в коде CLI не сверено), поэтому перед записью читать заново, писать атомарно, копию рядом.

Верно при любом варианте с записью: меняются только записи derflow по точному якорю, прочие ключи побайтно прежние; режим 0600; второй прогон не меняет ни байта; `--check` видит дрейф и не пишет; стендовый прогон не касается живого файла — аналога `--claude-dir <стенд>` для zcode нет, понадобится свой ключ; все места нормы — по факту. `./install.sh` из ворктри не звать: перелинкует живые среды.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Объём управления согласован с владельцем и записан в задачу: что держит install.sh и пишет ли он в живой config.json; критерии реализации дописаны по выбранному варианту до первой правки кода
<!-- AC:END -->
