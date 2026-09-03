from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.job_database import JobDatabase
from matching.job_matcher import match_job


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
        "SELECT * FROM jobs ORDER BY rowid DESC"
    ).fetchall()

    matched = []

    print("=" * 70)
    print("JOB INTELLIGENCE AGENT")
    print("FAST MATCHING WORKER")
    print("=" * 70)
    print(f"Jobs available: {len(rows)}")
    print()

    for job in rows:
        title = value(job, "title")
        location = value(job, "location")
        experience = value(
            job,
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
            matched.append((job, result))

    for job, result in matched:
        print("-" * 70)
        print(f"Title:       {value(job, 'title')}")
        print(f"Company:     {value(job, 'company')}")
        print(f"Location:    {value(job, 'location')}")
        print(f"Match:       {result['match_score']}/100")
        print(f"Category:    {result['category']}")

    print()
    print("=" * 70)
    print(f"Matched jobs: {len(matched)}")
    print("=" * 70)


if __name__ == "__main__":
    main()