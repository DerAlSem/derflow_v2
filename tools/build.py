#!/usr/bin/env python3
"""Сборка входных файлов и агентов сред из core/ + hosts/<среда>/.

    build.py [--out <каталог>]   # по умолчанию пишет в hosts/<среда>/generated/

Входной файл: core/AGENTS.md со слотами
    <!-- slot:<имя> -->
    текст по умолчанию (среда claude)
    <!-- /slot -->
Среда подменяет слот файлом hosts/<среда>/slots/<имя>.md; нет файла — остаётся
текст по умолчанию. Маркеры в сборку не попадают.

Агенты: тело — core/agents/<имя>.md. Среда может подменить шапку (frontmatter)
файлом hosts/<среда>/agents/<имя>.head или положить своего агента целиком —
hosts/<среда>/agents/<имя>.md.

Сборка детерминирована: install.sh --check сравнивает её с тем, что лежит в
generated/ и в живых каталогах, и называет ручную правку дрейфом.
"""
import argparse, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / "core"
HOSTS = {"claude": "CLAUDE.md", "zcode": "AGENTS.md",
         "kimi-code": "AGENTS.md", "kimi-work": "AGENTS.md"}
SLOT = re.compile(r"<!-- slot:(\S+) -->\n(.*?)<!-- /slot -->\n", re.S)


def entry(host):
    text = (CORE / "AGENTS.md").read_text()
    slots = ROOT / "hosts" / host / "slots"
    used = set()

    def fill(m):
        f = slots / f"{m.group(1)}.md"
        if f.is_file():
            used.add(f.name)
            body = f.read_text()
            return body if body.endswith("\n") else body + "\n"
        return m.group(2)

    out = SLOT.sub(fill, text)
    if "<!-- slot:" in out or "<!-- /slot -->" in out:
        sys.exit(f"❌ {host}: незакрытый слот в core/AGENTS.md")
    if slots.is_dir():
        orphan = {p.name for p in slots.glob("*.md")} - used
        if orphan:
            sys.exit(f"❌ {host}: слотов {sorted(orphan)} нет в core/AGENTS.md")
    return out


def split_head(text):
    if not text.startswith("---\n"):
        return "", text
    end = text.index("\n---\n", 4) + 5
    return text[:end], text[end:]


def agents(host, dst):
    dst.mkdir(parents=True, exist_ok=True)
    own = ROOT / "hosts" / host / "agents"
    for src in sorted((CORE / "agents").glob("*.md")):
        text = src.read_text()
        head = own / f"{src.stem}.head"
        if head.is_file():
            h = head.read_text()
            text = (h if h.endswith("\n") else h + "\n") + split_head(text)[1]
        (dst / src.name).write_text(text)
    if own.is_dir():
        for src in sorted(own.glob("*.md")):
            shutil.copyfile(src, dst / src.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()
    for host, name in HOSTS.items():
        base = (a.out / host) if a.out else ROOT / "hosts" / host / "generated"
        base.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(entry(host))
        if host != "claude":  # агенты claude — сам core/agents, без сборки
            if (base / "agents").exists():
                shutil.rmtree(base / "agents")
            agents(host, base / "agents")


if __name__ == "__main__":
    main()
