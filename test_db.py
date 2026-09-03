from database.job_database import JobDatabase

db = JobDatabase()

rows = db.get_active_jobs(10)

print()
print("=" * 70)
print("SAVED JOBS")
print("=" * 70)

for i, r in enumerate(rows, 1):
    print(
        f"{i}. "
        f"{r['company']} | "
        f"{r['title']} | "
        f"{r['location']} | "
        f"{r['source']}"
    )

print("=" * 70)
print(f"Total displayed: {len(rows)}")

db.close()