# 05 — Risks, Limitations, and Mitigations

## Competitive / Idea Risk

| Risk | Impact | Mitigation |
|---|---|---|
| A very similar project (known example: "Arborist") already exists for this exact hackathon, using the same core branching-search mechanism | Could be judged as unoriginal on "Quality of the Idea" | Every pitch, README line, and demo minute must foreground the **verification layer** (flaky-test forensics + adversarial testing) as the differentiator, not the branching mechanism itself. Explicitly name the difference in the video: "search-and-verify, not just search." |
| Judges have seen multiple "fork checkpoint, try N patches" projects | Diminishing novelty as more teams converge on the obvious use of Contree | Same as above — lead with what happens *after* a test goes green, since that's the underexplored part of the design space |

## Technical Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **All branches fail** across both search rounds | Dead end with nothing to show | Score partial credit (tests fixed vs. broken, not binary pass/fail); report the least-bad branch honestly; hard-cap at 2 rounds so this resolves quickly rather than looping |
| **Flaky target test** | A "winning" patch might not actually be reliable, or a genuinely correct patch might appear to fail once by chance | This is the headline feature (Idea 1): re-run the winning branch's test k times (recommend k=5) before declaring victory; if results are inconsistent, flag as unstable and try the next-best branch |
| **Patch passes the named test but breaks other things** | A dangerously misleading "success" | Idea 2 (adversarial branches) + mandatory full-suite run on the winner before final reporting |
| **Patch "fixes" the test by weakening or rewriting the test itself** (reward hacking) | Technically passes, solves nothing | Lock test files from being part of any patch's diff; reject any candidate patch that touches the test file; flag this explicitly in validation before a patch is even run |
| **High latency** from parallel sandbox boot + test execution, compounded by stability and adversarial rounds | Live demo risk; could look slow/boring on video | Use preloaded SWE images (skip install/setup time); parallelize aggressively (all forks in a round run concurrently, never sequentially); pre-warm a demo run before recording so a fresh run isn't the first thing judges see live |
| **Cost can grow with more rounds and verification stages** | Runaway spend, especially in a live/interactive demo | Hard caps: max 2 search rounds, k=5 stability reruns, m=2–3 adversarial forks, and an absolute per-run spend ceiling that halts the run and reports partial results if hit |
| **Nebius Sandboxes is in beta** with a stated ~50-concurrent-operations ceiling and per-project access requests | Could block development entirely if access isn't granted early, or throttle a demo with concurrent branches | Request Sandboxes/Contree access on Day 1 of the build (not later); design branch counts (3 search + 5 stability + 2–3 adversarial ≈ 10 concurrent max per run) comfortably under the concurrency ceiling; add retry/backoff around Contree calls |
| **SDK/documentation drift** — integration examples (e.g. mini-swe-agent + Contree) have been observed to be out of sync with the current SDK | Wasted debugging time following stale docs | Pin exact SDK versions in `requirements.txt`; smoke-test every Contree primitive (spawn, checkpoint, fork, run, rollback) in isolation on Day 1 before building orchestration logic on top of assumptions |
| **Determinism/caching in Contree could silently defeat the stability check** (see Architecture doc note) — if identical (state, command) pairs are cached, "5 reruns" might just replay one cached result | Idea 1's core mechanism could produce a false sense of verification | Validate experimentally before building on top of it; if caching is confirmed, introduce controlled variation (disable cache for this call type, or add a randomized flag to the test command) so reruns genuinely re-execute |
| **Difficulty reproducing the original failure** on arbitrary repos | Wasted sandbox time on repos that never even get to Checkpoint A | Constrain the demo (and ideally the MVP) to the 7,000+ preloaded SWE environments (SWE-bench Verified / SWE-rebench) rather than "any public GitHub repo" — this removes an entire class of setup failures |
| **Complex or slow-to-install repositories** | Long setup time eats into the round-trip budget and demo time | Same mitigation as above — preloaded images sidestep this entirely for the hackathon scope |
| **Orchestration bugs in fan-out/join logic** (e.g., a hung branch blocking the whole round) | A single stuck sandbox could stall the entire run | Per-branch timeout enforced independently; a round completes as soon as all branches report (pass, fail, or timeout) — no branch can block indefinitely |

## What We Will Explicitly Show in the Demo Regarding Costs and Failures

Being transparent about limitations is itself a credibility signal for judges, and should be treated as a deliberate design choice, not something to hide:

1. **A visible cost/latency counter** throughout the live run — never claim "instant" or hide the real time/cost numbers.
2. **At least one moment showing a failed or flagged branch**, not a cherry-picked all-green run — e.g., show a flaky test getting caught, or an adversarial test breaking an initial "pass."
3. **An honest "all branches failed" fallback screen**, even if it's not the run shown live — include a clip or screenshot in the video demonstrating this path exists and behaves gracefully rather than crashing or hanging.
4. **A clear statement of hard limits** (max rounds, max spend) visible in the UI or mentioned in narration — this frames the system as production-minded rather than a demo-only trick.
5. During beta, since Sandbox execution itself is free, **do not display a fabricated dollar cost for sandbox time** — show CPU-seconds/wall time instead, and be explicit in the video that model inference cost is the real dollar figure being tracked.
