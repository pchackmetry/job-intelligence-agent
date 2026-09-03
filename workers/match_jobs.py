from __future__ import annotations

import os
import sys
import sqlite3

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.job_database import JobDatabase
from matching.job_matcher import match_job


MATCH_CATEGORIES = {"STRONG", "GOOD"}


def value(row, *names):
    for name in names:
        if name in row.keys():
            v = row[name]
            if v is not None:
                return str(v)
    return ""


def main() -> None:

    db = JobDatabase()

    rows = db.connection.execute(
        """
        SELECT *
        FROM jobs
        ORDER BY rowid DESC
        """
    ).fetchall()

    print("=" * 90)
    print("JOB INTELLIGENCE AGENT")
    print("TECHNICAL FRESHER DATABASE CLASSIFICATION WORKER")
    print("=" * 90)
    print(f"Jobs available: {len(rows)}")
    print()

    matched_count = 0
    not_matched_count = 0
    skipped_verified = 0
    skipped_alerted = 0
    skipped_no_title = 0

    matched_jobs = []

    for index, job in enumerate(rows, start=1):

        job_id = job["id"]

        title = value(job, "title")
        company = value(job, "company")
        location = value(job, "location")

        experience = value(
            job,
            "experience_text",
            "experienceText",
            "experience"
        )

        description = value(job, "description")
        current_status = value(job, "status").upper()

        # Never downgrade jobs that have already been processed.
        if current_status == "VERIFIED":
            skipped_verified += 1
            continue

        if current_status == "ALERTED":
            skipped_alerted += 1
            continue

        if not title:
            skipped_no_title += 1

            db.connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                ("NOT_MATCHED", job_id),
            )

            not_matched_count += 1
            continue

        result = match_job(
            title=title,
            description=description,
            location=location,
            experience_text=experience,
        )

        category = str(
            result.get("category", "NONE")
        ).upper()

        score = int(
            result.get("match_score", 0) or 0
        )

        india_eligible = bool(
            result.get("india_eligible", False)
        )

        is_match = (
            category in MATCH_CATEGORIES
            and india_eligible
            and score >= 75
        )

        if is_match:

            matched_count += 1

            matched_jobs.append(
                (
                    job_id,
                    title,
                    company,
                    location,
                    score,
                    category,
                )
            )

            # Keep useful jobs active and ready for verification.
            db.connection.execute(
                """
                UPDATE jobs
                SET status = 'ACTIVE',
                    verification_status =
                        CASE
                            WHEN verification_status = 'VERIFIED'
                            THEN verification_status
                            ELSE 'UNVERIFIED'
                        END,
                    match_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (score, job_id),
            )

        else:

            not_matched_count += 1

            # Do not physically delete.
            db.connection.execute(
                """
                UPDATE jobs
                SET status = 'NOT_MATCHED',
                    match_score = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (score, job_id),
            )

        # Commit periodically so a long scan does not hold
        # one huge transaction.
        if index % 1000 == 0:
            db.connection.commit()

            print(
                f"Processed: {index:,}/{len(rows):,} | "
                f"Matched: {matched_count:,} | "
                f"Not matched: {not_matched_count:,}"
            )

    db.connection.commit()

    print()
    print("=" * 90)
    print("CLASSIFICATION COMPLETE")
    print("=" * 90)

    print(f"Jobs scanned       : {len(rows):,}")
    print(f"Technical matches  : {matched_count:,}")
    print(f"Not matched        : {not_matched_count:,}")
    print(f"Already VERIFIED   : {skipped_verified:,}")
    print(f"Already ALERTED    : {skipped_alerted:,}")
    print(f"No title           : {skipped_no_title:,}")

    print()
    print("-" * 90)
    print("TOP MATCHES")
    print("-" * 90)

    matched_jobs.sort(
        key=lambda x: x[4],
        reverse=True
    )

    for (
        job_id,
        title,
        company,
        location,
        score,
        category,
    ) in matched_jobs[:50]:

        print(
            f"{score:3}/100 | "
            f"{category:8} | "
            f"ID {job_id:<7} | "
            f"{title[:45]:45} | "
            f"{company[:25]:25} | "
            f"{location[:30]}"
        )

    print("-" * 90)
    print()
    print("Database status:")
    print("  MATCH      → ACTIVE + UNVERIFIED")
    print("  NO MATCH   → NOT_MATCHED")
    print("  VERIFIED   → preserved")
    print("  ALERTED    → preserved")
    print()
    print("No jobs were physically deleted.")
    print("=" * 90)


if __name__ == "__main__":
    main()