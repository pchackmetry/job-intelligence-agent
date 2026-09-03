"""
Telegram Connection Test
Job Intelligence Agent
Version: 2.0.0
"""

from pathlib import Path
import os
import sys

import requests
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

TIMEOUT = 20


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

if not ENV_FILE.exists():
    print("ERROR: .env file was not found.")
    print(f"Expected: {ENV_FILE}")
    sys.exit(1)

load_dotenv(ENV_FILE)


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# VALIDATE CONFIGURATION
# ============================================================

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN is missing.")
    print("Check your .env file.")
    sys.exit(1)

if TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    print("ERROR: Replace the placeholder Telegram bot token.")
    sys.exit(1)

if not CHAT_ID:
    print("ERROR: TELEGRAM_CHAT_ID is missing.")
    print("Check your .env file.")
    sys.exit(1)

if CHAT_ID == "PASTE_YOUR_CHAT_ID_HERE":
    print("ERROR: Replace the placeholder Telegram chat ID.")
    sys.exit(1)


# ============================================================
# TELEGRAM REQUEST
# ============================================================

api_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

payload = {
    "chat_id": CHAT_ID,
    "text": (
        "✅ Job Intelligence Agent\n\n"
        "Telegram connection test successful.\n"
        "The notification system is ready."
    ),
    "disable_web_page_preview": True,
}


print("=" * 60)
print("TELEGRAM CONNECTION TEST")
print("=" * 60)
print(f"Environment : {ENV_FILE}")
print(f"Chat ID     : {CHAT_ID}")
print("Token       : configured")
print("Sending test message...")
print()


# ============================================================
# SEND MESSAGE
# ============================================================

try:

    response = requests.post(
        api_url,
        json=payload,
        timeout=TIMEOUT,
    )

except requests.exceptions.Timeout:

    print("ERROR: Telegram request timed out.")
    print("Check your internet connection.")
    sys.exit(1)

except requests.exceptions.ConnectionError:

    print("ERROR: Could not connect to Telegram.")
    print("Check your internet connection.")
    sys.exit(1)

except requests.exceptions.RequestException as error:

    print(f"ERROR: Telegram request failed: {error}")
    sys.exit(1)


# ============================================================
# HTTP RESPONSE
# ============================================================

if response.status_code != 200:

    print(
        f"ERROR: Telegram returned HTTP "
        f"{response.status_code}."
    )

    try:
        print(response.json())
    except ValueError:
        print(response.text[:500])

    sys.exit(1)


# ============================================================
# TELEGRAM JSON RESPONSE
# ============================================================

try:

    data = response.json()

except ValueError:

    print("ERROR: Telegram returned invalid JSON.")
    print(response.text[:500])
    sys.exit(1)


if data.get("ok") is not True:

    print("ERROR: Telegram rejected the request.")

    description = data.get(
        "description",
        "Unknown Telegram error.",
    )

    print(f"Reason: {description}")
    sys.exit(1)


# ============================================================
# SUCCESS
# ============================================================

result = data.get("result", {})

message_id = result.get("message_id")

print("=" * 60)
print("SUCCESS")
print("=" * 60)
print("Telegram connection: OK")
print("Test message: SENT")

if message_id:
    print(f"Message ID: {message_id}")

print()
print("Your Telegram notification channel is working.")
print("=" * 60)