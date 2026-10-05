# 07 — Hackathon Submission Checklist

## Devpost Submission Requirements

| Item | Requirement | Status Notes |
|---|---|---|
| **Track** | Coding and Agentic Engineering Track | Confirm this is selected, not "Best Apps and Agents" |
| **Working project** | Must run on Nebius Token Factory or AI Cloud, and use at least one NVIDIA open-source model | Nemotron Nano/Super/Ultra usage must be real and demonstrable, not decorative |
| **Project description** | What was built, why, and how it works | Draw directly from `01-Project-Overview.md` |
| **Working demo** | URL to a hosted application or test build | Must actually be reachable by judges — test from a fresh browser/incognito session before submitting |
| **Demo video** | 3 minutes or shorter, public YouTube link, with audio covering Token Factory + Nemotron usage | See script guidance below |
| **Public code repository** | GitHub/GitLab/Bitbucket, publicly accessible | Must include an OSS license (Apache 2.0, MIT, or MPL 2.0) **visible at the top of the repo page** — not just a LICENSE file buried in the tree |
| **README** | Setup instructions, clear guidance for running the project | See structure below |
| **Nemotron/Token Factory usage explanation** | Highlight how Nemotron and Token Factory were used, and where they accelerated the workflow | Write this explicitly — don't assume it's obvious from code |
| **Feedback on Nebius/NVIDIA tools** | Required in the submission | Write a short, honest paragraph — the beta constraints and SDK/doc drift noted in the Risks doc are legitimate, useful feedback |
| **Prior-existence disclosure** | If the project existed before the submission period, disclose what was significantly updated | Not applicable unless work started before the official period |
| **IRL event city (optional)** | If a Builders & Brews event was attended, name the city for City Winner eligibility | Confirm with the team whether this applies |

## What to Highlight in the 3-Minute Video

Structure the video around the **verification story**, not the branching mechanism — per the differentiation strategy in `01-Project-Overview.md`, assume judges have seen branching-search agents before.

Suggested beat-by-beat structure (3:00 total):
1. **0:00–0:20 — The problem.** State plainly: "Coding agents generate patches. They don't prove you should trust them." Show a one-shot agent's fix that looks fine but isn't verified.
2. **0:20–0:50 — Search.** Submit a real bug. Show the tree fork into 3 branches on Contree, running in parallel. Narrate the Nano/Super patch generation and note this part costs cents and seconds, not dollars and minutes.
3. **0:50–1:30 — The catch (Idea 1).** Show a branch that passes once, then show the stability re-run catching an inconsistent result — this is the moment that separates BVA from a standard branching agent. Say explicitly: "A single green run isn't proof. We re-run it five times before we trust it."
4. **1:30–2:10 — The attack (Idea 2).** Show an adversarial branch generating a new test that breaks (or nearly breaks) the "verified" patch. This is the second differentiating moment.
5. **2:10–2:40 — The report.** Show the final confidence report and cost/latency summary. Say the actual numbers out loud (don't just show them on screen) — judges skimming audio-only need the number spoken.
6. **2:40–3:00 — Close.** One sentence on why this matters (trust is the blocker to real adoption of autonomous coding agents), and a clear statement of what ran on Nebius Token Factory Sandboxes and which Nemotron tiers did what.

**Do not spend more than 30 seconds total explaining the mechanics of forking/checkpointing itself** — judges evaluating multiple Contree-based projects will already understand the primitive; spend the time budget on what makes this project different.

## README Structure Recommendation

```markdown
# Branching Verification Agent

One-line pitch.

## What It Does
(2-3 sentences — pull from 01-Project-Overview.md's elevator pitch)

## Why It's Different
(The verification layer — flaky-test forensics + adversarial testing — explicitly contrasted with plain branching-search agents)

## Demo
- Live demo: [link]
- Video: [YouTube link]

## Architecture
(One diagram — reuse the Mermaid diagram from 03-Technical-Architecture.md — plus 2-3 sentences)

## How We Used Nebius Token Factory + NVIDIA Nemotron
(Explicit, concrete — which model tier did which job, and where Contree's checkpoint/fork/rollback was used for search vs. stability vs. adversarial verification)

## Setup
(Step-by-step — mirror the Phase 0 checklist from 06-Step-by-Step-Build-Guide.md)

## Running a Verification
(Exact commands / API calls to submit a run and view results)

## Limitations and Honest Feedback on Nebius/NVIDIA Tools
(Pull from 05-Risks-Limitations-and-Mitigations.md and the required Devpost feedback item — this section does double duty)

## License
(Visible badge/link at the top of the repo page, per submission requirements)
```

## How to Demonstrate Nemotron Model Routing and Contree Usage Clearly

- **In the UI:** label every node in the tree with which model tier generated it (a small badge: "Nano," "Super," "Ultra") so routing is visually self-evident without narration.
- **In the video:** narrate the routing logic once, plainly: "Cheap, fast Nano and Super models handle the parallel guesses. The big Ultra model only gets called when every guess fails and we need real reasoning about why."
- **In the README:** a small table (reuse the one from `03-Technical-Architecture.md`'s Model Routing Strategy section) mapping each pipeline step to its model tier and the reasoning behind it.
- **For Contree specifically:** call out in both video and README that forking is used for three distinct purposes (search, stability, adversarial) — this is the single clearest way to show sophisticated use of the sandbox primitive rather than the single obvious use case.

---

## Recommended Next Actions for the Team

1. **Today:** request Nebius Token Factory Sandboxes (Contree) beta access. This has the longest and least controllable lead time — start it before any code is written.
2. **Day 1–2:** run the Phase 0 smoke test (spawn, checkpoint, fork, run, rollback) and validate the determinism/caching behavior called out in the Risks and Architecture docs. This single validation gates whether Idea 1 works as designed — treat it as the first real go/no-go checkpoint.
3. **This week:** assign owners — suggest one person on orchestration/backend, one on the Contree/sandbox wrapper layer, one on frontend/tree UI, with model-routing and prompt work shared across whoever is free once Phase 1 is stable.
4. **Agree as a team, explicitly, on the differentiation pitch** ("search-and-verify, not just search") before writing any README or video copy, so every teammate describes the project the same way to judges.
5. **Build in the phase order in `06-Step-by-Step-Build-Guide.md`** — resist the temptation to start on the UI or the adversarial layer before the core search loop (Phase 1) is fully working end to end.
6. **Block real time for the demo video and README in Week 4**, not as an afterthought in the last 48 hours — per the Risks doc, submitting early avoids last-minute platform issues.
