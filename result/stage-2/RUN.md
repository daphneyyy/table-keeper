# Tablekeeper stage 2

From this directory, build and start the standalone service:

```sh
docker build -t tablekeeper-stage-2 .
docker run --rm --name tablekeeper-stage-2 --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 tablekeeper-stage-2
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

State is intentionally in memory and is lost on container restart. Run exactly one
application process: its state lock serializes reads, writes, and successful retry
receipts. Scrypt work is bounded and performed outside the state lock. Reservations
use UTC half-open intervals and absolute durations; local repeated times use the
first occurrence and nonexistent times are rejected.

`GET /_test/export` and `POST /_test/import` transfer complete state between independent
containers, including sessions, password hashes and original retry responses. These
unauthenticated test controls are enabled as required. Exports contain private test
credentials and must not be published. Snapshot envelope format is 1; the internal
state has a separate `schema_version: 2`. Stage-1 exports are accepted: live singles
gain `table_ids`, while saved request bodies and original responses remain untouched,
including old responses without `table_ids`. Session tokens and password hashes
remain valid. Import validates the entire candidate before replacing the destination.

Developer supplemental checks (against a running instance):

```sh
python3 tests/check_service.py http://127.0.0.1:8080
python3 tests/check_boundaries.py http://127.0.0.1:8080
python3 tests/check_combinations.py http://127.0.0.1:8080
```

This uses only Python's standard library. Official conformance checks are run by
the supplied harness, with this directory as the stage-2 Docker build context.
Both scripts accept a second service URL to verify import into another container.
JSON retry bodies preserve arbitrary numeric exponents without expanding their
values; historical timezone offsets containing seconds are rendered in UTC to
retain the instant while satisfying RFC3339.
