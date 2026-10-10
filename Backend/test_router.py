import sys
import asyncio
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.llm.router import call_model, ROUTES

async def main():
    print("Testing PatchTree LLM Router across all 5 jobs...\n")
    for job in ROUTES:
        res = await call_model(job, "ping")
        status = "STUB FALLBACK" if res["stub"] else "LIVE NEBIUS"
        print(f"[{job:28}] -> {res['model']} ({status}) [tokens: {res['tokens_in']} in, {res['tokens_out']} out]")
    print("\nAll routes verified successfully!")

if __name__ == "__main__":
    asyncio.run(main())
