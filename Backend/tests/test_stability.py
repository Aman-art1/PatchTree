import asyncio
import itertools
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import Node, Run
from app.orchestrator import pipeline
from app.orchestrator.pipeline import check_stability
from app.sandbox.contree_client import PATCH_MARKER, CommandResult, SandboxManager


class FlakySandbox(SandboxManager):
    """Stub sandbox whose forked test runs fail on the given call indices (shared across forks)."""

    def __init__(self, fail_on: set[int]):
        super().__init__(force_stub=True)
        self._fail_on, self._counter = fail_on, itertools.count()

    def fork(self, checkpoint_id: str) -> "FlakySandbox":
        child = FlakySandbox.__new__(FlakySandbox)
        child.__dict__.update(super().fork(checkpoint_id).__dict__)
        child._fail_on, child._counter = self._fail_on, self._counter
        return child

    def run_command(self, cmd: str) -> CommandResult:
        if next(self._counter) in self._fail_on:
            return CommandResult(1, "FAILED (flaky)")
        return CommandResult(0, "== 1 passed ==")


def _setup(sandbox: SandboxManager) -> tuple[Run, Node]:
    run = Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc),
              repo_url="https://github.com/example/repo", bug_description="x", target_test="pytest t.py")
    sandbox.spawn("python:3.11")
    cand = Node(node_id="c1", run_id=run.run_id, branch_type="search", checkpoint_id=sandbox.checkpoint(),
                test_command=run.target_test, test_result="pass")
    return run, cand


def test_stable_candidate():
    sb = FlakySandbox(fail_on=set())
    run, cand = _setup(sb)
    nodes = asyncio.run(check_stability(run, cand, sb))
    assert len(nodes) == 5 and all(n.branch_type == "stability" for n in nodes)
    assert (cand.is_stable, cand.stability_runs, cand.stability_passes) == (True, 5, 5)


def test_flaky_candidate():
    sb = FlakySandbox(fail_on={1, 3})
    run, cand = _setup(sb)
    nodes = asyncio.run(check_stability(run, cand, sb))
    assert sum(n.test_result == "pass" for n in nodes) == 3
    assert (cand.is_stable, cand.stability_runs, cand.stability_passes) == (False, 5, 3)


# ---------- run_pipeline integration ----------

T, F = True, False


class ScriptedSandbox(SandboxManager):
    """Stub sandbox where the i-th patched candidate (in test order) follows plan[i].

    plan[i] = results of that candidate's successive test runs: [branch run, stability x5].
    Unplanned candidates fail; the reproduce run (no patch applied) always fails.
    """

    def __init__(self, plan: dict[int, list[bool]], _shared: dict | None = None):
        super().__init__(force_stub=True)
        self.plan = plan
        self.shared = _shared if _shared is not None else {"order": [], "runs": {}, "lock": threading.Lock()}

    def fork(self, checkpoint_id: str) -> "ScriptedSandbox":
        child = ScriptedSandbox(self.plan, self.shared)
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
        with self.shared["lock"]:
            if patch not in self.shared["order"]:
                self.shared["order"].append(patch)
            idx = self.shared["order"].index(patch)
            n = self.shared["runs"][patch] = self.shared["runs"].get(patch, -1) + 1
        steps = self.plan.get(idx, [])
        ok = steps[n] if n < len(steps) else False
        return CommandResult(0 if ok else 1, "passed" if ok else "FAILED")


async def _run(plan: dict[int, list[bool]], max_rounds: int = 2):
    jobs: list[str] = []

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        jobs.append(job)
        content = "1. a\n2. b\n3. c\n4. d" if job == "replan_after_failure" else "```diff\n--- a\n+++ b\n```"
        return {"content": content, "model": "stub", "tokens_in": 1, "tokens_out": 1, "stub": True}

    run = Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc),
              repo_url="https://github.com/example/repo", bug_description="x", target_test="pytest t.py")
    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        final, nodes = await pipeline.run_pipeline(run, max_rounds=max_rounds, sandbox=ScriptedSandbox(plan))
    finally:
        pipeline.call_model = original
    return final, nodes, jobs


def _search(nodes: list[Node]) -> list[Node]:
    return [n for n in nodes if n.branch_type == "search"]


def test_pipeline_promotes_stable_winner():
    final, nodes, jobs = asyncio.run(_run({1: [T] * 6}))
    winner = _search(nodes)[1]
    assert final.status == "complete" and final.winner_node_id == winner.node_id
    assert final.confidence_score == 1.0 and winner.is_stable
    assert len(nodes) == 1 + 4 + 5 and "replan_after_failure" not in jobs


def test_pipeline_falls_back_to_second_candidate():
    final, nodes, jobs = asyncio.run(_run({0: [T, T, T, F, T, T], 1: [T] * 6}))
    first, second = _search(nodes)[:2]
    assert first.is_stable is False and first.stability_passes == 5 - 1
    assert final.winner_node_id == second.node_id and final.confidence_score == 1.0
    assert len(nodes) == 1 + 4 + 5 + 5 and "replan_after_failure" not in jobs


def test_pipeline_replans_when_all_candidates_flaky():
    flaky = [T, T, F, T, T, T]
    final, nodes, jobs = asyncio.run(_run({0: flaky, 1: flaky, 4: [T] * 6}))
    r1, r2 = _search(nodes)[:4], _search(nodes)[4:]
    assert r1[0].is_stable is False and r1[1].is_stable is False
    assert jobs.count("replan_after_failure") == 1
    assert final.status == "complete" and final.winner_node_id == r2[0].node_id
    assert len(nodes) == 1 + 4 + 5 + 5 + 4 + 5


def test_pipeline_fails_when_always_flaky():
    flaky = [T, F, F, F, F, F]
    final, nodes, jobs = asyncio.run(_run({i: flaky for i in range(8)}))
    assert final.status == "failed" and final.winner_node_id is None
    assert all(n.is_stable is False for n in nodes if n.branch_type == "search" and n.test_result == "pass")


if __name__ == "__main__":
    test_stable_candidate()
    test_flaky_candidate()
    test_pipeline_promotes_stable_winner()
    test_pipeline_falls_back_to_second_candidate()
    test_pipeline_replans_when_all_candidates_flaky()
    test_pipeline_fails_when_always_flaky()
    print("OK")
