"""SearchNode fan-out, evaluation, replan, and pipeline orchestration."""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from ..llm.router import call_model
from ..models.schemas import Node, Run
from ..sandbox.contree_client import CommandResult, SandboxManager

logger = logging.getLogger(__name__)

# Branch definitions: (job, temperature, instruction_template)
SEARCH_BRANCHES: list[tuple[str, float, str]] = [
    (
        "generate_patch_minimal",
        0.2,
        """You are a minimal-fix expert. Generate the smallest possible patch that fixes this bug.

Bug description: {bug_description}
Test command: {test_command}
Current test output (failing): {test_output}

Provide a unified diff patch that makes the test pass with minimal changes. Focus on the most direct fix.""",
    ),
    (
        "generate_patch_alternative",
        0.5,
        """You are exploring alternative approaches. Generate a patch using a different strategy than the obvious fix.

Bug description: {bug_description}
Test command: {test_command}
Current test output (failing): {test_output}

Provide a unified diff patch that fixes the bug using an alternative approach or refactoring.""",
    ),
    (
        "generate_patch_root_cause",
        0.6,
        """You are a root-cause analyst. The bug might not be where it appears. Look for the underlying cause elsewhere.

Bug description: {bug_description}
Test command: {test_command}
Current test output (failing): {test_output}

Provide a unified diff patch that addresses the root cause, which may be in a different module or layer.""",
    ),
    (
        "generate_patch_test_driven",
        0.2,
        """You are a test-driven development expert. Generate a patch that strictly satisfies the test contract.

Bug description: {bug_description}
Test command: {test_command}
Current test output (failing): {test_output}

Provide a unified diff patch that makes the test pass by strictly adhering to the expected behavior.""",
    ),
]

REPLAN_SYSTEM_PROMPT = (
    "You are a repair strategist. Every patch attempt in the previous round failed. "
    "Analyze the failures and reply with exactly 4 revised strategies for the next round, "
    "as numbered lines 1-4, one concise sentence each."
)

ADVERSARIAL_SYSTEM_PROMPT = (
    "You are an adversarial tester. Given a bug description, the target test, and a "
    "candidate patch, write one pytest test function designed to break the patch: probe "
    "edge cases, boundary values, and regressions the patch may have missed. "
    "Reply with only a python code block containing the test."
)

ADVERSARIAL_TEST_FILENAME = "test_adversarial_check.py"


def reproduce(run: Run, sandbox: SandboxManager) -> Node:
    """ReproduceNode: boot sandbox, run target test, record the failing root node."""
    sandbox.spawn("python:3.11")
    result = sandbox.run_command(run.target_test)
    return Node(
        node_id=str(uuid.uuid4()),
        run_id=run.run_id,
        branch_type="root",
        checkpoint_id=sandbox.checkpoint(),
        test_command=run.target_test,
        test_result="fail" if result.exit_code else "pass",
        test_output=result.output,
        status="done",
    )


def evaluate_search(branches: list[Node]) -> Node | None:
    """
    Deterministically pick a winner from a search round.

    Args:
        branches: Nodes produced by a search round.

    Returns:
        The first Node with test_result == "pass", or None if all failed.
    """
    for node in branches:
        if node.test_result == "pass":
            return node
    return None


def _parse_guidance(content: str) -> list[str]:
    """Extract up to 4 guidance strings from a replan response."""
    guidance = [
        m.group(1).strip()
        for m in re.finditer(r"(?m)^\s*\d+[.)]\s*(.+?)\s*$", content)
    ]
    if not guidance:
        guidance = [line.strip() for line in content.splitlines() if line.strip()]
    return guidance[:4]


async def replan(run: Run, failed_branches: list[Node]) -> list[str]:
    """
    After a failed search round, ask the Ultra tier for revised guidance.

    Concatenates every failed branch's hypothesis, patch, and test output into
    one prompt so the model can see why each attempt failed.

    Args:
        run: The Run being repaired.
        failed_branches: Nodes from the failed round.

    Returns:
        Up to 4 revised guidance strings, one per branch, for the next round.
    """
    attempts = "\n\n".join(
        f"--- Attempt {i + 1} ---\n"
        f"hypothesis: {node.hypothesis or ''}\n"
        f"patch:\n{node.patch_diff or ''}\n"
        f"test output:\n{node.test_output or ''}"
        for i, node in enumerate(failed_branches)
    )
    prompt = (
        f"Bug description: {run.bug_description}\n"
        f"Test command: {run.target_test}\n\n"
        f"All {len(failed_branches)} patch attempts failed:\n\n{attempts}\n\n"
        "Propose 4 revised strategies for the next search round."
    )
    response = await call_model(
        job="replan_after_failure",
        prompt=prompt,
        system_prompt=REPLAN_SYSTEM_PROMPT,
    )
    guidance = _parse_guidance(response["content"])
    logger.info("Replan produced %d guidance strings", len(guidance))
    return guidance


def extract_diff(content: str) -> str:
    """Extract unified diff from model response, stripping markdown fences if present."""
    match = re.search(r"```(?:diff|patch)?\s*\n([\s\S]*?)\n```", content)
    if match:
        return match.group(1).strip()
    return content.strip()


def extract_code(content: str) -> str:
    """Extract a python code block from a model response, stripping markdown fences."""
    match = re.search(r"```(?:python|py)?\s*\n([\s\S]*?)\n```", content)
    if match:
        return match.group(1).strip()
    return content.strip()


async def _execute_branch(
    run: Run,
    parent_node: Node,
    parent_sandbox: SandboxManager,
    branch_index: int,
    job: str,
    temperature: float,
    instruction_template: str,
    guidance: str | None = None,
) -> Node:
    """Execute a single search branch: fork, call model, apply patch, test."""
    node_id = str(uuid.uuid4())
    logger.info(f"Branch {branch_index + 1}/4 ({job}): starting node {node_id}")

    # Fork the sandbox from parent checkpoint
    fork = parent_sandbox.fork(parent_node.checkpoint_id)

    # Build the prompt
    prompt = instruction_template.format(
        bug_description=run.bug_description,
        test_command=parent_node.test_command or run.target_test,
        test_output=parent_node.test_output or "",
    )
    if guidance:
        prompt += f"\n\nRevised guidance from the failed previous round: {guidance}"

    # Call the model
    model_response = await call_model(job=job, prompt=prompt, temperature=temperature)

    # Extract patch from response (clean markdown fences if model wrapped the diff)
    raw_content = model_response.get("content", "")
    patch_diff = extract_diff(raw_content) or raw_content
    hypothesis = f"{job}: {patch_diff[:100]}..."

    # Apply the patch in the forked sandbox
    apply_result = fork.run_command(f"apply_patch {node_id}.diff")
    logger.debug(f"Branch {branch_index + 1}: patch apply exit_code={apply_result.exit_code}")

    if apply_result.exit_code != 0:
        test_result: Literal["pass", "fail", "error"] = "error"
        test_output = f"Patch application failed:\n{apply_result.output}"
    else:
        # Run the test
        test_result_obj = fork.run_command(parent_node.test_command or run.target_test)
        test_result = "pass" if test_result_obj.exit_code == 0 else "fail"
        test_output = test_result_obj.output

    # Create checkpoint after applying patch
    checkpoint_id = fork.checkpoint()

    node = Node(
        node_id=node_id,
        run_id=run.run_id,
        parent_node_id=parent_node.node_id,
        branch_type="search",
        checkpoint_id=checkpoint_id,
        hypothesis=hypothesis,
        patch_diff=patch_diff,
        test_command=parent_node.test_command or run.target_test,
        test_result=test_result,
        test_output=test_output,
        model_used=model_response["model"],
        tokens_in=model_response["tokens_in"],
        tokens_out=model_response["tokens_out"],
        status="done",
    )

    logger.info(
        f"Branch {branch_index + 1}/4 ({job}): node {node_id} -> test_result={test_result}, "
        f"tokens={model_response['tokens_in']}+{model_response['tokens_out']}"
    )

    return node


async def search_round(
    run: Run,
    parent_node: Node,
    round_num: int = 1,
    guidance: list[str] | None = None,
    sandbox: SandboxManager | None = None,
) -> list[Node]:
    """
    Execute a single search round with 4 concurrent branches from parent_node.

    Args:
        run: The Run object containing bug description and test command
        parent_node: The parent Node (typically root node from reproduce step)
        round_num: Round number for logging (default: 1)
        guidance: Optional revised strategies from replan(); guidance[i] is
            appended to branch i's prompt when present.
        sandbox: Optional sandbox instance (defaults to SandboxManager()).

    Returns:
        List of 4 Node objects, one per search branch
    """
    logger.info(f"=== Search Round {round_num}: starting 4-branch fan-out from node {parent_node.node_id} ===")

    # Create a parent sandbox from the parent checkpoint
    # We'll reuse this to fork for each branch
    parent_sandbox = sandbox or SandboxManager()
    if parent_sandbox.stub:
        parent_sandbox._checkpoints.setdefault(parent_node.checkpoint_id, [])

    # Build tasks for concurrent execution
    tasks = [
        _execute_branch(
            run=run,
            parent_node=parent_node,
            parent_sandbox=parent_sandbox,
            branch_index=i,
            job=job,
            temperature=temp,
            instruction_template=instruction,
            guidance=guidance[i] if guidance and i < len(guidance) else None,
        )
        for i, (job, temp, instruction) in enumerate(SEARCH_BRANCHES)
    ]

    # Execute all 4 branches concurrently
    nodes = await asyncio.gather(*tasks)

    logger.info(f"=== Search Round {round_num}: completed 4 branches ===")
    return list(nodes)


async def check_stability(
    run: Run,
    candidate: Node,
    sandbox: SandboxManager,
    k: int = 5,
) -> list[Node]:
    """
    Flaky-test forensics: fork the candidate's checkpoint k times and re-run the test in each fork.

    Args:
        run: The Run being repaired.
        candidate: A Node whose test passed once; updated in place with is_stable,
            stability_runs and stability_passes (stable only if every fork passes).
        sandbox: Sandbox used to fork the candidate checkpoint.
        k: Number of concurrent forks (default 5).

    Returns:
        One "stability" Node per fork.
    """
    cmd = candidate.test_command or run.target_test

    def _one() -> Node:
        fork = sandbox.fork(candidate.checkpoint_id)
        result = fork.run_command(cmd)
        return Node(
            node_id=str(uuid.uuid4()),
            run_id=run.run_id,
            parent_node_id=candidate.node_id,
            branch_type="stability",
            checkpoint_id=fork.checkpoint(),
            test_command=cmd,
            test_result="pass" if result.exit_code == 0 else "fail",
            test_output=result.output,
            status="done",
        )

    nodes = list(await asyncio.gather(*(asyncio.to_thread(_one) for _ in range(k))))
    candidate.stability_runs = k
    candidate.stability_passes = sum(n.test_result == "pass" for n in nodes)
    candidate.is_stable = candidate.stability_passes == k
    logger.info(f"Stability: node {candidate.node_id} passed {candidate.stability_passes}/{k}")
    return nodes


async def check_adversarial(
    run: Run,
    candidate: Node,
    sandbox: SandboxManager,
    m: int = 2,
) -> list[Node]:
    """
    Adversarial verification: fork the candidate checkpoint m times and, in each fork,
    write and run a freshly generated adversarial pytest designed to break the patch.

    test_result="pass" means the patch survived the attack; "fail" means the attack
    exposed a flaw. Sets run.adversarial_runs and run.adversarial_survived.

    Args:
        run: The Run being repaired.
        candidate: The stability-verified winner Node.
        sandbox: Sandbox used to fork the candidate checkpoint.
        m: Number of concurrent adversarial forks (default 2).

    Returns:
        One "adversarial" Node per fork.
    """
    prompt = (
        f"Bug description: {run.bug_description}\n"
        f"Target test command: {candidate.test_command or run.target_test}\n\n"
        f"Candidate patch under attack:\n{candidate.patch_diff or ''}\n\n"
        f"Write one pytest test function to save as {ADVERSARIAL_TEST_FILENAME} that tries "
        "to break this patch: edge cases, boundary inputs, and regressions it may miss."
    )
    test_command = f"pytest {ADVERSARIAL_TEST_FILENAME}"

    async def _one(index: int) -> Node:
        response = await call_model(
            job="generate_adversarial_test",
            prompt=prompt,
            system_prompt=ADVERSARIAL_SYSTEM_PROMPT,
        )
        test_code = extract_code(response["content"])

        def _exec() -> tuple[CommandResult, str]:
            fork = sandbox.fork(candidate.checkpoint_id)
            write = fork.run_command(
                f"cat > {ADVERSARIAL_TEST_FILENAME} << 'PATCHTREE_EOF'\n"
                f"{test_code}\nPATCHTREE_EOF"
            )
            logger.debug(f"Adversarial fork {index + 1}: write exit_code={write.exit_code}")
            result = fork.run_command(test_command)
            return result, fork.checkpoint()

        result, checkpoint_id = await asyncio.to_thread(_exec)
        return Node(
            node_id=str(uuid.uuid4()),
            run_id=run.run_id,
            parent_node_id=candidate.node_id,
            branch_type="adversarial",
            checkpoint_id=checkpoint_id,
            hypothesis=f"adversarial fork {index + 1}: {test_code.splitlines()[0] if test_code else 'empty'}",
            test_command=test_command,
            test_result="pass" if result.exit_code == 0 else "fail",
            test_output=result.output,
            model_used=response["model"],
            tokens_in=response["tokens_in"],
            tokens_out=response["tokens_out"],
            status="done",
        )

    nodes = list(await asyncio.gather(*(_one(i) for i in range(m))))
    run.adversarial_runs = m
    run.adversarial_survived = sum(n.test_result == "pass" for n in nodes)
    logger.info(
        f"Adversarial: patch {candidate.node_id} survived "
        f"{run.adversarial_survived}/{m} attacks"
    )
    return nodes


async def run_pipeline(
    run: Run,
    max_rounds: int = 2,
    sandbox: SandboxManager | None = None,
) -> tuple[Run, list[Node]]:
    """
    End-to-end patch search state machine:
    reproduce -> search_round -> evaluate_search -> replan -> repeat.

    Args:
        run: The Run to process.
        max_rounds: Maximum number of search rounds before giving up.
        sandbox: Optional sandbox instance (defaults to SandboxManager()).

    Returns:
        (updated_run, all_nodes_created). On success run.status is "complete"
        and run.winner_node_id is set; otherwise run.status is "failed".
    """
    sandbox = sandbox or SandboxManager()
    all_nodes: list[Node] = []
    run.status = "running"

    root_node = reproduce(run, sandbox)
    all_nodes.append(root_node)
    logger.info(f"Reproduce: root node {root_node.node_id} -> test_result={root_node.test_result}")

    guidance: list[str] | None = None
    for round_num in range(1, max_rounds + 1):
        branches = await search_round(run, root_node, round_num=round_num, guidance=guidance, sandbox=sandbox)
        all_nodes.extend(branches)

        winner: Node | None = None
        for candidate in (b for b in branches if b.test_result == "pass"):
            logger.info(f"Running stability check on candidate {candidate.node_id} (k=5)...")
            stability_nodes = await check_stability(run, candidate, sandbox=sandbox, k=5)
            all_nodes.extend(stability_nodes)

            if candidate.is_stable:
                winner = candidate
                logger.info(f"Candidate {candidate.node_id} verified stable ({candidate.stability_passes}/{candidate.stability_runs})!")
                break
            logger.warning(
                f"Candidate {candidate.node_id} demoted due to flakiness "
                f"({candidate.stability_passes}/{candidate.stability_runs} passes)."
            )

        if winner is not None:
            logger.info(f"Running adversarial verification on winner {winner.node_id} (m=2)...")
            adversarial_nodes = await check_adversarial(run, winner, sandbox=sandbox, m=2)
            all_nodes.extend(adversarial_nodes)
            run.status = "complete"
            run.winner_node_id = winner.node_id
            # Confidence combines stability pass rate and adversarial survival rate.
            stability_rate = winner.stability_passes / winner.stability_runs if winner.stability_runs else 1.0
            adversarial_rate = run.adversarial_survived / run.adversarial_runs if run.adversarial_runs else 1.0
            run.confidence_score = round(0.5 * stability_rate + 0.5 * adversarial_rate, 2)
            run.completed_at = datetime.now(timezone.utc)
            if run.created_at:
                run.total_wall_time_seconds = round((run.completed_at - run.created_at).total_seconds(), 2)
            run.total_cost_usd = round(sum(n.tokens_in + n.tokens_out for n in all_nodes) * 0.000001, 6)
            logger.info(f"Pipeline complete: verified stable winner {winner.node_id} in round {round_num}")
            return run, all_nodes

        if round_num < max_rounds:
            logger.info(f"Round {round_num}: no stable winner found; replanning with Nemotron Ultra")
            guidance = await replan(run, list(branches))

    run.status = "failed"
    run.completed_at = datetime.now(timezone.utc)
    if run.created_at:
        run.total_wall_time_seconds = round((run.completed_at - run.created_at).total_seconds(), 2)
    run.total_cost_usd = round(sum(n.tokens_in + n.tokens_out for n in all_nodes) * 0.000001, 6)
    logger.info(f"Pipeline failed: no passing patch after {max_rounds} rounds")
    return run, all_nodes
