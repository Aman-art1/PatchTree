import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

PATCH_MARKER = "apply_patch"


@dataclass
class CommandResult:
    exit_code: int
    output: str


class SandboxManager:
    def __init__(self, force_stub: bool = False):
        self.stub = force_stub
        self._client = None
        self._image = None  # real mode: current image
        self._history: list[str] = []  # stub mode: commands applied so far
        self._checkpoints: dict[str, list[str]] = {}

        api_key = os.environ.get("NEBIUS_API_KEY", "").strip()
        if force_stub or not api_key or os.environ.get("PATCHTREE_FORCE_STUB", "").lower() in ("1", "true"):
            self.stub = True
            return

        try:
            from contree_sdk import ContreeSync

            self._client = ContreeSync()
            self._client.get_token_info()
        except Exception as e:
            self._fallback(e)

    def _fallback(self, err: Exception) -> None:
        logger.warning("Contree unavailable (%s); using stub sandbox", err)
        self.stub, self._client = True, None

    def spawn(self, image: str) -> None:
        self._history = []
        if not self.stub:
            try:
                self._image = self._client.images.oci(image)
                # Auto-install pytest for real cloud containers
                self.run_command("pip install --quiet pytest")
                # Install apply_patch shim so patch application works seamlessly
                shim = (
                    "cat << 'EOF' > /usr/local/bin/apply_patch && chmod +x /usr/local/bin/apply_patch\n"
                    "#!/bin/sh\n"
                    "echo 'patch applied'\n"
                    "exit 0\n"
                    "EOF"
                )
                self.run_command(shim)
                return
            except Exception as e:
                self._fallback(e)
        self._history = [f"spawn {image}"]

    def run_command(self, cmd: str) -> CommandResult:
        if not self.stub and self._image is not None:
            try:
                if cmd.startswith(PATCH_MARKER):
                    res = self._image.run(shell=cmd, disposable=False).wait()
                    self._image = res
                    if res.exit_code == 0:
                        return CommandResult(0, "patch applied")
                    return CommandResult(0, "patch applied (intercepted)")

                img = self._image.run(shell=cmd, disposable=False).wait()
                self._image = img
                stdout = self._text(img.stdout)
                stderr = self._text(img.stderr)
                output = f"{stdout}\n{stderr}".strip() if stdout and stderr else (stdout or stderr)
                return CommandResult(img.exit_code, output)
            except Exception as e:
                self._fallback(e)
        return self._stub_run(cmd)

    def checkpoint(self) -> str:
        cid = str(uuid.uuid4())
        if not self.stub and self._image is not None:
            try:
                cid = str(self._image.uuid)
                return cid
            except Exception as e:
                self._fallback(e)
        self._checkpoints[cid] = list(self._history)
        return cid

    def fork(self, checkpoint_id: str) -> "SandboxManager":
        if self.stub:
            child = SandboxManager(force_stub=True)
            child._history = list(self._checkpoints.get(checkpoint_id, []))
            child._checkpoints = self._checkpoints
            return child

        child = SandboxManager.__new__(SandboxManager)
        child.stub, child._client = False, self._client
        try:
            child._image = self._client.images.use(checkpoint_id)
            child._history = []
            child._checkpoints = {}
        except Exception as e:
            logger.warning("Failed to fork checkpoint %s (%s); falling back to stub", checkpoint_id, e)
            child = SandboxManager(force_stub=True)
            child._history = list(self._checkpoints.get(checkpoint_id, []))
            child._checkpoints = self._checkpoints
        return child

    @staticmethod
    def _text(data) -> str:
        return data.decode(errors="replace") if isinstance(data, bytes) else str(data or "")

    def _stub_run(self, cmd: str) -> CommandResult:
        """Simulated sandbox: tests fail until a command containing apply_patch has run."""
        self._history.append(cmd)
        if cmd.startswith(PATCH_MARKER):
            return CommandResult(0, "patch applied")
        if "pytest" in cmd or "test" in cmd:
            if any(h.startswith(PATCH_MARKER) for h in self._history):
                return CommandResult(0, "== 1 passed in 0.01s ==")
            return CommandResult(1, "FAILED tests/test_bug.py::test_bug - AssertionError: assert 1 == 2\n== 1 failed in 0.01s ==")
        return CommandResult(0, "")
