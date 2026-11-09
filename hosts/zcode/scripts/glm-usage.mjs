#!/usr/bin/env node
// Квота GLM Coding Plan (Z.AI) — те же эндпоинты, что у официального плагина
// glm-plan-usage (github.com/zai-org/zai-coding-plugins), ключ берётся из конфига
// опенкода. Ноль зависимостей. Запуск: node ~/.zcode/scripts/glm-usage.mjs
import https from "node:https";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// unit/number — шкала окна квоты: замер 02.10.2026 — unit 3 при number 5 =
// 5-часовое окно, unit 6 при number 1 = неделя (сброс 8 окт = 1 окт + 7 дней,
// панель ZCode называет её «Weekly»); прочие значения печатаем как есть.
const WINDOW_LABEL = { "3:5": "5h", "6:1": "Weekly" };
const MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

const cfg = JSON.parse(readFileSync(join(homedir(), ".config/opencode/opencode.json"), "utf-8"));
const key = cfg.provider["zai-glm"]?.options?.apiKey;
if (!key) {
  console.error("нет ключа zai-glm в ~/.config/opencode/opencode.json");
  process.exit(1);
}

const get = (path) =>
  new Promise((resolve, reject) => {
    const req = https.request(
      { hostname: "api.z.ai", path, method: "GET", headers: { Authorization: key } },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () =>
          res.statusCode === 200 ? resolve(JSON.parse(data)) : reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0, 200)}`)),
        );
      },
    );
    req.setTimeout(8000, () => req.destroy(new Error("timeout")));
    req.on("error", reject);
    req.end();
  });

const pad = (n) => String(n).padStart(2, "0");
const relTime = (ms) => {
  let min = Math.max(0, Math.round((Number(ms) - Date.now()) / 60000));
  const d = Math.floor(min / 1440); min -= d * 1440;
  const h = Math.floor(min / 60); min -= h * 60;
  return `${d ? `${d}d ` : ""}${h}h${pad(min)}m`;
};

// api.z.ai отвечает неровно (часть IP недоступна из РФ) — 4 попытки: DNS каждый
// раз может дать другой адрес; стектрейс пользователю не нужен.
let data;
let lastErr;
for (let i = 0; i < 4; i++) {
  try {
    data = (await get("/api/monitor/usage/quota/limit")).data;
    break;
  } catch (e) {
    lastErr = e;
    await new Promise((r) => setTimeout(r, 700));
  }
}
if (!data) {
  console.error(`api.z.ai недоступен (${lastErr?.message ?? "нет ответа"}) — попробуй ещё раз`);
  process.exit(1);
}
const now = new Date();
console.log("GLM Quota:");
for (const l of data?.limits ?? []) {
  const label = WINDOW_LABEL[`${l.unit}:${l.number}`] ?? `window(unit=${l.unit}×${l.number})`;
  // Окно без расхода только что сбросилось: nextResetTime пуст, пока не начнётся.
  const resetMs = Number(l.nextResetTime);
  let resetInfo = "window not started";
  if (resetMs > 0) {
    const reset = new Date(resetMs);
    const sameDay = reset.toDateString() === now.toDateString();
    const at = sameDay
      ? `at ${pad(reset.getHours())}:${pad(reset.getMinutes())}`
      : `on ${reset.getDate()} ${MONTHS[reset.getMonth()]} ${pad(reset.getHours())}:${pad(reset.getMinutes())}`;
    resetInfo = `${relTime(resetMs)} till reset ${at}`;
  }
  console.log(`  ${label} - ${l.percentage}% (${l.currentValue}/${l.usage}, ${resetInfo})`);
}
