# Tablekeeper stage 1

From this directory, build and start the standalone service:

```sh
docker build -t tablekeeper-stage-1 .
docker run --rm --name tablekeeper-stage-1 --cpus 2 --memory 2g -e PORT=8080 -p 8080:8080 tablekeeper-stage-1
```

`GET http://localhost:8080/health` returns `{"status":"ok"}`. No manual setup,
external service, volume, or outbound runtime access is required. All dependencies
and IANA timezone data are installed during the image build. To use another port,
change both `-e PORT=9090` and `-p 9090:9090`.

The service initially has no users or restaurants. POST the stage-1 fixture JSON
to `/_test/reset` to atomically initialize it. Signup/login issue nonexpiring bearer
tokens; public restaurant/availability reads do not require them. All errors use
the specified JSON error envelope. POST `/reservations` and `/reservation-moves`
require `Idempotency-Key`.

State is intentionally in memory and is lost on container restart. Run exactly one
application process: its state lock serializes reads, writes, and successful retry
receipts. Scrypt work is bounded and performed outside the state lock. Reservations
use UTC half-open intervals and absolute durations; local repeated times use the
first occurrence and nonexistent times are rejected.

`GET /_test/export` and `POST /_test/import` transfer complete state between independent
containers, including sessions, password hashes and original retry responses. These
unauthenticated test controls are enabled as required. Exports contain private test
credentials and must not be published. Snapshot envelope format is 1; the internal
state has a separate `schema_version: 1` for future migrations. Import validates the
entire candidate before replacing the destination.

Developer supplemental checks (against a running instance):

```sh
python3 tests/check_service.py http://127.0.0.1:8080
```

This uses only Python's standard library. Official conformance checks are run by
the supplied harness, with this directory as the stage-1 Docker build context.
