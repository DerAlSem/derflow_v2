# Происхождение агентов и вендоренных скиллов

Что откуда взято, под какой лицензией, что здесь изменено и как обновить.

**Зачем файл.** Раньше это жило только в памяти сессий — а память не версионируется
вместе с файлами, устаревает и уже однажды потеряла запись (`gap-finder` в ней не
значился). Происхождение должно лежать рядом с тем, чьё оно.

Проверено и обновлено: **2026-07-25**.

---

## Три класса — и почему они установлены по-разному

| Класс | Что | Механизм |
|---|---|---|
| **Плагины** | `superpowers`, `self-learning` (`marketing-skills` снят в v5.0) | объявлены в `settings.json` → `enabledPlugins` + `extraKnownMarketplaces`; код в `plugins/` (не версионируется), обновление через `/plugin` |
| **Своё** | `skills/derflow`, `explore-code`, `audit-code`, `adopt-code`, `_orient-engine.md`, `_conformance-sweep.md`, `agents/gap-finder.md` | живёт здесь, версионируется, источник — этот репо |
| **Вендоренное** | 8 агентов + `skills/make-interfaces-feel-better` | скопировано и **закреплено намеренно** (см. решение ниже), обновление ручное по рецепту |

## Решение: вендоренное остаётся вендоренным (2026-07-25)

`wshobson/agents` **публикует** маркетплейс Claude Code
(`/plugin marketplace add wshobson/agents`, MIT) — то есть перевести 7 ролевых
агентов на автообновление технически можно. **Решено не переводить**, три причины:

1. **Гранулярная установка не поддерживается.** В манифесте 94 плагина, агенты
   упакованы в бандлы; отдельный агент не ставится. Семь нужных агентов = семь
   бандлов, каждый тянет своих агентов и скиллы в общий список. Ценность derflow
   в *малом известном* наборе целей маршрутизации — семь бандлов его затопят.
2. **Локальные правки потеряются.** Все копии здесь переведены на
   `model: inherit` (чтобы ехать на модели сессии), часть переименована под
   `имя файла == name:` (`review.md`→`code-reviewer`, `update-docs.md`→
   `documentation-expert`), `system-architect` дописан фронтматтером. Установка
   плагина это откатит.
3. **Для роутера закреплённость — свойство, а не дефект.** Имена агентов несущие:
   на них ссылается таблица дисамбигуации в `skills/derflow/SKILL.md`.
   Автообновление промптов агентов = молча меняющееся поведение маршрутизации.

Настоящий дефект был не в способе установки, а в том, что происхождение не было
записано рядом с файлами. Этот файл его закрывает.

---

## Агенты

### Из коллекции `wshobson/agents` (7)

`backend-architect` · `code-reviewer` · `context-manager` · `documentation-expert`
· `frontend-developer` · `python-pro` · `system-architect`

- **Источник:** https://github.com/wshobson/agents
- **Лицензия:** MIT
- **Маркеры принадлежности:** «When invoked:», «Query context manager».
- **Взято:** 2026-07-02 (вручную).
- **Локальные изменения:** `model:` → `inherit` у всех; `review.md` →
  `code-reviewer.md`, `update-docs.md` → `documentation-expert.md` (имя файла
  приведено к `name:`); `system-architect` был вообще без фронтматтера — добавлен.
- **Обновить:** сравнить с upstream вручную, перенести изменения, **сохранив**
  локальные правки выше. Не заменять файл целиком.

### `ui-ux-designer` (1)

- **Источник:** https://github.com/madinagbotoe/portfolio/tree/main/.claude/agents
- **Лицензия:** **Creative Commons Attribution 4.0 (CC BY 4.0) — атрибуция
  обязательна.** Заголовок с ссылкой и лицензией хранится внутри самого файла
  (`agents/ui-ux-designer.md:10-12`); **при любой правке и при любом шеринге его
  надо сохранять.**
- **Взято:** 2026-07-02.
- **Локальные изменения:** `model:` → `inherit`.

### Из той же коллекции, через `~/.config/opencode` (6, добавлены 2026-07-25)

`sql-pro` · `docs-architect` · `reference-builder` · `tutorial-engineer` ·
`legal-advisor` · `payment-integration`

- **Источник:** та же коллекция `wshobson/agents` (MIT), взяты не с апстрима, а
  из `~/.config/opencode/agents/`, где они уже лежали.
- **Локальные изменения при переносе:** фронтматтер приведён к формату Claude Code
  (`mode: subagent` убран, добавлен `tools:`, `model: inherit`); у
  `docs-architect` и `tutorial-engineer` починены имена — в opencode в поле
  `name:` протекли префиксы бандлов (`code-documentation-docs-architect`,
  `code-documentation-tutorial-engineer`); описания переписаны под
  дисамбигуацию derflow.
- **⚠️ Два из них обещают домен, которого не знают.** `legal-advisor` написан под
  GDPR/EU (152-ФЗ, ОФД/ФНС, самозанятые — вне его знания); `payment-integration`
  под Stripe/PCI/мультивалютность (СБП, ККТ, `KkmServer` — вне). Взяты сознательно
  как каркас общей дисциплины; ограничение продублировано в таблице дисамбигуации
  `skills/derflow/SKILL.md`, чтобы маршрут не обещал больше, чем агент умеет.
  **Осторожно с `workflow-cadence` в opencode:** его сценарий I объявляет
  `legal-advisor` агентом «узкого РФ-комплаенса», хотя это не так — маршрутная
  таблица там обещает то, чего в самом агенте нет.

### `gap-finder` (1) — своё

- **Источник:** написан здесь, не заимствован. Подтверждено 2026-07-25 сверкой с
  копией в `~/.config/opencode/agents/gap-finder.md`: содержание идентично,
  различается только фронтматтер под харнесс (`tools: Read, Grep, Glob` здесь
  против `mode: subagent` + `permission.bash: deny` там).
- Самый используемый агент в derflow (11 упоминаний в роутере).

---

## Вендоренные скиллы

### `skills/make-interfaces-feel-better`

- **Источник:** https://github.com/jakubkrehel/make-interfaces-feel-better
  (установлен владельцем 2026-07-25; до этого происхождение было утеряно —
  атрибуции в файлах нет, память ошибочно возводила его к `gmb_v2`).
- **Лицензия:** MIT.
- **Маркетплейса нет** (`.claude-plugin/` в репо отсутствует) → установка только
  копированием. Вендоринг здесь не выбор, а единственный доступный способ.
- **Обновлено до апстрима 2026-07-25.** Копия от 2026-07-02 отстала на три
  недели: `SKILL.md` 7803b → 11818b, добавлен отсутствовавший `icons.md`,
  переписан формат отчёта (severity, «Considered but Rejected»,
  verification/verdict), добавлены правила про систему стилей проекта и разбор
  анимации на 10% скорости. Локальных правок не было — расхождения оказались
  изменениями апстрима.
- **Не берём:** `agents/openai.yaml` из апстрима — артефакт под другой харнесс.
- **Обновить:**
  ```
  R=jakubkrehel/make-interfaces-feel-better
  for f in SKILL.md typography.md surfaces.md animations.md performance.md icons.md; do
    gh api repos/$R/contents/skills/make-interfaces-feel-better/$f --jq '.content' \
      | base64 -d > skills/make-interfaces-feel-better/$f
  done
  ```
  Старая версия всегда достаётся из git — перезапись обратима.

---

## Восстановление конфига с нуля

1. `git clone git@github.com:DerAlSem/claude-config.git` → скопировать
   `skills/ agents/ commands/ CLAUDE.md settings*.json` в `~/.claude/`.
2. Плагины подтянутся по `settings.json` (`enabledPlugins` +
   `extraKnownMarketplaces`) — их код в `plugins/` не версионируется намеренно.
3. Вендоренное приедет вместе с репо (оно здесь и живёт) — переустанавливать
   ниоткуда не надо.

## v5.0 (derflow_v2, 24.09.2026): исполнители на Sonnet

`python-pro` и `frontend-developer` переведены с `model: inherit` на
`model: sonnet`, их `description` ужат до двух строк. Причина: описания агентов
грузятся в каждую сессию, а `inherit` сажал исполнителей на Opus вместе с
оркестратором. Критики (`system-architect`, `gap-finder`, `ui-ux-designer`)
остаются на `inherit`: их ценность в более сильной модели. При обновлении
вендорской копии эти две правки накатываются заново.
