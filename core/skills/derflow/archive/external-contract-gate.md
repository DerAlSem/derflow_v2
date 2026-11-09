# Внешне-контрактный гейт — контракт до парсера и до вердикта (архив derflow, глава _gates до 13.09.2026)

## Внешне-контрактный гейт — контракт до парсера и до вердикта

Жил в движке Lane C, хотя сам объявлял себя применимым к любой полосе — и полоса
B, которая движок C не открывает, своего гейта не видела. Поэтому он здесь.

**External / third-party API / SDK / device integration? (любая полоса — B тоже)** Before writing any parser or serializer against it, get the **real wire-contract**: (a) the vendor's official reference with exact request/response field names, **or** (b) a captured live sample of the actual response. A parser built on *guessed* field names with a `// verify on live` comment does **not** enter the build — "verify-on-live" is not a substitute for knowing the contract, and a plan step that says "confirm exact fields on the live device later" is guessing wearing a plan's authority. Wire it *after* you hold the contract, not before. (Real cost: a KkmServer integration shipped parsing `Name` / top-level `SessionState` instead of `NameDevice` / nested `Info.SessionState` — plan-sanctioned guessing → days of one-field-at-a-time prod whack-a-mole with the owner.)

**This binds claims, not just code:** any statement that the external API *can't* do X, or *doesn't* return field Y — made in **design, architecture, or review** — is under the same gate. Our own parser reflects what we *extract*, not what the API *sends*; a feasibility verdict sourced from our code (not the vendor doc / a captured sample) is a guess that can kill a valid feature. (Real cost: `system-architect` ruled "SBP webhook returns no payer phone → phone-match login impossible" from our `payload.get('payerName')`; the vendor doc had `payerMobileNumber` all along — the feature was nearly cut on a false premise.)

Домены, где своего агента нет (платёжный контур, российское право), опираются
именно на этот гейт — см. `SKILL.md`.

