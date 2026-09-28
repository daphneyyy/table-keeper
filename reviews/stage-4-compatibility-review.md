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

## Runtime findings and scoped correction

Read `replans.py` and the service's closure/series/apply paths. Used an isolated stage-4 service with source mounted read-only, `tablekeeper-stage-4-dev` dependency image, port 51051. Source was evolving during developer verification. No backend edits were made.

The initial real-browser probe reproduced the confirmation mismatch: original receipt table `a` / Window nook, current repaired record `b` / Garden side, but replayed confirmation still Window nook. Preview did not mutate reservations/history; repair preserved accepted terms/start/end and added one reassigned history; current lookup and refreshed availability were correct. Initial JSON/screenshots: `reviews/stage-4-repair-evidence-01/`.

Lead explicitly authorized only `result/stage-4/app/static/app.js` for a correction. It now retains the original POST receipt/reference/body/key, immediately renders confirmed original details, then separately reads the current reservation for displayed table/time/status/accepted cutoff. The current read has attempt + selection + edited-form guards. Failure of that supplementary read retains a confirmed reference and labels details as original with a clear current-details-unavailable message; it produces neither booking-error nor booking-uncertain. No polling or new screen. No earlier-stage files changed (Git diff against accepted stage-3 revision verified).

## Executed checks

- `stage-4-browser-repair-probe.py` against port 51051: real repair then exact original-response replay now displays Garden side. Confirmed supplementary GET failure preserves original confirmation without uncertainty/error. Real series amendment refreshes the displayed time. A deliberately delayed older detail response cannot overwrite a newer attempt displaying a later assignment. Lookup and refreshed closure availability remain authoritative. 375px and 1440px screenshots; no mobile horizontal overflow.
- `stage-4-series-import-probes.py` against actual stage-3 source port 51057 and stage-4 destination port 51051: imports changed/cancelled occurrences and old receipts, repairs without changing terms/times/exception flags, amends using current repaired tables and original scheduled dates, skips cancelled/exceptions, handles stale rollback/no-op/empty eligible sets, respects closure half-open boundaries/explanations, and roundtrips immutable apply/amend receipts. All assertions passed.
- `stage-4-browser-upgrades.py` against actual stage-1/2/3 source services (ports 51544/51545/51057) and stage-4 destination: same browser signs in to old source; booking commits and its response is lost; raw source export is imported between requests; same body/key/token recovers the original reference and current labels; lookup and imported-anchor adoption pass for all three sources.
- `reviews/stage-4-regression-evidence/inherited-browser-check.py`: single/pair booking, unchanged replay without duplicates, lookup/cancel, committed-response loss, exact retry identity, in-page import, conflict refresh preserving inputs, out-of-order search metadata/grid/form, edited-field new request, closed-day state, public auth gate, signup/direct-route session, 375px layout, no browser page errors. Passed.
- `node --check result/stage-4/app/static/app.js` and `git diff --cached --check` passed.

Final browser JSON/screenshots: `reviews/stage-4-repair-evidence-02/`. Regression scripts/logs/screenshots: `reviews/stage-4-regression-evidence/`. The current-read-failure mobile screenshot was inspected visually: confirmed success, historical labels and the fallback explanation remain readable without overflow. No tokens or exported credential-bearing state were written to evidence.

All review containers were stopped after verification. Review #18 and authorized fix #19 are complete. No backend defect was identified in this focused pass; this does not replace independent final integrated QA or exhaustive optimizer acceptance.
