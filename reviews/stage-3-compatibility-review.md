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
