from database.job_database import JobDatabase
import json

db = JobDatabase()

jobs = db.get_pending_verification(1)

if not jobs:
    print("No pending jobs found.")
else:
    job = jobs[0]

    print("=" * 70)
    print("FIRST PENDING JOB")
    print("=" * 70)

    for key in job.keys():
        value = job[key]

        if key == "raw_json":
            print(f"\n{key}:")
            try:
                print(json.dumps(json.loads(value), indent=2))
            except Exception:
                print(value)
        else:
            print(f"{key}: {value}")

db.close()