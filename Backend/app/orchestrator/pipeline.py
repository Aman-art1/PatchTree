"""SearchNode fan-out, evaluation, replan, and pipeline orchestration."""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from ..llm.router import call_model
from ..models.schemas import Node, Run
from ..sandbox.contree_client import SandboxManager

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

    # Extract patch from response (assume it's in the content)
    patch_diff = model_response["content"]
    hypothesis = f"{job}: {patch_diff[:100]}..."  # First 100 chars as hypothesis

    # Apply the patch in the forked sandbox
    apply_result = fork.run_command(f"apply_patch {node_id}.diff")
    logger.debug(f"Branch {branch_index + 1}: patch apply exit_code={apply_result.exit_code}")

    # Run the test
    test_result_obj = fork.run_command(parent_node.test_command or run.target_test)
    test_result: Literal["pass", "fail", "error"] = "pass" if test_result_obj.exit_code == 0 else "fail"

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
        test_output=test_result_obj.output,
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
) -> list[Node]:
    """
    Execute a single search round with 4 concurrent branches from parent_node.

    Args:
        run: The Run object containing bug description and test command
        parent_node: The parent Node (typically root node from reproduce step)
        round_num: Round number for logging (default: 1)
        guidance: Optional revised strategies from replan(); guidance[i] is
            appended to branch i's prompt when present.

    Returns:
        List of 4 Node objects, one per search branch
    """
    logger.info(f"=== Search Round {round_num}: starting 4-branch fan-out from node {parent_node.node_id} ===")

    # Create a parent sandbox from the parent checkpoint
    # We'll reuse this to fork for each branch
    parent_sandbox = SandboxManager(force_stub=True)  # TODO: Remove force_stub when Contree is available
    parent_sandbox._checkpoints[parent_node.checkpoint_id] = []  # Ensure checkpoint exists

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
        sandbox: Optional sandbox for the reproduce step (stub by default).

    Returns:
        (updated_run, all_nodes_created). On success run.status is "complete"
        and run.winner_node_id is set; otherwise run.status is "failed".
    """
    sandbox = sandbox or SandboxManager(force_stub=True)  # TODO: Remove force_stub when Contree is available
    all_nodes: list[Node] = []
    run.status = "running"

    root_node = reproduce(run, sandbox)
    all_nodes.append(root_node)
    logger.info(f"Reproduce: root node {root_node.node_id} -> test_result={root_node.test_result}")

    guidance: list[str] | None = None
    for round_num in range(1, max_rounds + 1):
        branches = await search_round(run, root_node, round_num=round_num, guidance=guidance)
        all_nodes.extend(branches)

        winner = evaluate_search(branches)
        if winner is not None:
            run.status = "complete"
            run.winner_node_id = winner.node_id
            run.completed_at = datetime.now(timezone.utc)
            logger.info(f"Pipeline complete: winner {winner.node_id} in round {round_num}")
            return run, all_nodes

        if round_num < max_rounds:
            logger.info(f"Round {round_num}: no winner; replanning")
            guidance = await replan(run, list(branches))

    run.status = "failed"
    run.completed_at = datetime.now(timezone.utc)
    logger.info(f"Pipeline failed: no passing patch after {max_rounds} rounds")
    return run, all_nodes
