---
name: Default architectural choices when unsure
description: §16 of the roadmap doc gives binding tiebreakers — apply these without asking when designing a slice
type: feedback
---

When unsure between two designs, the roadmap §16 says pick:

- shared pipeline over per-account stream
- feature-driven over config-driven
- fail-closed over silent success
- reuse over duplication
- deterministic over smart
- explicit enum over free text
- completed bars over forming bars
- account-isolated risk over global risk
- separate simulated truth over mixed ledgers

**Why:** the roadmap is explicit and binding. These also map directly onto §12 stop conditions — violating any of these typically trips a stop condition (e.g. duplicate streaming = stop condition 2; free-text rejection reasons = stop condition 7; mixed ledgers = stop conditions 4–5).

**How to apply:** when scoping or coding, default to the listed choice without asking. Surface the call only if a constraint forces deviation.
