# 🌳 PatchTree

> **Autonomous AI agent that forks cloud sandboxes to explore, verify, and stress-test code patches before trusting them.**  
> *Built for the Nebius Token Factory x NVIDIA Global AI Hackathon (Coding & Agentic Engineering Track).*

---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Nebius-Token_Factory-7C3AED?style=for-the-badge&logo=cloud&logoColor=white" alt="Nebius Token Factory" />
  <img src="https://img.shields.io/badge/NVIDIA-Nemotron_3-76B900?style=for-the-badge&logo=nvidia&logoColor=white" alt="NVIDIA Nemotron 3" />
  <img src="https://img.shields.io/badge/Contree-Cloud_Sandboxes-0EA5E9?style=for-the-badge&logo=docker&logoColor=white" alt="Contree Sandboxes" />
  <img src="https://img.shields.io/badge/License-MPL_2.0-blue?style=for-the-badge" alt="License MPL 2.0" />
</p>

---

## ⚡ The Problem & The Solution

Most coding agents follow a fragile loop: **read the bug → generate one patch → hope the test passes**.

In production software, that is a coin flip dressed up as software engineering:
- **First guesses are often wrong** — single-shot agents hit dead ends with no systematic fallback.
- **First passes are often lucky** — tests are frequently flaky due to concurrency, timing, or execution order.
- **Green tests can hide regressions** — patches can pass the named test while breaking edge cases or weakening assertions.

| Capability | Standard Single-Shot Agents | PatchTree |
|---|---|---|
| **Exploration Strategy** | Single sequential attempt | **4-Way Concurrent Search** across distinct hypotheses |
| **Sandbox Isolation** | Reuses dirty container state | **Contree Snapshot Checkpointing & Clean Forking** |
| **Flakiness Handling** | Assumes 1 green run = permanent fix | **5-Fork Stability Forensics** to verify true stability |
| **Adversarial Hardening** | None (stops at first pass) | **Attack Forks** where a secondary model tries to break the patch |
| **Recovery on Failure** | Blind prompt retry | **Nemotron Ultra Meta-Replan** analyzing failure traces |
| **Final Output** | Unverified diff | **Diff + Decision-Ready Confidence Report + Execution Tree** |

---

## 🔄 How Errors Are Solved: The Lifecycle

PatchTree moves through five distinct verification stages:

```mermaid
flowchart LR
    A["1. Reproduce<br/>& Checkpoint"] --> B["2. 4-Branch<br/>Concurrent Search"]
    B --> C{"3. Evaluate<br/>& Forensics"}
    C -->|Pass| D["4. Stability &<br/>Adversarial Check"]
    C -->|All Fail| E["5. Ultra Replan<br/>(Analyze Traces)"]
    E --> B
    D --> F["6. Verified Patch<br/>+ Confidence Report"]
```

1. **Reproduction & Checkpoint A**  
   The sandbox boots the environment, runs the target test command, confirms the exact failure trace, and saves **Checkpoint A**. If an error cannot be reproduced, execution halts honestly.
2. **Concurrent Search Fan-Out**  
   PatchTree forks four independent copies of Checkpoint A simultaneously:
   - **Branch 1 (Minimal Fix — Nemotron Nano):** Direct, surgical patch targeting only the immediate symptom.
   - **Branch 2 (Alternative Strategy — Nemotron Super):** Explores alternative implementations or refactoring.
   - **Branch 3 (Root-Cause Fix — Nemotron Super):** Investigates deeper causes across callers or dependencies.
   - **Branch 4 (Test-Driven Fix — Nemotron Nano):** Strictly implements expected contract specifications.
3. **Flaky-Test Forensics**  
   When a patch turns green, PatchTree does **not** stop there. It forks the winning checkpoint $k$ times ($k=5$) and re-runs the identical test command across all five forks in parallel to ensure the pass was deterministic.
4. **Adversarial Self-Testing**  
   A secondary model receives the code changes and attempts to generate targeted attack tests designed to break the fix. Patches that survive both stability checks and adversarial attacks earn high confidence.
5. **Ultra-Tier Meta-Replan Loop**  
   If all four branches fail in a round, Nemotron Ultra (550B) inspects the concatenated stdout/stderr traces from every failed attempt, diagnoses why they failed, and prescribes four revised strategies for the next round.

---

## 🌲 Tree Architecture

```mermaid
flowchart TD
    subgraph Reproduction ["1. Reproduce"]
        Root["🚨 Root Node<br/>Confirm Test Failure & Checkpoint"]
    end

    subgraph Search ["2. 4-Branch Concurrent Search"]
        B1["Branch 1: Minimal Fix<br/>(Nemotron Nano)"]
        B2["Branch 2: Alternative Fix<br/>(Nemotron Super)"]
        B3["Branch 3: Root-Cause Fix<br/>(Nemotron Super)"]
        B4["Branch 4: Test-Driven Fix<br/>(Nemotron Nano)"]
    end

    subgraph EvalJoin ["3. Evaluation & Forensics"]
        Eval{"Evaluate<br/>Search"}
        Stability["🛡️ Stability Forensics<br/>Parallel Forks to rule out flakiness"]
        Replan["🧠 Meta-Replan<br/>(Nemotron Ultra analyzes traces)"]
    end

    subgraph Verified ["4. Trust Report"]
        Winner["✅ Verified Stable Patch<br/>Confidence Report + Diff"]
    end

    Root -->|Fork State| B1
    Root -->|Fork State| B2
    Root -->|Fork State| B3
    Root -->|Fork State| B4

    B1 & B2 & B3 & B4 --> Eval
    Eval -->|Passing Candidate| Stability
    Eval -->|All Failed| Replan
    Replan -->|Revised Strategies| Search
    Stability -->|Verified Stable| Winner
    Stability -->|Flaky Failure| Replan
```

---

## 🛠️ Tech Stack & Model Routing

| Layer | Technology | Role & Why |
|---|---|---|
| **Cloud Sandboxes** | **Nebius Contree SDK** | Instant container checkpointing, parallel forking, and isolated execution. |
| **Fast LLM Tier** | **NVIDIA Nemotron 3 Nano (30B)** | Cheap, high-throughput first-pass hypotheses and lightweight checks. |
| **Deep LLM Tier** | **NVIDIA Nemotron 3 Super (120B)** | Architectural refactoring, root-cause repair, and adversarial test generation. |
| **Reasoning Tier** | **NVIDIA Nemotron 3 Ultra (550B)** | Multi-trace failure analysis, meta-planning, and confidence reporting. |
| **API Server** | **FastAPI + Pydantic v2** | High-concurrency async orchestrator managing background tree tasks. |
| **Persistence** | **Supabase (PostgreSQL)** | Persistent storage for run metadata, node execution trees, and metrics. |
| **Frontend** | **React + Vite + TypeScript** | Interactive live tree visualization (React Flow) and diff inspection panel. |

---

## 📁 Repository Structure

```text
PatchTree/
├── Backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entrypoint & REST API endpoints
│   │   ├── orchestrator/         # Repair pipeline & multi-branch search state machine
│   │   ├── llm/                  # Nemotron tiered model router (Nano / Super / Ultra)
│   │   ├── sandbox/              # Contree SDK client wrapper with in-memory fallback
│   │   ├── models/               # Pydantic schemas (Run, Node, Tree)
│   │   └── db/                   # Supabase client & schemas
│   ├── tests/                    # End-to-end automated unit & integration test suites
│   ├── requirements.txt
│   └── .env.example
├── Frontend/                     # React + TypeScript tree visualization UI
├── docs/                         # Architecture, decision logs, and specifications
├── AGENTS.md                     # Agent engineering protocols
├── LICENSE                       # Mozilla Public License 2.0
└── README.md
```

---

## 🚀 Quickstart

### 1. Prerequisites
- Python 3.11+
- [Nebius Token Factory](https://tokenfactory.nebius.com) API Key & Project ID

### 2. Setup Backend
```bash
# Clone the repository
git clone https://github.com/Aman-art1/PatchTree.git
cd PatchTree/Backend

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Fill in your NEBIUS_API_KEY and NEBIUS_PROJECT_ID in .env
```

### 3. Run Verification Tests
PatchTree includes automated suites verifying API endpoints, Nemotron LLM routing, and cloud sandboxes:

```bash
# Fast API & schema tests (0.06s)
python tests/test_api.py

# Multi-branch Nemotron LLM search test
python tests/test_search.py

# Full evaluate & Ultra replan state machine test
python tests/test_evaluate.py

# Live Nebius Contree cloud sandbox test
python tests/test_real_contree.py
```

### 4. Start Development API Server
```bash
uvicorn app.main:app --reload --port 8000
```
Visit `http://localhost:8000/docs` to test interactive Swagger API endpoints.

---

## 🏆 Hackathon Context & Licensing

Built for the **Nebius x NVIDIA Global AI Hackathon (October 2026)**.  
*Track: Coding and Agentic Engineering (Agents that write, run, and test code in Token Factory Sandboxes).*

- **Contree Primitives Exploited:** OCI lightweight image import, snapshot checkpoints, parallel child forking, and non-cached deterministic command execution.
- **Model Efficiency:** Over 80% of tokens run on cheap Nano/Super endpoints, reserving 550B Ultra exclusively for failure reasoning.
- **License:** Open-source software released under the **[Mozilla Public License 2.0 (MPL-2.0)](LICENSE)**.

---

<p align="center">
  <sub>Licensed under the <a href="LICENSE">Mozilla Public License 2.0</a>.</sub>
</p>