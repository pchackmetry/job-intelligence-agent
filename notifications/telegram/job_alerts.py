# ============================================================
# LOAD TELEGRAM CONFIGURATION
# ============================================================

# Local development:
#   Uses .env when it exists.
#
# GitHub Actions / cloud:
#   Uses environment variables injected from GitHub Secrets.
#
# Priority:
#   1. Existing environment variables
#   2. Local .env file
#
# This keeps the same code usable locally and in the cloud.

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if ENV_FILE.exists() and load_dotenv is not None:
    load_dotenv(
        ENV_FILE,
        override=False,
    )


BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()

CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "",
).strip()


if not BOT_TOKEN:
    print(
        "ERROR: TELEGRAM_BOT_TOKEN is missing."
    )
    sys.exit(1)


if not CHAT_ID:
    print(
        "ERROR: TELEGRAM_CHAT_ID is missing."
    )
    sys.exit(1)
