import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("NEBIUS_API_KEY")
if not API_KEY or API_KEY == "your_nebius_api_key_here":
    print("❌ Error: Please put your real Nebius API Key in the .env file.")
    exit(1)

MODELS = [
    ("Nano", "https://api.tokenfactory.nebius.com/v1/", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
    ("Super", "https://api.tokenfactory.us-central1.nebius.com/v1/", "nvidia/nemotron-3-super-120b-a12b"),
    ("Ultra", "https://api.tokenfactory.us-central1.nebius.com/v1/", "nvidia/Nemotron-3-Ultra-550b-a55b"),
]

async def test_models():
    print("Testing connection to Nebius Token Factory for all 3 tiers...\n")
    for tier, base_url, model_name in MODELS:
        client = AsyncOpenAI(api_key=API_KEY, base_url=base_url)
        try:
            print(f"[{tier}] Sending test prompt to {model_name}...")
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "Respond with 1 sentence confirming your identity."}],
                max_tokens=300,
            )
            msg = response.choices[0].message
            text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
            print(f"✅ Success [{tier}]: {text}\n")
        except Exception as e:
            print(f"❌ Failed [{tier}]: {e}\n")

if __name__ == "__main__":
    asyncio.run(test_models())

