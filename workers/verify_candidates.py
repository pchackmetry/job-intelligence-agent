from database.job_database import JobDatabase
import subprocess
import sys
import json


db = JobDatabase()

targets = [
    "desktop support intern",
    "it service desk intern",
    "junior endpoint security analyst",
]

rows = db.connection.execute("SELECT * FROM jobs").fetchall()

rows = [
    dict(r)
    for r in rows
    if any(t in str(r["title"]).lower() for t in targets)
]

print("FOUND:", len(rows))

for job in rows:
    print("\n" + "=" * 70)
    print(job.get("company"), "|", job.get("title"))

    application_url = (
        job.get("application_url")
        or job.get("applicationUrl")
        or ""
    )

    official_url = (
        job.get("official_url")
        or job.get("officialUrl")
        or application_url
    )

    job["official_url"] = official_url
    job["application_url"] = application_url

    with open(
        "data/current_verification_job.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            job,
            f,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    result = subprocess.run(
        [
            sys.executable,
            "verification/job_verifier.py",
            "--json-file",
            "data/current_verification_job.json",
        ],
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)

    if result.stderr:
        print("ERROR:", result.stderr)