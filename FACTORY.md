# A five-role software factory

This factory separates planning, implementation and independent verification. Team Lead owns delivery and routes work. Architect turns requirements into a plan. Backend Engineer and Frontend Engineer implement within explicit file ownership. QA Engineer accepts or rejects a frozen committed revision using reproducible evidence.

The factory produced the four Tablekeeper stages. The final recorded product revision is `3995a95edcf221e3604816c4f56fd0c467145597`, independently accepted with 158 applicable tests for Stage 4 and 575 cumulative executions across all four folders. The [product README](README.md) explains the application and startup.

## Configuration and ownership

All five seats use **Codex**, model **`gpt-6-astra`**, with **medium** reasoning effort. Each mandate defines responsibilities, handoff requirements and acceptance rules. Domain-specific requirements belong in the task dispatch so the same mandates can support other projects.

| Seat | Ownership | Mandate |
|---|---|---|
| Team Lead | Planning handoff, file ownership, integration, repair routing and delivery status | [team-lead.md](mandates/team-lead.md) |
| Architect | Complete requirements review, delivery plan, dependencies and risks | [architect.md](mandates/architect.md) |
| Backend Engineer | Service behavior, state consistency, packaging and focused checks | [backend-engineer.md](mandates/backend-engineer.md) |
| Frontend Engineer | Browser interfaces, real-service integration and focused browser checks | [frontend-engineer.md](mandates/frontend-engineer.md) |
| QA Engineer | Independent verification, consolidated rejection/acceptance and preserved evidence | [qa-engineer.md](mandates/qa-engineer.md) |

## Recreate the factory

1. Prepare Band Desktop, Git, a running Docker daemon, and model-provider access. For this challenge, also prepare Python 3.12+, the supplied harness dependencies and Playwright Chromium. Keep the challenge package separate from the output checkout.
2. Create five distinct seats using the names above. Select Codex, `gpt-6-astra` and medium reasoning for each. Assign the corresponding mandate file. Seat names describe the roles; use the actual handles that Band assigns for communication.
3. Give every seat access to the same absolute output checkout and complete requirements. Prepare Git identity and the filesystem, container and browser permissions needed for the run. Keep provider credentials outside the product and its history.
4. Confirm direct mentions reach the intended seats and receive replies. Use one shared room for the staged delivery. The collaboration log records direct handoffs and replies between the roles.
5. Dispatch the complete task to Team Lead, including absolute requirement paths, output location, acceptance criteria, packaging requirements and stage boundaries. The Lead first requests an Architect plan, reviews it, then assigns implementation ownership and integration contracts.
6. Keep domain requirements in the dispatch and plan, not the mandates. Include complete applicable requirements in handoffs, or accessible absolute references with the full applicable text when a recipient cannot access a source.
7. Let implementers commit focused changes and return the full revision, artifact locations, executed checks and limitations. The Lead hands the integrated committed revision to QA. QA verifies a frozen checkout and reports reproducible results without silently repairing product code.
8. Route each rejection to the responsible implementer. Require a new commit and independent re-verification. Preserve the rejected evidence. Advance a stage only after acceptance, copying the accepted folder unchanged before extending the copy.
9. Finish with a clean-checkout cumulative run and standalone startup checks. Export the room after completion, retain original Git history, and package the documentation and evidence separately from product implementation.

Configure the required filesystem, Git, container and browser access before the run. Seats resolve decisions within those permissions and report blockers with evidence.

## Why this structure

**One coordinator with explicit ownership.** Backend owned service code, packaging and associated checks. Frontend owned static assets or narrowly scoped review artifacts. In later stages, the Lead authorized specific integration fixes instead of a broad UI rewrite. This kept concurrent changes separate and preserved earlier stages.

**Independent acceptance.** Passing developer checks did not clear a stage. QA used the supplied harness unchanged and added specification-derived probes. The extra pass cost time and model usage, but caught a visible defect after all 145 applicable supplied checks already passed.

**Sequential stages with parallel work inside a stage.** The factory retained an accepted implementation, committed its unchanged copy, then extended it. Frontend could review integration while Backend implemented new service behavior. QA used frozen revisions so ongoing work could not change the candidate underneath a test.

**Real integration and immutable evidence.** Browser recovery tests exercised the actual service and dropped responses, rather than a simulated success path. Upgrade tests populated real earlier implementations and terminated the source before checking the destination. Successful receipts and current state were tested separately.

**A shared model with different responsibilities.** All seats use the same model and reasoning setting. Specialization comes from role ownership and acceptance rules, keeping runtime configuration consistent across the team.

## A rejected result and its recovery

Stage 2's initial candidate `cf4f6c4199cfb1c83353c8b2967f4b268cc1ddb6` passed all 145 applicable supplied tests and functional integration checks. QA still rejected it because small booking-card text had insufficient contrast under QA's 4.5:1 normal-text benchmark. The specification required sufficient contrast but did not itself supply that numeric threshold.

The browser rendered `#687065` text on `#efeee4`, measuring **4.401412:1** at both 375px and 1440px. A more specific paragraph selector overrode the intended fine-print color. QA provided measured values, screenshots and a reproduction rather than making the fix itself.

| UTC on 2026-09-28 | Recorded action |
|---|---|
| 05:48:53 | QA reported the contrast blocker to Lead. |
| 05:49:01 | QA rejected Stage 2 and kept Stage 3 gated. |
| 05:49:17 | Lead assigned a scoped static-asset repair to Frontend. |
| 05:50:25 | Frontend returned commit `42a2b990f8b203fd2141db4a2e8b502313ff3791`. |
| 05:50:47 | Lead handed that exact revision to QA for re-verification. |
| 05:53:34 | QA accepted the fix and cleared the next-stage gate. |

The fix changed one CSS color to `#596252`. Independent browser measurements rose to **5.4711559863:1** in both viewports. QA reran contrast, browser recovery, migration and cumulative isolated checks and confirmed that the backend and earlier stage were unchanged. The interval from the first blocker message to acceptance was approximately **4 minutes 41 seconds**.

Evidence: [rejection](evidence/STAGE-2-cf4f6c41-REPORT.md), [acceptance](evidence/STAGE-2-42a2b990-REPORT.md), and the corresponding room messages `4330e8a9-9af9-4da7-9eba-2ab533a2d9d4`, `58e17743-9685-41e1-9563-70f00581d1ba`, `70c463c3-2f50-4493-9d9d-ea8e04b81817` and `fa0b58c0-1ea7-41f7-9bef-217312b4a744`.

## A later integration failure

Stage 4 exposed a subtler difference between the original booking receipt and current seating. After an operator repaired seating, retrying the original successful request correctly returned the original receipt, but the inherited confirmation UI showed that historical table as current.

Frontend reproduced the mismatch against a real service. Lead authorized a change only to Stage 4's `app/static/app.js`. The fix preserved the original receipt and retry identity, then separately fetched current reservation details for display. If that read failed, the UI kept the confirmed reference and explicitly labeled the original details. Guards prevented a late response from overwriting a newer attempt.

The correction is commit `1a96fceb69c1110b557a01bfdc30f452759717c9`. The [compatibility review](evidence/stage-4-compatibility-review.md) records the initial reproduction and fix. [Independent Stage 4 QA](evidence/STAGE-4-3995a95e-REPORT.md) verified current seating, failed supplementary reads, delayed responses and prior recovery behavior in the final candidate.

QA also preserved its own unsuccessful setup attempts: the first optimizer probe expected a private field in a public response, and another ran before service readiness. QA corrected the probe and readiness handling, then reran successfully. These were test-setup failures, not product defects or passing runs.

## Cost and usage

Estimated usage for the factory run:

| Tokens | Estimated model spend | Configured agents |
|---:|---:|---:|
| 18.8 million | US$29.68 | 5 |

| Seat | Estimated spend |
|---|---:|
| Backend Engineer | US$10.75 |
| QA Engineer | US$6.80 |
| Team Lead | US$5.04 |
| Frontend Engineer | US$4.74 |
| Architect | US$2.35 |
| **Total** | **US$29.68** |

The token count is rounded and spend is estimated. Per-seat token counts and input/output/cache splits are unavailable. The estimate covers the factory run and excludes infrastructure, human time, and subsequent presentation or documentation work.

## Timing and delivery

The [room log](room.json) records one human task dispatch followed by planning, implementation, review, repairs and final delivery. No later human steering appears in the recorded conversation.

| Milestone | UTC on 2026-09-28 |
|---|---|
| Task dispatched | 04:51:08 |
| Independent final acceptance | 06:50:37 |
| Lead reported delivery complete | 06:51:12 |

Dispatch to delivery took **2 hours 4 seconds**. This is wall-clock elapsed time, excluding preparation before dispatch and later submission work. Parallel seat activity means it should not be interpreted as summed compute time.

The log contains 2,170 events across the five seats, including 811 tool calls and their results. The [final chain report](evidence/FINAL-CHAIN-3995a95e-REPORT.md) records 120/145/152/158 passing cumulative executions and standalone startup with no outbound network, a custom port, no mounts and 2 CPU/2 GiB limits.

## Evidence

- [room.json](room.json): task dispatch, inter-agent handoffs, review decisions and delivery.
- [Stage 2 rejection](evidence/STAGE-2-cf4f6c41-REPORT.md) and [acceptance](evidence/STAGE-2-42a2b990-REPORT.md): measured contrast failure and independent verification of the repair.
- [Stage 4 compatibility review](evidence/stage-4-compatibility-review.md): current-seating display correction and browser recovery checks.
- [Stage 4 QA](evidence/STAGE-4-3995a95e-REPORT.md) and [final chain report](evidence/FINAL-CHAIN-3995a95e-REPORT.md): cumulative verification at the accepted revision.

Reports retain the original paths and commands used during verification. Detailed probes and screenshots are in the parent repository's `qa/`, `reviews/` and `checks/` directories. The `checks/` directory is ignored by Git, so its contents require separate inclusion when distributing the full evidence set. Test results describe the recorded environments and scenarios; hidden organizer tests are outside this evidence.
