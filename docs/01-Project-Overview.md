# 01 — Project Overview

## Working Title
**Branching Verification Agent** (internal codename: **BVA**)
*Coding and Agentic Engineering Track — Nebius x NVIDIA Global AI Hackathon*

## One-Liner
An agent that doesn't just generate a fix — it forks reality, tries several fixes in parallel isolated sandboxes, proves the winning fix is trustworthy (not just lucky), and shows its work as a live tree.

## Elevator Pitch
Most coding agents work like this: read the bug → write one patch → hope the test passes. That's a coin flip dressed up as engineering.

BVA treats bug-fixing as a **search-and-verify problem**, not a single-shot guess. It uses Nebius Token Factory Sandboxes (Contree) to fork the exact filesystem state where a bug reproduces, tries multiple independent fixes in parallel, and — critically — doesn't stop at "the test went green." It re-runs the target test multiple times to rule out flaky tests, and it spins up adversarial branches where a second model actively tries to break the winning patch with new tests. The result isn't just a diff; it's a diff plus a **confidence report**: how many times it passed, what attacks it survived, and what it cost to get there.

## Full Problem Statement
Three failure modes plague single-shot coding agents, and most hackathon coding-agent projects (including similar branching-search entries) only address the first one:

1. **Wrong fix.** The model's first patch is wrong and there's no fallback — solved by trying multiple patches in parallel (branching).
2. **Lucky fix.** The patch makes the *target* test pass, but the test itself is flaky (non-deterministic), or the patch happens to pass this run by chance. A single green run proves almost nothing. **Nobody in this hackathon's obvious solution space addresses this.**
3. **Narrow fix.** The patch passes the named test but breaks something else, or it "solves" the test by weakening it rather than fixing the underlying bug (reward hacking). **Also generally unaddressed.**

BVA is built around the idea that **verification is the actual hard problem**, not generation. Generating a plausible-looking patch is now cheap (any LLM can do it). Knowing whether you can trust that patch is not.

## Why This Is Strong for the Coding and Agentic Engineering Track

The track exists specifically for "agents that write, run, and test code in Token Factory Sandboxes." Judging criteria and how BVA addresses each:

| Judging Criterion | How BVA Scores On It |
|---|---|
| **Technological Implementation** | Uses Contree's checkpoint/fork/rollback primitives for three distinct purposes (search, flakiness detection, adversarial testing) instead of just one (search). Uses all three Nemotron tiers with a real division of labor, not routing for its own sake. |
| **Design** | Ships a complete product experience: a live tree UI, a cost/latency dashboard, and a plain-language trust report — not just a CLI that prints "PASS." |
| **Potential Impact** | Directly attacks a real, named problem in CI/CD and SWE-agent adoption: teams don't trust autonomous patches. A confidence score is what turns "an agent proposed a fix" into "I'm willing to merge this." |
| **Quality of the Idea** | Branching-search coding agents are a known pattern (see Differentiation below) and at least one very similar project already exists for this exact hackathon. BVA's differentiator — using branching for *trust*, not just *search* — is the part that is not commodity yet. |

## How It Uses Nebius Token Factory Sandboxes (Contree) + Nemotron Models

**Contree Sandboxes** provide three primitives BVA depends on:
- **Checkpoint** — save the exact filesystem state at a point in time.
- **Fork** — spin up N independent copies of a checkpoint that don't interfere with each other.
- **Rollback / replay** — return to any checkpoint, and re-running the same command from the same state is deterministic (Contree caches by state+command).

BVA uses forking for three different jobs, not one:
1. **Search forks** — N different patch hypotheses from the same bug-reproduction checkpoint.
2. **Stability forks** — the *same* patch and the *same* test, run N times, to measure flakiness.
3. **Adversarial forks** — the winning patch's checkpoint, forked so a second model can try to write a test that breaks it.

**Nemotron model routing:**
- **Nemotron Nano** — cheap, fast calls: generating simple patch hypotheses, running repeated stability checks, light classification (e.g., "is this failure the same failure as before?").
- **Nemotron Super** — mid-tier patch generation for harder hypotheses, and generating adversarial test cases.
- **Nemotron Ultra** — only called when (a) all branches in a round fail, and needs to plan the next round from failure traces, or (b) writing the final human-readable confidence report.

This tiering is a cost strategy, not decoration — most calls in the system are cheap-and-fast; the expensive model is reserved for genuinely hard reasoning steps.

## Differentiation from Existing Coding Agents

| System | What It Does | What It Doesn't Do |
|---|---|---|
| Claude Code / Cursor / Devin-style agents | Single-shot or lightly-iterative patch generation with a chat interface | No systematic parallel search; no repeated-run flakiness check; no adversarial self-testing |
| SWE-agent / AutoCodeRover | Structured single-agent loop over a repo | Same as above — one line of attempt at a time |
| **Arborist** (a known competing hackathon project) | Branches Contree checkpoints, tries parallel patches, tiers Nano/Super/Ultra, shows a tree UI | Stops once a test goes green. No flakiness verification, no adversarial testing, no confidence scoring. |
| **BVA** | Everything Arborist-style projects do, **plus** two verification layers most competitors skip | — |

**Be honest about this in every teammate conversation and in the video:** the "fork checkpoints and try several patches" mechanism is not a novel idea in this hackathon — assume judges will see it more than once. BVA's pitch has to be the **verification layer** (flaky-test detection + adversarial testing + confidence report), not the branching mechanism itself.

## Target Users
- **Individual developers / OSS maintainers** who want an agent to attempt bug fixes but don't trust a bare "tests pass" signal enough to merge blind.
- **Engineering teams evaluating autonomous coding agents** who need an audit trail (why should I trust this patch?) before adopting one in CI.
- **Hackathon judges**, functionally — the demo needs to sell trustworthiness, not just automation, in three minutes.

## High-Level Success Criteria for the Hackathon
1. End-to-end run on at least 3–5 preloaded SWE-bench-style issues, fully automated, with recorded cost and latency.
2. At least one live demo moment showing flaky-test detection catching something a naive one-shot agent would have missed.
3. At least one live demo moment showing an adversarial branch breaking a patch that "passed" the original test.
4. Public repo with a working demo link, README, and honest metrics (not just claims).
5. A tree UI that a judge can look at for 10 seconds and understand what happened.
