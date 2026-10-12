"""Integration tests for full-suite check and Nemotron Ultra confidence reports."""
import asyncio
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import Node, Run
from app.orchestrator import pipeline
from app.orchestrator.pipeline import generate_confidence_report, run_full_suite
from app.sandbox.contree_client import PATCH_MARKER, CommandResult, SandboxManager

T, F = True, False

REPORT_STUB = (
    "### PatchTree Confidence Report\n\n"
    "**Verdict:** Verified Stable & Resilient\n"
)
FAILURE_REPORT_STUB = (
    "### Honest Failure Report\n\n"
    "No candidate passed verification. Least-bad attempt noted.\n"
)


class ReportSandbox(SandboxManager):
    """Stub sandbox where the i-th patched candidate follows plan[i].

    plan[i] = [branch, stability x5, adversarial x2, full_suite].
    """

    def __init__(self, plan: dict[int, list[bool]], _shared: dict | None = None):
        super().__init__(force_stub=True)
        self.plan = plan
        self.shared = _shared if _shared is not None else {"order": [], "runs": {}, "lock": threading.Lock()}

    def fork(self, checkpoint_id: str) -> "ReportSandbox":
        child = ReportSandbox(self.plan, self.shared)
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


def _setup(sandbox: SandboxManager) -> tuple[Run, Node]:
    run = Run(
        run_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        repo_url="https://github.com/example/repo",
        bug_description="off by one",
        target_test="pytest t.py",
        full_suite_test="pytest",
    )
    sandbox.spawn("python:3.11")
    sandbox.run_command(f"{PATCH_MARKER} c1.diff")
    cand = Node(
        node_id="c1",
        run_id=run.run_id,
        branch_type="search",
        checkpoint_id=sandbox.checkpoint(),
        test_command=run.target_test,
        test_result="pass",
        patch_diff="--- a/app.py\n+++ b/app.py",
        stability_runs=5,
        stability_passes=5,
        is_stable=True,
    )
    return run, cand


async def _run(plan: dict[int, list[bool]], max_rounds: int = 2):
    jobs: list[str] = []

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        jobs.append(job)
        if job == "replan_after_failure":
            content = "1. a\n2. b\n3. c\n4. d"
        elif job == "generate_adversarial_test":
            content = "```python\ndef test_adversarial_edge_case():\n    assert True\n```"
        elif job == "generate_confidence_report":
            content = FAILURE_REPORT_STUB if "Honest Failure" in prompt else REPORT_STUB
        else:
            content = "```diff\n--- a\n+++ b\n```"
        return {"content": content, "model": "stub", "tokens_in": 1, "tokens_out": 1, "stub": True}

    run = Run(
        run_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        repo_url="https://github.com/example/repo",
        bug_description="x",
        target_test="pytest t.py",
    )
    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        final, nodes = await pipeline.run_pipeline(run, max_rounds=max_rounds, sandbox=ReportSandbox(plan))
    finally:
        pipeline.call_model = original
    return final, nodes, jobs


def test_run_full_suite_pass():
    sb = ReportSandbox({0: [T]})
    run, cand = _setup(sb)
    # Consume no plan via branch indexing: candidate already patched; first pytest is full suite.
    # Reset plan so the single patched history's first pytest uses step 0.
    sb.shared["order"] = []
    sb.shared["runs"] = {}
    sb.plan = {0: [T]}
    node = asyncio.run(run_full_suite(run, cand, sb))
    assert node.branch_type == "full_suite"
    assert node.parent_node_id == cand.node_id
    assert node.test_result == "pass"
    assert run.full_suite_result == "pass"


def test_run_full_suite_fail():
    sb = ReportSandbox({})
    run, cand = _setup(sb)
    sb.shared["order"] = []
    sb.shared["runs"] = {}
    sb.plan = {0: [F]}
    node = asyncio.run(run_full_suite(run, cand, sb))
    assert node.branch_type == "full_suite"
    assert node.test_result == "fail"
    assert run.full_suite_result == "fail"


def test_generate_confidence_report_winner():
    run = Run(
        run_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        repo_url="https://github.com/example/repo",
        bug_description="bug",
        target_test="pytest t.py",
        confidence_score=1.0,
        adversarial_runs=2,
        adversarial_survived=2,
        full_suite_result="pass",
        total_cost_usd=0.001,
        total_wall_time_seconds=12.0,
    )
    winner = Node(
        node_id="w1",
        run_id=run.run_id,
        branch_type="search",
        patch_diff="--- a\n+++ b",
        stability_runs=5,
        stability_passes=5,
        is_stable=True,
    )
    captured: dict = {}

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        captured["job"] = job
        captured["prompt"] = prompt
        return {"content": REPORT_STUB, "model": "stub/ultra", "tokens_in": 10, "tokens_out": 80, "stub": True}

    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        report = asyncio.run(generate_confidence_report(run, winner, [winner]))
    finally:
        pipeline.call_model = original

    assert captured["job"] == "generate_confidence_report"
    assert run.bug_description in captured["prompt"]
    assert winner.patch_diff in captured["prompt"]
    assert "5/5" in captured["prompt"]
    assert report == REPORT_STUB


def test_generate_confidence_report_failure():
    run = Run(
        run_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        repo_url="https://github.com/example/repo",
        bug_description="bug",
        target_test="pytest t.py",
    )
    captured: dict = {}

    async def fake_call_model(job, prompt, system_prompt=None, temperature=0.3):
        captured["prompt"] = prompt
        return {"content": FAILURE_REPORT_STUB, "model": "stub/ultra", "tokens_in": 5, "tokens_out": 40, "stub": True}

    original, pipeline.call_model = pipeline.call_model, fake_call_model
    try:
        report = asyncio.run(generate_confidence_report(run, None, []))
    finally:
        pipeline.call_model = original

    assert "Honest Failure" in captured["prompt"]
    assert report == FAILURE_REPORT_STUB


def test_pipeline_produces_13_nodes_and_report():
    final, nodes, jobs = asyncio.run(_run({1: [T] * 9}))
    assert final.status == "complete"
    assert final.confidence_score == 1.0
    assert final.full_suite_result == "pass"
    assert final.confidence_report is not None
    assert "Confidence Report" in final.confidence_report
    assert len(nodes) == 13, f"expected 1+4+5+2+1=13, got {len(nodes)}"
    assert nodes[0].branch_type == "root"
    assert [n.branch_type for n in nodes[1:5]] == ["search"] * 4
    assert [n.branch_type for n in nodes[5:10]] == ["stability"] * 5
    assert [n.branch_type for n in nodes[10:12]] == ["adversarial"] * 2
    assert nodes[12].branch_type == "full_suite"
    assert nodes[12].parent_node_id == final.winner_node_id
    assert nodes[12].test_result == "pass"
    assert jobs.count("generate_confidence_report") == 1
    assert jobs.count("generate_adversarial_test") == 2


def test_pipeline_full_suite_fail_lowers_confidence():
    # branch + 5 stability + 2 adversarial pass; full suite fails
    final, nodes, jobs = asyncio.run(_run({0: [T] * 8 + [F]}))
    assert final.status == "complete"
    assert final.full_suite_result == "fail"
    # 0.4*1 + 0.4*1 + 0.2*0 = 0.8
    assert final.confidence_score == 0.8
    suite = [n for n in nodes if n.branch_type == "full_suite"]
    assert len(suite) == 1 and suite[0].test_result == "fail"
    assert final.confidence_report is not None


def test_pipeline_honest_failure_report():
    final, nodes, jobs = asyncio.run(_run({}))
    assert final.status == "failed"
    assert final.winner_node_id is None
    assert final.confidence_report is not None
    assert "Failure" in final.confidence_report
    assert jobs.count("generate_confidence_report") == 1
    assert not any(n.branch_type == "full_suite" for n in nodes)


if __name__ == "__main__":
    test_run_full_suite_pass()
    test_run_full_suite_fail()
    test_generate_confidence_report_winner()
    test_generate_confidence_report_failure()
    test_pipeline_produces_13_nodes_and_report()
    test_pipeline_full_suite_fail_lowers_confidence()
    test_pipeline_honest_failure_report()
    print("OK")
