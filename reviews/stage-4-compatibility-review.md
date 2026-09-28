# Stage-4 compatibility review — prepared

Read full stage-4 specification with previously reviewed full stages 1–3 and active room plan. Shared review #18. Accepted stage-3 revision: `70a9c89ff681bb9ac0c2b91a44cc6cca9a877c61`. Product inspection is read-only; review files only. No new screens or earlier-stage modifications.

## Current-state versus original-receipt boundary

Stage 1 requires a successful idempotent retry to return its original JSON value even after amendments. Stage 4 separately requires existing confirmation and lookup to reflect an applied repair. Inherited confirmation maps table labels from the create/replay response, while lookup fetches the current reservation. Therefore a repaired booking replay can legitimately return the old assignment while the UI still presents that old assignment as the current confirmation.

This is a hypothesis from source/spec inspection, not a reproduced stage-4 defect yet. No live polling is required. Once a real repair is available, test a real browser booking, manager preview/apply, unchanged form retry, current lookup and refreshed availability. Preserve the API's original response exactly. If the mismatch reproduces, propose a narrowly scoped post-success current-reservation read for displayed details while retaining reference, body/key and original receipt identity; clearly handle failure of that supplementary read without inventing current success. Do not edit assets until Lead authorizes a concrete correction.

Prepared `reviews/stage-4-browser-repair-probe.py <disposable-base-url> <evidence-dir>` uses real Chromium and synthetic fixture credentials. It verifies preview purity, deterministic simple reassignment, preserved accepted terms/start/end, reassigned history, exact original retry JSON, shown table labels, current lookup, refreshed closed-table availability and 375/1440 screenshots. It prints no tokens or snapshots. It resets its target, so use an isolated instance.

## Additional review coverage when source is ready

- Closure exclusion for singles/pairs, half-open boundaries, independent explanation rules, and accepted capacities under policy changes.
- Series amendment after an individual exception and cancellation; original scheduled dates/current tables retained; repairs preserve exception flags; series counters advance once; no-op/stale/replay/failure leave correct histories and counters.
- Actual stage-3 export containing changed/cancelled occurrences imported into stage 4, then amended/repaired. Preserve original booking/series receipts and owner identity.
- Existing browser loss-after-commit retry, stale search ordering, contrast and 375/1440 layout. No asynchronous screen refresh is assumed.

Runtime results and any concrete findings will be appended after Backend's source-ready handoff. QA remains acceptance owner.
