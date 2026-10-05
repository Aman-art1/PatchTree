# 06 — Step-by-Step Build Guide

## Phased Implementation Plan

Five weeks assumed to the 30 Oct 2026 deadline. Each phase ends with something runnable — never leave a phase in a half-working state going into the next one.

### Phase 0 (Day 1–2): Access and Environment Setup
- [ ] Sign up for Nebius Token Factory; request Sandboxes (Contree) beta access — **do this first**, since access is per-project and may take time to be granted
- [ ] Get Nemotron Nano/Super/Ultra API keys working with a trivial `curl`/script call to each
- [ ] Install the Contree SDK; run the simplest possible smoke test: spawn a sandbox from a preloaded SWE image, run one shell command, checkpoint, fork it once, run a command on the fork, roll back
- [ ] **Validate the determinism/caching question** (see Architecture and Risks docs) before writing any orchestration code that depends on repeated-run behavior
- [ ] Set up repo skeleton (see Repository Structure below), Docker Compose for Postgres + Redis, `.env.example`

**Exit criteria:** a single script can spawn a sandbox, fork it, run a command on each fork, and print results. No orchestration logic yet — just proof the primitives work as documented.

### Phase 1 (Week 1): Core Search Loop — the MVP
- [ ] Build the `ReproduceNode`: given a preloaded SWE-bench issue, boot the sandbox and confirm the target test fails
- [ ] Build the `SearchNode`: fork into 3 branches, call Nemotron Nano/Super to generate a patch hypothesis per branch, apply the patch, run the test
- [ ] Build the join/evaluate step: if any branch passes, that's the winner (no stability/adversarial checks yet at this phase)
- [ ] Build the `ReplanNode` (Ultra) for the case where all 3 branches fail, capped at 2 total rounds
- [ ] Store every node's data per the schema in the Architecture doc
- [ ] Bare-bones API: `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/tree` (no WebSocket yet — polling is fine at this stage)

**This is the Minimum Viable Version that can already be demoed:** a repo + failing test goes in, a tree of 3 branches with a winner (or honest failure) comes out, viewable via API response even before there's a UI. If nothing else gets built, this phase alone is a legitimate (if unoriginal — see Risks doc) submission.

### Phase 2 (Week 2): Idea 1 — Flaky-Test Forensics
- [ ] Build the `StabilityNode`: fork the winning checkpoint k times (k=5), rerun the identical test command on each
- [ ] Build the evaluate-stability join: all-pass → promote to verified winner; any failure → flag as unstable, demote, and either try the next-best search branch or trigger a replan
- [ ] Add flakiness data to the node schema and API response
- [ ] **This phase depends entirely on the Phase 0 determinism validation being correct** — do not start this phase until that's confirmed

**Exit criteria:** a run can now distinguish "passed once" from "verified stable," and the API/data model reflects it.

### Phase 3 (Week 3): Idea 2 — Adversarial Verification + Full-Suite Check
- [ ] Build the `AdversarialNode`: fork the stable winning checkpoint m times (m=2–3), prompt Nemotron Super/Ultra to write a test designed to break the patch, run it
- [ ] Build the evaluate-adversarial join and the confidence-score calculation (combine stability result + adversarial survival rate + full-suite result into one score/summary)
- [ ] Add a `FullSuiteNode`: run the entire repo test suite against the final winning checkpoint
- [ ] Build the final `ReportNode`: Ultra generates the plain-language confidence report

**Exit criteria:** a completed run produces a diff plus a full confidence report combining all three verification layers. **If time is tight, this phase can be cut back to just the adversarial check without the full-suite run** — see Risks doc for what to preserve if forced to cut scope.

### Phase 4 (Week 4): UI and Demo Polish
- [ ] Build the React + react-flow tree UI, wired to live run data (upgrade backend to WebSocket streaming at this point if not done already)
- [ ] Build the cost/latency header and the confidence report view
- [ ] Style pass (Tailwind) — this needs to look like a product, not a debug console, per the "Design" judging criterion
- [ ] Pick and pre-run 3–5 demo issues from the preloaded SWE set; verify they produce interesting, demonstrable behavior (at least one flaky-test catch, at least one adversarial catch)
- [ ] Record the 3-minute demo video (see Submission Checklist doc for exact content requirements)

### Phase 5 (Week 5): Buffer, Testing, Submission
- [ ] Reserve this week for fixing whatever broke in Phase 4 — do not schedule new features here
- [ ] Finalize README, public repo license, setup instructions (see Submission Checklist doc)
- [ ] Submit early, not at the deadline — Devpost and Nebius platform issues near a deadline are a real risk

## Nebius Token Factory + Contree Access Setup (Checklist)
1. Create/verify a Nebius account and join the hackathon via Devpost.
2. Sign up for the Nebius Builder Program if credits are needed (listed as a hackathon to-do).
3. Request Token Factory Sandboxes (Contree) beta access for your project — confirm the granted concurrent-operations limit.
4. Generate API keys for Nemotron model endpoints via Token Factory.
5. Store keys in `.env` (never commit); populate `.env.example` with placeholder names for teammates.
6. Run the Phase 0 smoke test before writing any application code.

## Repository Structure

```
bva/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes
│   │   ├── orchestrator/     # LangGraph or custom state machine, one file per node type
│   │   ├── models/           # Pydantic schemas matching the data model doc
│   │   ├── sandbox/          # Contree SDK wrapper — isolate all Contree calls here
│   │   ├── llm/               # Nemotron routing/client wrapper
│   │   └── db/                # Postgres models/migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # TreeView, NodeDetail, CostHeader, ReportView
│   │   ├── hooks/             # WebSocket + React Query hooks
│   │   └── App.tsx
│   └── package.json
├── docs/                      # this documentation package lives here
├── docker-compose.yml
├── .env.example
└── README.md
```

**Isolate the Contree SDK behind a single `sandbox/` wrapper module.** Given the SDK-drift risk noted in the Risks doc, this means a breaking API change only requires updating one file, not hunting through orchestration logic.

## Testing Strategy
- **Unit tests** for the orchestrator's decision logic (e.g., "given these 3 branch results, does it correctly route to stability vs. replan vs. failure-report?") — these don't need real sandboxes, just mocked results.
- **One golden integration test**: a single fixed, cheap preloaded SWE issue run end-to-end against real Contree + real (cheap-tier) model calls, run manually before each demo rehearsal, not in CI (to avoid burning cost/quota on every push).
- **Determinism test**: explicitly test the caching behavior identified in the Risks doc — this one test protects the entire Idea 1 feature.
- **Frontend**: manual QA against a pre-recorded run is sufficient given the timeline; do not over-invest in frontend test automation for a hackathon.

## What Must Be Ready for Final Submission
- [ ] Working demo URL (hosted application or test build)
- [ ] 3-minute-or-shorter public YouTube demo video with audio explaining Token Factory + Nemotron usage
- [ ] Public code repository (GitHub/GitLab/Bitbucket) with an OSS license visible at the top of the repo page
- [ ] README with setup instructions and clear run guidance
- [ ] Project description covering what was built, why, and how it works
- [ ] Explicit written notes on how Nemotron models and Token Factory/Contree were used
- [ ] Feedback on Nebius Token Factory / AI Cloud / NVIDIA tools (a stated requirement of the submission)

(Full detail on each of these is in `07-Hackathon-Submission-Checklist.md`.)
