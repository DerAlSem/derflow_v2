#!/usr/bin/env node
// shot — снимок страницы headless-Chromium'ом, когда claude-in-chrome не снимает
// (Page.captureScreenshot в Vivaldi висит до таймаута, JS при этом работает).
//
//   node ~/.claude/scripts/shot.mjs <url> <out.png> [опции]
//     --click "<текст>"   кликнуть кнопку/ссылку по видимому тексту (можно повторять)
//     --wait "<css>"      дождаться селектора перед снимком
//     --full              вся страница, а не только вьюпорт
//     --size 1280x800     размер вьюпорта (по умолчанию 1280x800)
//     --timeout <мс>      предел на каждый шаг (по умолчанию 15000)
//
// Playwright и браузер стоят вне git, в ~/.claude/tools/shot/ (каталог игнорирует
// белый список .gitignore). Нет установки — скрипт печатает, как поставить.
// Весь прогон ограничен сторожем: зависнуть молча он не может.

import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { join } from 'node:path';

const TOOL_DIR = join(homedir(), '.claude/tools/shot');

function die(msg, code = 1) {
  process.stderr.write(`shot: ${msg}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const opts = { clicks: [], wait: null, full: false, width: 1280, height: 800, timeout: 15000 };
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const val = () => (i + 1 < argv.length ? argv[++i] : die(`${a} требует значения`, 2));
    if (a === '--click') opts.clicks.push(val());
    else if (a === '--wait') opts.wait = val();
    else if (a === '--full') opts.full = true;
    else if (a === '--size') {
      const m = /^(\d+)x(\d+)$/.exec(val());
      if (!m) die('--size ждёт ШxВ, например 390x844', 2);
      opts.width = +m[1];
      opts.height = +m[2];
    } else if (a === '--timeout') opts.timeout = +val() || die('--timeout ждёт число мс', 2);
    else if (a.startsWith('--')) die(`неизвестная опция ${a}`, 2);
    else pos.push(a);
  }
  if (pos.length !== 2) die('использование: shot.mjs <url> <out.png> [--click текст] [--wait css] [--full] [--size ШxВ] [--timeout мс]', 2);
  [opts.url, opts.out] = pos;
  return opts;
}

function loadPlaywright() {
  try {
    return createRequire(join(TOOL_DIR, 'package.json'))('playwright');
  } catch {
    die(`playwright не найден в ${TOOL_DIR}. Поставить:\n` +
        `  cd ${TOOL_DIR} && npm install playwright && npx playwright install chromium-headless-shell`);
  }
}

const opts = parseArgs(process.argv.slice(2));
const { chromium } = loadPlaywright();

// Сторож на весь прогон: шагов не больше, чем кликов + 3, каждый под своим таймаутом.
const budget = opts.timeout * (opts.clicks.length + 3) + 5000;
const guard = setTimeout(() => die(`общий предел ${budget} мс исчерпан — прогон прерван`), budget);
guard.unref();

let browser;
let step = 'запуск браузера';
try {
  browser = await chromium.launch({ timeout: opts.timeout });
  const page = await browser.newPage({ viewport: { width: opts.width, height: opts.height } });
  page.setDefaultTimeout(opts.timeout);

  step = `загрузка ${opts.url}`;
  await page.goto(opts.url, { waitUntil: 'load', timeout: opts.timeout });

  for (const text of opts.clicks) {
    step = `клик «${text}»`;
    // Сначала роль кнопки/ссылки с таким именем, иначе любой видимый элемент с текстом.
    const byRole = page.getByRole('button', { name: text }).or(page.getByRole('link', { name: text }));
    const target = (await byRole.count()) ? byRole.first() : page.getByText(text, { exact: false }).first();
    await target.click({ timeout: opts.timeout });
    await page.waitForLoadState('load', { timeout: opts.timeout }).catch(() => {});
  }

  if (opts.wait) {
    step = `ожидание селектора ${opts.wait}`;
    await page.waitForSelector(opts.wait, { state: 'visible', timeout: opts.timeout });
  }

  // Короткая пауза на сетевое затишье; не дождались — снимаем как есть.
  await page.waitForLoadState('networkidle', { timeout: Math.min(opts.timeout, 3000) }).catch(() => {});

  step = `снимок в ${opts.out}`;
  await page.screenshot({ path: opts.out, fullPage: opts.full, timeout: opts.timeout });
  process.stdout.write(`${opts.out}  (${page.url()})\n`);
} catch (e) {
  const first = String(e?.message ?? e).split('\n')[0];
  await browser?.close().catch(() => {});
  die(`упал на шаге «${step}»: ${first}`);
}
await browser.close();
clearTimeout(guard);
