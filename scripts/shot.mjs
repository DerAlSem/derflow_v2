#!/usr/bin/env node
// shot — снимок страницы headless-Chromium'ом. Путь проверки рендера ПО УМОЛЧАНИЮ:
// в Vivaldi владельца (claude-in-chrome) сессии не лезут, кроме боевой админки
// под его живой учёткой и прямого «посмотри у меня».
//
//   node ~/.claude/scripts/shot.mjs <url> <out.png> [опции]
//     --click "<текст>"   кликнуть кнопку/ссылку по видимому тексту (можно повторять)
//     --wait "<css>"      дождаться селектора перед снимком
//     --full              вся страница, а не только вьюпорт
//     --size 1280x800     размер вьюпорта (по умолчанию 1280x800)
//     --mobile            телефонный вьюпорт 390x844, плотность 2, touch
//     --auth <имя|файл>   войти сохранённой сессией (Playwright storageState)
//     --timeout <мс>      предел на каждый шаг (по умолчанию 15000)
//
//   node ~/.claude/scripts/shot.mjs --save-auth <имя|файл> <url>
//     открывает ОКНО Chromium (не Vivaldi); человек логинится и закрывает окно —
//     cookie и localStorage ложатся в файл. Голое имя = tools/shot/auth/<имя>.json:
//     каталог вне git, файл 0600. Сессия — секрет: в коммит и в проект не класть.
//
// Playwright и браузер стоят вне git, в ~/.claude/tools/shot/ (каталог игнорирует
// белый список .gitignore). Нет установки — скрипт печатает, как поставить.
// Весь прогон ограничен сторожем: зависнуть молча он не может.

import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { chmodSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const TOOL_DIR = join(homedir(), '.claude/tools/shot');
const AUTH_DIR = join(TOOL_DIR, 'auth');

function die(msg, code = 1) {
  process.stderr.write(`shot: ${msg}\n`);
  process.exit(code);
}

function parseArgs(argv) {
  const opts = { clicks: [], wait: null, full: false, width: 1280, height: 800, timeout: 15000,
                 mobile: false, auth: null, saveAuth: null };
  const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const val = () => (i + 1 < argv.length ? argv[++i] : die(`${a} требует значения`, 2));
    if (a === '--click') opts.clicks.push(val());
    else if (a === '--wait') opts.wait = val();
    else if (a === '--full') opts.full = true;
    else if (a === '--mobile') opts.mobile = true;
    else if (a === '--auth') opts.auth = authPath(val());
    else if (a === '--save-auth') opts.saveAuth = authPath(val());
    else if (a === '--size') {
      const m = /^(\d+)x(\d+)$/.exec(val());
      if (!m) die('--size ждёт ШxВ, например 390x844', 2);
      opts.width = +m[1];
      opts.height = +m[2];
    } else if (a === '--timeout') opts.timeout = +val() || die('--timeout ждёт число мс', 2);
    else if (a.startsWith('--')) die(`неизвестная опция ${a}`, 2);
    else pos.push(a);
  }
  if (opts.saveAuth) {
    if (pos.length !== 1) die('использование: shot.mjs --save-auth <имя|файл> <url>', 2);
    opts.url = pos[0];
    return opts;
  }
  if (pos.length !== 2) die('использование: shot.mjs <url> <out.png> [--click текст] [--wait css] [--full] ' +
                            '[--size ШxВ] [--mobile] [--auth имя] [--timeout мс]', 2);
  [opts.url, opts.out] = pos;
  if (opts.auth && !existsSync(opts.auth)) die(`нет сохранённой сессии ${opts.auth} — сперва --save-auth`, 2);
  return opts;
}

// Голое имя без пути и расширения — файл в AUTH_DIR; иначе путь как есть.
function authPath(name) {
  return /[\/]|\.json$/.test(name) ? resolve(name) : join(AUTH_DIR, `${name}.json`);
}

function contextOptions(opts) {
  const o = opts.mobile
    ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }
    : { viewport: { width: opts.width, height: opts.height } };
  if (opts.auth) o.storageState = opts.auth;
  return o;
}

// Окно для входа: без сторожа (темп задаёт человек), состояние пишется каждые 2 с
// и при закрытии вкладки — окно, закрытое крестиком, не теряет вход.
async function saveAuth(chromium, opts) {
  mkdirSync(dirname(opts.saveAuth), { recursive: true });
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();
  const save = async () => {
    await context.storageState({ path: opts.saveAuth });
    chmodSync(opts.saveAuth, 0o600);
  };
  await page.goto(opts.url).catch(e => process.stderr.write(`shot: ${String(e.message).split('\n')[0]}\n`));
  process.stdout.write(`войди в открывшемся окне и закрой его — сессия ляжет в ${opts.saveAuth}\n`);
  const tick = setInterval(() => save().catch(() => {}), 2000);
  await new Promise(r => { page.on('close', r); browser.on('disconnected', r); });
  clearInterval(tick);
  await save().catch(() => {});
  await browser.close().catch(() => {});
  process.stdout.write(`${opts.saveAuth}  сохранено\n`);
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
if (opts.saveAuth) {
  await saveAuth(chromium, opts);
  process.exit(0);
}

// Сторож на весь прогон: шагов не больше, чем кликов + 3, каждый под своим таймаутом.
const budget = opts.timeout * (opts.clicks.length + 3) + 5000;
const guard = setTimeout(() => die(`общий предел ${budget} мс исчерпан — прогон прерван`), budget);
guard.unref();

let browser;
let step = 'запуск браузера';
try {
  browser = await chromium.launch({ timeout: opts.timeout });
  const page = await browser.newPage(contextOptions(opts));
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
