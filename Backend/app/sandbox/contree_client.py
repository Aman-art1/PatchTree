"""Sandbox wrapper: real Contree SDK when available, in-memory stub otherwise."""
import logging
import uuid
from dataclasses import dataclass

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
        if not force_stub:
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
                return
            except Exception as e:
                self._fallback(e)
        self._history = [f"spawn {image}"]

    def run_command(self, cmd: str) -> CommandResult:
        if not self.stub:
            try:
                img = self._image.run(shell=cmd, disposable=False).wait()
                self._image = img
                return CommandResult(img.exit_code, self._text(img.stdout) + self._text(img.stderr))
            except Exception as e:
                self._fallback(e)
        return self._stub_run(cmd)

    def checkpoint(self) -> str:
        cid = str(uuid.uuid4())
        if not self.stub:
            try:
                cid = str(self._image.uuid)
                return cid
            except Exception as e:
                self._fallback(e)
        self._checkpoints[cid] = list(self._history)
        return cid

    def fork(self, checkpoint_id: str) -> "SandboxManager":
        child = SandboxManager(force_stub=True) if self.stub else SandboxManager.__new__(SandboxManager)
        if self.stub:
            child._history = list(self._checkpoints[checkpoint_id])
            child._checkpoints = self._checkpoints
        else:
            child.stub, child._client = False, self._client
            child._image, child._history, child._checkpoints = self._client.images.use(checkpoint_id), [], {}
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
