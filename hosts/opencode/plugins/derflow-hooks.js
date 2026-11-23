// Обёртка derflow-хуков (живут в ~/.claude/hooks и ~/.claude/scripts, контракт —
// Claude Code settings.json) под OpenCode promise-plugin API.
//
// Контракт (packages/plugin/src/promise/plugin.ts; имена хуков и событий
// сверены по бинарю v2.3.2, 23.11.2026): default-экспорт
// { id, setup: (ctx) => Promise<Cleanup|void> }. Хуки навешиваются доменами:
//   session.hook("prompt")     → wake-дельта отложки первым промптом сессии;
//                                git-статус и канон-дрифт — только в лог;
//   tool.hook("execute.before")→ гейт openspec-critique-gate на bash/task/
//                                agent/skill; throw = Tool.Error, вызов
//                                отклоняется до исполнения;
//   event.subscribe()          → session.execution.* → openspec-reap-gate
//                                (не блокирует).
// Постулаты: setup обязан завершиться (вечный for-await по событиям живёт в
// фоновой задаче, cleanup её гасит); ни один вызов скрипта не имеет права
// уронить или подвесить сессию опенкода.
// Картинки промпта плагин не трогает: модель сессии читает их сама (модальности
// описаны в ~/.config/opencode/opencode.json). Внешней транскрипции и подмены
// image-частей здесь нет намеренно: на видящей модели они подменяли бы её
// собственное зрение.

import { appendFile, mkdir, writeFile } from "node:fs/promises"

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

// Дедуп reap-гейта: idle-события глобальные, их получают все инстансы плагина
// (служба держит по инстансу на подключение — 07.10 наблюдалось 8×). Квитанция
// <sid>.<секунда> с O_EXCL атомарна и между процессами: кто первым создал файл,
// тот единственный и обрабатывает idle. Окно в одну секунду для гейта безвредно:
// два РАЗНЫХ конца ходов одной сессии в одну секунду не случаются, а пропущенный
// реап догонит следующий idle — гейт ненасыщающий и не блокирует.
const REAP_DEDUP_DIR = "/tmp/opencode-reap-dedup"

export default {
  id: "derflow-hooks",
  setup: async (ctx) => {
    const directory = ctx.location?.directory ?? process.cwd()
    await dbg(`setup: dir=${directory}`)
    const woken = new Set()
    await run(`find ${REAP_DEDUP_DIR} -type f -mtime +1 -delete 2>/dev/null || true`, undefined, 10000)

    const promptReg = await ctx.session.hook("prompt", async (event) => {
      try {
        const sid = event.sessionID ?? "?"
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
      await toolReg?.dispose?.()
      await loop
    }
  },
}
