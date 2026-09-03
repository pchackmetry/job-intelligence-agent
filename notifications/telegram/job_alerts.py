"""
Telegram Job Alerts
Job Intelligence Agent
Version: 1.0.0

Sends verified, high-match jobs from SQLite to Telegram.
"""

from database.job_database import JobDatabase
from matching.job_matcher import match_job

from dotenv import load_dotenv

import os
import sys
import sqlite3
import requests
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

TELEGRAM_TIMEOUT = 20
MIN_MATCH_SCORE = 75


# ============================================================
# LOAD ENV
# ============================================================

if not ENV_FILE.exists():
    print(f"ERROR: .env not found: {ENV_FILE}")
    sys.exit(1)

load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN is missing.")
    sys.exit(1)

if not CHAT_ID:
    print("ERROR: TELEGRAM_CHAT_ID is missing.")
    sys.exit(1)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_URL = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
)


def send_telegram(message: str) -> bool:
    """Send one Telegram message safely."""

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(
            TELEGRAM_URL,
            json=payload,
            timeout=TELEGRAM_TIMEOUT,
        )

    except requests.exceptions.Timeout:
        print("ERROR: Telegram request timed out.")
        return False

    except requests.exceptions.RequestException as error:
        print(f"ERROR: Telegram request failed: {error}")
        return False

    if response.status_code != 200:
        print(
            f"ERROR: Telegram HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
        return False

    try:
        data = response.json()
    except ValueError:
        print("ERROR: Telegram returned invalid JSON.")
        return False

    if data.get("ok") is not True:
        print(
            "ERROR: Telegram rejected message:",
            data.get("description", "Unknown error"),
        )
        return False

    return True


# ============================================================
# DATABASE
# ============================================================

try:
    db = JobDatabase()
except Exception as error:
    print(f"ERROR: Database connection failed: {error}")
    sys.exit(1)


# ============================================================
# CREATE ALERT TABLE
# ============================================================

try:
    db.connection.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_alerts (
            fingerprint TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        )
        """
    )

    db.connection.commit()

except Exception as error:
    print(f"ERROR: Could not create telegram_alerts table: {error}")
    sys.exit(1)


# ============================================================
# HELPERS
# ============================================================

def value(row, *names, default=""):
    """Safely retrieve a database field."""

    for name in names:
        try:
            if name in row.keys():
                result = row[name]

                if result is not None:
                    return result

        except Exception:
            pass

    return default


def clean(value_to_clean):
    """Convert value to clean string."""

    if value_to_clean is None:
        return ""

    return str(value_to_clean).strip()


def already_sent(fingerprint: str) -> bool:
    """Check whether this job was already sent."""

    if not fingerprint:
        return False

    row = db.connection.execute(
        """
        SELECT 1
        FROM telegram_alerts
        WHERE fingerprint = ?
        LIMIT 1
        """,
        (fingerprint,),
    ).fetchone()

    return row is not None


def mark_sent(fingerprint: str):
    """Record successful Telegram alert."""

    if not fingerprint:
        return

    db.connection.execute(
        """
        INSERT OR IGNORE INTO telegram_alerts
        (fingerprint, sent_at)
        VALUES (?, ?)
        """,
        (
            fingerprint,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    db.connection.commit()


# ============================================================
# FORMAT JOB
# ============================================================

def format_job(job, match):
    """Create Telegram alert message."""

    company = clean(value(job, "company"))
    title = clean(value(job, "title"))
    location = clean(value(job, "location"))

    work_mode = clean(
        value(
            job,
            "work_mode",
            "workMode",
        )
    )

    experience = clean(
        value(
            job,
            "experience_text",
            "experienceText",
            "experience",
        )
    )

    salary = clean(value(job, "salary"))

    posted_at = clean(
        value(
            job,
            "posted_at",
            "postedAt",
            "first_seen",
            "firstSeen",
        )
    )

    deadline = clean(
        value(
            job,
            "deadline",
        )
    )

    application_url = clean(
        value(
            job,
            "application_url",
            "applicationUrl",
            "url",
        )
    )

    score = match.get(
        "match_score",
        0,
    )

    category = match.get(
        "category",
        "GOOD",
    )

    if not location:
        location = "Not specified"

    if not work_mode:
        work_mode = "Not specified"

    if not experience:
        experience = "Fresher / Entry Level"

    if not salary:
        salary = "Not specified"

    if not posted_at:
        posted_at = "Not specified"

    if not deadline:
        deadline = "Not specified"

    message = (
        "🔥 VERIFIED NEW JOB\n"
        "\n"
        f"💼 {title}\n"
        f"🏢 {company}\n"
        "\n"
        f"📍 {location}\n"
        f"🏠 {work_mode}\n"
        f"💼 Experience: {experience}\n"
        f"📅 Posted: {posted_at}\n"
        f"⏳ Deadline: {deadline}\n"
        "\n"
        f"⭐ Match: {score}/100\n"
        f"🎯 Category: {category}\n"
        "\n"
        "🛡 Verification\n"
        "✅ Company/job page verified\n"
        "✅ Application URL verified\n"
        "✅ Entry-level signal detected\n"
        "\n"
        "🔗 APPLY\n"
        f"{application_url or 'Application link unavailable'}"
    )

    return message


# ============================================================
# LOAD VERIFIED JOBS
# ============================================================

print("=" * 70)
print("TELEGRAM JOB ALERT WORKER v1.0.0")
print("=" * 70)

try:
    rows = db.connection.execute(
        """
        SELECT *
        FROM jobs
        WHERE UPPER(COALESCE(verification_status, '')) = 'VERIFIED'
        """
    ).fetchall()

except sqlite3.OperationalError as error:
    print(f"ERROR: Database query failed: {error}")
    sys.exit(1)

except Exception as error:
    print(f"ERROR: Could not load jobs: {error}")
    sys.exit(1)


print(f"VERIFIED JOBS FOUND: {len(rows)}")


# ============================================================
# PROCESS JOBS
# ============================================================

sent = 0
skipped = 0
errors = 0


for row in rows:

    try:

        job = dict(row)

        fingerprint = clean(
            value(job, "fingerprint")
        )

        title = clean(
            value(job, "title")
        )

        location = clean(
            value(job, "location")
        )

        experience = clean(
            value(
                job,
                "experience_text",
                "experienceText",
                "experience",
            )
        )

        if not title:
            skipped += 1
            continue

        # ----------------------------------------------------
        # MATCH
        # ----------------------------------------------------

        match = match_job(
            title,
            "",
            location,
            experience,
        )

        score = match.get(
            "match_score",
            0,
        )

        if (
            match.get("category")
            not in ("STRONG", "GOOD")
        ):
            skipped += 1
            continue

        if score < MIN_MATCH_SCORE:
            skipped += 1
            continue

        if not match.get("india_eligible"):
            skipped += 1
            continue

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        if already_sent(fingerprint):
            print(
                f"SKIP ALREADY SENT: "
                f"{title} | {location}"
            )
            skipped += 1
            continue

        # ----------------------------------------------------
        # SEND
        # ----------------------------------------------------

        message = format_job(
            job,
            match,
        )

        print()
        print(
            f"SENDING: {title} | "
            f"{company if (company := clean(value(job, 'company'))) else 'Unknown'} | "
            f"{location}"
        )
        print(
            f"MATCH: {score}/100"
        )

        success = send_telegram(message)

        if success:

            mark_sent(fingerprint)

            sent += 1

            print(
                "TELEGRAM: SENT"
            )

        else:

            errors += 1

            print(
                "TELEGRAM: FAILED"
            )

    except Exception as error:

        errors += 1

        print(
            f"ERROR processing job: {error}"
        )

        continue


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("TELEGRAM ALERT SUMMARY")
print("=" * 70)

print(f"Verified jobs : {len(rows)}")
print(f"Sent          : {sent}")
print(f"Skipped       : {skipped}")
print(f"Errors        : {errors}")

print("=" * 70)

if errors == 0:
    print("STATUS: SUCCESS")
else:
    print("STATUS: COMPLETED WITH ERRORS")

print("=" * 70)