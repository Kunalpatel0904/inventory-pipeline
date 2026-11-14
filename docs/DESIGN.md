# Design and trade-off note

**Goal:** a correct, explainable vertical slice: events in, trustworthy daily balances out, with every rejected or
corrected record traceable, reruns safe, and failures visible.

## Key decisions
1. **Event ledger + derived balances (not update-in-place).** `inventory_movement`/`inventory_leg` are append-only; `daily_balance`
   is a pure function of the ledger. A backdated correction is just another event, so history is never overwritten, and balances can always be
   rebuilt or audited from the ledger (reconciliation does exactly that with an independent SQL path).
2. **Legs.** Expanding movements into signed legs (transfer = 2) turns every aggregate into one `SUM(signed_qty)`, and makes
   "transfers net to zero" and "closing == ledger sum" simple, checkable invariants.
3. **Tail-only rebuild for backdating.** A change at date *d* only invalidates that pair from *d* forward. We delete and regenerate that tail from the
   previous day's closing. Measured ~2x faster than recomputing everything on the 100k run, and the incremental result is tested equal to a one-shot build.
4. **Atomic unit = file.** Ledger, legs, rejects, balances and audit row commit together. This gives clean retry semantics (rerun the same command) at the cost of
   one big transaction per file; row-level atomicity would leave balances inconsistent after a crash.
5. **Two idempotency layers.** File content hash (cheap skip) + `movement_id`/`content_hash` (safe replay, conflict detection). Either alone is not enough:
   a corrected file with a new hash still replays old events; a replayed event with changed content must not silently overwrite history.
6. **Reject, don't repair.** Bad rows go to `reject_record` with file, line, one reason code and the raw record; nothing is guessed or coerced
   (`10.5` is rejected, not rounded). Exception: whitespace and case are normalised.
7. **Negative stock is a warning, not a reject.** Late-recorded receipts make temporary negatives legitimate; dropping the issue would corrupt the balance. It is surfaced in reconciliation.
8. **Determinism.** No wall-clock in business rules (the future-date rule compares to the event's own `recorded_at`), stable ordering (file order, first duplicate wins), seeded generator.

## Trade-offs
| choice | gain | cost / when I would change it |
|---|---|---|
| SQLite + stdlib | zero setup, runs anywhere, real transactions and SQL for reconciliation | single writer, no concurrency; move to Postgres/warehouse for multi-writer or TBs |
| Dense `daily_balance` | trivial consumer queries, simple continuity checks | storage grows with pairs x days; use sparse rows + as-of join for slow movers |
| Whole file in memory | simple, fast validation | caps file size; chunked streaming is the next step |
| Per-file transaction | strong consistency | long locks on huge files; chunk by date partition |
| Type-1 dimensions | simple | no history of product renames; use SCD2 if reports need it |
| First duplicate wins | deterministic | a "corrected resend" under the same ID is rejected by design; corrections must be new events (adjustments) |

## Things deliberately not done
Streaming/orchestration, cost valuation, lot/serial tracking, in-transit stock, auth/secrets (none needed), UI. Each is a bounded extension of this design.
