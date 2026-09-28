# Focused independent verification of repaired contracts

Reviewed revision: `8a03d186c658a4c777dc90c15b2eac0e5b9f3e8a`.

All three findings from `stage-1-http-implementation-review.md` are independently verified fixed. No remaining blocker from this focused review; independent QA owns full stage acceptance.

## Evidence

Confirmed `git diff --exit-code 8a03d186c658a4c777dc90c15b2eac0e5b9f3e8a -- result/stage-1` was empty before/after checking. Used a disposable container with that source mounted read-only, working directory `/review`, bytecode writes disabled, and `python -m app.main`. Dependency image: `tablekeeper-stage-1-dev:latest`, image ID `sha256:4f1798ec69db8c340de2eecf60072a5d49e243e2a970461bdcf8b71d90b8b99c`. Container stopped after verification. No backend files modified.

Command:

```sh
/Users/daphneyang/Desktop/GitHub/dark-factory-wearedevs/.venv/bin/python -B reviews/stage-1-http-review.py http://127.0.0.1:62770
```

Exit code: 0. Output:

```text
PASS public browsing/charset, simultaneous tokens, amend/cancel original replay, reset invalidation, import restoration and invalid-import rollback
large ignored number create 201 non-error-envelope
export after large ignored number 200 non-error-envelope
different large ignored number same key 409 idempotency_key_reuse
PASS large-number export/import retains original receipt and numeric distinction
unsupported TRACE method 405 method_not_allowed
year 0001 availability 200 non-error-envelope
PASS early-year availability can be booked unchanged
```

The reproduction script now asserts repaired behavior rather than merely printing the former defect responses. Its added raw-byte export/import check avoids the test client's own lossy floating-point decoder. The imported receipt replays the original success under the retained token, while a changed large number still receives 409. Early-year availability is also submitted unchanged to create and succeeds with 201. Unsupported-method responses have the required error object and nonempty message.

Scope: focused HTTP integration regression, not a repeat of the full supplied suite, clean-build verification, concurrency acceptance or stage-2 browser testing. The original finding report remains historical evidence; this document closes its three findings.
