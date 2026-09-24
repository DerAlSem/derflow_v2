#!/usr/bin/env python3
"""Миграция репозитория с openspec + реестра отложки на Backlog.md.

    bl-migrate.py                         показать план, ничего не писать
    bl-migrate.py --apply                 выполнить
    --waiting DIR          ящик отложки проекта (берётся целиком)
    --global-waiting DIR   общий ящик (~/.claude/waiting): только строки,
                           чей entry содержит --entry ПОДСТРОКА

Что куда:
  openspec/specs/<cap>/spec.md     → doc «<cap>» в backlog/docs/capabilities
  openspec/changes/<id>/ (живые)   → To Do: описание = proposal.md,
                                     заметки = tasks.md, ссылка на каталог
  строка отложки state: waiting    → Backlog: Due = review_by, в описании
                                     «почему не сейчас» и блок пробы ```when
  строка отложки state: done       → пропуск
  хендоффы всех ворктри            → To Do: заголовок = «имя:», заметки =
    (.claude/handoff/*.md и          текст хендоффа, в описании ветка и
     openspec/changes/*/HANDOFF.md)  ворктри — недопиленные сессии

Запускать из корня репозитория после `backlog init`. Каталог openspec/ и
строки отложки не удаляются — это делаешь ты, когда сверишь результат.
Повторный запуск пропускает то, что уже перенесено (по заголовку).
"""
import argparse, json, pathlib, re, subprocess, sys

LABEL = "migrated"


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, errors="replace")


def existing_titles():
    titles = set()
    p = run(["backlog", "task", "list", "--json"])
    if p.returncode == 0:
        titles |= {t["title"] for t in json.loads(p.stdout).get("tasks", [])}
    p = run(["backlog", "doc", "list", "--plain"])
    titles |= set(p.stdout.split("\n")) if p.returncode == 0 else set()
    return titles


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fields, key = {}, None
    for line in m.group(1).splitlines():
        if key and (line.startswith("  ") or not line.strip()):
            fields[key] += line[2:] + "\n"
            continue
        key = None
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v == "|":
            key, fields[k.strip()] = k.strip(), ""
        else:
            fields[k.strip()] = v.strip('"')
    return fields, m.group(2)


def plan_specs(root):
    for spec in sorted((root / "openspec" / "specs").glob("*/spec.md")):
        cap = spec.parent.name
        yield ("doc", cap, spec.read_text(encoding="utf-8"))


def change_is_complete(tasks_text):
    return "- [x]" in tasks_text and "- [ ]" not in tasks_text


def plan_changes(root):
    ch = root / "openspec" / "changes"
    for d in sorted(p for p in ch.glob("*") if p.is_dir() and p.name != "archive"):
        prop, tasks, hand = d / "proposal.md", d / "tasks.md", d / "HANDOFF.md"
        desc = prop.read_text(encoding="utf-8") if prop.exists() else ""
        notes = tasks.read_text(encoding="utf-8") if tasks.exists() else ""
        if hand.exists():
            notes += "\n\n## Хендофф\n\n" + hand.read_text(encoding="utf-8", errors="replace")
        title = d.name
        if change_is_complete(notes):
            title = f"Дозакрыть: {d.name}"   # задачи сделаны, заявка не заархивирована
        yield ("todo", title, desc, notes, str(d.relative_to(root)))


def plan_waiting(dirs, entry):
    for base in dirs:
        for f in sorted(pathlib.Path(base).expanduser().glob("*.md")):
            fields, body = frontmatter(f.read_text(encoding="utf-8"))
            if not fields.get("title") or fields.get("state") != "waiting":
                continue
            if entry and entry not in fields.get("entry", ""):
                continue
            parts = [f"**Почему не сейчас / когда:** {fields.get('ripe_when', '—')}"]
            if fields.get("probe", "none").strip() not in ("none", ""):
                head = [f"host: {fields.get('host', 'local')}"]
                if fields.get("cwd", "none") != "none":
                    head.append(f"cwd: {fields['cwd']}")
                if fields.get("ripe_match", "none") != "none":
                    head.append(f"match: {re.escape(fields['ripe_match'])}")
                parts.append("```when\n" + "\n".join(head) + "\n---\n"
                             + fields["probe"].rstrip() + "\n```")
            parts.append(f"Перенесено из отложки `{f.name}`.\n\n" + body.strip())
            yield ("backlog", fields["title"], "\n\n".join(parts),
                   fields.get("review_by"))


def worktrees():
    out, cur = [], None
    for line in run(["git", "worktree", "list", "--porcelain"]).stdout.splitlines():
        if line.startswith("worktree "):
            cur = pathlib.Path(line[9:])
            out.append(cur)
    return out


def head_field(text, name):
    m = re.search(rf"^{name}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def plan_handoffs(root):
    """Хендоффы, которых нет в текущем дереве.

    `.claude/handoff/*.md` не в git — у каждого ворктри свои; дубли по
    содержимому схлопываются. `openspec/changes/*/HANDOFF.md` в git: копия в
    каждом ворктри одна и та же, поэтому берётся только заявка, которой нет в
    текущем дереве (живёт лишь на своей ветке), и одна на id — самая свежая.
    """
    import hashlib
    here = {p.name for p in (root / "openspec" / "changes").glob("*")} \
        | {p.name.split("-", 3)[-1] for p in (root / "openspec" / "changes" / "archive").glob("*")}
    seen_text, by_change = set(), {}
    out = []
    for wt in worktrees():
        for f in sorted((wt / ".claude" / "handoff").glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            h = hashlib.sha1(text.encode()).hexdigest()
            if h in seen_text:
                continue
            seen_text.add(h)
            out.append((wt, f, text))
        for f in (wt / "openspec" / "changes").glob("*/HANDOFF.md"):
            cid = f.parent.name
            if cid in here:
                continue
            m = f.stat().st_mtime
            if cid not in by_change or m > by_change[cid][0]:
                by_change[cid] = (m, wt, f)
    for _, wt, f in by_change.values():
        out.append((wt, f, f.read_text(encoding="utf-8", errors="replace")))
    for wt, f, text in out:
        branch = head_field(text, "ветка").split()[0:1]
        branch = branch[0] if branch else "?"
        name = head_field(text, "имя") or (f.parent.name if f.name == "HANDOFF.md" else f.stem)
        desc = (f"Сессия остановлена до переезда на docflow.\n\n"
                f"Ветка: `{branch}` · ворктри: `{wt}`\n"
                f"Хендофф: `{f}` (в заметках — полная копия).\n\n"
                f"Продолжать: `bl-lock.sh take` в этом ворктри, дальше "
                f"по заметкам.")
        yield ("handoff", f"Недопилено: {name}", desc, text, str(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--waiting", action="append", default=[])
    ap.add_argument("--global-waiting", action="append", default=[])
    ap.add_argument("--entry", default="")
    a = ap.parse_args()
    root = pathlib.Path(run(["git", "rev-parse", "--show-toplevel"]).stdout.strip() or ".")
    if not (root / "backlog").exists():
        print("нет backlog/ — сначала backlog init", file=sys.stderr)
        return 1
    have = existing_titles()
    items = list(plan_specs(root)) + list(plan_changes(root)) \
        + list(plan_waiting(a.waiting, "")) \
        + list(plan_waiting(a.global_waiting, a.entry or "\0")) \
        + list(plan_handoffs(root))
    n = 0
    for it in items:
        kind, title = it[0], it[1]
        if title in have or any(title in h for h in have if kind == "doc"):
            print(f"· пропуск (уже есть) {kind}: {title}")
            continue
        print(f"+ {kind}: {title}")
        n += 1
        if not a.apply:
            continue
        if kind == "doc":
            p = run(["backlog", "doc", "create", title, "-p", "capabilities",
                     "-t", "specification", "--plain"])
            m = re.search(r"\b(doc-\d+)\b", p.stdout, re.I)
            if not m:
                print(f"  ❌ {p.stdout}{p.stderr}", file=sys.stderr); continue
            run(["backlog", "doc", "update", m.group(1), "--content", it[2]])
        elif kind == "handoff":
            _, _, desc, notes, ref = it
            p = run(["backlog", "task", "create", title, "-s", "To Do",
                     "-l", f"{LABEL},handoff", "-d", desc, "--notes", notes,
                     "--ref", ref, "--plain"])
            if p.returncode:
                print(f"  ❌ {p.stderr}", file=sys.stderr)
        elif kind == "todo":
            _, _, desc, notes, ref = it
            argv = ["backlog", "task", "create", title, "-s", "To Do",
                    "-l", LABEL, "-d", desc or title, "--ref", ref, "--plain"]
            if notes:
                argv += ["--notes", notes]
            p = run(argv)
            if p.returncode:
                print(f"  ❌ {p.stderr}", file=sys.stderr)
        else:
            _, _, desc, due = it
            argv = ["backlog", "task", "create", title, "-s", "Backlog",
                    "-l", LABEL, "-d", desc, "--plain"]
            if due and re.match(r"\d{4}-\d{2}-\d{2}$", due):
                argv += ["--due-date", due]
            p = run(argv)
            if p.returncode:
                print(f"  ❌ {p.stderr}", file=sys.stderr)
    from collections import Counter
    c = Counter(("todo-дозакрыть" if it[0] == "todo" and it[1].startswith("Дозакрыть:") else it[0])
                for it in items if it[1] not in have)
    print("\nпо видам: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
    print(f"{'перенесено' if a.apply else 'к переносу'}: {n}"
          + ("" if a.apply else "  (запусти с --apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
