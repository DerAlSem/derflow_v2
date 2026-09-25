#!/usr/bin/env python3
"""Сторож отставшего корня: отцепленный HEAD основного чекаута, который никто не двигает.

Корень держат отцепленным нарочно (ветки заняты ворктри, waiting/MIGRATION.md),
и он молча отстаёт: сессия в корне отвечает по старому коду и не видит
backlog/config.yml. Замер 25.09.2026: gmb_v2 отстал от origin/develop на 1514.

Зовётся хуком SessionStart. Молчит, если: не git, ворктри (не основной чекаут),
HEAD на ветке, отставания нет. Иначе — чистое (tracked) дерево сдвигает вперёд,
грязное или отказ checkout — одна строка 🔴.

База — ref, к которому корень отцепили в последний раз (рефлог «checkout: moving
from X to origin/Y»), иначе origin/HEAD. fetch НЕ зовётся (таймаут хука): сравнение
идёт с тем origin, что уже на диске, и строка называет его возраст.
"""
import json, os, re, subprocess, sys, time

def git(*a, cwd):
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def main():
    cwd = os.getcwd()
    try:
        cwd = json.load(sys.stdin).get("cwd") or cwd
    except Exception:
        pass
    rc, top, _ = git("rev-parse", "--show-toplevel", cwd=cwd)
    if rc:
        return
    _, gd, _ = git("rev-parse", "--absolute-git-dir", cwd=top)
    _, cd, _ = git("rev-parse", "--git-common-dir", cwd=top)
    if os.path.realpath(gd) != os.path.realpath(os.path.join(top, cd)):
        return  # ворктри: его HEAD — чужая работа
    if git("symbolic-ref", "-q", "HEAD", cwd=top)[0] == 0:
        return  # на ветке: отставание ветки — не наша забота

    base = None
    _, log, _ = git("reflog", "-200", "--format=%gs", cwd=top)
    for line in log.splitlines():
        m = re.match(r"checkout: moving from \S+ to (origin/\S+)$", line)
        if m:
            base = m.group(1); break
    if not base:
        rc, ref, _ = git("symbolic-ref", "-q", "--short",
                         "refs/remotes/origin/HEAD", cwd=top)
        base = ref if rc == 0 else None
    if not base or git("rev-parse", "-q", "--verify", base, cwd=top)[0]:
        return

    _, behind, _ = git("rev-list", "--count", f"HEAD..{base}", cwd=top)
    _, ahead, _ = git("rev-list", "--count", f"{base}..HEAD", cwd=top)
    behind, ahead = int(behind or 0), int(ahead or 0)
    if behind == 0:
        return
    fh = os.path.join(gd, "FETCH_HEAD")
    age = (f"fetch {time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(fh)))}"
           if os.path.exists(fh) else "fetch не делался")
    name = os.path.basename(top)
    head = git("rev-parse", "--short", "HEAD", cwd=top)[1]
    red = (f"🔴 корень {name}: отцеплен на {head}, отстаёт от {base} на {behind} "
           f"(база — {age}; сети на старте нет). ")

    if ahead:
        print(red + f"Сдвиг не делаю: на корне {ahead} своих коммитов вне {base}. "
              "Ответы по коду из корня — по старому коду.")
        return
    _, dirty, _ = git("status", "--porcelain", "--untracked-files=no", cwd=top)
    if dirty:
        n = len(dirty.splitlines())
        print(red + f"Сдвиг не делаю: {n} изменённых отслеживаемых файлов. "
              f"Сдвиг вручную: git checkout --detach {base}")
        return
    # checkout 1500 коммитов может не влезть в таймаут хука; отдельная сессия
    # процесса переживёт убийство хука и не оставит index.lock посреди работы
    p = subprocess.Popen(["git", "checkout", "-q", "--detach", base], cwd=top,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    try:
        _, err = p.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        print(f"↻ корень {name}: сдвигаю {head} → {base} (+{behind}), checkout идёт "
              "в фоне; до его конца файлы корня — вперемешку.")
        return
    if p.returncode:
        files = [l.strip() for l in err.splitlines() if l.startswith(("\t", "    "))]
        why = f"мешают неотслеживаемые: {', '.join(files[:4])}" if files else err[:160]
        print(red + f"checkout отказал — {why}.")
        return
    print(f"↻ корень {name}: сдвинут {head} → {base} (+{behind}, база — {age}).")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"🔴 stale-root: сторож упал ({e.__class__.__name__}: {e})")
