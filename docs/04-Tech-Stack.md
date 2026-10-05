# 04 — Tech Stack

## Backend

| Choice | Justification |
|---|---|
| **Python 3.11+** | Contree SDK and most Nebius integrations are Python-first; team velocity in a hackathon favors one primary language |
| **FastAPI** | Async-native (needed for concurrent sandbox calls and WebSocket streaming), fast to build, automatic OpenAPI docs for teammate onboarding |
| **LangGraph** (fallback: custom asyncio state machine) | Matches the branching/fan-out/join structure directly; **validate early** that it plays well with Contree's async calls — if friction is high, a hand-rolled state machine is a safe fallback and is explicitly acceptable per the Build Guide |
| **Nebius Contree SDK** | Official SDK for spawning, checkpointing, forking, and running commands in Sandboxes — this is the core dependency the whole product is built around |
| **Redis** | Task queue (for dispatching branch work) + pub/sub (for pushing live tree updates to WebSocket clients) |
| **Celery or RQ** (or plain `asyncio.gather` if scale doesn't require a broker) | Given hackathon scale (a handful of concurrent runs, not production traffic), `asyncio.gather` over async Contree/model calls is likely sufficient and simpler than standing up Celery — prefer the simpler option unless concurrency needs prove otherwise |

## Frontend

| Choice | Justification |
|---|---|
| **React + TypeScript** | Team familiarity, huge ecosystem, fast to iterate under a deadline |
| **react-flow** | Purpose-built for node/edge graph UIs — directly fits the tree visualization requirement without hand-rolling SVG/canvas layout |
| **TailwindCSS** | Fast styling for a demo-quality UI in limited time |
| **Native WebSocket API** (or `socket.io` if bidirectional events get complex) | Live status updates to the tree as branches complete |
| **React Query** | Polling fallback + caching for run summary and report views |

## Database / Storage

| Choice | Justification |
|---|---|
| **PostgreSQL** (SQLite acceptable for pure local dev/demo) | Structured run/node data as defined in the Architecture doc's data model; relational fits the parent/child tree structure well |
| **Object storage for large artifacts** (Nebius object storage if available, else local disk during hackathon) | Full diffs, test logs, and stdout/stderr can be large — store as blobs referenced by node ID rather than inline in Postgres rows |
| **No vector database needed** — this project has no semantic search or RAG requirement; do not add one just because it's a common pattern elsewhere |

## Infrastructure (Nebius)

| Component | Purpose |
|---|---|
| **Nebius Token Factory — Nemotron 3 Nano / Super / Ultra endpoints** | All model inference calls, per the routing strategy in the Architecture doc |
| **Nebius Token Factory Sandboxes (Contree)** | All checkpoint/fork/run/rollback operations — the core infrastructure dependency |
| **Nebius Serverless Endpoints** | Optional — if the demo app itself needs to be hosted with low-latency inference in front of it |
| **Nebius Serverless Jobs** | Overnight full-suite verification job (nice-to-have feature) |

**Beta constraints to plan around** (see Risks doc for full detail): Sandboxes is in beta with a stated 50-concurrent-operations ceiling and per-project access. Request Contree/Sandboxes access on Day 1, not Week 3.

## Key Libraries and SDKs

- `contree` / Nebius Sandboxes Python SDK — checkpoint, fork, run, rollback
- `nebius` Token Factory client (or plain `httpx`/`requests` against the OpenAI-compatible or Anthropic-style endpoint, per current Token Factory API docs)
- `fastapi`, `uvicorn` — API server
- `websockets` (via FastAPI's built-in WebSocket support) — live updates
- `pydantic` — request/response and internal data models (maps directly to the JSON schema in the Architecture doc)
- `pytest` — backend testing
- `react-flow`, `zustand` or React Query — frontend graph state

## Development Tools

- **Docker Compose** for local dev: Postgres + Redis + backend, so any teammate can `docker compose up` and be running in minutes.
- **GitHub Actions** — minimal CI: lint + unit tests on push. Not a priority to over-invest in given the deadline, but a green CI badge is a small credibility signal for judges browsing the repo.
- **`.env.example`** committed with all required keys (Nebius Token Factory API key, Contree project ID) so a new teammate — or a judge testing the repo — can get running without guessing configuration.
- **Structured logging** (`structlog` or plain JSON logs) from day one — with a tree of concurrent branches, debugging via `print()` will not scale even during the hackathon itself.
