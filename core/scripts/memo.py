#!/usr/bin/env python3
"""memo — вердикт гейта принадлежит ДЕРЕВУ, а не сессии.

    memo.py check [--config PATH]      # зелёный? кэш или прогон
    memo.py list [--all]               # что лежит в кэше
    memo.py forget --current|--all|<tree_sha>

Задача: две сессии на одном стволе гоняют один и тот же гейт по разу каждая, на
неизменившемся коде. Общего состояния у них нет, потому что вердикт привязан к
НАМЕРЕНИЮ сессии, а не к состоянию дерева. Здесь он привязан к дереву.

Ключ — (tree_sha, gate_version_external). Текста команд гейта в ключе НЕТ
намеренно: `deploy.json` лежит в дереве и закоммичен, значит правка команд
меняет tree_sha сама. Если конфиг не отслеживается — кэш выключается, потому что
эта опора исчезает (см. `cacheable()`).

Путь конфига (`--config`) в ключе тоже нет: два отслеживаемых конфига с разными
`gate_pure` на одном дереве целятся в один и тот же файл вердикта. Опору
«правка команд двигает tree_sha» это снимает, поэтому `read_verdict` сверяет
записанные `commands` с тем, что собираются гнать сейчас (см. её докстринг).

Кэшируется ТОЛЬКО pass. Провал — событие, а не знание о дереве: разовый
`Permission denied` иначе заблокировал бы sha до правки байта.

Коды: 0 зелёный · 1 красный · 2 конфигурация либо положение.
"""

import argparse
import hashlib
import json
import os
import pathlib
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

# MEMO_HOME существует ради стенда укусов: без подмены дома укусы писали бы в
# живой ~/.claude/gate-verdicts и не воспроизводились бы дважды подряд.
HOME = pathlib.Path(os.environ.get("MEMO_HOME") or (pathlib.Path.home() / ".claude"))
VERDICTS = HOME / "gate-verdicts"
CONFIG_NAME = "deploy.json"


def die(code, msg):
    print(f"memo: {msg}", file=sys.stderr)
    sys.exit(code)


def git(*args, cwd=None):
    # Отсутствие самого git — не «git ответил ошибкой», а «спросить некого»:
    # subprocess бросает FileNotFoundError ДО всякого кода возврата. Без этой
    # ветки инструмент, обещающий коды 0/1/2, отдавал трейсбек.
    try:
        p = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError) as e:
        die(2, f"git не запускается — {e}. Без git нет ни репозитория, ни дерева.")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


@dataclass
class Ctx:
    toplevel: pathlib.Path
    common: pathlib.Path
    repo_id: str
    tree_sha: str
    dirty: list = field(default_factory=list)


def context(cwd=None):
    """Положение: какой репозиторий, какое дерево, грязно ли."""
    cwd = pathlib.Path(cwd) if cwd else pathlib.Path.cwd()
    rc, top, err = git("rev-parse", "--show-toplevel", cwd=cwd)
    if rc != 0:
        die(2, f"не репозиторий git: {cwd}")
    # --path-format=absolute обязателен: без него git отдаёт «.git» из корня,
    # «../.git» из подкаталога и абсолютный путь из ворктри. На сравнении этих
    # строк главный сценарий (два ворктри одного репозитория) развалился бы молча.
    rc, common, err = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    if rc != 0:
        die(2, f"git не отдал --git-common-dir: {err}")
    common = pathlib.Path(common).resolve()
    rc, tree, err = git("rev-parse", "HEAD^{tree}", cwd=cwd)
    if rc != 0:
        die(2, "в репозитории нет коммитов — дерева нет, вердикту не к чему привязаться")
    rc, porc, err = git("status", "--porcelain", "--untracked-files=no", cwd=cwd)
    if rc != 0:
        die(2, f"git status не отдал результат: {err}")
    # --untracked-files=no — то же определение грязи, что у deploy.sh:127.
    # Компромисс назван вслух: untracked-файл с кодом вердиктом не покрыт, и
    # deploy.sh его тоже не увезёт. Без флага кэш не сработал бы ни разу: в
    # рабочем ворктри почти всегда лежит черновик.
    main_dir = common.parent if common.name == ".git" else common
    slug = "".join(c if (c.isalnum() or c in "._-") else "-" for c in main_dir.name)[:32]
    repo_id = f"{slug}-{hashlib.sha256(str(common).encode()).hexdigest()[:8]}"
    return Ctx(toplevel=pathlib.Path(top), common=common, repo_id=repo_id,
               tree_sha=tree, dirty=[ln for ln in porc.splitlines() if ln.strip()])


def load_config(ctx, explicit=None):
    """Что гнать и что входит в ключ. Ошибки конфига — код 2, не трейсбек."""
    path = pathlib.Path(explicit).expanduser() if explicit else ctx.toplevel / CONFIG_NAME
    if not path.is_file():
        die(2, f"нет {path} — memo не знает, что гнать")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        # ValueError, а не json.JSONDecodeError: битая кодировка (например,
        # деплой.json сохранён cp1251-редактором) даёт UnicodeDecodeError ещё на
        # read_text, ДО разбора JSON — он не подкласс JSONDecodeError. Оба —
        # подклассы ValueError (см. read_verdict про то же самое).
        die(2, f"{path}: не JSON — {e}")
    except OSError as e:
        die(2, f"{path}: не читается — {e}")
    if not isinstance(cfg, dict):
        die(2, f"{path}: не JSON-объект")
    gate = cfg.get("gate_pure")
    if not isinstance(gate, list) or not gate or not all(isinstance(c, str) for c in gate):
        die(2, f"{path}: gate_pure должен быть непустым списком строк")
    ext = cfg.get("gate_version_external", [])
    if not isinstance(ext, list) or not all(isinstance(p, str) for p in ext):
        die(2, f"{path}: gate_version_external должен быть списком путей")
    # Прочие поля (targets, gate_env, gate_post, allow_skips) принадлежат 1b-3 и
    # здесь не читаются. Один файл на три поставки: ранняя не спотыкается о поздние.
    return path, gate, ext


def gate_version(ctx, ext):
    """Ключ по тому, чего дерево НЕ видит. Текста команд здесь нет — он в дереве."""
    parts = {}
    for raw in sorted(ext):
        p = pathlib.Path(raw).expanduser()
        if not p.is_absolute():
            p = ctx.toplevel / p
        try:
            parts[raw] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError as e:
            die(2, f"gate_version_external: {raw} не читается — {e}")
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12], parts


def config_tracked(ctx, path):
    """Отслеживается ли конфиг git. Не отслеживается — команды гейта деревом не покрыты."""
    try:
        rel = path.resolve().relative_to(ctx.toplevel.resolve())
    except ValueError:
        return False
    rc, _, _ = git("ls-files", "--error-unmatch", "--", str(rel), cwd=ctx.toplevel)
    return rc == 0


def cacheable(ctx, cfgpath):
    """Можно ли доверять кэшу на этом дереве — и если нет, то почему словами.

    Обе причины ведут к одному: то, что гоняется, не совпадает с тем, что описывает
    ключ. Грязное дерево — HEAD^{tree} описывает НЕ рабочую копию. Неотслеживаемый
    конфиг — команды гейта не покрыты tree_sha (решение Р3 плана), и подмена
    команд прошла бы мимо и грязи, и ключа.
    """
    if ctx.dirty:
        return False, f"дерево грязное, правлено отслеживаемых файлов: {len(ctx.dirty)}"
    if not config_tracked(ctx, cfgpath):
        return False, f"{cfgpath.name} не отслеживается git — команды гейта деревом не покрыты"
    return True, None


def run_gate(ctx, gate):
    """Гоняем команды по очереди в корне репозитория. Первый ненулевой — конец.

    БЕЗ ШЕЛЛА и БЕЗ КОНВЕЙЕРА, и это не гигиена, а требование спеки, исполненное
    структурно: `| tail` глотает код возврата pytest (feedback_pipe_swallows_pytest_rc).
    Без shell=True конвейер невозможен в принципе. Цена: перенаправления в
    gate_pure запрещены — команде, которой они нужны, место в скрипте в дереве.

    stdout/stderr наследуются, а не перехватываются: гейт идёт минуты, и человек
    обязан видеть его вывод по мере появления.

    Все команды разбираются shlex ДО запуска первой: если разбор ломается на
    ВТОРОЙ команде, первая до этого момента уже отработала бы свои минуты, а
    гейт всё равно закончился бы трейсбеком — минуты потрачены впустую на
    результат, который не запишется. Разбор — код 2 с именем команды, а не
    ValueError наверх.
    """
    parsed = []
    for cmd in gate:
        try:
            argv = shlex.split(cmd)
        except ValueError as e:
            die(2, f"gate_pure: «{cmd}» не разобралась — {e}")
        if not argv:
            die(2, f"пустая команда в gate_pure: {cmd!r}")
        parsed.append((cmd, argv))

    started = time.monotonic()
    for cmd, argv in parsed:
        print(f"→ {cmd}", flush=True)
        try:
            rc = subprocess.run(argv, cwd=ctx.toplevel).returncode
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"гейт красный: «{cmd}» не запустилась — {e}")
            return False, round(time.monotonic() - started, 1)
        if rc != 0:
            print(f"гейт красный: «{cmd}» вышла кодом {rc}. Вердикт НЕ записан.")
            return False, round(time.monotonic() - started, 1)
    # Пара, не тройка: упавшую команду печатает сам run_gate строкой выше, и
    # третий элемент никто никогда не читал.
    return True, round(time.monotonic() - started, 1)


def session_id():
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or f"pid:{os.getpid()}"


def env_fingerprint():
    """ДИАГНОСТИКА, а не ключ (решение Р5 плана).

    Вердикт по дереву переживает `pip install`. Отпечаток венва в ключе обесценивал
    бы кэш при установке любого постороннего инструмента, а ловил бы только редкий
    сценарий «пакет снесли, дерево не менялось». Устаревший венв ломается в
    безопасную сторону: гейт краснеет, красное не кэшируется. Поэтому отпечаток
    ЗАПИСЫВАЕТСЯ и показывается человеком в `memo list`, но решений по нему не
    принимается.
    """
    return {"python": sys.executable,
            "python_version": ".".join(str(x) for x in sys.version_info[:3])}


def verdict_path(ctx, gv):
    return VERDICTS / ctx.repo_id / f"{ctx.tree_sha}.{gv}.json"


def read_verdict(path, commands):
    """Вердикт либо None. Битый файл — это отсутствие вердикта, а не авария.

    `ValueError`, а не `json.JSONDecodeError`: испорченные байты дают
    `UnicodeDecodeError` ещё на `read_text`, ДО разбора JSON, и он не подкласс
    ни `OSError`, ни `JSONDecodeError`. Оба — подклассы `ValueError`, и ловить
    надо его: иначе кэш, который обязан молча отсутствовать, роняет инструмент.

    `commands` — список команд, которые собираются гнать СЕЙЧАС; докстринг
    модуля обещает, что правка gate_pure сама двигает tree_sha, потому что
    deploy.json лежит в дереве и закоммичен. Это верно ТОЛЬКО для
    фиксированного пути конфига. Флаг `--config` эту опору снимает: путь
    конфига в ключ (tree_sha, gate_version_external) не входит, и два
    отслеживаемых конфига с разными gate_pure на одном дереве целятся в ОДИН
    файл вердикта. Без сверки записанных `commands` второй вызов брал бы
    вердикт первого и не гонял бы свой гейт вообще — ложная зелень. Ключ
    трогать не надо: содержимое команд и так покрыто tree_sha при фиксированном
    пути, дыра была в идентичности ФАЙЛА, а не в составе ключа, и сверка
    `commands` закрывает её точнее, чем правка ключа.
    """
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("result") != "pass":
        return None
    if d.get("host") != socket.gethostname():
        print(f"вердикт снят на другом хосте ({d.get('host')}) — не беру: "
              f"инвариант 2, зависящее от среды не делится между машинами")
        return None
    if d.get("commands") != list(commands):
        print(f"вердикт записан для других команд ({d.get('commands')!r}) — "
              f"не беру: сейчас гонятся {list(commands)!r}")
        return None
    return d


def write_verdict(path, payload):
    """tmp + os.replace: файл вердикта либо целый, либо его нет.

    Писателей на один файл может быть НЕСКОЛЬКО: два ворктри на одном tree_sha
    и одном gv целятся буквально в одно имя файла двумя процессами. Безопасность
    даёт не единственность писателя (её тут нет), а атомарность подмены —
    os.replace делает готовый tmp видимым файлом одним системным вызовом, и
    любой конкурент видит либо старую версию, либо новую целиком, никогда рвань.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp-{os.getpid()}"
    # finally, а не «и так заменится»: любой отказ между созданием tmp и
    # os.replace (нет места, на месте вердикта каталог, права) оставлял файл
    # .tmp-<pid> навсегда — никто их не подметал. После удачной подмены tmp уже
    # не существует, поэтому missing_ok.
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def cmd_check(a):
    ctx = context()
    cfgpath, gate, ext = load_config(ctx, a.config)
    gv, extparts = gate_version(ctx, ext)
    vp = verdict_path(ctx, gv)

    can_cache, why = cacheable(ctx, cfgpath)
    if can_cache:
        v = read_verdict(vp, gate)
        if v:
            # Интерпретатор печатается ЗДЕСЬ, а не только в `list`: решение Р5
            # оставило отпечаток диагностикой, но диагностика, которой нет в
            # точке принятия решения, не работает. В ключ он по-прежнему не
            # входит — это строка для человека, а не условие.
            env = v.get("env") or {}
            pv = env.get("python_version", "?")
            cur = ".".join(str(x) for x in sys.version_info[:3])
            print(f"гейт пройден: дерево {ctx.tree_sha[:12]} · gv {gv} · "
                  f"{v.get('recorded_at', '?')} · python {pv}"
                  f"{'' if pv == cur else f' (сейчас {cur})'} · "
                  f"сессия {v.get('session', '?')}")
            return 0
    else:
        print(f"кэш выключен: {why}")

    ok, took = run_gate(ctx, gate)
    if not ok:
        return 1

    if not can_cache:
        print(f"гейт зелёный за {took} с. Вердикт НЕ записан: {why}")
        return 0

    try:
        write_verdict(vp, {
            "tree_sha": ctx.tree_sha,
            "gate_version": gv,
            "repo_id": ctx.repo_id,
            "result": "pass",
            "recorded_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "host": socket.gethostname(),
            "session": session_id(),
            # `worktree` и `external` кодом не читаются намеренно: это улики
            # для человека, открывшего json руками, — из какого дерева снят
            # вердикт и какие внешние входы вошли в ключ. `duration_s` читает
            # `memo list`: по нему видно, что именно экономит кэш.
            "worktree": str(ctx.toplevel),
            "duration_s": took,
            "commands": list(gate),
            "external": extparts,
            "env": env_fingerprint(),
        })
    except OSError as e:
        # Отказ ХРАНИЛИЩА (например, chmod 500 на gate-verdicts) не имеет права
        # выглядеть красным гейтом: гейт был зелёным, просто некуда было это
        # записать. Формулировка — та же, что уже используется для выключенного
        # кэша чуть выше: «гейт зелёный, вердикт НЕ записан: <причина>», код 0.
        print(f"гейт зелёный за {took} с. Вердикт НЕ записан: {e}")
        return 0
    print(f"гейт зелёный за {took} с. Вердикт записан: {vp}")
    return 0


def _load_rows(dirs):
    rows = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                v = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # ValueError — та же правка и по той же причине, что в load_config
                # и read_verdict: битый кэш обязан молча отсутствовать в `list`,
                # а не ронять инструмент трейсбеком именно тогда, когда кэш
                # испорчен и человек пришёл его разбирать.
                continue
            if isinstance(v, dict):
                rows.append(v)
    return rows


def cmd_list(a):
    ctx = context()
    print(f"репозиторий: {ctx.repo_id}   ({ctx.common})")
    print(f"дерево HEAD: {ctx.tree_sha}")
    print(f"грязное:     {'да, файлов ' + str(len(ctx.dirty)) if ctx.dirty else 'нет'}")
    # list читает конфиг МЯГКО: смотреть кэш надо и в репозитории без конфига,
    # иначе инструмент «посмотреть и сбросить» отказывает ровно там, где нужен.
    # Отказы ловятся ПООТДЕЛЬНОСТИ. Один широкий except SystemExit глотал и
    # die про нечитаемый внешний вход, и печатал «конфига нет» — диагноз, прямо
    # противоречащий тому, что die уже написал в stderr. `list` обязан
    # оставаться мягким (это инструмент «посмотреть и сбросить», он нужен
    # именно когда сломано), но мягкость не значит право врать о причине.
    try:
        cfgpath, gate, ext = load_config(ctx, a.config)
    except SystemExit:
        print("ключ gv:     — конфига нет либо он невалиден")
    else:
        try:
            gv, _ = gate_version(ctx, ext)
        except SystemExit:
            print("ключ gv:     — внешний вход gate_version_external не читается")
        else:
            print(f"ключ gv:     {gv}   ({len(ext)} внешних входов, {len(gate)} команд)")
            can, why = cacheable(ctx, cfgpath)
            if not can:
                print(f"кэш:         выключен — {why}")

    dirs = sorted(VERDICTS.glob("*")) if a.all else [VERDICTS / ctx.repo_id]
    rows = _load_rows(dirs)
    if not rows:
        print("вердиктов нет")
        return 0
    print()
    print(f"  {'дерево':13} {'gv':13} {'снят':20} {'хост':14} {'python':10} {'длит':8} сессия")
    for v in sorted(rows, key=lambda r: r.get("recorded_at", ""), reverse=True):
        mark = "→" if v.get("tree_sha") == ctx.tree_sha else " "
        env = v.get("env", {}) or {}
        print(f"{mark} {v.get('tree_sha', '')[:12]:13} {v.get('gate_version', ''):13} "
              f"{v.get('recorded_at', '')[:19]:20} {str(v.get('host', ''))[:13]:14} "
              f"{str(env.get('python_version', ''))[:9]:10} "
              f"{(str(v['duration_s']) + ' с') if v.get('duration_s') is not None else '—':8} "
              f"{v.get('session', '')}")
    return 0


def cmd_forget(a):
    ctx = context()
    d = VERDICTS / ctx.repo_id
    if a.all:
        targets = sorted(d.glob("*.json"))
    elif a.current:
        targets = sorted(d.glob(f"{ctx.tree_sha}.*.json"))
    else:
        # Длина одна не спасает: '???????' — те же 7 знаков, что и короткий sha,
        # но глоб `*.json` по маске `???????*.json` совпадает с ЛЮБЫМ именем —
        # радиус `--all` без `--all`. Хуже: строка вида '../чужой-репо/' содержит
        # "/", а pathlib.Path.glob честно проходит по "..": `d.glob('../x/*.json')`
        # уводит за пределы каталога ЭТОГО репозитория — снос вердиктов ЧУЖОГО.
        # Проверять надо ШЕСТНАДЦАТИРИЧНОСТЬ префикса, а не длину: sha дерева
        # состоит только из [0-9a-f], и ни "?", ни "/", ни "." туда не попадут
        # случайно. Порог 7 — длина короткого sha у git по умолчанию.
        if len(a.tree_sha) < 7:
            die(2, f"префикс дерева слишком короткий: {a.tree_sha!r}. "
                   f"Нужно хотя бы 7 знаков; снести всё — это явный --all")
        if any(c not in "0123456789abcdef" for c in a.tree_sha):
            die(2, f"префикс дерева должен быть шестнадцатеричным (0-9a-f): "
                   f"{a.tree_sha!r}. Снести всё — это явный --all")
        targets = sorted(d.glob(f"{a.tree_sha}*.json"))
    if not targets:
        print("нечего забывать")
        return 0
    for t in targets:
        try:
            t.unlink()
        except FileNotFoundError:
            # Сестринская сессия успела забыть тот же вердикт между glob и
            # unlink. Это не отказ: файла нет — цель достигнута, и печатать
            # «забыт» о чужой работе тоже незачем.
            continue
        print(f"забыт: {t.name}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="memo", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="что лежит в кэше")
    p_list.add_argument("--config", help=f"путь к {CONFIG_NAME}")
    p_list.add_argument("--all", action="store_true", help="по всем репозиториям")
    p_list.set_defaults(fn=cmd_list)
    p_check = sub.add_parser("check", help="гейт зелёный? кэш или прогон")
    p_check.add_argument("--config", help=f"путь к {CONFIG_NAME}")
    p_check.set_defaults(fn=cmd_check)

    p_forget = sub.add_parser("forget", help="сбросить вердикт")
    g = p_forget.add_mutually_exclusive_group(required=True)
    g.add_argument("--current", action="store_true", help="вердикты текущего дерева")
    g.add_argument("--all", action="store_true", help="все вердикты этого репозитория")
    g.add_argument("tree_sha", nargs="?", help="префикс sha дерева")
    p_forget.set_defaults(fn=cmd_forget)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
