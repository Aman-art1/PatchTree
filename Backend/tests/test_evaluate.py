"""Test Phase 1 Sub-step 3: evaluate_search, replan, and run_pipeline."""
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.models.schemas import Node, Run, RunCreate
from app.orchestrator import pipeline
from app.sandbox.contree_client import PATCH_MARKER, CommandResult, SandboxManager


def _make_run() -> Run:
    req = RunCreate(
        repo_url="https://github.com/example/repo",
        bug_description="Function returns 1 instead of 2",
        target_test="pytest tests/test_bug.py",
    )
    return Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), **req.model_dump())


def _make_node(test_result: str, run_id: str, tag: str = "") -> Node:
    return Node(
        node_id=str(uuid.uuid4()),
        run_id=run_id,
        branch_type="search",
        checkpoint_id=str(uuid.uuid4()),
        hypothesis=f"hypothesis {tag}",
        patch_diff=f"diff {tag}",
        test_command="pytest tests/test_bug.py",
        test_result=test_result,
        test_output=f"test output {tag or test_result}",
        model_used="stub/model",
        tokens_in=10,
        tokens_out=20,
        status="done",
    )


class AlwaysFailingSandbox(SandboxManager):
    """Stub sandbox where tests never pass, even after apply_patch."""

    def __init__(self, force_stub: bool = True):
        super().__init__(force_stub=True)

    def fork(self, checkpoint_id: str) -> "AlwaysFailingSandbox":
        child = AlwaysFailingSandbox()
        child._history = list(self._checkpoints[checkpoint_id])
        child._checkpoints = self._checkpoints
        return child

    def _stub_run(self, cmd: str) -> CommandResult:
        self._history.append(cmd)
        if cmd.startswith(PATCH_MARKER):
            return CommandResult(0, "patch applied")
        if "pytest" in cmd or "test" in cmd:
            return CommandResult(1, "FAILED tests/test_bug.py::test_bug\n== 1 failed in 0.01s ==")
        return CommandResult(0, "")


class SecondRoundPassSandbox(AlwaysFailingSandbox):
    """Stub sandbox that fails every test through call 5, then passes.

    Call 1 is the reproduce test; calls 2-5 are the round-1 branch tests, so
    round 1 always fails and round 2 always passes.
    """

    test_calls = 0

    def fork(self, checkpoint_id: str) -> "SecondRoundPassSandbox":
        child = SecondRoundPassSandbox()
        child._history = list(self._checkpoints[checkpoint_id])
        child._checkpoints = self._checkpoints
        return child

    def _stub_run(self, cmd: str) -> CommandResult:
        self._history.append(cmd)
        if cmd.startswith(PATCH_MARKER):
            return CommandResult(0, "patch applied")
        if "pytest" in cmd or "test" in cmd:
            type(self).test_calls += 1
            if type(self).test_calls > 5:
                return CommandResult(0, "== 1 passed in 0.01s ==")
            return CommandResult(1, "FAILED tests/test_bug.py::test_bug\n== 1 failed in 0.01s ==")
        return CommandResult(0, "")


# ---------- evaluate_search ----------


def test_evaluate_search():
    print("\n=== test_evaluate_search ===")
    run = _make_run()

    # All 4 branches fail -> None
    branches = [_make_node("fail", run.run_id) for _ in range(4)]
    assert pipeline.evaluate_search(branches) is None
    print("all fail -> None: OK")

    # Mixed results -> the passing node wins
    winner = _make_node("pass", run.run_id)
    branches = [_make_node("fail", run.run_id), winner, _make_node("error", run.run_id), _make_node("fail", run.run_id)]
    assert pipeline.evaluate_search(branches) is winner
    print("one pass -> winner: OK")

    # Multiple passes -> first one wins (deterministic)
    first, second = _make_node("pass", run.run_id), _make_node("pass", run.run_id)
    assert pipeline.evaluate_search([first, second]) is first
    print("multiple pass -> first: OK")

    # Empty input -> None
    assert pipeline.evaluate_search([]) is None
    print("empty -> None: OK")

    print("test_evaluate_search: all assertions passed")


# ---------- replan ----------


async def test_replan():
    print("\n=== test_replan ===")
    run = _make_run()
    failed = [_make_node("fail", run.run_id, tag=f"branch-{i}") for i in range(4)]

    captured: dict = {}

    async def fake_call_model(job: str, prompt: str, system_prompt: str | None = None, temperature: float = 0.3) -> dict:
        captured["job"] = job
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return {
            "content": "1. Fix the off-by-one in the return statement\n"
            "2. Refactor the parsing layer instead\n"
            "3. Patch the caller, not the callee\n"
            "4. Align the test double with real behavior",
            "model": "stub/nemotron-ultra",
            "tokens_in": 100,
            "tokens_out": 50,
            "stub": True,
        }

    original = pipeline.call_model
    pipeline.call_model = fake_call_model
    try:
        guidance = await pipeline.replan(run, failed)
    finally:
        pipeline.call_model = original

    assert captured["job"] == "replan_after_failure", f"wrong job: {captured['job']}"
    print(f"job routed to: {captured['job']}")

    # All 4 failed branch outputs are concatenated into the prompt
    for i in range(4):
        assert f"test output branch-{i}" in captured["prompt"], f"prompt missing branch {i} output"
        assert f"diff branch-{i}" in captured["prompt"], f"prompt missing branch {i} patch"
    assert run.bug_description in captured["prompt"]
    print("prompt contains all 4 failed branch outputs: OK")

    assert len(guidance) == 4, f"expected 4 guidance strings, got {len(guidance)}"
    assert all(isinstance(g, str) and g for g in guidance)
    print(f"guidance: {guidance}")
    print("test_replan: all assertions passed")


# ---------- run_pipeline ----------


async def test_run_pipeline_winner_round_1():
    print("\n=== test_run_pipeline_winner_round_1 ===")
    run = _make_run()

    final_run, all_nodes = await pipeline.run_pipeline(run, max_rounds=2)

    # Default stub passes tests after apply_patch, so round 1 finds a winner
    assert final_run.status == "complete", f"expected complete, got {final_run.status}"
    assert final_run.winner_node_id is not None
    node_ids = {n.node_id for n in all_nodes}
    assert final_run.winner_node_id in node_ids, "winner not among created nodes"
    assert len(all_nodes) == 5, f"expected root + 4 branches, got {len(all_nodes)}"
    assert all_nodes[0].branch_type == "root"
    assert final_run.completed_at is not None
    print(f"winner in round 1: {final_run.winner_node_id}")
    print("test_run_pipeline_winner_round_1: all assertions passed")


async def test_run_pipeline_replans_and_wins_round_2():
    print("\n=== test_run_pipeline_replans_and_wins_round_2 ===")
    run = _make_run()
    SecondRoundPassSandbox.test_calls = 0

    jobs_called: list[str] = []
    real_call_model = pipeline.call_model

    async def spy_call_model(job: str, prompt: str, system_prompt: str | None = None, temperature: float = 0.3) -> dict:
        jobs_called.append(job)
        if job == "replan_after_failure":
            return {
                "content": "1. a\n2. b\n3. c\n4. d",
                "model": "stub/nemotron-ultra",
                "tokens_in": 1,
                "tokens_out": 1,
                "stub": True,
            }
        return await real_call_model(job=job, prompt=prompt, system_prompt=system_prompt, temperature=temperature)

    original_sandbox = pipeline.SandboxManager
    pipeline.call_model = spy_call_model
    pipeline.SandboxManager = SecondRoundPassSandbox
    try:
        final_run, all_nodes = await pipeline.run_pipeline(run, max_rounds=2)
    finally:
        pipeline.call_model = real_call_model
        pipeline.SandboxManager = original_sandbox

    assert "replan_after_failure" in jobs_called, "replan was not invoked after round 1 failed"
    assert final_run.status == "complete", f"expected complete, got {final_run.status}"
    assert final_run.winner_node_id is not None
    assert len(all_nodes) == 9, f"expected root + 4 + 4 nodes, got {len(all_nodes)}"
    print(f"winner in round 2 after replan: {final_run.winner_node_id}")
    print("test_run_pipeline_replans_and_wins_round_2: all assertions passed")


async def test_run_pipeline_honest_failure():
    print("\n=== test_run_pipeline_honest_failure ===")
    run = _make_run()

    original_sandbox = pipeline.SandboxManager
    pipeline.SandboxManager = AlwaysFailingSandbox
    try:
        final_run, all_nodes = await pipeline.run_pipeline(run, max_rounds=2)
    finally:
        pipeline.SandboxManager = original_sandbox

    assert final_run.status == "failed", f"expected failed, got {final_run.status}"
    assert final_run.winner_node_id is None
    assert len(all_nodes) == 9, f"expected root + 4 + 4 nodes, got {len(all_nodes)}"
    assert final_run.completed_at is not None
    print(f"no winner after 2 rounds -> status: {final_run.status}, nodes: {len(all_nodes)}")
    print("test_run_pipeline_honest_failure: all assertions passed")


if __name__ == "__main__":
    test_evaluate_search()
    asyncio.run(test_replan())
    asyncio.run(test_run_pipeline_winner_round_1())
    asyncio.run(test_run_pipeline_replans_and_wins_round_2())
    asyncio.run(test_run_pipeline_honest_failure())
    print("\nAll evaluate/replan tests passed!")
