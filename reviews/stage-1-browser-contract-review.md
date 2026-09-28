# Stage-1 HTTP and browser-integration contract review

Reviewed 2026-09-27 by Frontend Engineer. This is a specification/design review, not implementation acceptance or a passing runtime test report. Shared assignment: #4.

## Evidence and scope

Read the complete local `tablekeeper/spec/stage-1.md` (472 lines), `stage-2.md` (240 lines), and `docs/participant-guide.md` (877 lines) under `/Users/daphneyang/Desktop/GitHub/dark-factory-wearedevs/`, plus the active immutable room plan. Local access is confirmed. At inspection, `/Users/daphneyang/Desktop/GitHub/band-output/result/stage-1/` did not exist. Consequently no backend code, HTTP service, Docker build, or browser behavior has been verified here. No stage-2 implementation was performed and no backend-owned files were changed.

During review, `result/stage-1/app/rules.py` and `app/__init__.py` became available as uncommitted work. Read `rules.py` in full and ran 13 read-only Python helper assertions via `python3 -B`/`runpy`: parsed JSON equality including boolean-versus-number and unknown-field differences; both specified spring gaps; both first-occurrence fall folds; New York fold absolute duration; adjacent nonoverlap; and four invalid party-size types/ranges. All passed. The reviewed `rules.py` SHA-256 was `1938538dd4bec7209334ad78be7532913483ccdcd152d1d3247fe21933c7067d`. This is helper-level evidence only, against evolving code; routes, session persistence, response envelopes, transactional behavior, imports and exports were not available for this check. There was no existing Git commit at the time of inspection.

The approved Python/FastAPI single-process transactional design is compatible with these contracts if the following boundaries are implemented explicitly. Findings below are risks to prevent, not observed defects. The preliminary rules implementation already addresses explicit numeric/boolean distinction, local-time gap/fold resolution, absolute duration and half-open occupancy.

## Highest-priority integration risks

1. **A retry must return historical success, not current reservation state.** Persist a deep-copied original JSON response with the parsed original body under `(user, method, path, key)`. A successful create or batch replay returns 200 and the exact original JSON value even after PATCH, cancellation, export/import, or a later schema upgrade. Do not regenerate old responses with a new serializer. In stage 2, a genuine old stage-1 receipt can lack `table_ids`; the future frontend should fall back to `[table_id]`. Fresh stage-2 responses must use the stage-2 shape. Lookup is authoritative for current state; a replay confirmation is evidence of the original successful operation.
2. **Browser identity must outlive a service upgrade.** Export/import preserves every bearer token, user ID, display name and password hash. Login must add a session rather than revoke earlier tokens. There is no required logout/revoke endpoint or identity endpoint: future logout can clear client session state, and the browser can retain token, user ID and display name from signup/login across routes. Import between requests must not clear browser identity or pending submission state. Reset intentionally clears server sessions; container-restart durability is not required.
3. **FastAPI defaults can violate the wire contract.** Use explicit error translation and strict JSON validation; framework coercion must not silently accept booleans as integers, numeric strings, malformed timestamps, or return `detail` envelopes. All 4xx/5xx must use `{error:{code,message}}`. Set API JSON content type to the specified `application/json; charset=utf-8`. A successful reset/import is 204 without a JSON body. Public routes and test controls cannot inherit mandatory bearer dependencies.
4. **Retry identity includes ignored fields.** Unknown body fields do not affect domain validation, but remain part of parsed-body equality. Reordered object keys/whitespace must replay; an unknown field change must produce reuse conflict. Resolve saved receipts after object parsing/authentication and before domain/current-resource validation. Python equality needs particular care: `True == 1` must not make two different JSON values equal. Do not claim a key on failure. Body-level numeric equality should follow JSON-value semantics rather than raw serialized spelling.
5. **Local wall-clock strings must never pass through the browser's timezone.** Forward availability `starts_at_local` unchanged to create. Display its local date/time using restaurant metadata. RFC3339 response timestamps need an explicit offset; avoid using a visitor-local `Date` rendering for restaurant time. Server arithmetic for duration, overlap and cutoff uses instants, with first occurrence for repeated local times and rejection of spring gaps.

## Error/status/type matrix

This matrix records the complete relevant categories rather than imposing precedence where the spec does not define one.

| Input or operation | Required result | Integration consequence |
|---|---|---|
| Invalid JSON/non-object request body; ordinary field wrong JSON type | 400 `malformed_request` | Never leak framework validation shape |
| Missing required field/query; correct type but invalid format/range/length | 422 `validation_failed` | Show server refusal, preserve useful input |
| `party_size` below 1, fractional, string, boolean or otherwise noninteger | 422 `validation_failed` | Browser must send a JSON integer; server remains strict |
| `starts_at_local` string includes offset, Z, seconds or lacks bare minute form | 422 `validation_failed` | Submit exact `YYYY-MM-DDTHH:MM`; other wrong JSON types use 400 |
| Query integer `1e9`, `4.0`, `+4` | 422 `validation_failed` | Send plain decimal digits |
| Missing/empty required idempotency key | 400 `missing_idempotency_key` | Generate before first attempt and retain |
| Key over 255 characters | 422 `validation_failed` | Keep client key bounded |
| Missing/malformed/unknown bearer on private route | 401 `unauthenticated` | Ask diner to sign in; do not fabricate identity |
| Another user's reservation / unknown reservation | 404 `not_found` | No existence leak; list contains only caller's confirmed and cancelled records |
| Authenticated but forbidden operation, where specified | 403 `forbidden` | Generic convention; ownership lookup specifically uses 404 |
| Duplicate signup email | 409 `email_taken` | Auth form refusal |
| Invalid email / signup password shorter than 8 | 422 `validation_failed` | Auth form validation |
| Wrong login password / unknown email | 401 `unauthenticated` | Same outward error |
| Unknown restaurant/table or wrong restaurant's table | 404 `not_found` | Treat identifiers as opaque and restaurant-scoped |
| Occupancy conflict | 409 `table_unavailable` | Future UI shows booking-error, refreshes availability, retains form/inputs |
| Off-grid / outside hours / excessive party | 422 `not_on_slot_grid` / `outside_opening_hours` / `party_exceeds_capacity` | Preserve specific server code |
| Nonexistent local time | 422 `invalid_local_time` | Never offered by availability |
| Cancel/PATCH within current-start cutoff or later | 409 `cutoff_passed` | Do not measure cutoff against proposed new start |
| PATCH cancelled booking | 409 `reservation_cancelled` | Leave original state unchanged |
| Repeat cancel | 200 current cancelled reservation | Repeat cancel succeeds, including after time has advanced |
| First successful create/moves | 201 | Store response before releasing transaction |
| Same-key/same-body replay | 200 original response | No new booking/mutation |
| Same-key/different parsed JSON after prior success | 409 `idempotency_key_reuse` | Takes precedence over new domain validation/current state |
| Invalid moves shape, duplicate references, length outside 1..8 | 422 `validation_failed` | Endpoint-specific shape exception to generic type rule |
| Moves across restaurants | 422 `validation_failed` | Atomic failure |
| Invalid import JSON | 400 `malformed_request` | Destination unchanged |
| Missing import fields, wrong track/version, invalid state | 422 `validation_failed` | Destination unchanged; no partial replacement |

Unknown body fields and query parameters are ignored for domain validation. IDs are opaque strings of at most 64 characters, including fixture IDs. References remain unique 6–12 uppercase letters/digits. Never reject a booking solely for being in the past.

## Public browsing and future HTTP/HTML routing

- `GET /restaurants`, `GET /restaurants/{id}`, `GET /availability`, `/health`, signup/login, and reset/export/import require no bearer. Export/import explicitly override the broad authentication wording in stage-1 §6/§8.
- Return restaurant detail in fixture shape, including table labels/order. Availability includes every eligible slot even when no tables are free; only a closed/no-slot day has an empty `slots` list. This distinction drives unavailable cells versus `no-slots`.
- In stage 2 only, `/`, `/signup`, `/login`, `/lookup` must directly return HTML. Keep `/auth/*`, `/restaurants*`, `/availability`, `/reservations*`, `/reservation-moves`, and test controls as API routes. Avoid a catch-all static handler swallowing API 404s or changing their error envelope.
- Same-origin bundled assets need no separate-origin CORS design. No external fonts/scripts/styles/runtime services. Build dependencies into each stage's independent image. No browser implementation belongs in stage 1.

## Time and atomicity checks to retain

Availability and booking must use the same time rules: fixture-order table IDs; opening-anchored slot grid; skipped gap slots omitted; repeated slots offered once at their first occurrence. Resolve Berlin 2026-03-29/2026-10-25 and New York 2026-03-08/2026-11-01 using IANA data bundled in the image. Compute ends by absolute duration and check closing boundaries as instants. Use half-open occupancy so adjacency succeeds. Sort caller reservations by start instant descending, not offset-bearing timestamp text.

For atomic moves, validate ownership/same restaurant and non-occupancy errors in input order; for each booking, current cutoff precedes changed-field checks. Then check all resulting bookings, including unchanged listed bookings, against one another and unlisted occupancy. A swap must succeed when its resulting state is valid. Commit the response receipt and all mutations under the same state boundary. Readers must never see partial batches or the transient vacancy of a failed amendment.

## Future browser recommendations (design only)

- Maintain one search-generation identity across availability, restaurant labels and booking form. Abort is optional; generation checks are still necessary before rendering late responses. A stale response must not alter any part of a newer search.
- Capture a request's body and key before fetching. Keep them for unchanged submits after both success and uncertain response loss; regenerate when a field changes. A lost response produces only nonempty `booking-uncertain` for that attempt, not `booking-error` or a new confirmation. Confirmed rejection produces `booking-error`. Successful retry removes uncertainty/error elements and displays the original reference.
- Keep form inputs/selection when a conflict triggers availability refresh. Do not let that refresh overwrite the form or create confirmation. Keep the form after success for repeat-submit behavior.
- Use table labels for human text and fixture IDs only for values/test IDs. In stage 2, declared pairs remain nontransitive, canonical in fixture combination order; `available_table_ids` remains singles only. Support both new `table_ids` responses and preserved old single-table receipts.
- Preserve display identity across direct screen navigation using a same-origin session storage approach. Client pending-request memory only needs to survive in-page import between requests; reload recovery and cross-tab synchronization are expressly unnecessary.
- Never treat client-side cached state as proof of server success. Treat token/display name and all rendered API strings as data, using text-safe DOM rendering.

## Suggested independent verification sequence

1. Browse all three public GETs without auth; test unknown IDs, missing query values, strict query integers, empty tables per slot versus closed day, fixture table order, and offset-bearing timestamp formats.
2. Signup/login twice; verify both tokens work, private lookup hides another user's reference, and account hashing is retained through import. Do not publish exports containing credentials/tokens.
3. Create using key K; reorder body keys and replay; vary an ignored field and receive reuse conflict; try invalid changed body under K and still receive reuse conflict. Exercise failed-first-key reuse and independent user/path namespaces.
4. Amend then cancel a booking; replay K and compare the entire original JSON value. Repeat for a moves receipt. Verify current lookup differs appropriately from the historical receipt.
5. Export populated state, import into an independent destination with existing different data, and verify retained tokens/references/receipts, removal of destination data/credentials, repeated import, invalid-import rollback and unchanged source snapshot.
6. Test DST gaps/folds, absolute duration, half-open adjacency, cutoff against current start, rollback, swaps, unchanged listed occupancy, and concurrent identical-key calls (one 201, all other successes 200).
7. After stage-1 QA accepts its committed revision and stage 2 is authorized: run the browser with out-of-order searches and a proxy that drops a committed response, then perform a real stage-1 export → stage-2 import between requests. The unchanged pending body/key must recover the original reference, with the existing token and current-user text retained. Verify required selectors, direct routes and 375px layout against the full stage-2 spec.

## Disposition

No incompatible design decision found in the approved architecture. The risks above need implementation evidence; stage-1 acceptance remains with independent QA. A read-only review of a committed backend revision is still required before claiming code-level conformance. The stage-2 build gate remains closed until stage-1 QA passes.
