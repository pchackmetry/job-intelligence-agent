"""
Job Intelligence Agent
Single Verified Job → Telegram Sender
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

DB = ROOT / "data" / "jobs.db"

ENV_FILE = ROOT / ".env"


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# VALIDATION
# ============================================================

def validate_config() -> None:

    if not BOT_TOKEN:
        raise RuntimeError(
            f"TELEGRAM_BOT_TOKEN not found in {ENV_FILE}"
        )

    if not CHAT_ID:
        raise RuntimeError(
            f"TELEGRAM_CHAT_ID not found in {ENV_FILE}"
        )

    if not DB.exists():
        raise FileNotFoundError(
            f"Database not found: {DB}"
        )


# ============================================================
# DATABASE
# ============================================================

def get_connection() -> sqlite3.Connection:

    conn = sqlite3.connect(
        str(DB),
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return conn


def ensure_alert_table() -> None:

    conn = get_connection()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_alerts (
                fingerprint TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
            """
        )

        conn.commit()

    finally:
        conn.close()


def get_job_by_id(
    job_id: int,
) -> sqlite3.Row | None:

    conn = get_connection()

    try:

        return conn.execute(
            """
            SELECT *
            FROM jobs
            WHERE id = ?
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()

    finally:
        conn.close()


def get_job_by_fingerprint(
    fingerprint: str,
) -> sqlite3.Row | None:

    conn = get_connection()

    try:

        return conn.execute(
            """
            SELECT *
            FROM jobs
            WHERE fingerprint = ?
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

    finally:
        conn.close()


# ============================================================
# HELPERS
# ============================================================

def get_value(
    job: sqlite3.Row,
    *names: str,
) -> str:

    keys = set(job.keys())

    for name in names:

        if name in keys:

            value = job[name]

            if value is not None:

                return str(value)

    return ""


def clean(value: str) -> str:

    return (
        value
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def telegram_escape(value: str) -> str:

    # Telegram HTML mode only requires escaping these.
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ============================================================
# DUPLICATE PROTECTION
# ============================================================

def already_sent(
    fingerprint: str,
) -> bool:

    if not fingerprint:
        return False

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT 1
            FROM telegram_alerts
            WHERE fingerprint = ?
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()

        return row is not None

    finally:
        conn.close()


def mark_sent(
    fingerprint: str,
) -> None:

    if not fingerprint:
        return

    from datetime import datetime

    conn = get_connection()

    try:

        conn.execute(
            """
            INSERT OR IGNORE INTO telegram_alerts (
                fingerprint,
                sent_at
            )
            VALUES (?, ?)
            """,
            (
                fingerprint,
                datetime.now().isoformat(
                    timespec="seconds"
                ),
            ),
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# FORMAT MESSAGE
# ============================================================

def format_job_message(
    job: sqlite3.Row,
) -> str:

    title = clean(
        get_value(
            job,
            "title",
            "job_title",
        )
    )

    company = clean(
        get_value(
            job,
            "company",
            "company_name",
        )
    )

    location = clean(
        get_value(
            job,
            "location",
            "job_location",
        )
    )

    work_mode = clean(
        get_value(
            job,
            "work_mode",
            "workMode",
            "remote_type",
        )
    )

    experience = clean(
        get_value(
            job,
            "experience",
            "experience_text",
            "experienceText",
        )
    )

    posted = clean(
        get_value(
            job,
            "posted_at",
            "postedAt",
        )
    )

    deadline = clean(
        get_value(
            job,
            "deadline",
        )
    )

    salary = clean(
        get_value(
            job,
            "salary",
        )
    )

    match_score = clean(
        get_value(
            job,
            "match_score",
            "matchScore",
        )
    )

    job_confidence = clean(
        get_value(
            job,
            "job_confidence",
            "jobConfidence",
        )
    )

    application_url = clean(
        get_value(
            job,
            "application_url",
            "applicationUrl",
            "apply_url",
            "applyUrl",
            "url",
        )
    )

    source = clean(
        get_value(
            job,
            "source",
        )
    )

    if not location:
        location = "Not specified"

    if not work_mode:
        work_mode = "Not specified"

    if not experience:
        experience = "Not specified"

    if not posted:
        posted = "Not specified"

    if not deadline:
        deadline = "Not specified"

    if not salary:
        salary = "Not specified"

    if not match_score:
        match_score = "N/A"

    if not job_confidence:
        job_confidence = "N/A"

    if not application_url:
        application_url = ""

    message = []

    message.append(
        "🔥 <b>VERIFIED NEW JOB</b>"
    )

    message.append("")

    message.append(
        f"<b>{telegram_escape(title)}</b>"
    )

    message.append(
        telegram_escape(company)
    )

    message.append("")

    message.append(
        f"📍 {telegram_escape(location)}"
    )

    message.append(
        f"🏠 {telegram_escape(work_mode)}"
    )

    message.append(
        f"💼 Experience: "
        f"{telegram_escape(experience)}"
    )

    message.append(
        f"📅 Posted: "
        f"{telegram_escape(posted)}"
    )

    message.append(
        f"⏳ Deadline: "
        f"{telegram_escape(deadline)}"
    )

    if salary:
        message.append(
            f"💰 Salary: "
            f"{telegram_escape(salary)}"
        )

    message.append("")

    message.append(
        f"⭐ Match: "
        f"{telegram_escape(match_score)}/100"
    )

    message.append(
        "🛡 <b>Verification</b>"
    )

    message.append(
        "Company/ATS verified"
    )

    message.append(
        "Application link verified"
    )

    message.append(
        "Posted recently"
    )

    message.append(
        f"⭐ Job confidence: "
        f"{telegram_escape(job_confidence)}"
    )

    if source:
        message.append(
            f"🔎 Source: "
            f"{telegram_escape(source)}"
        )

    message.append("")

    if application_url:

        safe_url = telegram_escape(
            application_url
        )

        message.append(
            "🔗 <b>APPLY</b>"
        )

        message.append(
            f'<a href="{safe_url}">'
            "DIRECT APPLICATION"
            "</a>"
        )

    else:

        message.append(
            "🔗 <b>APPLY</b>"
        )

        message.append(
            "Application link not available"
        )

    return "\n".join(message)


# ============================================================
# TELEGRAM API
# ============================================================

def send_telegram(
    message: str,
) -> None:

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "Telegram API error "
            f"{response.status_code}: "
            f"{response.text}"
        )

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram rejected message: {data}"
        )


# ============================================================
# SEND ONE JOB
# ============================================================

def send_one_job(
    job: sqlite3.Row,
) -> bool:

    fingerprint = clean(
        get_value(
            job,
            "fingerprint",
        )
    )

    if not fingerprint:

        raise RuntimeError(
            "Job has no fingerprint."
        )

    job_id = get_value(
        job,
        "id",
    )

    title = clean(
        get_value(
            job,
            "title",
            "job_title",
        )
    )

    company = clean(
        get_value(
            job,
            "company",
            "company_name",
        )
    )

    if already_sent(
        fingerprint
    ):

        print(
            f"⏭ Job #{job_id} already sent: "
            f"{title} | {company}",
            flush=True,
        )

        return False

    message = format_job_message(
        job
    )

    send_telegram(
        message
    )

    mark_sent(
        fingerprint
    )

    print(
        f"📨 Telegram sent for "
        f"Job #{job_id}: "
        f"{title} | {company}",
        flush=True,
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Send exactly one verified job "
            "to Telegram."
        )
    )

    group = parser.add_mutually_exclusive_group(
        required=True
    )

    group.add_argument(
        "--job-id",
        type=int,
        help="SQLite jobs.id",
    )

    group.add_argument(
        "--fingerprint",
        type=str,
        help="Job fingerprint",
    )

    args = parser.parse_args()

    try:

        validate_config()

        ensure_alert_table()

        if args.job_id is not None:

            job = get_job_by_id(
                args.job_id
            )

        else:

            job = get_job_by_fingerprint(
                args.fingerprint
            )

        if job is None:

            print(
                "❌ Job not found.",
                flush=True,
            )

            return 1

        verification_status = (
            get_value(
                job,
                "verification_status",
            )
            .strip()
            .upper()
        )

        if verification_status != "VERIFIED":

            print(
                "❌ Job is not VERIFIED. "
                f"Current status: "
                f"{verification_status or 'UNKNOWN'}",
                flush=True,
            )

            return 1

        send_one_job(
            job
        )

        return 0

    except Exception as exc:

        print(
            f"❌ {exc}",
            flush=True,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )