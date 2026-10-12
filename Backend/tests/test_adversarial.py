import asyncio
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import Node, Run
from app.orchestrator import pipeline
from app.orchestrator.pipeline import check_adversarial
from app.sandbox.contree_client import PATCH_MARKER, CommandResult, SandboxManager


class AdversarialSandbox(SandboxManager):
    """Stub sandbox where the i-th patched candidate (in test order) follows plan[i].

    plan[i] = results of that candidate's successive test runs: [branch run,
    stability x5, adversarial xm, full_suite]. Only pytest executions consume a
    plan step; file writes (cat/echo) are no-ops. Unplanned candidates fail;
    runs on an unpatched history always fail.
    """

    def __init__(self, plan: dict[int, list[bool]], _shared: dict | None = None):
        super().__init__(force_stub=True)
        self.plan = plan
        self.shared = _shared if _shared is not None else {"order": [], "runs": {}, "lock": threading.Lock()}

    def fork(self, checkpoint_id: str) -> "AdversarialSandbox":
        child = AdversarialSandbox(self.plan, self.shared)
        child._history = list(self._checkpoints.get(checkpoint_id, []))
        child._checkpoints = self._checkpoints
        return child

    def _stub_run(self, cmd: str) -> CommandResult:
        self._history.append(cmd)
        if cmd.startswith(PATCH_MARKER):
            return CommandResult(0, "patch applied")
        patch = next((h for h in self._history if h.startswith(PATCH_MARKER)), None)
        if patch is None:
            return CommandResult(1, "FAILED root")
        if "pytest" not in cmd:
            return CommandResult(0, "")
        with self.shared["lock"]:
            if patch not in self.shared["order"]:
                self.shared["order"].append(patch)
            idx = self.shared["order"].index(patch)
            n = self.shared["runs"][patch] = self.shared["runs"].get(patch, -1) + 1
        steps = self.plan.get(idx, [])
        ok = steps[n] if n < len(steps) else False
        return CommandResult(0 if ok else 1, "passed" if ok else "FAILED")


ADVERSARIAL_RESPONSE = "```python\ndef test_adversarial_edge_case():\n    assert True\n```"


def _setup(sandbox: SandboxManager) -> tuple[Run, Node]:
    run = Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc),
              repo_url="https://github.com/example/repo", bug_description="x", target_test="pytest t.py")
    sandbox.spawn("python:3.11")
    sandbox.run_command(f"{PATCH_MARKER} c1.diff")
    cand = Node(node_id="c1", run_id=run.run_id, branch_type="search", checkpoint_id=sandbox.checkpoint(),
                test_command=run.target_test, test_result="pass",
                patch_diff="--- a/app.py\n+++ b/app.py")
    return run, cand


async def _check(sandbox: AdversarialSandbox, m: int = 2):
    calls: list[dict] = []

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        calls.append({"job": job, "prompt": prompt})
        return {"content": ADVERSARIAL_RESPONSE, "model": "stub", "tokens_in": 1, "tokens_out": 1, "stub": True}

    run, cand = _setup(sandbox)
    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        nodes = await check_adversarial(run, cand, sandbox, m=m)
    finally:
        pipeline.call_model = original
    return run, cand, nodes, calls


def test_patch_survives_all_attacks():
    sb = AdversarialSandbox({0: [True, True]})
    run, cand, nodes, calls = asyncio.run(_check(sb))
    assert len(nodes) == 2 and len(calls) == 2
    assert all(c["job"] == "generate_adversarial_test" for c in calls)
    assert all(cand.patch_diff in c["prompt"] and run.bug_description in c["prompt"] for c in calls)
    assert all(n.branch_type == "adversarial" for n in nodes)
    assert all(n.parent_node_id == cand.node_id for n in nodes)
    assert all(n.test_result == "pass" for n in nodes)
    assert (run.adversarial_runs, run.adversarial_survived) == (2, 2)


def test_patch_broken_by_attack():
    sb = AdversarialSandbox({0: [True, False]})
    run, cand, nodes, calls = asyncio.run(_check(sb))
    assert sum(n.test_result == "pass" for n in nodes) == 1
    assert sum(n.test_result == "fail" for n in nodes) == 1
    assert (run.adversarial_runs, run.adversarial_survived) == (2, 1)


# ---------- run_pipeline integration ----------

T, F = True, False


async def _run(plan: dict[int, list[bool]], max_rounds: int = 2):
    jobs: list[str] = []

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        jobs.append(job)
        if job == "replan_after_failure":
            content = "1. a\n2. b\n3. c\n4. d"
        elif job == "generate_adversarial_test":
            content = ADVERSARIAL_RESPONSE
        elif job == "generate_confidence_report":
            content = "### PatchTree Confidence Report\n\n**Verdict:** ok\n"
        else:
            content = "```diff\n--- a\n+++ b\n```"
        return {"content": content, "model": "stub", "tokens_in": 1, "tokens_out": 1, "stub": True}

    run = Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc),
              repo_url="https://github.com/example/repo", bug_description="x", target_test="pytest t.py")
    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        final, nodes = await pipeline.run_pipeline(run, max_rounds=max_rounds, sandbox=AdversarialSandbox(plan))
    finally:
        pipeline.call_model = original
    return final, nodes, jobs


def test_pipeline_clean_run_produces_13_nodes():
    # Candidate 1: branch pass + 5 stability + 2 adversarial + full suite, all passing.
    final, nodes, jobs = asyncio.run(_run({1: [T] * 9}))
    assert final.status == "complete" and final.confidence_score == 1.0
    assert (final.adversarial_runs, final.adversarial_survived) == (2, 2)
    assert final.full_suite_result == "pass"
    assert final.confidence_report is not None
    assert len(nodes) == 13, f"expected 1 root + 4 search + 5 stability + 2 adversarial + 1 full_suite, got {len(nodes)}"
    assert nodes[0].branch_type == "root"
    assert [n.branch_type for n in nodes[1:5]] == ["search"] * 4
    assert [n.branch_type for n in nodes[5:10]] == ["stability"] * 5
    assert [n.branch_type for n in nodes[10:12]] == ["adversarial"] * 2
    assert nodes[12].branch_type == "full_suite"
    assert jobs.count("generate_adversarial_test") == 2
    assert jobs.count("generate_confidence_report") == 1
    adversarial = nodes[10:12]
    assert all(n.parent_node_id == final.winner_node_id for n in adversarial)
    assert all(n.test_result == "pass" for n in adversarial)
    assert nodes[12].parent_node_id == final.winner_node_id


def test_pipeline_partial_adversarial_survival():
    # Candidate 0: branch + 5 stability + 2 adversarial + full suite; one attack breaks the patch.
    final, nodes, jobs = asyncio.run(_run({0: [T] * 6 + [T, F, T]}))
    assert final.status == "complete" and final.winner_node_id is not None
    assert (final.adversarial_runs, final.adversarial_survived) == (2, 1)
    assert final.full_suite_result == "pass"
    # 0.4*1.0 + 0.4*0.5 + 0.2*1.0 = 0.8
    assert final.confidence_score == 0.8, f"expected 0.4*1 + 0.4*0.5 + 0.2*1, got {final.confidence_score}"
    adversarial = [n for n in nodes if n.branch_type == "adversarial"]
    assert len(adversarial) == 2
    assert all(n.parent_node_id == final.winner_node_id for n in adversarial)


if __name__ == "__main__":
    test_patch_survives_all_attacks()
    test_patch_broken_by_attack()
    test_pipeline_clean_run_produces_13_nodes()
    test_pipeline_partial_adversarial_survival()
    print("OK")
