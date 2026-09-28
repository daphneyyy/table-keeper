# Tablekeeper stage 4

From this directory, build and start the standalone service:

```sh
docker build -t tablekeeper-stage-4 .
docker run --rm --name tablekeeper-stage-4 --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 tablekeeper-stage-4
```

Open `http://localhost:8080/` to search and book. Signup, login and lookup are also
directly available at `/signup`, `/login` and `/lookup`. Browser assets are bundled
under `app/static/` and served from the same origin without a CDN.

`GET http://localhost:8080/health` returns `{"status":"ok"}`. No manual setup,
external service, volume, or outbound runtime access is required. All dependencies
and IANA timezone data are installed during the image build. To use another port,
change both `-e PORT=9090` and `-p 9090:9090`.

The service initially has no users or restaurants. POST the stage-1 fixture JSON
to `/_test/reset` to atomically initialize it. Signup/login issue nonexpiring bearer
tokens; public restaurant/availability reads do not require them. All errors use
the specified JSON error envelope. POST `/reservations` and `/reservation-moves`
require `Idempotency-Key`.

Fixtures may declare `combinable` pairs. Requests accept `table_id` or `table_ids`
(never both); declared pairs normalize to fixture order and occupy both members.
Availability exposes singles and eligible pairs in `available_options`. Cancels,
amendments and atomic moves update the entire table set together.

Stage 3 adds public policy listing and `explain=true` availability. Fixture
`manager_user_ids` may publish complete dated policies with an idempotency key.
Bookings retain accepted terms until a real amendment adopts the resulting date's
policy. Owner-only history and decision endpoints expose revisions and terms;
optional `expected_revision` prevents stale amendments. `/series` atomically adopts
an editable reservation and generates recurring local-calendar occurrences.
Individual edits permanently mark exceptions; cancellation affects only that
occurrence. Batch writes update each affected series counter once.

Stage 4 adds manager-only idempotent closure preview and application at
`/restaurants/{id}/replans` and `/restaurants/{id}/replans/{plan_id}/apply`.
The exact search supports six tables, four pairs and six considered bookings. It
minimizes changed assignments, unused seats under each booking's accepted terms,
then the reference-ordered option ranks. Previews reserve nothing. Applying a plan
atomically installs its closure and assignments, retaining accepted terms and times.
Restaurant revisions detect stale plans; successful receipts remain replayable.

Owner-only `POST /series/{series_id}/amend` requires an idempotency key and
`expected_revision`, `from_index`, and `local_time`. Eligible occurrences retain
their original scheduled dates and current tables; cancelled members and exceptions
are skipped. All validation precedes commit. Real changes adopt their date's policy,
while no-ops retain terms. Series amendments and seating repairs preserve exception
flags and increment each affected series once.

State is intentionally in memory and is lost on container restart. Run exactly one
application process: its state lock serializes reads, writes, and successful retry
receipts. Scrypt work is bounded and performed outside the state lock. Reservations
use UTC half-open intervals and absolute durations; local repeated times use the
first occurrence and nonexistent times are rejected.

`GET /_test/export` and `POST /_test/import` transfer complete state between independent
containers, including sessions, password hashes and original retry responses. These
unauthenticated test controls are enabled as required. Exports contain private test
credentials and must not be published. Snapshot envelope format is 1; the internal
state has a separate `schema_version: 4`. Actual stage-1 and stage-2 exports are
accepted: live records gain revision 1, policy-0 accepted terms and a baseline
history entry. Earlier stages did not record histories, so that entry represents
the imported current fields; unknown past amendments/cancellation times are not
invented. Stage-1 live singles also gain `table_ids`. Saved request bodies and
original responses remain untouched, including old responses without `table_ids`,
`revision` or `accepted_terms`. Session tokens and password hashes remain valid.
Actual stage-3 exports also retain complete policies, series, histories and revisions,
including individually changed and cancelled occurrences. New snapshots retain
plans and closures as well. Import validates the entire candidate before replacing
the destination.

Developer supplemental checks (against a running instance):

```sh
python3 tests/check_service.py http://127.0.0.1:8080
python3 tests/check_boundaries.py http://127.0.0.1:8080
python3 tests/check_combinations.py http://127.0.0.1:8080
python3 tests/check_policies_series.py http://127.0.0.1:8080
python3 tests/check_replans_series_amend.py http://127.0.0.1:8080
python3 tests/check_stage4_boundaries.py http://127.0.0.1:8080
PYTHONPATH=. python3 tests/check_optimizer.py
```

HTTP checks use only Python's standard library. The optimizer oracle runs with the
service dependencies installed, or inside its image with this directory mounted
read-only and `PYTHONPATH` set to the mount path. It compares the production solver
with independent exhaustive Cartesian-product enumeration over 594 small cases.
`check_replans_series_amend.py` accepts extra URLs for actual stage-1, stage-2 and
stage-3 instances to populate and migrate. Tests cover exact receipt round-trips,
changed/cancelled imported series, atomic races, closures and failed-key reuse. Official conformance checks are run by
the supplied harness, with this directory as the stage-4 Docker build context.
The inherited `check_service.py` and `check_boundaries.py` scripts accept a second
service URL to verify import into another container. `check_combinations.py`
instead accepts an optional second URL pointing to an actual stage-1 service,
which it populates and exports to test migration into the primary service URL.
`check_policies_series.py` accepts extra URLs for running actual earlier-stage
services and checks migration/adoption into its primary stage-4 URL. All developer
scripts reset their targets and use synthetic test accounts; do not point them at
state you wish to retain.
JSON retry bodies preserve arbitrary numeric exponents without expanding their
values; historical timezone offsets containing seconds are rendered in UTC to
retain the instant while satisfying RFC3339.
