# A five-role software factory

This factory separates planning, implementation and independent verification. Team Lead owns delivery and routes work. Architect turns requirements into a plan. Backend Engineer and Frontend Engineer implement within explicit file ownership. QA Engineer accepts or rejects a frozen committed revision using reproducible evidence.

The factory produced the four Tablekeeper stages. The final recorded product revision is `3995a95edcf221e3604816c4f56fd0c467145597`, independently accepted with 158 applicable tests for Stage 4 and 575 cumulative executions across all four folders. The [product README](README.md) explains the application and startup.

## Configuration and ownership

The operator supplied the following configuration: **all five seats use Codex, model `gpt-6-astra`, reasoning effort `medium`**. The mandate files preserve the supplied role instructions, with runtime metadata added and the Lead's developer-role names aligned to the Engineer seat names. They contain no track-specific interfaces or requirements.

| Seat | Ownership | Mandate |
|---|---|---|
| Team Lead | Planning handoff, file ownership, integration, repair routing and delivery status | [team-lead.md](mandates/team-lead.md) |
| Architect | Complete requirements review, delivery plan, dependencies and risks | [architect.md](mandates/architect.md) |
| Backend Engineer | Service behavior, state consistency, packaging and focused checks | [backend-engineer.md](mandates/backend-engineer.md) |
| Frontend Engineer | Browser interfaces, real-service integration and focused browser checks | [frontend-engineer.md](mandates/frontend-engineer.md) |
| QA Engineer | Independent verification, consolidated rejection/acceptance and preserved evidence | [qa-engineer.md](mandates/qa-engineer.md) |

The complete export supplied as `final.json` records join events and messages for all five configured seats. This directory preserves it unchanged as `room.json`:

| Observed seat | Band sender identity |
|---|---|
| Team Lead | `d0dd773f-c3bd-4b49-82cf-c12190c56672` |
| Architect | `afa04c6d-9f41-4b85-adbf-5fa1d3838433` |
| Backend Engineer | `8ba99f3f-8c06-4625-8992-7545eeb4e699` |
| Frontend Engineer | `74a32ff1-92ed-49b0-a72d-3796b3027734` |
| QA Engineer | `a88ab9c1-8286-4099-8851-b06b5be3a0e2` |

Architect's participation is directly recorded. At 04:51:34 UTC, Lead delegated planning to Architect. At 04:56:20–04:56:21 UTC, Architect returned the stage-1 design and complete sequential delivery plan, identifying `plan.md` and `architecture.json` as the published artifacts. At 04:57:29–04:57:31 UTC, Lead approved the design and full plan and confirmed implementation ownership. Architect reported no product-code implementation, consistent with the role boundary.

The planning exchange is traceable through messages `8de1116d-6c6a-43d4-859e-bb5d70b2b5da`, `b95e00b4-831b-40f2-9456-6dc51d7ac7d1`, `58f0f046-88f2-4e0d-8200-71280da66fdf` and `71e28897-6cc2-40f2-b4c4-c0a33877fb86`. Runtime/model settings remain operator-reported, rather than independently verified from a per-seat runtime manifest.

## Recreate the factory

1. Prepare Band Desktop, Git, a running Docker daemon, and model-provider access. For this challenge, also prepare Python 3.12+, the supplied harness dependencies and Playwright Chromium. Keep the challenge package separate from the output checkout.
2. Create five distinct seats using the names above. Select Codex, `gpt-6-astra` and medium reasoning for each. Assign the corresponding mandate file. Seat names describe the roles; use the actual handles that Band assigns for communication.
3. Give every seat access to the same absolute output checkout and complete requirements. Prepare Git identity and the filesystem, container and browser permissions needed for the run. Keep provider credentials outside the product and its history.
4. Confirm direct mentions reach the intended seats and receive replies. Use one shared room for the staged delivery. The reviewed export demonstrates reciprocal Lead/Architect, Lead/QA, Lead/Backend, Lead/Frontend and Frontend/Backend communication.
5. Dispatch the complete task to Team Lead, including absolute requirement paths, output location, acceptance criteria, packaging requirements and stage boundaries. The Lead first requests an Architect plan, reviews it, then assigns implementation ownership and integration contracts.
6. Keep domain requirements in the dispatch and plan, not the mandates. Include complete applicable requirements in handoffs, or accessible absolute references with the full applicable text when a recipient cannot access a source.
7. Let implementers commit focused changes and return the full revision, artifact locations, executed checks and limitations. The Lead hands the integrated committed revision to QA. QA verifies a frozen checkout and reports reproducible results without silently repairing product code.
8. Route each rejection to the responsible implementer. Require a new commit and independent re-verification. Preserve the rejected evidence. Advance a stage only after acceptance, copying the accepted folder unchanged before extending the copy.
9. Finish with a clean-checkout cumulative run and standalone startup checks. Export the room after completion, retain original Git history, and package the documentation and evidence separately from product implementation.

The mandates ask seats to resolve decisions within granted permissions and report blockers rather than wait for human steering. That instruction does not expand filesystem or service permissions. The operator must configure the required access before an autonomous run.

## Why this structure

**One coordinator with explicit ownership.** Backend owned service code, packaging and associated checks. Frontend owned static assets or narrowly scoped review artifacts. In later stages, the Lead authorized specific integration fixes instead of a broad UI rewrite. This kept concurrent changes separate and preserved earlier stages.

**Independent acceptance.** Passing developer checks did not clear a stage. QA used the supplied harness unchanged and added specification-derived probes. The extra pass cost time and model usage, but caught a visible defect after all 145 applicable supplied checks already passed.

**Sequential stages with parallel work inside a stage.** The factory retained an accepted implementation, committed its unchanged copy, then extended it. Frontend could review integration while Backend implemented new service behavior. QA used frozen revisions so ongoing work could not change the candidate underneath a test.

**Real integration and immutable evidence.** Browser recovery tests exercised the actual service and dropped responses, rather than a simulated success path. Upgrade tests populated real earlier implementations and terminated the source before checking the destination. Successful receipts and current state were tested separately.

**A shared model with different responsibilities.** All seats used the same operator-reported model and reasoning setting. Specialization came from ownership and acceptance rules. No model comparison was measured, so the evidence does not establish that this configuration minimizes cost.

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

The operator supplied this room-level estimate:

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

The seat estimates sum to the reported total. The token count is rounded, and no per-seat token breakdown, input/output/cache split, billing invoice or pricing calculation was supplied. These values are reported estimates, not costs reconstructed from message count or independently audited charges. The complete log confirms Architect participation, but does not provide a per-event billing breakdown for attributing the estimate to individual actions. Infrastructure and human time are not quantified. This estimate is for the reported factory room, not the subsequent presentation or documentation work.

## Timing and delivery evidence

The complete `final.json` export, copied unchanged to `room.json`, has **2,170 events**: 5 participant events, 115 text messages, 99 thought messages, 811 tool calls, 811 tool results and 329 task events. Its observed interval is **2026-09-28 04:50:45.649–06:51:22.195 UTC**, or **2 hours 0 minutes 36.546 seconds**. In Los Angeles, that is September 27, 21:50:45–23:51:22 PDT.

The first events record the five seats joining. The single human task dispatch is message `4d072cef-25a6-47b1-998f-b735ed7f6e03`, at **04:51:08.407 UTC**, instructing Lead to build all four stages sequentially. Lead reported delivery complete at **06:51:12.438 UTC**, making the observed dispatch-to-delivery elapsed time **2 hours 4.031 seconds**. The final agent turn completed at 06:51:22.195 UTC. These are wall-clock intervals from the room log, not active compute time or summed seat runtimes. They exclude preparation before dispatch and later presentation, documentation and submission work.

At 06:50:37 UTC, QA reported acceptance of Stage 4 and the final four-folder chain. At 06:51:12 UTC, Lead reported delivery complete. The [final chain report](evidence/FINAL-CHAIN-3995a95e-REPORT.md) records 120/145/152/158 passing cumulative executions and standalone startup with no outbound network, a custom port, no mounts and 2 CPU/2 GiB limits. These are historical verification results at the named product revision.

## Evidence limits and submission status

- The current evidence source is `final.json`, exported at 2026-09-28 07:41:36.705 UTC with `scope: full` and an empty participant-filter list. It contains all five agent identities, the initial dispatch, Architect planning, implementation handoffs, rejection and repair, and final acceptance. `result/room.json` is its byte-for-byte copy. The earlier root `room.json` remains a historical export and is no longer the basis for the timing or roster description.
- The complete export contains one human text message: the initial dispatch. No later human steering appears in the recorded run. This supports autonomous execution within the room; it does not independently audit activity outside the exported conversation.
- Several frontend-associated commits use the Git author name `Xuewen Yang`. The room messages attribute the relevant work and revisions to Frontend Engineer. Git author names alone cannot establish which agent performed an action.
- Runtime/model settings, mandates and cost estimates are operator-supplied. These files document that configuration retrospectively and do not claim to be an export of the seat settings during the run.
- Reports in `evidence/` are unchanged copies. Their absolute paths identify historical local evidence. The parent's ignored `checks/` files may not appear in a public clone; include the intended artifacts before relying on those references externally.
- The local harness target is `result/`, while the Git root is its parent. The guide expects the eventual submitted repository to expose the stage folders at its root. Final public packaging must reconcile this without rewriting the product history. Local offline validation is not proof of that final packaging.
- This documentation does not claim that a video, public repository submission, submission receipt or hidden-test result exists. The existing presentation describes the product; the guide additionally asks the presentation/video to explain and show the factory.

The reusable factory contribution is the role separation, evidence-carrying handoffs, independent rejection and repair loop, and preserved stage boundaries. The current record supports concrete examples of those behaviors while leaving the evidence limits above visible.
