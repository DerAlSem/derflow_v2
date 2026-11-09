// Обёртка derflow-хуков (живут в ~/.claude/hooks и ~/.claude/scripts, контракт —
// Claude Code settings.json) под OpenCode v2.0.20 promise-plugin API.
//
// Контракт (packages/plugin/src/promise/plugin.ts тега v2.0.20): default-экспорт
// { id, setup: (ctx) => Promise<Cleanup|void> }. Хуки навешиваются доменами:
//   session.hook("prompt")     → внешние глаза: картинки промпта описывает
//                                glm-5.3-flash прямым API, текст дописывается
//                                в промпт (модель сессии не трогается) +
//                                wake-дельта отложки + git-статус в лог;
//   tool.hook("execute.before")→ гейт openspec-critique-gate на bash/task/
//                                agent/skill; throw = Tool.Error, вызов
//                                отклоняется до исполнения;
//   event.subscribe()          → session.idle → openspec-reap-gate (не блокирует).
// Постулаты: setup обязан завершиться (вечный for-await по событиям живёт в
// фоновой задаче, cleanup её гасит); ни один вызов скрипта не имеет права
// уронить или подвесить сессию опенкода.

import { createHash } from "node:crypto"
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"

const PROBE = "/tmp/derflow-plugin-probe.log"
const dbg = (msg) =>
  appendFile(PROBE, `${new Date().toISOString()} ${msg}\n`).catch(() => {})
const HOME = process.env.HOME

// Запуск внешнего скрипта с жёстким таймаутом: ни один хук не висит дольше.
const run = async (script, payload, timeoutMs = 15000) => {
  try {
    const proc = Bun.spawn(["bash", "-c", script], {
      stdin: payload === undefined ? "ignore" : new Response(payload).body,
      stdout: "pipe",
      stderr: "pipe",
    })
    const timer = setTimeout(() => proc.kill(), timeoutMs)
    try {
      // kill() бьёт только bash: дочерний процесс (напр. python) может остаться
      // живым и держать stdout-пайп — чтение тогда не разрешится само. Гонка
      // с грейсом 2 с не даёт хуку висеть дольше бюджета (консультация opus 07.10).
      const out = await Promise.race([
        new Response(proc.stdout).text(),
        new Promise((resolve) => setTimeout(() => resolve(""), timeoutMs + 2000)),
      ])
      const code = await proc.exited
      return { code, out }
    } finally {
      clearTimeout(timer)
    }
  } catch (e) {
    await dbg(`run failed: ${script} — ${e}`)
    return { code: -1, out: "" }
  }
}

// Имена инструментов OpenCode v2.0.20 → канонические клодовские для гейт-скрипта
// (shell — аналог Bash, subagent — Task/Agent; старые имена оставлены на случай
// переименования в будущих версиях).
const GATED_TOOLS = {
  shell: "Bash",
  bash: "Bash",
  subagent: "Task",
  task: "Task",
  agent: "Agent",
  skill: "Skill",
}

// «Сессия ушла в idle» в событиях v2.0.20 — это session.execution.* (session.idle
// из старых версий больше не публикуется).
const IDLE_EVENTS = new Set([
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
])

// Явный opt-out из wake-дельты: строка-маркер в шаблоне команды
// (~/.config/opencode/commands/*.md). Команды с точечным выводом (/glm-usage)
// реестр отложек не озвучивают; сессия при этом не помечается «прокнутой» —
// первый обычный промпт дельту получит.
const NOWAKE = "<!-- derflow:nowake -->"

// Vision-обход, версия 2 (07.10, консультация opus): glm-5.3 текстовая, flash
// из той же семьи мультимодальна. Версия 1 переключала сессию на flash и
// возвращала следующим промптом — бой 07.10 показал: ход с картинкой ЦЕЛИКОМ
// делал flash (включая работу), возврат не наступал, маркер терялся при
// рестарте службы. Теперь внешние глаза: prompt-хук описывает картинку прямым
// API (сестра-канон ручного перегляда — ~/.claude/scripts/see.sh), описание
// дописывается в текст промпта, модель сессии не трогается вовсе. Flash'у уходит
// ТОЛЬКО нейтральная транскрипция — вопрос пользователя не передаётся, иначе
// работу начнёт строить flash.
const VISION_MODEL = "glm-5.3-flash"
const VISION_URL = "https://api.z.ai/api/coding/paas/v4/chat/completions"
const VISION_PROMPT =
  "Перепиши дословно весь текст на изображении, сохраняя строки и столбцы таблиц. " +
  "Затем коротко опиши то, что не текст (схемы, графики, цвета-статусы). " +
  "Ничего не додумывай: нечитаемое помечай [?]."
const VISION_DIR = "/tmp/opencode-vision"
// Дедуп reap-гейта: idle-события глобальные, их получают все инстансы плагина
// (служба держит по инстансу на подключение — 07.10 наблюдалось 8×). Квитанция
// <sid>.<секунда> с O_EXCL атомарна и между процессами: кто первым создал файл,
// тот единственный и обрабатывает idle. Окно в одну секунду для гейта безвредно:
// два РАЗНЫХ конца ходов одной сессии в одну секунду не случаются, а пропущенный
// реап догонит следующий idle — гейт ненасыщающий и не блокирует.
const REAP_DEDUP_DIR = "/tmp/opencode-reap-dedup"
const VISION_BUDGET_MS = 60_000 // на все картинки одного промпта (opus: 45–60 с)
const VISION_REQ_MS = 45_000 // на одну картинку, но не больше остатка бюджета
const VISION_CONCURRENCY = 2 // у кодинг-плана z.ai лимит одновременных запросов
const isImage = (uri) =>
  (uri ?? "").startsWith("data:image") || /\.(png|jpe?g|webp|gif|bmp|tiff?)([?#]|$)/i.test(uri ?? "")
// pdf/видео/аудио flash тоже видит, но не тянем: одна строка в текст промпта.
const isOtherMedia = (uri) =>
  /^data:(video|audio|application\/pdf)/i.test(uri ?? "") ||
  /\.(pdf|mp4|mov|webm|mkv|avi|mp3|wav|m4a|ogg)([?#]|$)/i.test(uri ?? "")

// Ключ z.ai: env, затем опенкод-конфиг (как see.sh). В лог не печатается никогда.
const zaiKey = async () => {
  if (process.env.ZAI_API_KEY) return process.env.ZAI_API_KEY
  try {
    const cfg = JSON.parse(await readFile(`${HOME}/.config/opencode/opencode.json`, "utf8"))
    return cfg?.provider?.["zai-glm"]?.options?.apiKey ?? ""
  } catch {
    return ""
  }
}

// Картинка из промпта → стабильный файл в VISION_DIR (хеш содержимого: повторная
// вставка не плодит копий; мёртвый путь /tmp после перезагрузки виден в заголовке
// описания — see.sh на него отвечает внятно).
const materializeImage = async (uri) => {
  try {
    let bytes, mime
    if (uri.startsWith("data:")) {
      const m = /^data:([^;,]+);base64,(.*)$/s.exec(uri)
      if (!m) return null
      mime = m[1]
      bytes = Buffer.from(m[2], "base64")
    } else {
      const p = uri.startsWith("file:") ? fileURLToPath(uri) : uri
      bytes = await readFile(p)
      const em = /\.(\w{2,5})([?#]|$)/.exec(p.split("/").pop() ?? "")
      const ext = em?.[1]?.toLowerCase()
      mime = ext === "jpg" ? "image/jpeg" : ext ? `image/${ext}` : "image/png"
    }
    const ext = (mime.split("/")[1] ?? "png").replace("jpeg", "jpg")
    const path = `${VISION_DIR}/${createHash("sha256").update(bytes).digest("hex").slice(0, 24)}.${ext}`
    await mkdir(VISION_DIR, { recursive: true })
    await writeFile(path, bytes)
    return { path, mime }
  } catch {
    return null
  }
}

// Одно изображение → блок «заголовок + транскрипция», либо внятный отказ.
// Пустого описания не бывает никогда — иначе 5.3 начнёт выдумывать за flash.
const describeImage = async (img, apiKey, deadline) => {
  const header = `[изображение → текст · ${VISION_MODEL} · ${img.path}]`
  if (!apiKey) return `${header}\n[НЕ распознано: нет ключа z.ai — скажи владельцу, что картинку не видел]`
  try {
    const remaining = deadline - Date.now()
    if (remaining < 5000) throw new Error("общий бюджет распознавания вышел")
    const body = {
      model: VISION_MODEL,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: VISION_PROMPT },
            {
              type: "image_url",
              image_url: {
                url: `data:${img.mime};base64,${(await readFile(img.path)).toString("base64")}`,
              },
            },
          ],
        },
      ],
    }
    const res = await fetch(VISION_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(Math.min(VISION_REQ_MS, remaining)),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const text = (await res.json())?.choices?.[0]?.message?.content?.trim()
    if (!text) throw new Error("пустой ответ flash")
    return `${header}\n${text}`
  } catch (e) {
    return `${header}\n[НЕ распознано: ${String(e?.message ?? e)} — скажи владельцу, что картинку не видел, или прогони see.sh по пути из заголовка]`
  }
}

// Параллельно с потолком: результаты в порядке входа, а не завершения.
const runLimited = async (tasks, cap) => {
  const out = new Array(tasks.length)
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(cap, tasks.length) }, async () => {
      for (let i = next++; i < tasks.length; i = next++) out[i] = await tasks[i]()
    }),
  )
  return out
}

export default {
  id: "derflow-hooks",
  setup: async (ctx) => {
    const directory = ctx.location?.directory ?? process.cwd()
    await dbg(`setup: dir=${directory}`)
    const woken = new Set()
    // кеш распознавания за жизнь службы: та же картинка — тот же блок, без
    // повторного похода во flash
    const visionCache = new Map()
    // /tmp/opencode-vision не растёт вечно: старше 7 дней — в расход
    await run(`find ${VISION_DIR} -type f -mtime +7 -delete 2>/dev/null || true`, undefined, 10000)
    await run(`find ${REAP_DEDUP_DIR} -type f -mtime +1 -delete 2>/dev/null || true`, undefined, 10000)

    const promptReg = await ctx.session.hook("prompt", async (event) => {
      try {
        const sid = event.sessionID ?? "?"
        // Внешние глаза до всего остального: картинка становится текстом ДО хода,
        // модель сессии не переключается вовсе. Отказ глаза не роняет ход —
        // модель видит внятную строку «НЕ распознано».
        try {
          const files = event.prompt?.files ?? []
          if (files.some((f) => isImage(f?.uri) || isOtherMedia(f?.uri))) {
            const apiKey = await zaiKey()
            const deadline = Date.now() + VISION_BUDGET_MS
            await dbg(`vision: распознаю картинку(и) промпта ${sid}`)
            const blocks = []
            const fresh = []
            for (const f of files) {
              if (!isImage(f?.uri)) continue
              const img = await materializeImage(String(f?.uri ?? ""))
              if (!img) {
                blocks.push("[изображение НЕ прочитано: путь/URI недоступен — попроси владельца описать текстом]")
                continue
              }
              const cached = visionCache.get(img.path)
              if (cached) blocks.push(cached)
              else fresh.push(img)
            }
            const described = await runLimited(
              fresh.map((img) => async () => {
                const block = await describeImage(img, apiKey, deadline)
                visionCache.set(img.path, block)
                return block
              }),
              VISION_CONCURRENCY,
            )
            blocks.push(...described)
            for (const f of files) {
              const u = String(f?.uri ?? "")
              if (isImage(u) || !isOtherMedia(u)) continue
              const label = /^data:([^;,]+)/.exec(u)?.[1] ?? u.split("/").pop() ?? "файл"
              if (/pdf/i.test(label)) {
                // текстовый pdf 5.3 читает сам — PDFKit локально, зрение не нужно
                const p = u.startsWith("data:") ? "" : u.startsWith("file:") ? fileURLToPath(u) : u
                blocks.push(
                  `[приложен pdf${p ? ` · ${p}` : ""}: глаза не тянут — вытащи текст сам, ~/.claude/scripts/pdf-text.sh${p ? ` ${p}` : ""}; ответит «скан» или пусто — попроси владельца пересказать]`,
                )
              } else {
                blocks.push(`[приложено нераспознанным (${label}): видео/аудио глаза не тянут — попроси владельца пересказать]`)
              }
            }
            if (blocks.length) {
              event.prompt.text = (event.prompt.text ?? "").concat("\n\n", blocks.join("\n\n"))
              // image-части убираем из промпта: base64 не тащится в историю и в
              // хранилище сеанса. Если ядро мутацию игнорирует — картинку вырежут
              // modalities и context-хук (заглушка ниже), описание уже в тексте.
              const kept = files.filter((f) => !isImage(f?.uri))
              try {
                event.prompt.files = kept
              } catch {}
              await dbg(`vision: ${blocks.length} блок(ов), ${fresh.length} свежих, files осталось ${kept.length}`)
            }
          }
        } catch (e) {
          await dbg(`vision eyes failed: ${e}`)
        }
        if ((event.prompt?.text ?? "").includes(NOWAKE)) {
          await dbg("nowake prompt (command), дельта пропущена")
          return
        }
        // Первый промпт сессии ≈ SessionStart: дельта отложки уходит в контекст.
        if (!woken.has(sid)) {
          woken.add(sid)
          const wake = await run(`python3 ${HOME}/.claude/scripts/waiting.py wake`)
          const delta = wake.out.trim()
          if (delta) {
            const text = (event.prompt.text ?? "").concat(`\n\n[derflow wake]\n${delta}`)
            event.prompt.text = text
          }
        }
        // git-статус и канон-дрифт — только в лог, контекст не трогаем.
        const st = await run(
          `b=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) && n=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ') && echo "git: $b · $n uncommitted file(s)" || true`,
        )
        const drift = await run(`python3 ${HOME}/.claude/hooks/canon-drift.py`)
        const line = [st.out.trim(), drift.out.trim()].filter(Boolean).join(" | ")
        if (line) await dbg(`prompt ${sid}: ${line}`)
      } catch (e) {
        await dbg(`prompt hook failed: ${e}`)
      }
    })

    // История с картинками роняет текстовые модели плана («content.type is
    // invalid»), даже если картинка была ходами раньше. Перед ходом на текстовой
    // модели image-части замещаются текстовой заглушкой — история остаётся целой.
    // flash картинки ВИДИТ даже через кодинг-план (замер 03.10: валидный png →
    // 200 «Красный»); режется только glm-5.3 — гейтвей отдаёт 1210 «allowed
    // values: ['text']». С версии 2 глаза описывают картинку в текст промпта, а
    // этот хук — страховка на случай, если ядро игнорирует мутацию files выше
    // или в истории остались картинки старых сеансов.
    const TEXT_ONLY_MODELS = new Set(["glm-5.3"])
    const contextReg = await ctx.session.hook("context", async (event) => {
      try {
        if (!TEXT_ONLY_MODELS.has(event.model?.id ?? "")) return
        let removed = 0
        for (const message of event.messages ?? []) {
          const content = message?.content
          if (!Array.isArray(content)) continue
          for (let i = 0; i < content.length; i++) {
            const part = content[i]
            const isImagePart =
              part?.type === "image" ||
              part?.media?.kind === "image" ||
              part?.kind === "image" ||
              String(part?.mediaType ?? part?.mime ?? "").startsWith("image/")
            if (!isImagePart) continue
            removed++
            content[i] = {
              type: "text",
              text: "[изображение недоступно текстовой модели — описание ищи блоком «изображение → текст» в тексте промпта; блока нет — картинки ты НЕ видел, не выдумывай]",
            }
          }
        }
        if (removed > 0) await dbg(`context: ${removed} image part(s) → placeholder for ${event.model.id}`)
      } catch (e) {
        await dbg(`context hook failed: ${e}`)
      }
    })

    // Компакция собирает историю в обход context-хука: сессия на glm-5.3 с
    // картинками падала «content.type is invalid» (скрин 03.10). Чистим там.
    // Имя хука по контракту v2.0.20 — "compaction" (packages/plugin/src/promise/
    // session.ts); "compacting" — мёртвая регистрация, ядро его не зовёт.
    // Страховочная сетка: с modalities в конфиге ядро чистит картинки само
    // (unsupportedParts на всех kind, боем проверено 03.10), хук остаётся на
    // случай форм, которые unsupportedParts не узнает.
    try {
      await ctx.session.hook("compaction", async (event) => {
        let fixed = 0
        for (const message of event.messages ?? []) {
          const content = message?.content
          if (!Array.isArray(content)) continue
          for (let i = 0; i < content.length; i++) {
            const part = content[i]
            const isImage =
              part?.type === "image" ||
              part?.media?.kind === "image" ||
              part?.kind === "image" ||
              String(part?.mediaType ?? part?.mime ?? "").startsWith("image/")
            if (!isImage) continue
            fixed++
            content[i] = {
              type: "text",
              text: "[изображение недоступно текстовой модели — описание ищи блоком «изображение → текст» в тексте промпта; блока нет — картинки ты НЕ видел, не выдумывай]",
            }
          }
        }
        if (fixed > 0) await dbg(`compaction: ${fixed} image part(s) → placeholder`)
      })
      await dbg("compaction hook registered")
    } catch (e) {
      await dbg(`compaction hook failed: ${e}`)
    }

    const toolReg = await ctx.tool.hook("execute.before", async (event) => {
      const canonical = GATED_TOOLS[(event.tool ?? "").toLowerCase()]
      if (!canonical) return
      const payload = JSON.stringify({
        tool_name: canonical,
        tool_input: {
          // клодовские имена полей, которых в опенкоде может не быть
          command: event.input?.command ?? "",
          prompt: event.input?.prompt ?? "",
          skill: event.input?.skill ?? "",
          subagent_type:
            event.input?.subagent_type ?? event.input?.subagentType ?? event.input?.agent ?? "",
        },
        cwd: directory,
      })
      const gate = await run(`${HOME}/.claude/hooks/openspec-critique-gate.sh`, payload)
      await dbg(`gate ${canonical} code=${gate.code}`)
      if (gate.code === 2) {
        throw new Error(
          `Гейт критик-слоя: ${gate.out.trim() || "заявка требует свежей отметки критиков"}`,
        )
      }
    })

    // session.idle → reap-гейт. Стрим бесконечный, поэтому читаем фоновой
    // задачей: setup завершается сразу, cleanup гасит итератор. Дедуп — до
    // всего: событие одно на все инстансы, обрабатывать имеет право один.
    const events = await ctx.event.subscribe()
    let stop = false
    const loop = (async () => {
      try {
        for await (const ev of events) {
          if (stop) break
          if (!IDLE_EVENTS.has(ev?.type)) continue
          const sid = String(ev.data?.sessionID ?? "?").replace(/[^\w.-]/g, "_")
          try {
            await mkdir(REAP_DEDUP_DIR, { recursive: true })
            await writeFile(`${REAP_DEDUP_DIR}/${sid}.${Math.floor(Date.now() / 1000)}`, "", { flag: "wx" })
          } catch {
            continue // квитанция занята: этот idle уже взял другой инстанс
          }
          await dbg(`idle ${ev.type} ${sid}`)
          // reap должен смотреть в каталог СЕССИИ, чей idle пришёл, а не в
          // каталог нашего подключения; если ядро каталог не отдаёт — прежний
          // fallback на directory инстанса
          let cwd = directory
          try {
            const s = await ctx.session.get({ sessionID: ev.data?.sessionID })
            const d = s?.directory ?? s?.location?.directory
            if (d) cwd = d
          } catch {}
          const reap = await run(
            `${HOME}/.claude/hooks/openspec-reap-gate.sh`,
            JSON.stringify({ cwd }),
          )
          if (reap.out.trim()) await dbg(`reap: ${reap.out.trim().slice(0, 400)}`)
        }
      } catch (e) {
        await dbg(`event loop ended: ${e}`)
      }
    })()
    await dbg("setup done")

    return async () => {
      stop = true
      try {
        await events.return?.()
      } catch {}
      await promptReg?.dispose?.()
      await contextReg?.dispose?.()
      await toolReg?.dispose?.()
      await loop
    }
  },
}
