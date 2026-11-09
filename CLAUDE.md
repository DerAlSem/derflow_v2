# derflow — канон процесса разработки для всех сред

Задачи этого репо ведутся через docflow с первого дня (09.11.2026). Реестр
`waiting/` — глобальный ящик для всех репо (`waiting.py --global`), сюда не
мигрируется: строки принадлежат чужим репо.

**Раскладка.** `core/` — канон: скиллы derflow и docflow, scripts, hooks,
schemas, агенты, входной файл `core/AGENTS.md` со слотами. `hosts/<среда>/` —
только то, чем среда правда отличается (claude, zcode, opencode). `skills/` —
скиллы-спутники (ru-text, copywriting, explore-code…). `tools/build.py` собирает
`hosts/*/generated`, `install.sh` раскладывает симлинки в `~/.claude`,
`~/.zcode`, `~/.config/opencode`.

**Правка действует сразу:** живые среды смотрят в этот чекаут. Правка
`core/AGENTS.md`, `hosts/*/slots` или шапок агентов — после `./install.sh`
(иначе `--check` покажет отставший generated). Коммить вместе с generated.

**Параллельный репо — ворктри не изолирует.** Скиллы и хуки читаются из живого
чекаута, копия в ворктри не действует до мержа: правь read-modify-write по
точному якорю, коммить мелко, `git status` до и после. Стенд RED для правки
роутера — ворктри + `./install.sh --claude-dir <стенд> --only claude` из него,
`CLAUDE_CONFIG_DIR=<стенд>`.

**Публичный репо** (`derflow_v2`): в `hosts/` ни ключей, ни хостов — скрипты
читают ключи из конфигов сред при запуске.


<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.55.3 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**At the beginning of each conversation in this project, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
