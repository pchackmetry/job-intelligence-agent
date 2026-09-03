from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.job_database import JobDatabase
from matching.job_matcher import match_job


MAX_RESULTS = 100


def get_value(row, *names):
    for name in names:
        if name in row.keys():
            value = row[name]
            if value is not None:
                return str(value)
    return ""


def main():
    db = JobDatabase()

    rows = db.connection.execute(
        """
        SELECT *
        FROM jobs
        ORDER BY rowid DESC
        """
    ).fetchall()

    print("=" * 70)
    print("FAST JOB MATCH SCAN")
    print("=" * 70)
    print(f"Database jobs: {len(rows)}")
    print("Using title + location + experience only")
    print()

    matches = []

    for row in rows:
        title = get_value(row, "title")
        location = get_value(row, "location")
        experience = get_value(
            row,
            "experience_text",
            "experienceText",
            "experience",
        )

        if not title:
            continue

        result = match_job(
            title=title,
            description="",
            location=location,
            experience_text=experience,
        )

        if (
            result.get("category") in {"STRONG", "GOOD"}
            and result.get("india_eligible")
        ):
            matches.append((row, result))

            if len(matches) >= MAX_RESULTS:
                break

    print(f"Alert-ready matches: {len(matches)}")
    print()

    for row, result in matches:
        company = get_value(row, "company")
        title = get_value(row, "title")
        location = get_value(row, "location")

        print(
            f"{result['match_score']:>3} | "
            f"{company} | "
            f"{title} | "
            f"{location}"
        )

    print()
    print("=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()