# Stage-1 HTTP implementation review

Read-only review of evolving, uncommitted backend code on 2026-09-27. Read `app/main.py`, `service.py`, `state.py` and `auth.py` in full, with the previously reviewed `rules.py`. Governing requirements remain the full stage-1 specification. This extends the earlier contract/design review and does not replace independent QA on a committed revision.

## Method and reproduction

Started a disposable instance using the existing `tablekeeper-stage-1-dev:latest` image for dependencies, with current `result/stage-1` mounted read-only at `/review`, working directory `/review`, `PYTHONDONTWRITEBYTECODE=1`, and entrypoint `python -m app.main`. Used a separate random localhost port. All mutations affected this isolated in-memory instance only. Stopped the container after the checks.

Reproduction script: `/Users/daphneyang/Desktop/GitHub/band-output/reviews/stage-1-http-review.py`. Run with the challenge `.venv/bin/python -B` and an isolated service base URL. It resets its target, uses synthetic fixture credentials, and prints no tokens or export payloads. It was run against `http://127.0.0.1:61820`. Code may have changed subsequently; these findings describe the observed snapshot.

Source SHA-256 values recorded after the run:

| File | SHA-256 |
|---|---|
| main.py | dbd42c18ca92cc2b9342fc8d6d207e34a923bee34d73b4534a5faf1fcebeb70f |
| service.py | c13c8d17052055b161b1c455e93c8ae9809b230c9adc5b426c97cd3d83448887 |
| state.py | 6abe272399eafe037ecb702c6cf1e0155dd663c84dab08dd06997d2762adafdf |
| auth.py | a9145010b0e53a093f77c03586dd5a084a37b20e832c5772072a06c2c6c2d7ca |

## Findings sent to Backend

### High: ignored large JSON numbers break export and retry identity

`main.py` parses request JSON using the default float decoder. A valid create body with an extra ignored field `"ignored": 1e400` succeeds with 201. The decoder converts the number to infinity, which is copied into the completed receipt body. `GET /_test/export` then returns **500 `internal_error`** because JSONResponse cannot serialize infinity. Sending the same key and a body with `"ignored": 2e400` returns **200**, even though it is a different JSON value and must return 409 `idempotency_key_reuse`.

Requirements implicated: stage-1 §3.4 unknown fields ignored, §5 no 5xx, §7 full parsed-body equality, §10 export of all successful receipt bodies. Preserve JSON numbers without lossy float overflow in decoding, comparison and snapshot encoding; simply rejecting the unknown field would conflict with the unknown-field rule. Add a regression that exports/imports the large-number receipt and proves distinct numeric values cannot replay each other.

### Medium: framework method errors bypass the required envelope

`TRACE /health` returns **405 `{"detail":"Method Not Allowed"}`**, because the request never enters the catch-all endpoint. Stage-1 §5 requires the `{error:{code,message}}` envelope for every 4xx/5xx. Although TRACE is not a required application operation, any returned failure still needs the common shape. Register a framework HTTPException handler; the spec does not prescribe a particular code for unsupported methods.

### Medium: low calendar years fail availability formatting

With ordinary Monday opening hours, `GET /availability?restaurant_id=r&date=0001-01-01&party_size=2` returns **422 `validation_failed`**. `service.py` builds local strings using `strftime('%Y-%m-%dT%H:%M')`; the Linux runtime emits year `1` rather than `0001`, then the shared validator rejects its own generated string. The request date itself is a valid `YYYY-MM-DD`, and §4 allows any calendar date without rejecting solely because it is in the past. Use an explicitly four-digit year or `isoformat(timespec='minutes')`. Verify availability's local strings remain directly bookable for early years too.

## Passing focused HTTP checks

- All three public GET routes work without a token and send the specified JSON charset.
- Two logins produce simultaneously usable bearer tokens.
- Create → PATCH → cancel → repeat cancel succeeds; unchanged-key replay returns the exact original response, not the amended/cancelled current state.
- Export → reset invalidates old tokens; import restores both tokens and the original receipt.
- Invalid-import rejection leaves the destination reservation unchanged.
- A used key with an invalid changed party size yields reuse conflict before field validation.

Output from the isolated run:

```text
PASS public browsing/charset, simultaneous tokens, amend/cancel original replay, reset invalidation, import restoration and invalid-import rollback
large ignored number create 201 non-error-envelope
export after large ignored number 500 internal_error
different large ignored number same key 200 non-error-envelope
unsupported TRACE method 405 non-error-envelope
year 0001 availability 422 validation_failed
```

`non-error-envelope` is the script's label for a response lacking `error.code`; on a successful create/replay it is expected. On the TRACE failure it marks the envelope defect.

## Limits and disposition

This is a focused integration review, not the full conformance/concurrency suite or a clean image-build verification. The inspected source is evolving and uncommitted. The large-number snapshot/retry defect should be fixed before acceptance; the two boundary defects should also be corrected. Backend received exact triggers and the reproduction script. No frontend or backend implementation files were changed by this review.
