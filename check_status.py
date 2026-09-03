import sqlite3

c = sqlite3.connect("data/jobs.db")

rows = c.execute("""
SELECT verification_status, COUNT(*)
FROM jobs
GROUP BY verification_status
""").fetchall()

for row in rows:
    print(row)

c.close()