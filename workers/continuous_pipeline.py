"""
Job Intelligence Agent - Continuous Sequential Processor
Version: 5.0.0

Flow:
    SQLite
       â†“
    Queue new jobs
       â†“
    Job 1 â†’ Match â†’ Reject OR Verify â†’ SQLite VERIFIED â†’ Telegram
       â†“
    Job 2 â†’ Match â†’ Reject OR Verify â†’ SQLite VERIFIED â†’ Telegram
       â†“
    ...

Features:
- Strict one-job-at-a-time processing
- Automatically updates SQLite after verification
- Automatically sends Telegram after VERIFIED
- Reads verifier JSON reliably
- Falls back to verifier stdout when JSON is unavailable
- Preserves verification confidence/score
- Handles temporary errors without corrupting job state
- Prevents duplicate queue processing
- Keeps discovering jobs independently
- Processes approximately 30% of queued jobs per cycle
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "jobs.db"

VERIFIER = ROOT / "verification" / "job_verifier.py"
TELEGRAM = ROOT / "notifications" / "telegram" / "send_single_job.py"

VERIFICATION_DIR = ROOT / "data" / "verification_results"


# ============================================================
# SETTINGS
# ============================================================

MAX_BATCH = 500
PROCESS_PERCENT = 30
MIN_PROCESS = 1

CHECK_EVERY = 10

VERIFY_TIMEOUT = 30
VERIFY_EXTRA_TIMEOUT = 15

TELEGRAM_TIMEOUT = 60

PAUSE_BETWEEN_JOBS = 1


# ============================================================
# ENVIRONMENT
# ============================================================

os.chdir(ROOT)

ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT)
ENV["PYTHONIOENCODING"] = "utf-8"

VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOGGING
# ============================================================

def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


# ============================================================
# DATABASE
# ============================================================

def connect_db() -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Database not found: {DB}")

    conn = sqlite3.connect(
        str(DB),
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")

    return conn


def ensure_queue_table() -> None:
    conn = connect_db()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_processing_queue (
                job_id INTEGER PRIMARY KEY,
                queued_at TEXT NOT NULL,
                processing_started_at TEXT,
                processed_at TEXT,
                result TEXT,
                error TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_queue_pending
            ON job_processing_queue(processed_at, job_id)
            """
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# QUEUE
# ============================================================

def queue_new_jobs() -> int:
    """
    Add all currently pending jobs to the processing queue.

    Existing queue records are ignored.
    """

    conn = connect_db()

    try:
        before = conn.total_changes

        conn.execute(
            """
            INSERT OR IGNORE INTO job_processing_queue (
                job_id,
                queued_at
            )
            SELECT
                id,
                ?
            FROM jobs
            WHERE
                COALESCE(status, 'ACTIVE') = 'ACTIVE'
                AND COALESCE(
                    verification_status,
                    'UNVERIFIED'
                ) IN ('UNVERIFIED', 'PENDING')
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
            ),
        )

        conn.commit()

        return conn.total_changes - before

    finally:
        conn.close()


def cleanup_queue() -> None:
    """
    Remove queue records that no longer require processing.
    """

    conn = connect_db()

    try:
        conn.execute(
            """
            DELETE FROM job_processing_queue
            WHERE job_id IN (
                SELECT q.job_id
                FROM job_processing_queue q
                LEFT JOIN jobs j
                    ON j.id = q.job_id
                WHERE
                    j.id IS NULL
                    OR COALESCE(
                        j.verification_status,
                        'UNVERIFIED'
                    ) NOT IN (
                        'UNVERIFIED',
                        'PENDING'
                    )
                    OR COALESCE(
                        j.status,
                        'ACTIVE'
                    ) != 'ACTIVE'
            )
            """
        )

        conn.commit()

    finally:
        conn.close()


def get_queue_size() -> int:
    conn = connect_db()

    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM job_processing_queue q
            JOIN jobs j
                ON j.id = q.job_id
            WHERE
                q.processed_at IS NULL
                AND COALESCE(
                    j.status,
                    'ACTIVE'
                ) = 'ACTIVE'
                AND COALESCE(
                    j.verification_status,
                    'UNVERIFIED'
                ) IN ('UNVERIFIED', 'PENDING')
            """
        ).fetchone()

        return int(row[0] or 0)

    finally:
        conn.close()


def get_next_jobs(limit: int) -> list[sqlite3.Row]:
    conn = connect_db()

    try:
        rows = conn.execute(
            """
            SELECT
                j.*
            FROM job_processing_queue q
            JOIN jobs j
                ON j.id = q.job_id
            WHERE
                q.processed_at IS NULL
                AND COALESCE(
                    j.status,
                    'ACTIVE'
                ) = 'ACTIVE'
                AND COALESCE(
                    j.verification_status,
                    'UNVERIFIED'
                ) IN ('UNVERIFIED', 'PENDING')
            ORDER BY
                j.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return rows

    finally:
        conn.close()


# ============================================================
# QUEUE STATUS
# ============================================================

def mark_processing(job_id: int) -> None:
    conn = connect_db()

    try:
        conn.execute(
            """
            UPDATE job_processing_queue
            SET
                processing_started_at = ?,
                error = NULL
            WHERE job_id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                job_id,
            ),
        )

        conn.commit()

    finally:
        conn.close()


def mark_processed(
    job_id: int,
    result: str,
    error: str | None = None,
) -> None:
    conn = connect_db()

    try:
        conn.execute(
            """
            UPDATE job_processing_queue
            SET
                processed_at = ?,
                result = ?,
                error = ?
            WHERE job_id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                result,
                error,
                job_id,
            ),
        )

        conn.commit()

    finally:
        conn.close()


# ============================================================
# JOB STATUS
# ============================================================

def update_job(
    job_id: int,
    *,
    verification_status: str | None = None,
    status: str | None = None,
    match_score: int | None = None,
    job_confidence: int | None = None,
    hr_name: str | None = None,
    hr_title: str | None = None,
    hr_email: str | None = None,
    hr_confidence: int | None = None,
) -> None:

    fields: list[str] = []
    values: list[Any] = []

    if verification_status is not None:
        fields.append("verification_status = ?")
        values.append(verification_status)

    if status is not None:
        fields.append("status = ?")
        values.append(status)

    if match_score is not None:
        fields.append("match_score = ?")
        values.append(match_score)

    if job_confidence is not None:
        fields.append("job_confidence = ?")
        values.append(job_confidence)

    if hr_name is not None:
        fields.append("hr_name = ?")
        values.append(hr_name)

    if hr_title is not None:
        fields.append("hr_title = ?")
        values.append(hr_title)

    if hr_email is not None:
        fields.append("hr_email = ?")
        values.append(hr_email)

    if hr_confidence is not None:
        fields.append("hr_confidence = ?")
        values.append(hr_confidence)

    fields.append("updated_at = CURRENT_TIMESTAMP")

    values.append(job_id)

    conn = connect_db()

    try:
        conn.execute(
            f"""
            UPDATE jobs
            SET
                {", ".join(fields)}
            WHERE id = ?
            """,
            values,
        )

        conn.commit()

    finally:
        conn.close()


def set_job_status(
    job_id: int,
    verification_status: str,
    status: str | None = None,
) -> None:

    update_job(
        job_id,
        verification_status=verification_status,
        status=status,
    )


# ============================================================
# VALUE HELPERS
# ============================================================

def value(
    job: sqlite3.Row,
    *names: str,
) -> str:

    keys = set(job.keys())

    for name in names:
        if name in keys:
            item = job[name]

            if item is not None:
                return str(item)

    return ""


def safe_int(value_: Any) -> int | None:
    if value_ is None:
        return None

    try:
        return int(float(value_))
    except Exception:
        return None


def job_json(job: sqlite3.Row) -> str:
    data: dict[str, Any] = {}

    for key in job.keys():
        item = job[key]

        if item is None:
            data[key] = ""
        else:
            data[key] = item

    return json.dumps(
        data,
        ensure_ascii=False,
        default=str,
    )


# ============================================================
# MATCHING
# ============================================================

def is_target_job(job: sqlite3.Row) -> tuple[bool, int]:
    """
    Run the existing local matcher.

    Returns:
        (matched, score)
    """

    try:
        sys.path.insert(0, str(ROOT))

        from workers.match_jobs import match_job

        title = value(
            job,
            "title",
            "job_title",
        )

        description = value(
            job,
            "description",
            "job_description",
        )

        location = value(
            job,
            "location",
            "job_location",
        )

        experience = value(
            job,
            "experience",
            "experience_text",
            "experienceText",
        )

        result = match_job(
            title,
            description,
            location,
            experience,
        )

        if isinstance(result, tuple):

            if len(result) >= 2:

                first = result[0]
                second = result[1]

                if isinstance(first, bool):
                    return first, safe_int(second) or 0

                if isinstance(first, (int, float)):
                    score = int(first)
                    return score >= 75, score

                if isinstance(second, (int, float)):
                    score = int(second)
                    return score >= 75, score

            if len(result) >= 1:

                first = result[0]

                if isinstance(first, bool):
                    return first, 0

                if isinstance(first, (int, float)):
                    score = int(first)
                    return score >= 75, score

        if isinstance(result, dict):

            matched = result.get(
                "matched",
                result.get(
                    "is_match",
                    None,
                ),
            )

            score = result.get(
                "match_score",
                result.get(
                    "score",
                    0,
                ),
            )

            score_int = safe_int(score) or 0

            if matched is not None:
                return bool(matched), score_int

            return score_int >= 75, score_int

        if isinstance(result, bool):
            return result, 0

        if isinstance(result, (int, float)):
            score = int(result)
            return score >= 75, score

        return bool(result), 0

    except Exception as exc:

        log(
            f"âŒ Matcher error for "
            f"Job #{value(job, 'id')}: {exc}"
        )

        raise


# ============================================================
# VERIFIER JSON
# ============================================================

def load_verification_json(
    output_file: Path,
) -> dict[str, Any] | None:

    if not output_file.exists():
        return None

    try:

        with output_file.open(
            "r",
            encoding="utf-8",
        ) as handle:

            data = json.load(handle)

        if isinstance(data, dict):
            return data

    except Exception as exc:

        log(
            f"âš  Could not parse verifier JSON: "
            f"{exc}"
        )

    return None


def extract_verification_status(
    data: dict[str, Any] | None,
    stdout: str,
    stderr: str,
) -> tuple[str, int | None, dict[str, Any]]:

    if data:

        raw_status = (
            data.get("verification_status")
            or data.get("verificationStatus")
            or data.get("status")
            or ""
        )

        status = str(
            raw_status
        ).strip().upper()

        confidence = (
            data.get("confidence")
            or data.get("job_confidence")
            or data.get("verification_score")
            or data.get("verificationScore")
        )

        confidence_int = safe_int(confidence)

        if status in {
            "VERIFIED",
            "UNCERTAIN",
            "PENDING",
            "REJECTED",
        }:
            return status, confidence_int, data

    combined = (
        f"{stdout}\n{stderr}"
    ).upper()

    if re.search(
        r"VERIFICATION\s+RESULT.*?\n.*?STATUS\s*:\s*VERIFIED",
        combined,
        re.DOTALL,
    ):
        return "VERIFIED", None, data or {}

    if re.search(
        r"STATUS\s*:\s*VERIFIED",
        combined,
    ):
        return "VERIFIED", None, data or {}

    if "STATUS              : UNCERTAIN" in combined:
        return "UNCERTAIN", None, data or {}

    if "STATUS              : REJECTED" in combined:
        return "REJECTED", None, data or {}

    if "UNCERTAIN" in combined:
        return "UNCERTAIN", None, data or {}

    if "REJECTED" in combined:
        return "REJECTED", None, data or {}

    return "NOT_VERIFIED", None, data or {}


# ============================================================
# VERIFICATION
# ============================================================

def verify_job(
    job: sqlite3.Row,
) -> tuple[
    bool,
    str,
    dict[str, Any],
]:
    """
    Verify exactly ONE job.

    IMPORTANT:
    This function does not merely execute the verifier.
    It reads the verifier result and returns the result
    so SQLite can be updated automatically.
    """

    title = value(
        job,
        "title",
        "job_title",
    )

    company = value(
        job,
        "company",
        "company_name",
    )

    location = value(
        job,
        "location",
        "job_location",
    )

    description = value(
        job,
        "description",
        "job_description",
    )

    source_url = value(
        job,
        "source_url",
        "sourceUrl",
        "url",
    )

    official_url = value(
        job,
        "official_url",
        "officialUrl",
    )

    application_url = value(
        job,
        "application_url",
        "applicationUrl",
        "apply_url",
        "applyUrl",
        "url",
    )

    requisition_id = value(
        job,
        "requisition_id",
        "requisitionId",
    )

    job_id = value(
        job,
        "id",
    )

    fingerprint = value(
        job,
        "fingerprint",
    )

    safe_name = (
        fingerprint
        or f"id_{job_id}"
    )

    safe_name = re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        safe_name,
    )

    output_file = (
        VERIFICATION_DIR
        / f"job_{safe_name}.json"
    )

    # Remove stale verifier output.
    try:
        if output_file.exists():
            output_file.unlink()
    except Exception:
        pass

    command = [
        sys.executable,
        str(VERIFIER),

        "--company",
        company,

        "--title",
        title,

        "--location",
        location,

        "--description",
        description,

        "--source-url",
        source_url,

        "--official-url",
        official_url,

        "--application-url",
        application_url,

        "--requisition-id",
        requisition_id,

        "--json-output",
        str(output_file),

        "--timeout",
        str(VERIFY_TIMEOUT),
    ]

    log(
        f"ðŸ” Verifying Job #{job_id}..."
    )

    try:

        result = subprocess.run(
            command,
            cwd=ROOT,
            env=ENV,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=(
                VERIFY_TIMEOUT
                + VERIFY_EXTRA_TIMEOUT
            ),
        )

    except subprocess.TimeoutExpired:

        return (
            False,
            "VERIFIER_TIMEOUT",
            {},
        )

    except Exception as exc:

        return (
            False,
            f"VERIFIER_ERROR: {exc}",
            {},
        )

    data = load_verification_json(
        output_file
    )

    status, confidence, data = (
        extract_verification_status(
            data,
            result.stdout or "",
            result.stderr or "",
        )
    )

    if confidence is not None:
        data = dict(data)
        data["_confidence"] = confidence

    # Helpful diagnostic information.
    if result.stdout:
        lines = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

        for line in lines:

            if (
                line.startswith("Status")
                or line.startswith("Confidence")
                or line.startswith("Verification score")
            ):
                log(
                    f"   {line}"
                )

    if status == "VERIFIED":

        log(
            f"âœ… Verification result: VERIFIED"
        )

        return (
            True,
            "VERIFIED",
            data,
        )

    if status == "UNCERTAIN":

        return (
            False,
            "UNCERTAIN",
            data,
        )

    if status == "REJECTED":

        return (
            False,
            "REJECTED",
            data,
        )

    if result.returncode != 0:

        return (
            False,
            f"VERIFIER_EXIT_{result.returncode}",
            data,
        )

    return (status == "VERIFIED", status or "NOT_VERIFIED", data)


# ============================================================
# SAVE VERIFICATION RESULT
# ============================================================

def save_verified_result(
    job_id: int,
    data: dict[str, Any],
) -> None:
    """
    Automatically write useful verifier information
    into the jobs table.
    """

    confidence = (
        data.get("confidence")
        or data.get("verification_score")
        or data.get("verificationScore")
        or data.get("_confidence")
    )

    confidence_int = safe_int(
        confidence
    )

    match_score = (
        data.get("match_score")
        or data.get("matchScore")
    )

    match_score_int = safe_int(
        match_score
    )

    hr_name = (
        data.get("hr_name")
        or data.get("hrName")
    )

    hr_title = (
        data.get("hr_title")
        or data.get("hrTitle")
    )

    hr_email = (
        data.get("hr_email")
        or data.get("hrEmail")
    )

    hr_confidence = safe_int(
        data.get("hr_confidence")
        or data.get("hrConfidence")
    )

    update_job(
        job_id,
        verification_status="VERIFIED",
        status="ACTIVE",
        match_score=match_score_int,
        job_confidence=confidence_int,
        hr_name=(
            str(hr_name)
            if hr_name
            else None
        ),
        hr_title=(
            str(hr_title)
            if hr_title
            else None
        ),
        hr_email=(
            str(hr_email)
            if hr_email
            else None
        ),
        hr_confidence=hr_confidence,
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_for_job(
    job_id: int,
) -> bool:
    """
    Send exactly ONE verified job.

    send_single_job.py handles duplicate protection.
    """

    if not TELEGRAM.exists():

        log(
            f"âŒ Telegram worker not found: "
            f"{TELEGRAM}"
        )

        return False

    log(
        f"ðŸ“¨ Sending Job #{job_id} to Telegram..."
    )

    try:

        result = subprocess.run(
            [
                sys.executable,
                str(TELEGRAM),
                "--job-id",
                str(job_id),
            ],
            cwd=ROOT,
            env=ENV,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=TELEGRAM_TIMEOUT,
        )

    except subprocess.TimeoutExpired:

        log(
            f"âŒ Telegram timeout for Job #{job_id}"
        )

        return False

    except Exception as exc:

        log(
            f"âŒ Telegram error for "
            f"Job #{job_id}: {exc}"
        )

        return False

    stdout = (
        result.stdout or ""
    ).strip()

    stderr = (
        result.stderr or ""
    ).strip()

    if stdout:
        print(
            stdout,
            flush=True,
        )

    if stderr:
        print(
            stderr,
            flush=True,
        )

    if result.returncode == 0:

        log(
            f"âœ… Telegram completed for "
            f"Job #{job_id}"
        )

        return True

    log(
        f"âŒ Telegram failed for "
        f"Job #{job_id} "
        f"(exit code {result.returncode})"
    )

    return False


# ============================================================
# PROCESS ONE JOB
# ============================================================

def process_one_job(
    job: sqlite3.Row,
) -> str:

    job_id = int(
        value(job, "id") or 0
    )

    company = value(
        job,
        "company",
        "company_name",
    )

    title = value(
        job,
        "title",
        "job_title",
    )

    log("")
    log("=" * 70)
    log(
        f"PROCESSING JOB #{job_id}"
    )
    log(
        f"{title} | {company}"
    )
    log("=" * 70)

    # --------------------------------------------------------
    # STEP 1 - MATCH
    # --------------------------------------------------------

    log("1/3 Matching...")

    try:

        matched, score = (
            is_target_job(job)
        )

    except Exception as exc:

        log(
            f"âš  Matching error: {exc}"
        )

        return "MATCH_ERROR"

    if score:

        log(
            f"ðŸŽ¯ Match score: {score}/100"
        )

    if not matched:

        log(
            "âŒ NOT A TARGET JOB"
        )

        update_job(
            job_id,
            verification_status="NOT_MATCHED",
        )

        return "NOT_MATCHED"

    log(
        "âœ… TARGET JOB"
    )

    # Save match score before verification.
    if score:

        update_job(
            job_id,
            match_score=score,
        )

    # --------------------------------------------------------
    # STEP 2 - VERIFY
    # --------------------------------------------------------

    log("2/3 Verifying...")

    verified, reason, verification_data = (
        verify_job(job)
    )

    if not verified:

        log(
            f"âŒ Verification result: {reason}"
        )

        if reason in {
            "UNCERTAIN",
            "PENDING",
            "VERIFIER_TIMEOUT",
        } or reason.startswith(
            "VERIFIER_ERROR"
        ) or reason.startswith(
            "VERIFIER_EXIT"
        ):

            # Keep recoverable verification states
            # in the queue instead of permanently
            # losing the job.
            update_job(
                job_id,
                verification_status="PENDING",
                status="ACTIVE",
            )

            return reason

        update_job(
            job_id,
            verification_status=reason,
        )

        return reason

    log(
        "âœ… VERIFIED"
    )

    # --------------------------------------------------------
    # IMPORTANT FIX
    # --------------------------------------------------------
    # The verifier CLI only produces a result.
    # We explicitly write VERIFIED back to SQLite.
    # --------------------------------------------------------

    try:

        save_verified_result(
            job_id,
            verification_data,
        )

        log(
            f"ðŸ’¾ SQLite updated: "
            f"Job #{job_id} = VERIFIED"
        )

    except Exception as exc:

        log(
            f"âŒ Could not update SQLite: {exc}"
        )

        return "DATABASE_UPDATE_ERROR"

    # --------------------------------------------------------
    # STEP 3 - TELEGRAM
    # --------------------------------------------------------

    log("3/3 Sending Telegram...")

    sent = send_telegram_for_job(
        job_id
    )

    if sent:

        log(
            "ðŸ“¨ Telegram alert completed."
        )

        return "VERIFIED_TELEGRAM"

    log(
        "âš  Telegram failed."
    )

    # Keep job VERIFIED.
    # Telegram sender has its own duplicate protection,
    # so the processor can retry the notification later.
    update_job(
        job_id,
        verification_status="VERIFIED",
        status="ACTIVE",
    )

    return "VERIFIED_TELEGRAM_FAILED"


# ============================================================
# RECOVER STUCK JOBS
# ============================================================

def recover_stuck_jobs() -> int:
    """
    Recover queue entries that were marked processing
    but never completed.

    This protects against crashes/restarts.
    """

    conn = connect_db()

    try:

        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM job_processing_queue
            WHERE
                processed_at IS NULL
                AND processing_started_at IS NOT NULL
                AND processing_started_at < datetime(
                    'now',
                    '-30 minutes'
                )
            """
        ).fetchone()

        count = int(
            row[0] or 0
        )

        if count:

            conn.execute(
                """
                UPDATE job_processing_queue
                SET
                    processing_started_at = NULL,
                    error = 'RECOVERED_AFTER_STALE_PROCESS'
                WHERE
                    processed_at IS NULL
                    AND processing_started_at IS NOT NULL
                    AND processing_started_at < datetime(
                        'now',
                        '-30 minutes'
                    )
                """
            )

            conn.commit()

            log(
                f"â™» Recovered {count} stuck queue jobs."
            )

        return count

    finally:
        conn.close()


# ============================================================
# VERIFY DATABASE CONSISTENCY
# ============================================================

def repair_verified_queue_entries() -> int:
    """
    If a job became VERIFIED externally, remove it
    from the pending queue.
    """

    conn = connect_db()

    try:

        cursor = conn.execute(
            """
            UPDATE job_processing_queue
            SET
                processed_at = COALESCE(
                    processed_at,
                    ?
                ),
                result = COALESCE(
                    result,
                    'ALREADY_VERIFIED'
                )
            WHERE
                processed_at IS NULL
                AND job_id IN (
                    SELECT id
                    FROM jobs
                    WHERE verification_status = 'VERIFIED'
                )
            """,
            (
                datetime.now().isoformat(
                    timespec="seconds"
                ),
            ),
        )

        conn.commit()

        return cursor.rowcount

    finally:
        conn.close()


# ============================================================
# MAIN LOOP
# ============================================================

def main() -> None:

    log("=" * 70)
    log(
        "JOB INTELLIGENCE AGENT"
    )
    log(
        "CONTINUOUS SEQUENTIAL PROCESSOR v5.0.0"
    )
    log("=" * 70)

    log(
        f"Project: {ROOT}"
    )

    log(
        f"Database: {DB}"
    )

    log(
        f"Maximum queue batch: {MAX_BATCH}"
    )

    log(
        f"Process percentage: {PROCESS_PERCENT}%"
    )

    log(
        f"Check interval: {CHECK_EVERY}s"
    )

    log(
        "Mode: JOB AFTER JOB"
    )

    log(
        "Verification: AUTOMATIC"
    )

    log(
        "SQLite update: AUTOMATIC"
    )

    log(
        "Telegram: AUTOMATIC"
    )

    log("=" * 70)

    ensure_queue_table()

    while True:

        try:

            # ------------------------------------------------
            # RECOVERY
            # ------------------------------------------------

            recover_stuck_jobs()

            repair_verified_queue_entries()

            # ------------------------------------------------
            # ADD NEW DISCOVERED JOBS
            # ------------------------------------------------

            added = queue_new_jobs()

            if added:

                log(
                    f"ðŸ“¥ Added {added} new jobs to queue."
                )

            cleanup_queue()

            # ------------------------------------------------
            # QUEUE STATUS
            # ------------------------------------------------

            queue_size = get_queue_size()

            if queue_size == 0:

                log(
                    "â³ No pending jobs. "
                    "Waiting for discovery..."
                )

                time.sleep(
                    CHECK_EVERY
                )

                continue

            # ------------------------------------------------
            # SELECT 30%
            # ------------------------------------------------

            selected = min(
                queue_size,
                MAX_BATCH,
            )

            process_count = max(
                MIN_PROCESS,
                int(
                    selected
                    * PROCESS_PERCENT
                    / 100
                ),
            )

            process_count = min(
                process_count,
                selected,
            )

            jobs = get_next_jobs(
                process_count
            )

            if not jobs:

                time.sleep(
                    CHECK_EVERY
                )

                continue

            log("")
            log(
                f"ðŸ“Š Queue: {queue_size} jobs"
            )

            log(
                f"ðŸŽ¯ Selected: {len(jobs)} jobs"
            )

            log(
                "ðŸ”„ Processing strictly ONE BY ONE"
            )

            # ------------------------------------------------
            # ONE JOB AFTER ANOTHER
            # ------------------------------------------------

            for job in jobs:

                job_id = int(
                    value(
                        job,
                        "id",
                    ) or 0
                )

                try:

                    mark_processing(
                        job_id
                    )

                    result = process_one_job(
                        job
                    )

                    mark_processed(
                        job_id,
                        result,
                    )

                    log(
                        f"âœ… Job #{job_id} "
                        f"finished: {result}"
                    )

                except KeyboardInterrupt:

                    raise

                except Exception as exc:

                    error = str(exc)

                    log(
                        f"âŒ Job #{job_id} "
                        f"error: {error}"
                    )

                    mark_processed(
                        job_id,
                        "ERROR",
                        error,
                    )

                # Small pause between jobs.
                time.sleep(
                    PAUSE_BETWEEN_JOBS
                )

        except KeyboardInterrupt:

            log("")
            log(
                "Stopping processor..."
            )

            break

        except Exception as exc:

            log(
                f"âŒ Main loop error: {exc}"
            )

            time.sleep(
                CHECK_EVERY
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
