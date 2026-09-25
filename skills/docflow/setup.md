# docflow — подключение репозитория

Однократно, из корня репозитория, все сессии закрыты.

1. Backlog.md: `brew install backlog-md` (или `npm i -g backlog.md`).
   Версию закрепи и обновляй осознанно: инструкции агенту едут вместе с ней.
2. `backlog init "<Имя>" --defaults --integration-mode cli --agent-instructions claude --task-prefix <px>`
3. В `backlog/config.yml`:
   `statuses: ["Backlog", "To Do", "In Progress", "Done"]`
4. Миграция — сначала сверка базы с origin, потом план, потом `--apply`.
   `git fetch`, затем `git rev-list --count develop..origin/develop` обязан
   дать 0; иначе `git pull --ff-only` на базе. Боевое 24.09.2026: локальный
   `develop` отстал на 11 коммитов, миграцию делали дважды. База не `develop`
   — та же сверка для неё и `--base <ветка>` в команде:
   `python3 ~/.claude/scripts/bl-migrate.py --waiting .claude/waiting --global-waiting ~/.claude/waiting --entry <путь-репо>`
5. В проектный `.claude/settings.json` → `hooks.SessionStart`:
   `python3 ~/.claude/scripts/bl-wake.py` (timeout 5).
6. В проектный `CLAUDE.md`: «Задачи этого репо ведутся через docflow;
   openspec выведен из обращения <дата>». Блок Backlog.md, который вписал
   `init`, оставь как есть.
7. Сверь `backlog board`, закоммить `backlog/`. `openspec/` и строки
   отложки удаляй отдельным коммитом, когда убедишься, что всё переехало.

## С нуля — новый проект

Миграции нет, закрывать сессии не нужно. Пустой каталог:
`git init`, затем шаги 1–3, 5 и 6 выше (в 6 — «ведутся через docflow с
первого дня»). Remote ещё нет — `backlog init` предупредит про
`remoteOperations`; это не ошибка, пройдёт с `git remote add`. Первый
коммит — `backlog/` и `CLAUDE.md`, потом брейншторм и задачи через docflow.
