# Stage-4 developer verification

Runtime revision: `e54d968326a43ae0db64839b725c7375f6166644`.
Unchanged stage-3 inheritance: `f9c60632a8bb4ff2201f6d65f8638b98765e9c36`.
Integrated Frontend confirmation correction: `1a96fceb69c1110b557a01bfdc30f452759717c9`.
The evidence-only follow-up commit does not change runtime source, dependencies,
Dockerfile, tests, or browser assets.

## Packaged image and cumulative checks

Built `tablekeeper-stage-4-final`, image
`sha256:5cc7534349f063409b13b73a8de650a319213a5eec66ea0c104000084f4a8d69`.
Ran the unchanged supplied harness with `--stage 4 --mode isolated` against the
result root: **158 passed**, comprising 120 stage-1, 25 stage-2, 7 stage-3 and 6
stage-4 checks. Report: [evidence/report.json](evidence/report.json).
Complete local logs:
`/Users/daphneyang/Desktop/GitHub/band-output/checks/backend-s4-e54d968-final/`.

The image starts with a custom PORT, serves API and bundled HTML with Docker
`--network none`, and was run with 2 CPUs / 2 GiB. No runtime source mount was used
for final checks. [Offline evidence](evidence/offline.log).

## Additional specification-derived checks

- [Optimizer oracle](evidence/optimizer.log): 594 comparisons against independent
  exhaustive Cartesian-product enumeration. Exhausted 2/4-seat capacity
  configurations through four tables and added 300 seeded cases with mixed
  per-booking accepted capacities, pairs, fixed records and existing closures.
- [Stage-4 HTTP checks](evidence/check_replans_series_amend.log): preview purity,
  authorization and strict errors, fixed/half-open boundaries, closures excluding
  singles and pairs, reassigned histories, exact immutable receipts, snapshot
  round-trips, stale/infeasible rollback, empty plans, 30 concurrent applications,
  30 concurrent series amendments, cancelled/exception skips, original dates,
  retained repaired tables, nonoccupancy error precedence and all-or-nothing
  failures. Actual stages 1, 2 and 3 were populated and exported by separate
  containers, then imported and amended with original tokens, hashes and receipts.
  Stage-3 migration included individually changed and cancelled series members.
- [Boundaries](evidence/check_stage4_boundaries.log): exact supported 6-table,
  4-pair, 6-considered-booking boundary; all three planning limits; accepted
  capacities despite policy shrink; operator repairs after cutoff; corrupted
  plan/closure/history/receipt import rollback; unrelated-restaurant revisions;
  fixed conflicts outside the proposed closure interval; empty eligible sets and
  expired no-ops; stale-before-cutoff; New York/Berlin series gap rollback.
- Inherited [service](evidence/check_service.log), [numeric/time boundaries](evidence/check_boundaries.log),
  [combinations](evidence/check_combinations.log) and [policies/series](evidence/check_policies_series.log)
  supplemental suites also passed against the final image.

Frontend separately exercised real browser repairs, supplementary-read failure,
stale detail responses, stage-1/2/3 upgrade retries and inherited browser flows.
Its committed report is
`/Users/daphneyang/Desktop/GitHub/band-output/reviews/stage-4-compatibility-review.md`.

No stage-1, stage-2 or stage-3 files changed from accepted stage-3 revision
`70a9c89ff681bb9ac0c2b91a44cc6cca9a877c61`. `git diff --check` passed.
Developer evidence is not independent QA acceptance. The documented planner limits
are enforced; state remains intentionally in-memory as permitted by the spec.
