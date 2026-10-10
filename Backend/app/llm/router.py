"""Routes PatchTree jobs to Nemotron tiers on Nebius Token Factory (stub fallback offline)."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)
TIERS = {
    "nano": {
        "model": os.getenv("NEBIUS_MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
        "base_url": os.getenv("NEBIUS_BASE_URL_NANO", "https://api.tokenfactory.nebius.com/v1/"),
    },
    "super": {
        "model": os.getenv("NEBIUS_MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
        "base_url": os.getenv("NEBIUS_BASE_URL_SUPER", "https://api.tokenfactory.us-central1.nebius.com/v1/"),
    },
    "ultra": {
        "model": os.getenv("NEBIUS_MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
        "base_url": os.getenv("NEBIUS_BASE_URL_ULTRA", "https://api.tokenfactory.us-central1.nebius.com/v1/"),
    },
}

# job -> (tier, default temperature)
ROUTES = {
    "generate_patch_minimal": ("nano", 0.2),
    "generate_patch_alternative": ("super", 0.5),
    "generate_patch_root_cause": ("super", 0.6),
    "generate_patch_test_driven": ("nano", 0.2),
    "replan_after_failure": ("ultra", 0.3),
}


async def call_model(job: str, prompt: str, system_prompt: str | None = None, temperature: float = 0.3) -> dict:
    """Returns {content, model, tokens_in, tokens_out, stub}."""
    if job not in ROUTES:
        raise ValueError(f"Unknown job: {job}")
    tier, route_temp = ROUTES[job]
    cfg = TIERS[tier]
    model = cfg["model"]
    base_url = cfg["base_url"]
    temp = route_temp if job != "replan_after_failure" else temperature

    key = os.getenv("NEBIUS_API_KEY")
    if key:
        try:
            client = AsyncOpenAI(api_key=key, base_url=base_url)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = await client.chat.completions.create(
                model=model, temperature=temp, messages=messages
            )
            msg = resp.choices[0].message
            content = msg.content or getattr(msg, "reasoning", "") or ""
            usage = resp.usage
            return {
                "content": content,
                "model": model,
                "tokens_in": usage.prompt_tokens if usage else 0,
                "tokens_out": usage.completion_tokens if usage else 0,
                "stub": False,
            }
        except Exception as e:
            logger.warning("Nebius call failed for %s (%s); using stub response", model, e)

    return {
        "content": f"[stub:{job}] --- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-return 1\n+return 2\n",
        "model": f"stub/{model}",
        "tokens_in": len(prompt.split()),
        "tokens_out": 20,
        "stub": True,
    }

