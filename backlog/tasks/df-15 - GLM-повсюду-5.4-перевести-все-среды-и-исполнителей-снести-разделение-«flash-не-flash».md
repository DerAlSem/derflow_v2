---
id: DF-15
title: >-
  GLM повсюду 5.4: перевести все среды и исполнителей, снести разделение «flash
  / не flash»
status: To Do
assignee: []
created_date: '2026-11-23T08:49:28Z'
labels: []
dependencies: []
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Решение владельца 23.11.2026 (вариант 3 из итога DF-14, дословно): «У нас всё, нет больше разделения на флеш и не флеш, вижн перенесли в 5.4. Надо всё переводить.» Предыстория — DF-14 и doc-3 «Чтение изображений в средах»: слепота glm-5.3 (бой 04.10.2026, rk_bot) закрыта упором в трёх местах, zcode уже переведён на чтение картинкой моделью сессии. Осталось: исполнители и разведка ztui на GLM-5.3-Flash; Claude Code через scripts/glm.sh на glm-5.3 с hooks/glm-blind.py и scripts/see.sh; opencode на zai-glm/glm-5.3 с внешними глазами в hosts/opencode/plugins/derflow-hooks.js и плагином vision-probe.js. Ловушки: внешние глаза opencode срабатывают на любую картинку промпта независимо от модели и при переводе подменят зрение 5.4 транскрипцией flash; glm-blind.py завязан на метку DERFLOW_HOST=glm, а не на модель; install.sh не подчищает симлинки удалённых файлов в живых каталогах и не видит их в --check; ~/.config/opencode/opencode.json содержит ключ провайдера — править точечно и не печатать ключ; glm-5.3 остаётся выбираемым в /model ztui.
<!-- SECTION:DESCRIPTION:END -->
