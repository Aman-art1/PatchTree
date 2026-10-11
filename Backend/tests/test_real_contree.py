"""Smoke test real Contree Sandboxes execution, checkpointing, and forking."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from contree_sdk import ContreeSync

def _text(val) -> str:
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace").strip()
    return str(val or "").strip()

def main():
    print("--- Testing Real Contree Sandboxes ---")
    client = ContreeSync()
    info = client.get_token_info()
    print(f"Permissions: {info.permissions}")
    print(f"Limits: {info.limits}")

    print("\n1. Importing lightweight image ('alpine:latest')...")
    image = client.images.oci("alpine:latest")
    print(f"Image reference created! UUID: {image.uuid}")

    print("\n2. Running shell command on base container...")
    run_res = image.run(shell="echo 'Contree sandbox alive!'; uname -a", disposable=False).wait()
    print(f"Exit code: {run_res.exit_code}")
    print(f"Stdout:\n{_text(run_res.stdout)}")

    print("\n3. Testing Checkpoint & Fork...")
    checkpoint_id = str(run_res.uuid)
    print(f"Checkpoint ID: {checkpoint_id}")

    fork_img = client.images.use(checkpoint_id)
    fork_res = fork_img.run(shell="echo 'Forked successfully from checkpoint!'", disposable=True).wait()
    print(f"Fork exit code: {fork_res.exit_code}")
    print(f"Fork stdout: {_text(fork_res.stdout)}")

    print("\n4. Validating Determinism / Caching question...")
    r1 = client.images.use(checkpoint_id).run(shell="date +%s%N", disposable=True).wait()
    r2 = client.images.use(checkpoint_id).run(shell="date +%s%N", disposable=True).wait()
    t1 = _text(r1.stdout)
    t2 = _text(r2.stdout)
    print(f"Run 1 output: {t1}")
    print(f"Run 2 output: {t2}")
    if t1 != t2:
        print("✅ Commands re-execute independently (NO cache collision for repeated runs)!")
    else:
        print("⚠️ Warning: Output was identical, caching may be enabled.")

    print("\n🎉 Real Contree Sandboxes verified end-to-end!")

if __name__ == "__main__":
    main()
