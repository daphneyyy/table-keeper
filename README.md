# Tablekeeper software factory

This repository contains a five-role agent factory and its Tablekeeper restaurant reservation product. The final application is in [`result/stage-4/`](result/stage-4/).

- [Product README and startup instructions](result/README.md)
- [Factory setup, decisions, costs and recovery evidence](result/FACTORY.md)
- [Five reusable seat mandates](result/mandates/)
- [Complete room export](final.json)
- [Product presentation](output/Tablekeeper_Product_Overview_Final.pptx)

The challenge harness target is `result/`, which contains the four standalone stages, documentation, mandates and an unchanged copy of `final.json` as `result/room.json`. The Git root remains this directory. No stage files or existing history were relocated.

Recorded independent QA accepted all four stage folders at product revision `3995a95edcf221e3604816c4f56fd0c467145597`. The four cumulative runs passed 120, 145, 152 and 158 applicable tests, respectively. See the [final chain report](result/evidence/FINAL-CHAIN-3995a95e-REPORT.md) for scope and limitations.

The supplied usage estimate is **18.8 million tokens and US$29.68** across five roles. The complete export records all five seats, including Architect's planning handoff and the Lead's approval. It contains one human task dispatch, followed by approximately **2 hours** to the Lead's delivery report. [FACTORY.md](result/FACTORY.md) documents the collaboration, timing and cost basis. The earlier root `room.json` is retained as a historical export; `final.json` is the current evidence source.

The product presentation explains the website. A factory demonstration video, public repository submission and final submission receipt are not established by these files. The participant guide expects stage folders at the root of the eventual submission repository; this working repository instead places them under `result/`. Passing a local check against `result/` does not resolve that public submission packaging difference.
