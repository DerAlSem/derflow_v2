---
id: doc-2
title: 'kimi-code TUI: настройка и кастомизация'
type: guide
created_date: '2026-11-10T15:01:00Z'
updated_date: '2026-11-11T04:37:00Z'
---
# kimi-code TUI: настройка и кастомизация

Карта того, что в TUI kimi-code настраивается без патча и что требует патча в
клоне, с ценой каждой правки. Разведка DF-6 (10.11.2026), источник — исходники
`~/dev/kimi-code` (ветка `derflow-hand`, 2.5.2). Операционная правда форка —
doc-1 там же.

## Ключевой факт: сайдбара нет

Раскладка TUI — одна вертикальная колонка (regular): транскрипт → activity →
notify → queue → btw → survey → редактор → футер (`buildLayout`,
`apps/kimi-code/src/tui/kimi-tui.ts:1498`). Fullscreen (`TuiAltScreen`):
транскрипт растёт в ScrollView, остальное собрано в нижний док
(`src/tui/tui-state.ts:193`), у queue/notify скроллящиеся тела
(`DOCK_QUEUE_ROWS=3`, `DOCK_UPDATES_ROWS=6`, `src/tui/constant/rendering.ts`).
«Панели» из `components/panes/` — горизонтальные полосы этой колонки, а не
правый столбец. Правого сайдбара в коде нет вообще (нет ни одного HStack в
`src/tui`).

## Слой 1: конфиг без патча (`~/.kimi-code/tui.toml`)

Схема — `src/tui/config.ts` (`TuiConfigFileSchema`). Живое применение без
рестарта: `/reload-tui` (кроме `tui_mode` — тот просит рестарт) и `/settings`
(пикеры: model, permission, theme, tuiMode, groupTools, groupThinking,
mermaid, editor, survey, experiments, upgrade, usage).

### Requirement: Слоты футера и свой statusline

#### Scenario: перестановка/усечение слотов

КОГДА в `[status_line]` задан `items` ТОГДА line 1 футера собирается из слотов
в заданном порядке: `mode, goal, model, tasks, environment, cwd, git, tips`
(`footer.ts:44`, дефолт — все, кроме `tips`; tips тогда живут справа и
ротируются раз в 10 с). Список без `tips` гасит советы совсем; включённый
`tips` ставит их инлайн в указанное место. Неизвестные имена игнорируются с
warning. Пустые слоты (нет goal, не git-репо, локальное окружение)
схлопываются сами.

#### Scenario: своя строка статуса

КОГДА задан `[status_line] command` ТОГДА команда получает JSON-снапшот на
stdin (`model, cwd, gitBranch, permissionMode, planMode, contextUsage,
contextTokens, maxContextTokens, sessionId, version`), и первая строка её
stdout целиком заменяет line 1; ctrl+o-хинт при этом уезжает на line 2
(`utils/status-line-command.ts`). Таймаут 300 мс, троттлинг 1 с, запуск через
`sh -c` с env `KIMI_CODE_STATUS_LINE=1`, любой сбой — молчаливый fallback на
встроенный футер.

#### Scenario: derflow-оснастка футера (состояние DF-7, 11.11.2026)

Живой `~/.kimi-code/tui.toml`: `status_line.command =
"$HOME/.kimi-code/statusline.sh"` (вне git) + `status_line.items` без `tips`
(советы погашены и во fallback-футере). Строка: `<ветка> · <задача> · <модель> ·
ctx <n>%[ · plan|<режим>]`; задача — «имя:» свежайшего хендоффа с совпавшей
«ветка:» (`.claude/handoff/`, `handoff/`), иначе замок bl-lock на этой ветке,
иначе имя каталога. Тёплый прогон ~50 мс (бюджет 300); сбой или не-git —
корректная усечённая строка либо молчаливый fallback.

### Requirement: Тема

#### Scenario: выбор темы

КОГДА задан `theme` ТОГДА `auto` — детект фона терминала с живым слежением,
`dark`/`light` — встроенные палитры, любое другое имя — кастомная тема из
`~/.kimi-code/themes/<name>.json` (`theme/custom-theme-loader.ts`): zod-схема
`{name, displayName?, base: dark|light, colors: {токен: #RRGGBB}}`, неуказанные
токены добираются из base. Всего 19 семантических токенов `ColorPalette`
(`theme/colors.ts`, у каждого документировано, что он красит);
`theme/theme-schema.json` — для авторинга. `/theme` перечисляет кастомные
темы и валидирует файл до сохранения. Цена фирменной темы — один JSON, патч
не нужен.

#### Scenario: тема derflow (состояние DF-7, 11.11.2026)

Живая тема — `~/.kimi-code/themes/derflow.json` (вне git), `theme = "derflow"` в
tui.toml: base dark, переопределены только `primary`/`borderFocus` `#F2A0C4`
(розовый — не пересекается ни с одним семантическим токеном) и `accent`
`#7FDBE8`. Остальные 16 токенов наследуются из dark.

### Requirement: Прочие ключи

#### Scenario: уведомления

КОГДА `[notifications] enabled=true` ТОГДА уведомления уходят как OSC 9 в
iTerm2/WezTerm/Ghostty/Warp/Kitty (allow-list), иначе BEL; в tmux — DCS
passthrough (`utils/terminal-notification.ts`). `notification_condition` —
`unfocused` | `always`. В Ghostty работает из коробки.

#### Scenario: автотитул вкладки

КОГДА `auto_session_title=false` ТОГДА автогенерация заголовка после первого
хода отключена (`kimi-tui.ts:2392`; дополнительно гейтится core-конфигом).
ВАЖНО: OSC 0-тайтл пишется в любом случае при аттаче сессии
(`updateTerminalTitle`, `kimi-tui.ts:3765` — при пустом title пишет имя
продукта), поэтому hand.sh нужна хотя бы одна перезапись заголовка после
аттача; но с `auto_session_title=false` гонка схлопывается с 40-секундного
цикла до одной записи через ~2–3 с. Побочка: session-picker показывает title
— без автотитула там остаются технические имена сессий. Состояние DF-7
(11.11.2026): `auto_session_title=false` в живом tui.toml; hand.sh переписывает
заголовок ОДИН раз через 3 с после старта (цикл 2–40 с снят).

#### Scenario: остальное

`tui_mode` — regular | fullscreen (experimental: alt-screen, нижний док,
группировка транскрипта; смена требует рестарта). `render_latex`,
`disable_paste_burst`, `cache_expiry_hint`, `editor.command`.
`[markdown] mermaid` — final | off. `[transcript.group]` — `tools`
(auto/explore/off) + `group_thinking` (только fullscreen).
`disable_feedback_survey` в tui.toml — legacy: теперь живёт в core config
(пишется через `/settings → survey`), из tui.toml вычищается
(`removeLegacySurveySetting`). `[upgrade] auto_install=false` — гард
подменённого бинаря (doc-1).

## Слой 2: патч (клон, `apps/kimi-code/src/tui`)

### Requirement: Скрытие и перестановка панелей

#### Scenario: перестановка полос

КОГДА нужен другой порядок полос ТОГДА правится порядок `addChild` в
`buildLayout` (`kimi-tui.ts:1498`) + зеркало выхода `stopUiForExit`
(`kimi-tui.ts:1524`) + fullscreen-док (`tui-state.ts:193`). Цена — десятки
строк, риск при ребейзе низкий-средний.

#### Scenario: удаление полосы насовсем

КОГДА полоса не нужна совсем ТОГДА: activity —
`resolveActivityPaneMode`/`updateActivityPane` (`kimi-tui.ts:4599`); queue —
`updateQueueDisplay` (`kimi-tui.ts:4764`); notify — контроллер в
`session-event-handler`; btw — `controllers/btw-panel.ts`; survey —
`controllers/survey-controller.ts` (уже читает core-конфиг). Цена —
единицы-десятки строк на полосу.

#### Scenario: автоскрытие (уже есть)

Автоскрытие встроено: queue видна только при непустой очереди; activity в
idle — однострочный спейсер, при диалогах/approval — hidden; notify
сворачивается в однострочный стаб в конце хода и на коротком экране (<32
строк при ожидании prompt); btw закрывается по Esc и не выше трети экрана;
survey показывается только по триггеру. Допиливать почти нечего — только
«совсем не показывать».

#### Scenario: фокус

Фокус-управление: notify-panel забирает фокус по Ctrl+N/клику, возвращает по
Esc/Ctrl+N/Enter; диалоги и approval подменяют редактор через `editorSlot`
(`tui-state.ts:287`); колёсико скроллит доки без захвата фокуса.

### Requirement: Оформление

#### Scenario: цвета и welcome

Все цвета — 19 токенов через `currentTheme` (`theme/theme.ts`); chalk named
colors вне темы запрещены CI-гардом (`chalk-named-color-guard.test.ts`) —
поэтому оформление правится либо темой (JSON, см. слой 1), либо вёрсткой
компонентов. Welcome (`chrome/welcome.ts`) — статичный render(): лого
`▐█▛█▛█▌`, Directory/Session/Model/Version/MCP. Правка — десятки строк.

#### Scenario: настоящий правый сайдбар

КОГДА нужен столбец справа ТОГДА pi-tui даёт HStack/VStack/flex
(grow/shrink/basis): HStack(transcript, sidebar) в корне regular-раскладки,
туда queue/notify. Цена — средний патч (~50–150 строк) плюс аудит ширин:
панели рендерятся на всю переданную ширину и считают её терминальной
(queue `renderItem`, notify `wrapTextWithAnsi`). Риск при ребейзе средний:
layout-код апстрим трогает чаще, чем хвост `finishStartup` (точка DF-5).

## Предложения владельцу (что хочешь — цена)

1. **Конфиг, $0 — ✅ сделано (DF-7, 11.11.2026)** — убрать tips из футера: `status_line.items` без `tips`
   (советы дублируют working-tips у спиннера).
2. **Конфиг, $0 — ✅ сделано (DF-7, 11.11.2026)** — свой `statusline.sh`: первая строка футера под derflow
   (ветка + имя хендоффа/задачи); JSON на stdin уже несёт `gitBranch` и `cwd`.
3. **Конфиг, $0 — ✅ сделано (DF-7, 11.11.2026)** — кастом-тема `~/.kimi-code/themes/derflow.json` (base dark,
   фирменные primary/accent).
4. **Конфиг, $0 — ✅ сделано (DF-7, 11.11.2026)** — `auto_session_title=false` + упрощение hand.sh: цикл
   перезаписи заголовка 2–40 с заменяется одной записью через ~2–3 с после
   старта. Побочка: технические имена в session-picker.
5. **Патч, ~10–30 строк** — выключить конкретную полосу насовсем (notify,
   queue), если мешает. Survey выключается конфигом, патч не нужен.
6. **Патч, десятки строк** — переставить полосы (например queue под btw).
7. **Средний патч, 50–150 строк + аудит ширин** — настоящий правый сайдбар;
   только если вертикальной колонки перестанет хватать.

Рекомендация: исчерпать слой 1 (пп. 1–4), патч начинать от реальной боли;
сайдбар (п. 7) — отдельной задачей и последним.
