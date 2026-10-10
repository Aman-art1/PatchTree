import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.schemas import Run, RunCreate
from app.orchestrator.pipeline import reproduce
from app.sandbox.contree_client import SandboxManager


def test_reproduce():
    req = RunCreate(repo_url="https://github.com/example/repo", bug_description="off by one", target_test="pytest tests/test_bug.py")
    run = Run(run_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), **req.model_dump())
    sandbox = SandboxManager(force_stub=True)  # drop force_stub once Contree beta access is granted
    root = reproduce(run, sandbox)
    assert root.test_result == "fail" and "AssertionError" in root.test_output

    # fork from the root checkpoint, apply a patch, test passes; root checkpoint stays failing
    fork = sandbox.fork(root.checkpoint_id)
    fork.run_command("apply_patch fix.diff")
    assert fork.run_command(run.target_test).exit_code == 0
    assert sandbox.fork(root.checkpoint_id).run_command(run.target_test).exit_code == 1
    print("root node:", root.model_dump_json(indent=2))
    print("OK")


if __name__ == "__main__":
    test_reproduce()
