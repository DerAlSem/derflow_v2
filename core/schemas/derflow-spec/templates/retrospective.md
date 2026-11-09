# Retrospective — <change name>

## §0 Evidence

<!-- Gathered from tooling, not memory. Numbers first; every later claim cites one. -->

| | |
|---|---|
| Commits | <count> (`<first>..<last>`) |
| Diff | <N files, +X / -Y lines> |
| Tasks | <done>/<total> |
| Verify | `DECISION: <PASS \| PASS_WITH_WARNINGS \| FAIL>` |
| New deps | <none, or list> |

Commit chain:
<!-- one line per commit: <sha> <subject> -->

## §1 Wins

<!-- Each cited with evidence: commit hash, file path, or test name.
     A win with no citation is a feeling, not a finding. -->

- <what worked> — *<evidence>*

## §2 Misses

<!-- Severity: 🔴 blocking · 🟡 painful · 📌 nit -->

- 🔴 <what did not work> — *<evidence>*

## §3 Plan deviations

<!-- Tasks whose scope changed, and why. Omit if none. -->

## §4 Discipline compliance

| Gate | Status |
|---|---|
| Review verdict obtained and not stale | ✓ / ✗ |
| TDD: test red before green | ✓ / ✗ |
| Verify on the highest available contour (ran the thing) | ✓ / ✗ |
| External wire-contract held before parser/verdict | ✓ / ✗ / n/a |

### Deliberately skipped

<!-- One block per ✗. Three questions, all required. -->

**<gate name>**
- **What**: <the specific gate or step>
- **Why this cycle**: <CONCRETE trigger — commit hash, log line, observed
  behavior. "Seemed unnecessary" is not an answer.>
- **How to prevent recurrence**: <schema fix / rule tightening / line in the
  project's CLAUDE.md / explicit boundary-case note>

## §5 Surprises

<!-- Assumptions that turned out wrong. -->

## §6 Promote candidates

<!-- The payload. Unchecked items carry to the next cycle.
     A lesson with no trigger condition will not fire — "How to apply" is
     the difference between a note and a rule. -->

- [ ] 🔴 <one-sentence lesson>
      → **Promote to** <memory | project CLAUDE.md | this schema | a skill | one-off>
      > **Why**: <the cost this lesson already paid>
      > **How to apply**: <the trigger condition, so it fires unprompted>

---

<!-- FORWARD-POINTER POLICY: if facts change after this is written, do NOT
     rewrite it — that destroys the audit trail. Append instead:
     > **Update YYYY-MM-DD**: section X superseded by <link> -->
