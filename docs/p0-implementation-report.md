# P0 Implementation Report — 拾光 V2

## Identity Gate (manual, Sol)

| Field | Value | Result |
|-------|-------|--------|
| repo | matith/shadowV2 | PASS |
| local root | D:\LIB\mimo\shadowV2 | PASS |
| project UUID | 11dd729c-beaa-42cf-bad1-a06ab4f89e1b | PASS |
| canonical | g000259 (legal successor of g000256) | PASS |
| baseline commit | b167253 → HEAD 5ab7623 | PASS |

## Scope

- Plan: `plan-p0-v3` (35 modules)
- Scenarios: A / C / E + X-series invariants
- No P1/P2 product work. External I/O is Fake/Mock only (simulate the world, do not bypass blackboxes).

## What was implemented

Runtime package `src/shiguang/` with BBM-aligned blackbox boundaries:

| Layer | Modules |
|-------|---------|
| identity | Project Identity Gate (hard reject on mismatch) |
| source-evidence | raw-source-store, provenance-chain, effect-receipt-store |
| personal-ledger-core | matter-ledger, event-ledger, people-ledger |
| state-commit-engine | op-validator, patch-committer, correction-applier, change-receipt |
| summary-system | capsule-store, incremental-reducer, dirty-tracker |
| context-engine | working-context-compiler, ledger-router, directive-policy |
| durable-task-runtime | reminder-scheduler, delayed runner, task-action-bridge, FakeClock |
| agent-runtime | model-adapter (RuleBasedModel), turn-orchestrator, ledger-ops-proposer |
| interaction-layer | inbound-message-gateway (Fake), message-normalizer, delivery-router (Fake), channel-identity-mapping |
| projection-layer | table-projection (Local Inspector) |

## Invariants verified

1. **Idempotent ops** — duplicate `op_id` → DUPLICATE receipt, no double Matter/Event/Reminder
2. **Source immutability** — Correction never mutates raw sources; hashes stable
3. **Commit then success** — success wording only after durable commit; invalid ops leave no `op_log`
4. **Reminder restart/idempotent fire** — `run_due` twice → one FIRED delivery; collapse_key dedup
5. **Capsule incremental** — basis_revision tracks matter.revision; STALE detectable
6. **Same Matter reuse** — T0/T1 create one Matter only
7. **Human/AI consistency** — projection reads same ledger; cell edits go through State/Commit
8. **Evidence/receipts** — change receipts on commits; effect receipts on delivery
9. **Durable complete via bridge** — TaskActionBridge produces ops → Commit updates Matter (no direct write)
10. **Identity gate** — wrong UUID raises IdentityError before any write

## Scenario results

| Scenario | Result |
|----------|--------|
| A 日常承诺 (T0→remind→complete) | PASS |
| C 多轮事项 (T0→T1 same Matter, events append, capsule) | PASS |
| E 纠正 (T2 Source kept, current=周四) | PASS |
| Nightly T0–T5 full script | PASS |

## Test results

```
Ran 18 tests in ~1.6s
OK
```

- Unit: identity, idempotent ops, source immutability
- Boundary: commit atomicity, high-risk confirm, effect receipt, projection→commit
- Scenario: A, C, E, restart recovery
- Integration: nightly T0–T5
- P1 slices (does not break P0): matter tree expand, archive mini-capsule recall, knowledge upsert

See `docs/p0-test-output.txt` for deterministic output.

## Simulated external edges

- FakeInboundChannel (user messages)
- FakeDeliveryAdapter (reply/notification + collapse)
- FakeClock (reminder due time travel)
- RuleBasedModel (replaceable ModelAdapter; no real provider in P0 tests)

## Not tested with real integrations

- WeCom / email / real mobile push
- WPS multi-dim table / web projection product
- Real LLM provider (ModelAdapter is interface + rule model)
- OCR / voice product capabilities (P2)

## Known limitations (P0)

- RuleBasedModel covers nightly fixture + common Chinese patterns, not open-domain NL
- Reminder due parsing is heuristic (明天下午 / 周X)
- Attachments stored via source store path; full blob FS layout is stub-level
- Directive policy has one night-quiet rule; full directive language is later
- Tree parent/child expand implemented in projection but not exercised in A/C/E

## Independent audit focus

1. Is State/Commit truly the only ledger write path?
2. Does Correction ever mutate Source?
3. Can success be claimed without durable commit?
4. Reminder fire idempotency under restart
5. Matter de-duplication across multi-turn updates
6. Identity gate cannot write other projects
7. Evidence chain Capsule→Event→Source resolvable
8. Tests are deterministic (FakeClock, fixed fixtures)

## Status

**READY_FOR_INDEPENDENT_AUDIT**

P0 STATUS: **PASS**
P1 STATUS: **PARTIAL** (matter tree expand, archive mini-capsule recall, knowledge ledger upsert — tested; File/Product ledgers, HOT/WARM/COLD, backup/migration not started)

P0_BASELINE_ACCEPTED_FOR_AUDIT
commit: a4a287f (P0) + this commit (P1 slices + report)
