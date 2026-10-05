# 00 — Decisions Log

This document records key decisions made during planning conversations that clarify or add to the existing project documentation (`01-Project-Overview.md` through `07-Hackathon-Submission-Checklist.md`). It is written in plain language to ensure all team members have a shared understanding.

---

## Project Identity

- **Project / Repository Name:** PatchTree
- **Reasoning:** The name reflects the core mechanic of the system (branching and forking a tree of patch attempts). It is short, memorable, and demo-friendly.
- **License:** MPL 2.0 (Mozilla Public License 2.0)
- **License Reasoning:** Satisfies the hackathon's required open-source license list (Apache 2.0, MIT, or MPL 2.0). It was chosen over MIT because it includes explicit patent protection.
- **Commercial Use Note:** Note that it does NOT allow charging for commercial use — no open-source license on the approved list does.

---

## Frontend Framework Decision

- **Chosen:** React + Vite (not Next.js)
- **Reasoning:**
  - The app is a private live dashboard, not a public content site. Next.js's main strengths (server-side rendering for SEO and fast public page loads) don't apply here.
  - The app also needs a long-lived WebSocket connection for live tree updates, which fits a dedicated Python/FastAPI backend better than Next.js's short-lived API routes.
  - Using Next.js would add a second framework to maintain without removing any backend work, since the real orchestration logic has to be in Python anyway (for the Contree SDK and Nebius model calls).
- **Note:** If the team is already more comfortable with Next.js, it can still work — just have the frontend talk directly to the FastAPI backend's WebSocket and endpoints, not through Next's own API layer.

---

## Repository Structure

- **Monorepo Layout:** `backend/`, `frontend/`, `docker-compose.yml`, `README.md`, and `docs/` all at the top level of one repo.
- **Reasoning:** Frontend (React/Vite) and backend (Python/FastAPI) are different languages, so keeping them in separate top-level folders in one repo is the standard pattern for this kind of project — simpler for a small team than two separate repos.

---

## Local Development Setup

- **Database:** PostgreSQL, run locally via Docker (not installed manually).
- **docker-compose.yml's Job:** Only starts supporting services (the Postgres database, and later Redis if needed) in the background — it does NOT run the frontend or backend during development. Those are run directly on the developer's machine (`npm run dev` for frontend, `uvicorn` for backend) for fast iteration.
- **Backend Packaging:** The backend is only packaged into its own Docker container later, when preparing for deployment, not during day-to-day coding.

---

## Hosting / Deployment Plan

- **Nebius Hosting Requirements:** The web app itself (frontend + backend) does not need to be hosted on Nebius to satisfy the hackathon rules. The hackathon's requirement is that AI model calls and sandbox execution run through Nebius — which they do, since the backend calls Nebius Token Factory and Nebius Sandboxes (Contree) APIs directly.
- **Planned Hosting for the Public Demo URL:** Render or Railway (fast, simple deploys from GitHub), rather than Nebius AI Cloud's own hosting options (Virtual Machine / Standalone / Kubernetes), which would require more manual setup and aren't necessary for this requirement.

---

## Search Branch Differentiation (clarifies 03-Technical-Architecture.md's Search Branching section)

- **Instruction Diversity:** The 3 parallel search branches must each be given a genuinely different instruction, not just asked the same question 3 times, or they tend to produce near-identical patches.
- **Recommended 3 Distinct Instructions:**
  1. *"Make the smallest possible change that could fix this."* (minimal/cautious fix)
  2. *"Find a different approach — assume the minimal fix is wrong."* (alternative approach)
  3. *"Look for the fix somewhere else in the code — the bug may not be where it first appears."* (root-cause-elsewhere fix)
- **Explicitly Excluded:** A "test adjustment" branch (i.e., editing the test itself to make it pass) — this is reward hacking and is already flagged as a risk to avoid in `05-Risks-Limitations-and-Mitigations.md`; it must never be one of the 3 branch instructions.
