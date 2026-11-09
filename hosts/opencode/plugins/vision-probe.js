// Диагностика vision-инцидента opencode v2.0.20 (задача «картинки и компакция»).
// session.hook("http.request") видит ИСХОДЯЩЕЕ тело к провайдеру — нижний уровень,
// где уже не важно, в какой форме картинка жила в сообщениях. Логирует все
// не-текстовые части; для glm-5.3 замещает их текстом (страховочная сетка под
// context/compaction-хуки derflow-hooks.js: ловит в т.ч. картинки внутри
// tool-result, куда те не спускаются).
export default {
  id: "vision-probe",
  setup: async (ctx) => {
    const { appendFile } = await import("node:fs/promises")
    const PROBE = "/tmp/derflow-plugin-probe.log"
    const dbg = (m) => appendFile(PROBE, `${new Date().toISOString()} ${m}\n`).catch(() => {})
    const TEXT_ONLY = new Set(["glm-5.3"])
    // VISION_PROBE_READONLY=1 — только лог, без подмены тела (чистый репро бага).
    const READONLY = process.env.VISION_PROBE_READONLY === "1"

    const sanitize = (messages) => {
      let n = 0
      for (const m of messages ?? []) {
        if (!Array.isArray(m?.content)) continue
        for (let i = 0; i < m.content.length; i++) {
          const part = m.content[i]
          if (part?.type === "text" || typeof part === "string") continue
          n++
          m.content[i] = { type: "text", text: `[${part?.type ?? "non-text"} part omitted: text-only model]` }
        }
      }
      return n
    }

    await ctx.session.hook("http.request", async (event) => {
      try {
        const req = event.request
        if (!req.body) return
        const ct = req.headers.get("content-type") ?? ""
        if (!ct.includes("json")) return
        const probe = req.clone()
        const text = await probe.text()
        const model = event.model ?? {}
        let note = `http kind=${event.kind} model=${model.providerID}/${model.id} bytes=${text.length}`
        try {
          const body = JSON.parse(text)
          const hits = []
          const walk = (node, path, depth) => {
            if (!node || typeof node !== "object" || depth > 8) return
            if (Array.isArray(node)) {
              node.forEach((n, i) => walk(n, `${path}[${i}]`, depth + 1))
              return
            }
            const t = typeof node.type === "string" ? node.type : null
            if (t && t !== "text" && t !== "tool-call" && t !== "tool_result" && t !== "tool_use" && t !== "function")
              hits.push({ path, type: t, sample: JSON.stringify(node).slice(0, 240) })
            for (const [k, v] of Object.entries(node)) walk(v, `${path}.${k}`, depth + 1)
          }
          walk(body.messages ?? [], "messages", 0)
          if (hits.length) note += ` | non-text: ${JSON.stringify(hits.slice(0, 5))}`
          if (!READONLY && TEXT_ONLY.has(model.id ?? "")) {
            const n = sanitize(body.messages)
            if (n > 0) {
              note += ` | SANITIZED ${n} part(s)`
              const headers = {}
              req.headers.forEach((v, k) => (headers[k] = v))
              event.request = new Request(req.url, {
                method: req.method,
                headers,
                body: JSON.stringify(body),
              })
            }
          }
        } catch (e) {
          note += ` | body-parse-fail: ${e.message}`
        }
        await dbg(note)
      } catch (e) {
        await dbg(`probe http.request failed: ${e}`)
      }
    })
    await dbg("vision-probe: http.request hook registered")
  },
}
