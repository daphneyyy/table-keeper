# Tablekeeper

Tablekeeper is a restaurant reservation service with a responsive customer website. Diners search by restaurant, date and party size, select a table or supported table combination, confirm a booking, and retrieve or cancel it using their account and confirmation reference.

The final implementation is [`stage-4/`](stage-4/). It includes all earlier capabilities and adds atomic seating repairs after a table closure and amendments to recurring bookings. These advanced operations use the API. The website provides search, signup/login, booking, confirmation and lookup/cancellation, without dedicated manager or recurring-booking screens.

## Run the final application

Requirements: Git and a running Docker installation. From this directory:

```sh
docker build -t tablekeeper-stage-4 ./stage-4
docker run --rm --name tablekeeper-stage-4 --cpus 2 --memory 2g -e PORT=8080 -p 127.0.0.1:8080:8080 tablekeeper-stage-4
```

Open [http://localhost:8080/](http://localhost:8080/). Direct routes also include `/signup`, `/login` and `/lookup`. `GET /health` returns `{"status":"ok"}`. For another port, change both the `PORT` value and the container port mapping. See [`stage-4/RUN.md`](stage-4/RUN.md) for the full runtime contract and supplemental checks.

The service starts empty. To try the website, run this demo reset in a second terminal. It replaces all existing state in this local instance and creates one synthetic restaurant, open every Monday:

```sh
curl --fail-with-body -X POST http://localhost:8080/_test/reset \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "users": [],
  "restaurants": [{
    "id": "demo_restaurant",
    "name": "Tablekeeper Demo",
    "timezone": "Europe/Berlin",
    "slot_minutes": 30,
    "reservation_duration_minutes": 90,
    "cancellation_cutoff_minutes": 60,
    "opening_hours": [{"weekday": "mon", "opens": "18:00", "closes": "23:00"}],
    "tables": [
      {"id": "window", "label": "Window", "capacity": 2},
      {"id": "garden", "label": "Garden", "capacity": 4}
    ],
    "combinable": [["window", "garden"]]
  }],
  "reservations": []
}
JSON
```

Create an account in the website, search a future Monday with a party size of two, select a time and reserve. Keep the confirmation reference, then use My reservation to retrieve or cancel the booking. All displayed booking times are local to the restaurant. A selection alone does not reserve a table.

## Delivered stages

| Folder | Capability added | Applicable cumulative tests passed |
|---|---|---:|
| [`stage-1/`](stage-1/) | Reservation API, accounts, atomic moves, retries and state transfer | 120 |
| [`stage-2/`](stage-2/) | Customer website, table combinations and browser recovery | 145 |
| [`stage-3/`](stage-3/) | Dated policies, accepted terms, history and recurring reservations | 152 |
| [`stage-4/`](stage-4/) | Closure preview/application and recurring amendments | 158 |

Each folder contains its own source, dependencies, `Dockerfile` and `RUN.md`. Later stages extend copies of accepted earlier stages. Each folder builds independently, without importing its siblings.

Recorded independent QA accepted product revision `3995a95edcf221e3604816c4f56fd0c467145597`. The final four-folder run passed **575 cumulative test executions**, not 575 distinct tests. Stage 4 passed all **158 applicable supplied tests**, plus independent browser, migration, concurrency and bounded optimization checks. QA records these results in the [collaboration log](room.json), including final acceptance message `ff4d16b2-4044-4216-b2a8-b2c06cf2536d`. Hidden organizer tests are outside this evidence.

- [Bundled Stage 4 developer test report](stage-4/tests/evidence/report.json)
- [Supplemental test scripts](stage-4/tests/)
- [Factory and repair workflow](FACTORY.md)
- [Role mandates](mandates/)
- [Agent collaboration log](room.json)

## Implementation and limits

The application uses Python, FastAPI and Uvicorn, with same-origin HTML/CSS/JavaScript. One application process coordinates an in-memory state store. A shared lock protects state transitions and successful retry receipts. The container bundles browser assets, runtime dependencies and timezone data and needs no outbound runtime services.

State disappears on container restart. Run one application process. Successful retry responses retain the original receipt, while current reservation reads show subsequent changes. Stage 4 supports state imported from the team's actual earlier implementations. Closure planning supports up to six tables, four declared pairs and six considered bookings.

The required test reset/export/import controls are unauthenticated. Exported state includes session and credential material. The startup example binds to localhost for demonstration. Persistent storage, public deployment hardening and protection or removal of test controls would require additional work.

## Run the bundled checks

With the local application running, execute the supplemental HTTP checks from this repository root using Python 3:

```sh
python3 stage-4/tests/check_service.py http://127.0.0.1:8080
python3 stage-4/tests/check_boundaries.py http://127.0.0.1:8080
python3 stage-4/tests/check_combinations.py http://127.0.0.1:8080
python3 stage-4/tests/check_policies_series.py http://127.0.0.1:8080
python3 stage-4/tests/check_replans_series_amend.py http://127.0.0.1:8080
python3 stage-4/tests/check_stage4_boundaries.py http://127.0.0.1:8080
```

These checks reset their target and use synthetic accounts. Run them against a disposable local instance. The HTTP scripts use Python's standard library. The optimizer check requires the service dependencies and runs from `stage-4/` with `PYTHONPATH=. python3 tests/check_optimizer.py`. See [RUN.md](stage-4/RUN.md) for details.

The bundled [developer report](stage-4/tests/evidence/report.json) records the cumulative isolated run at revision `e54d968326a43ae0db64839b725c7375f6166644`. Independent QA's subsequent acceptance at revision `3995a95edcf221e3604816c4f56fd0c467145597` is recorded in [room.json](room.json). The official challenge harness is not bundled in this repository.

## Repository contents

| Path | Contents |
|---|---|
| `stage-1/` through `stage-4/` | Standalone application stages with source, packaging and startup instructions |
| [mandates/](mandates/) | Five reusable role mandates |
| [room.json](room.json) | Task dispatch, planning, implementation handoffs, reviews and delivery |
| [stage-4/tests/](stage-4/tests/) | Supplemental verification scripts |
| [stage-4/tests/evidence/](stage-4/tests/evidence/) | Bundled developer test results |
| [FACTORY.md](FACTORY.md) | Factory setup, workflow, repair examples, timing and cost |

The build took approximately two hours from task dispatch to delivery, with estimated usage of 18.8 million tokens and US$29.68 in model spend.
