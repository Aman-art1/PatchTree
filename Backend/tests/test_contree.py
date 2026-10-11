import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

api_key = os.getenv("NEBIUS_API_KEY")
project_id = os.getenv("NEBIUS_PROJECT_ID")

print("--- Contree Sandbox Smoke Test ---")
print(f"Nebius API Key present: {bool(api_key)}")
print(f"Nebius Project ID: {project_id}")

if not project_id:
    print("\n[NOTE] NEBIUS_PROJECT_ID is not set in your .env file yet.")
    print("Contree SDK needs 'Project: <project_id>' header to authenticate.")
    print("Checking token / connection without project ID first...")

try:
    from contree_sdk import ContreeSync
    client = ContreeSync()
    print("Contree client initialized.")
    token_info = client.get_token_info()
    print(f"Success! Token verified: {token_info}")
except Exception as e:
    print(f"\n[ERROR] Communicating with Contree Sandboxes:")
    print(e)
