#!/usr/bin/env python3
"""tariff-meter — строкка тарифа и квоты для инъекции в контекст (UserPromptSubmit).

Пик: пн–пт 14:00–18:00 UTC+8 (кредиты ×1); всё остальное, включая выходные, — ×0.5.
Квота: GET api.z.ai/api/monitor/usage/quota/limit ключом плана (из opencode.json,
права 600), кэш 5 минут в /tmp. Любая ошибка — тишина: хук не должен шуметь.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

CACHE = "/tmp/ztui-tariff-cache.json"
TTL = 300
OPENCODE = os.path.expanduser("~/.config/opencode/opencode.json")
UTC8 = timezone(timedelta(hours=8))


def tariff_line() -> str:
    now = datetime.now(UTC8)
    peak = now.weekday() < 5 and 14 <= now.hour < 18
    if peak:
        return "ПИК ×1.0 (до 18:00 UTC+8)"
    return "ОФФ-ПИК ×0.5 (пик пн–пт 14–18 UTC+8)"


def quota_lines() -> list:
    try:
        cached = json.load(open(CACHE))
        if cached.get("at", 0) > datetime.now().timestamp() - TTL:
            return cached["lines"]
    except Exception:
        pass
    key = json.load(open(OPENCODE))["provider"]["zai-glm"]["options"]["apiKey"]
    req = urllib.request.Request(
        "https://api.z.ai/api/monitor/usage/quota/limit",
        headers={"Authorization": key, "Accept-Language": "en-US,en"},
    )
    with urllib.request.urlopen(req, timeout=6) as r:
        data = json.load(r).get("data") or {}
    lines = []
    label = {("3", "5"): "5ч", ("6", "1"): "нед"}.get
    for lim in data.get("limits") or []:
        name = label((str(lim.get("unit")), str(lim.get("number")))) or f"окно{lim.get('number')}×u{lim.get('unit')}"
        pct = lim.get("percentage")
        reset = lim.get("nextResetTime")
        when = (
            datetime.fromtimestamp(reset / 1000).strftime("%H:%M")
            if reset
            else "?"
        )
        lines.append(f"{name} {pct}% (сброс {when})")
    payload = {"at": datetime.now().timestamp(), "lines": lines}
    try:
        json.dump(payload, open(CACHE, "w"))
    except Exception:
        pass
    return lines


def main() -> None:
    parts = [tariff_line()]
    try:
        parts += quota_lines()
    except Exception:
        pass
    # Контракт ZCode: plain stdout движок хуков молча выбрасывает — в контекст
    # идёт только JSON с additionalContext (замер 09.11.2026, исходники
    # ~/dev/ZCode packages/core/src/hooks/configured-runner-callback.ts).
    line = "[ТАРИФ: " + " · ".join(parts) + "]"
    print(json.dumps({"additionalContext": line}, ensure_ascii=False))


if __name__ == "__main__":
    main()
