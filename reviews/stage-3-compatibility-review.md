# Stage-3 compatibility review — preparation

Read full stage-3 specification, alongside previously read complete stages 1/2 and participant guide, plus the active plan. Shared assignment #14. Stage-2 accepted revision: `42a2b990f8b203fd2141db4a2e8b502313ff3791`; unchanged stage-3 inheritance: `b29fc4acca9ed126c508ed278d1ee72a77bff024`.

Backend implementation is in progress. These are source-derived risks and prepared probes, not executed stage-3 verification or acceptance.

## Inherited UI assessment

The grid already uses `available_table_ids`/`available_options` for selectable states and uses server-supplied local slot starts. It does not calculate slots or reservation ends from fixture duration. Table labels and declared pairs are stable across policy publication, so the existing label mapping remains appropriate. Original receipts can lack `table_ids`, `revision`, and `accepted_terms`; the inherited UI already falls back to `[table_id]` and requires none of the new fields. Browser session and pending body/key state have no coupling to server schema or policy publication.

The extra capacity and cutoff labels do rely on original fixture detail and can become false under stage 3. In inherited `app.js`, `renderResults` computes the `Up to N guests` label from `restaurant.tables[].capacity`; `renderBooking` uses `restaurant.cancellation_cutoff_minutes` for the booking fine print. The specification deliberately preserves that restaurant detail unchanged while selected policies change capacities and cutoffs.

Proposed correction after concrete reproduction and explicit scope approval:

- Use a matching authoritative `available_options[].capacity` for each offered table set. If there is no available option, omit the numeric capacity or use neutral seating wording rather than assert the fixture value as current.
- Before confirmation, use neutral cutoff wording, since the current search responses do not expose cutoff. After confirmation, describe only the returned receipt's `accepted_terms.cancellation_cutoff_minutes`; for an old receipt without terms, remain neutral. A current lookup may show its current accepted terms.
- The inherited UI shows start time only. No fabricated end is rendered. If adding end time is desired, show returned `ends_at` with its own explicit offset/local context; do not derive it from fixture duration or a visitor's timezone. No new screen is needed.

Lead agreed the risk and requested a concrete reproduction before any static edit. Review remains read-only; no earlier stage or static files modified.

## Prepared independent probes

`reviews/stage-3-contract-probes.py <disposable-base-url>` resets its target and checks policy publication order/date ties/permissions/receipt precedence; accepted terms and history immutability; reversed-pair no-op; invalid and stale revisions; owner-only history/decision/series including unauthenticated 404; independent explanation rules; anchor identity/history; calendar recurrence; per-series batch revision counting; cancellation/replays; failed adoption exact-state rollback/key reuse; and populated stage-3 export/import with historical receipts.

`reviews/stage-3-browser-policy-probe.py <disposable-base-url> <evidence-directory>` uses real Chromium against a synthetic fixture, publishes a capacity/grid/duration/cutoff-changing policy after login, checks authoritative grid states/times, makes a real pair booking and lookup, records shown labels against accepted terms, and captures 1440px/375px screenshots. It does not manufacture API responses.

Both scripts use synthetic fixture credentials and avoid printing tokens or exports. They require the challenge `.venv` with httpx/Playwright. Runtime results and source review will be appended after Backend's source-ready handoff. A genuine prior-stage export/import with the signed-in browser and pending retry will also be verified once the stage-3 service is available.

## Executed review — initial stage-3 implementation

Used a dedicated container from `tablekeeper-stage-3-dev`, image ID `sha256:6ace03ac9b2c89f12d0db26496b9a63b7fb0b23940bf88d07046b2280c7ed87d`, at localhost port 65103. Read the new `policies.py`, full `service.py`, and full `state.py`; no backend files modified. Source was still uncommitted and evolving, so this is not final revision acceptance.

`stage-3-contract-probes.py` exited 0: all prepared policy/history/revision/series/rollback/snapshot checks passed. No concrete backend failure was identified in this focused review.

`stage-3-browser-policy-probe.py` exited 0 and captured `reviews/stage-3-policy-evidence-01/policy-ui.json` plus 1440px/375px screenshots. The server correctly offered a pair with capacity 6 for party 5 after publication and changed its grid to 60-minute steps; the UI's fixture-derived label remained `Up to 4 guests`. The accepted cutoff was 30 minutes while visible fine print stated 120. Returned end was 20:00 for the policy's 120-minute duration; the UI showed the correct 18:00 start and did not invent an end. Pair labels and current lookup remained correct. No horizontal overflow at 375px.

`stage-3-browser-upgrades.py` exited 0 against genuine independent earlier-stage source containers (stage 1 at port 65120, stage 2 at 65121). Both upgrade paths passed: browser signs in to old service, real booking commits but response is dropped, raw export imports into stage 3, unchanged open form recovers original response with exact body/key and retained token. Labels and lookup reference remain correct for old single/pair receipts; adoption of each imported anchor also succeeds under policy 0. Tokens and exports were not saved to disk.

Lead authorized only `stage-3/app/static/app.js` for the reproduced wording correction, tracked separately as shared task #15. No optional end-time display will be added. Review #14 is complete with this UI finding transferred to that scoped fix. Full-stage acceptance remains with QA.

## Scoped correction and verification

Asset-only fix committed as `b414768f9569e9460c98532a70ec6b78032cbb0a`. Changed only `result/stage-3/app/static/app.js`: row capacities come from matching `available_options`; unavailable rows without an option use neutral seating wording. Booking cutoff is neutral before confirmation, after an edit, during submission and for legacy receipts; a successful response with `accepted_terms` displays that receipt's cutoff. No new screen or optional end-time display. Existing selectors and request identity/search-generation paths are retained. Stage-1 and stage-2 files are unchanged from accepted `42a2b990f8b203fd2141db4a2e8b502313ff3791` (Git diff verified).

For final checks, mounted current stage-3 source read-only into a separate disposable container using the stage-3 dev image dependencies, port 65466. The following exited 0:

```sh
node --check result/stage-3/app/static/app.js
git diff --cached --check
/Users/daphneyang/Desktop/GitHub/dark-factory-wearedevs/.venv/bin/python reviews/stage-3-browser-policy-probe.py http://127.0.0.1:65466 reviews/stage-3-policy-evidence-02
/Users/daphneyang/Desktop/GitHub/dark-factory-wearedevs/.venv/bin/python reviews/stage-3-browser-upgrades.py http://127.0.0.1:65466 http://127.0.0.1:65120 http://127.0.0.1:65121
/Users/daphneyang/Desktop/GitHub/dark-factory-wearedevs/.venv/bin/python reviews/stage-3-regression-evidence/inherited-browser-check.py
```

Policy JSON/screenshots and logs are under `reviews/stage-3-policy-evidence-02/`. They show `Up to 6 guests`, the accepted 30-minute cutoff, neutral unavailable-row/pending wording, and 375/1440 layouts. Publishing a newer 10-minute policy then repeating the unchanged booking returns and displays the original 30-minute accepted cutoff. No horizontal overflow at 375px. The old-receipt upgrade script additionally asserts neutral cutoff wording for both actual stage-1 and stage-2 imports.

The inherited browser regression script/log/screenshots under `reviews/stage-3-regression-evidence/` confirm singles/pairs, repeat-submit identity, lookup/cancel, real commit then response loss, exact body/key retry, in-page import, conflict refresh/input retention, deliberately delayed older metadata and availability, edited-field new request, closed-day empty state, public auth gate, signup and direct-route session persistence. No browser page errors. Visual inspection of the final mobile policy confirmation found no clipping or overflow.

All four review containers were stopped after verification. No tokens or exported credential-bearing state were written to evidence. Backend was evolving during review; these are scoped independent checks and a verified asset commit, not final integrated QA acceptance.
