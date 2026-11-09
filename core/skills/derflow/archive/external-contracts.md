# Внешние API, контракты и что openspec не держит (архив derflow, глава _lane-c до 13.09.2026)

## Внешние API и контракты

**Гейт переехал в `_gates.md`** — он объявлял себя применимым к любой полосе, но
лежал здесь, и полоса B, которая этот движок не открывает, его не видела.
Правило то же: wire-контракт (вендорский референс или захваченный сэмпл) до
парсера **и до вердикта** о том, чего внешний API «не умеет».

## Что openspec НЕ держит

**Content / marketing-heavy work? (selling site, landing, campaign)** Two layers, two homes. **openspec holds only the *system behavior/contract*** — routes, lead/ticket flows, validation, events. The **marketing layer — positioning, ICP, offer, pricing, copy, narrative — lives in its own homes** (`.agents/product-marketing.md`, offer/copy docs owned by the `marketing-skills`), **never as openspec SHALLs** (a SHALL is code-checkable; "the hero conveys 'built by practitioners'" is not). Route the marketing layer to `product-marketing` → `offers`/`pricing` → `copywriting` (+ `ru-text` for native Russian); openspec captures what the site *does*, not what it *says*.

