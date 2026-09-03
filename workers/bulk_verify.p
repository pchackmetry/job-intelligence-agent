from database.job_database import JobDatabase
from matching.job_matcher import match_job
import subprocess
import sys
import json


db = JobDatabase()
rows = db.connection.execute("SELECT * FROM jobs").fetchall()

candidates = []

print("Scanning jobs...")

for row in rows:
    title = str(row["title"] or "")
    location = str(row["location"] or "")

    if "experience_text" in row.keys():
        experience = str(row["experience_text"] or "")
    else:
        experience = ""

    result = match_job(title, "", location, experience)

    if result["category"] in ("STRONG", "GOOD") and result["india_eligible"]:
        candidates.append((dict(row), result))

print(f"Candidates: {len(candidates)}")

verified = 0
uncertain = 0
rejected = 0

for job, match in candidates:

    fingerprint = job.get("fingerprint")
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
        encoding="utf-8"
    ) as f:
        json.dump(job, f, ensure_ascii=False, indent=2, default=str)

    print(
        f"\nVERIFYING: {job.get('company')} | "
        f"{job.get('title')} | {job.get('location')}"
    )

    result = subprocess.run(
        [
            sys.executable,
            "verification/job_verifier.py",
            "--json-file",
            "data/current_verification_job.json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    output = result.stdout

    if "Status              : VERIFIED" in output:
        status = "VERIFIED"
        verified += 1

    elif "Status              : UNCERTAIN" in output:
        status = "UNCERTAIN"
        uncertain += 1

    else:
        status = "FAILED"
        rejected += 1

    # Save verification status to database
    if fingerprint:
        try:
            db.set_verification_status(
                fingerprint,
                status,
                reason=f"Automatic verification: {status}",
                checked_url=application_url,
            )
            print(f"DB UPDATED: {status}")

        except Exception as e:
            print(f"DB UPDATE ERROR: {e}")

    print(output)


print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"Candidates : {len(candidates)}")
print(f"Verified   : {verified}")
print(f"Uncertain  : {uncertain}")
print(f"Rejected   : {rejected}")
print("=" * 60)
