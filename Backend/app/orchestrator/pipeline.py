"""Phase 1 Sub-step 2: SearchNode fan-out with concurrent 4-branch exploration."""
import asyncio
import logging
import uuid
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


async def _execute_branch(
    run: Run,
    parent_node: Node,
    parent_sandbox: SandboxManager,
    branch_index: int,
    job: str,
    temperature: float,
    instruction_template: str,
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


async def search_round(run: Run, parent_node: Node, round_num: int = 1) -> list[Node]:
    """
    Execute a single search round with 4 concurrent branches from parent_node.

    Args:
        run: The Run object containing bug description and test command
        parent_node: The parent Node (typically root node from reproduce step)
        round_num: Round number for logging (default: 1)

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
        )
        for i, (job, temp, instruction) in enumerate(SEARCH_BRANCHES)
    ]

    # Execute all 4 branches concurrently
    nodes = await asyncio.gather(*tasks)

    logger.info(f"=== Search Round {round_num}: completed 4 branches ===")
    return list(nodes)
