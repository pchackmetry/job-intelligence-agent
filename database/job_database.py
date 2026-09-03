from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "jobs.db"


# ============================================================
# CONSTANTS
# ============================================================

ACTIVE = "ACTIVE"
UNCERTAIN = "UNCERTAIN"
CLOSED = "CLOSED"
REMOVED = "REMOVED"

UNVERIFIED = "UNVERIFIED"
PENDING = "PENDING"
VERIFIED = "VERIFIED"
FAILED = "FAILED"


# ============================================================
# DATABASE
# ============================================================

class JobDatabase:
    """
    SQLite storage layer for the Job Intelligence Agent.

    Responsibilities:
        - Store normalized jobs
        - Deduplicate jobs
        - Track first/last seen
        - Track verification
        - Track status
        - Store scoring information
        - Preserve raw source data
    """

    def __init__(self, db_path: Path = DB_PATH):

        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            self.db_path,
            timeout=30,
        )

        self.connection.row_factory = sqlite3.Row

        # Performance + reliability
        self.connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        self.connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        self.connection.execute(
            "PRAGMA busy_timeout=30000"
        )

        self.create_tables()

    # ========================================================
    # CONNECTION
    # ========================================================

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    # ========================================================
    # TABLE CREATION
    # ========================================================

    def create_tables(self) -> None:

        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- =================================================
                -- IDENTIFIERS
                -- =================================================

                global_id TEXT,

                fingerprint TEXT NOT NULL UNIQUE,

                source TEXT,

                source_url TEXT,

                application_url TEXT,

                requisition_id TEXT,

                ats_id TEXT,

                -- =================================================
                -- COMPANY
                -- =================================================

                company TEXT,

                employer_type TEXT,

                agency_name TEXT,

                -- =================================================
                -- JOB
                -- =================================================

                title TEXT,

                description TEXT,

                department TEXT,

                team TEXT,

                employment_type TEXT,

                commitment TEXT,

                -- =================================================
                -- LOCATION
                -- =================================================

                location TEXT,

                country TEXT,

                region TEXT,

                country_iso TEXT,

                latitude REAL,

                longitude REAL,

                is_remote INTEGER,

                work_mode TEXT,

                -- =================================================
                -- EXPERIENCE
                -- =================================================

                experience TEXT,

                experience_min INTEGER,

                experience_max INTEGER,

                is_fresher_friendly INTEGER DEFAULT 0,

                -- =================================================
                -- SALARY
                -- =================================================

                salary_currency TEXT,

                salary_period TEXT,

                salary_summary TEXT,

                salary_min REAL,

                salary_max REAL,

                -- =================================================
                -- DATES
                -- =================================================

                posted_at TEXT,

                deadline TEXT,

                fetched_at TEXT,

                first_seen TEXT NOT NULL,

                last_seen TEXT NOT NULL,

                -- =================================================
                -- LANGUAGE
                -- =================================================

                language TEXT,

                -- =================================================
                -- MATCHING
                -- =================================================

                country_match INTEGER DEFAULT 0,

                role_match INTEGER DEFAULT 0,

                experience_match INTEGER DEFAULT 0,

                remote_match INTEGER DEFAULT 0,

                match_score INTEGER DEFAULT 0,

                -- =================================================
                -- CONFIDENCE
                -- =================================================

                job_confidence INTEGER DEFAULT 0,

                verification_status TEXT DEFAULT 'UNVERIFIED',

                -- =================================================
                -- STATUS
                -- =================================================

                status TEXT DEFAULT 'ACTIVE',

                check_count INTEGER DEFAULT 1,

                -- =================================================
                -- RECRUITER
                -- =================================================

                hr_name TEXT,

                hr_title TEXT,

                hr_email TEXT,

                hr_confidence INTEGER DEFAULT 0,

                -- =================================================
                -- NOTIFICATION
                -- =================================================

                telegram_sent INTEGER DEFAULT 0,

                telegram_sent_at TEXT,

                -- =================================================
                -- RAW DATA
                -- =================================================

                raw_json TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );


            -- ====================================================
            -- INDEXES
            -- ====================================================

            CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint
            ON jobs(fingerprint);


            CREATE INDEX IF NOT EXISTS idx_jobs_global_id
            ON jobs(global_id);


            CREATE INDEX IF NOT EXISTS idx_jobs_company
            ON jobs(company);


            CREATE INDEX IF NOT EXISTS idx_jobs_title
            ON jobs(title);


            CREATE INDEX IF NOT EXISTS idx_jobs_status
            ON jobs(status);


            CREATE INDEX IF NOT EXISTS idx_jobs_verification
            ON jobs(verification_status);


            CREATE INDEX IF NOT EXISTS idx_jobs_posted_at
            ON jobs(posted_at);


            CREATE INDEX IF NOT EXISTS idx_jobs_match_score
            ON jobs(match_score);


            CREATE INDEX IF NOT EXISTS idx_jobs_fresher
            ON jobs(is_fresher_friendly);


            CREATE INDEX IF NOT EXISTS idx_jobs_source
            ON jobs(source);


            CREATE INDEX IF NOT EXISTS idx_jobs_company_title
            ON jobs(company, title);


            -- ====================================================
            -- SCAN HISTORY
            -- ====================================================

            CREATE TABLE IF NOT EXISTS scan_runs (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                source TEXT,

                started_at TEXT NOT NULL,

                finished_at TEXT,

                jobs_found INTEGER DEFAULT 0,

                new_jobs INTEGER DEFAULT 0,

                updated_jobs INTEGER DEFAULT 0,

                errors INTEGER DEFAULT 0,

                status TEXT DEFAULT 'RUNNING'
            );


            -- ====================================================
            -- JOB STATUS HISTORY
            -- ====================================================

            CREATE TABLE IF NOT EXISTS job_status_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                old_status TEXT,

                new_status TEXT,

                reason TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE
            );


            -- ====================================================
            -- VERIFICATION HISTORY
            -- ====================================================

            CREATE TABLE IF NOT EXISTS verification_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                old_status TEXT,

                new_status TEXT,

                reason TEXT,

                checked_url TEXT,

                checked_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE
            );


            -- ====================================================
            -- NOTIFICATION HISTORY
            -- ====================================================

            CREATE TABLE IF NOT EXISTS notification_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                job_id INTEGER NOT NULL,

                channel TEXT,

                notification_type TEXT,

                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,

                success INTEGER DEFAULT 0,

                error TEXT,

                FOREIGN KEY(job_id)
                    REFERENCES jobs(id)
                    ON DELETE CASCADE
            );


            CREATE INDEX IF NOT EXISTS idx_status_history_job
            ON job_status_history(job_id);


            CREATE INDEX IF NOT EXISTS idx_verification_history_job
            ON verification_history(job_id);


            CREATE INDEX IF NOT EXISTS idx_notification_history_job
            ON notification_history(job_id);
            """
        )

        self.connection.commit()

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @staticmethod
    def _bool(value: Any) -> int | None:

        if value is None:
            return None

        if isinstance(value, bool):
            return int(value)

        if isinstance(value, int):
            return 1 if value else 0

        if isinstance(value, str):

            value = value.strip().lower()

            if value in {
                "true",
                "yes",
                "1",
                "remote",
            }:
                return 1

            if value in {
                "false",
                "no",
                "0",
            }:
                return 0

        return None

    @staticmethod
    def _json(value: Any) -> str | None:

        if value is None:
            return None

        if isinstance(value, str):
            return value

        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
        except Exception:
            return str(value)

    @staticmethod
    def _sqlite_value(value: Any) -> Any:
        """Convert common Python objects to SQLite-safe primitive values."""
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (str, int, float, bytes)):
            return value
        return str(value)

    # ========================================================
    # JOB UPSERT
    # ========================================================

    def upsert_job(
        self,
        job: dict[str, Any],
    ) -> str:

        fingerprint = self._sqlite_value(job.get("fingerprint"))

        if not fingerprint:
            raise ValueError(
                "Job must contain a fingerprint"
            )

        existing = self.connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

        now = (
            self._sqlite_value(job.get("fetched_at"))
            or job.get("last_seen")
            or job.get("discovered_at")
        )

        if not now:
            now = self._current_timestamp()
        else:
            now = self._sqlite_value(now)

        if existing:

            self.connection.execute(
                """
                UPDATE jobs
                SET

                    global_id = ?,

                    source = ?,
                    source_url = ?,
                    application_url = ?,

                    requisition_id = ?,
                    ats_id = ?,

                    company = ?,
                    employer_type = ?,
                    agency_name = ?,

                    title = ?,
                    description = ?,

                    department = ?,
                    team = ?,
                    employment_type = ?,
                    commitment = ?,

                    location = ?,
                    country = ?,
                    region = ?,
                    country_iso = ?,

                    latitude = ?,
                    longitude = ?,

                    is_remote = ?,
                    work_mode = ?,

                    experience = ?,
                    experience_min = ?,
                    experience_max = ?,

                    is_fresher_friendly = ?,

                    salary_currency = ?,
                    salary_period = ?,
                    salary_summary = ?,
                    salary_min = ?,
                    salary_max = ?,

                    posted_at = ?,
                    deadline = ?,
                    fetched_at = ?,

                    language = ?,

                    country_match = ?,
                    role_match = ?,
                    experience_match = ?,
                    remote_match = ?,

                    match_score = ?,
                    job_confidence = ?,

                    last_seen = ?,

                    check_count = check_count + 1,

                    status = 'ACTIVE',

                    raw_json = ?,

                    updated_at = CURRENT_TIMESTAMP

                WHERE fingerprint = ?
                """,
                (
                    self._sqlite_value(job.get("global_id")),

                    self._sqlite_value(job.get("source")),
                    self._sqlite_value(job.get("source_url")),
                    self._sqlite_value(job.get("application_url")),

                    self._sqlite_value(job.get("requisition_id")),
                    self._sqlite_value(job.get("ats_id")),

                    self._sqlite_value(job.get("company")),
                    self._sqlite_value(job.get("employer_type")),
                    self._sqlite_value(job.get("agency_name")),

                    self._sqlite_value(job.get("title")),
                    self._sqlite_value(job.get("description")),

                    self._sqlite_value(job.get("department")),
                    self._sqlite_value(job.get("team")),
                    self._sqlite_value(job.get("employment_type")),
                    self._sqlite_value(job.get("commitment")),

                    self._sqlite_value(job.get("location")),
                    self._sqlite_value(job.get("country")),
                    self._sqlite_value(job.get("region")),
                    self._sqlite_value(job.get("country_iso")),

                    job.get("latitude"),
                    job.get("longitude"),

                    self._bool(job.get("is_remote")),
                    self._sqlite_value(job.get("work_mode")),

                    self._sqlite_value(job.get("experience")),
                    job.get("experience_min"),
                    job.get("experience_max"),

                    self._bool(
                        job.get("is_fresher_friendly")
                    ) or 0,

                    self._sqlite_value(job.get("salary_currency")),
                    self._sqlite_value(job.get("salary_period")),
                    self._sqlite_value(job.get("salary_summary")),
                    job.get("salary_min"),
                    job.get("salary_max"),

                    self._sqlite_value(job.get("posted_at")),
                    self._sqlite_value(job.get("deadline")),
                    self._sqlite_value(job.get("fetched_at")),

                    self._sqlite_value(job.get("language")),

                    self._bool(
                        job.get("country_match")
                    ) or 0,

                    self._bool(
                        job.get("role_match")
                    ) or 0,

                    self._bool(
                        job.get("experience_match")
                    ) or 0,

                    self._bool(
                        job.get("remote_match")
                    ) or 0,

                    int(job.get("match_score") or 0),

                    int(job.get("job_confidence") or 0),

                    now,

                    self._json(
                        job.get("raw_json")
                        or job.get("raw")
                    ),

                    fingerprint,
                ),
            )

            return "UPDATED"

        # ====================================================
        # INSERT NEW JOB
        # ====================================================

        insert_columns = [
            "global_id", "fingerprint",
            "source", "source_url", "application_url",
            "requisition_id", "ats_id",
            "company", "employer_type", "agency_name",
            "title", "description",
            "department", "team", "employment_type", "commitment",
            "location", "country", "region", "country_iso",
            "latitude", "longitude",
            "is_remote", "work_mode",
            "experience", "experience_min", "experience_max",
            "is_fresher_friendly",
            "salary_currency", "salary_period", "salary_summary",
            "salary_min", "salary_max",
            "posted_at", "deadline", "fetched_at",
            "first_seen", "last_seen",
            "language",
            "country_match", "role_match", "experience_match", "remote_match",
            "match_score", "job_confidence",
            "verification_status", "status",
            "check_count",
            "hr_name", "hr_title", "hr_email", "hr_confidence",
            "telegram_sent",
            "raw_json",
        ]

        insert_values = [
            self._sqlite_value(job.get("global_id")),
            fingerprint,

            self._sqlite_value(job.get("source")),
            self._sqlite_value(job.get("source_url")),
            self._sqlite_value(job.get("application_url")),

            self._sqlite_value(job.get("requisition_id")),
            self._sqlite_value(job.get("ats_id")),

            self._sqlite_value(job.get("company")),
            self._sqlite_value(job.get("employer_type")),
            self._sqlite_value(job.get("agency_name")),

            self._sqlite_value(job.get("title")),
            self._sqlite_value(job.get("description")),

            self._sqlite_value(job.get("department")),
            self._sqlite_value(job.get("team")),
            self._sqlite_value(job.get("employment_type")),
            self._sqlite_value(job.get("commitment")),

            self._sqlite_value(job.get("location")),
            self._sqlite_value(job.get("country")),
            self._sqlite_value(job.get("region")),
            self._sqlite_value(job.get("country_iso")),

            job.get("latitude"),
            job.get("longitude"),

            self._bool(job.get("is_remote")),
            self._sqlite_value(job.get("work_mode")),

            self._sqlite_value(job.get("experience")),
            job.get("experience_min"),
            job.get("experience_max"),

            self._bool(job.get("is_fresher_friendly")) or 0,

            self._sqlite_value(job.get("salary_currency")),
            self._sqlite_value(job.get("salary_period")),
            self._sqlite_value(job.get("salary_summary")),
            job.get("salary_min"),
            job.get("salary_max"),

            self._sqlite_value(job.get("posted_at")),
            self._sqlite_value(job.get("deadline")),
            self._sqlite_value(job.get("fetched_at")),

            now,
            now,

            self._sqlite_value(job.get("language")),

            self._bool(job.get("country_match")) or 0,
            self._bool(job.get("role_match")) or 0,
            self._bool(job.get("experience_match")) or 0,
            self._bool(job.get("remote_match")) or 0,

            int(job.get("match_score") or 0),
            int(job.get("job_confidence") or 0),

            job.get("verification_status") or UNVERIFIED,
            job.get("status") or ACTIVE,

            int(job.get("check_count") or 1),

            self._sqlite_value(job.get("hr_name")),
            self._sqlite_value(job.get("hr_title")),
            self._sqlite_value(job.get("hr_email")),
            int(job.get("hr_confidence") or 0),

            self._bool(job.get("telegram_sent")) or 0,

            self._json(job.get("raw_json") or job.get("raw")),
        ]

        placeholders = ", ".join("?" for _ in insert_columns)
        columns_sql = ", ".join(insert_columns)

        self.connection.execute(
            f"""
            INSERT INTO jobs ({columns_sql})
            VALUES ({placeholders})
            """,
            insert_values,
        )

        return "NEW"

    # ========================================================
    # BULK INSERT
    # ========================================================

    def upsert_jobs(
        self,
        jobs: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:

        stats = {
            "new": 0,
            "updated": 0,
            "errors": 0,
        }

        try:

            self.connection.execute(
                "BEGIN"
            )

            for job in jobs:

                try:

                    result = self.upsert_job(
                        job
                    )

                    if result == "NEW":
                        stats["new"] += 1

                    elif result == "UPDATED":
                        stats["updated"] += 1

                except Exception as exc:

                    stats["errors"] += 1
                    stats.setdefault("error_details", []).append(
                        f"{type(exc).__name__}: {exc}"
                    )
                    print(
                        f"❌ Database job error: {type(exc).__name__}: {exc}"
                    )

            self.connection.commit()

        except Exception:

            self.connection.rollback()

            raise

        return stats

    # ========================================================
    # FIND JOB
    # ========================================================

    def get_job(
        self,
        fingerprint: str,
    ) -> sqlite3.Row | None:

        return self.connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()

    # ========================================================
    # ACTIVE JOBS
    # ========================================================

    def get_active_jobs(
        self,
        limit: int = 100,
    ) -> list[sqlite3.Row]:

        return self.connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE status = 'ACTIVE'

            ORDER BY

                CASE
                    WHEN match_score IS NULL
                    THEN 0
                    ELSE match_score
                END DESC,

                posted_at DESC

            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    # ========================================================
    # NEW / UNVERIFIED JOBS
    # ========================================================

    def get_pending_verification(
        self,
        limit: int = 100,
    ) -> list[sqlite3.Row]:

        return self.connection.execute(
            """
            SELECT *
            FROM jobs
            WHERE verification_status IN (
                'UNVERIFIED',
                'PENDING'
            )
            AND status = 'ACTIVE'

            ORDER BY
                posted_at DESC

            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    # ========================================================
    # HIGH MATCH JOBS
    # ========================================================

    def get_high_match_jobs(
        self,
        minimum_score: int = 75,
        limit: int = 100,
    ) -> list[sqlite3.Row]:

        return self.connection.execute(
            """
            SELECT *
            FROM jobs

            WHERE status = 'ACTIVE'

            AND match_score >= ?

            ORDER BY
                match_score DESC,
                posted_at DESC

            LIMIT ?
            """,
            (
                minimum_score,
                limit,
            ),
        ).fetchall()

    # ========================================================
    # VERIFICATION
    # ========================================================

    def set_verification_status(
        self,
        fingerprint: str,
        new_status: str,
        reason: str | None = None,
        checked_url: str | None = None,
    ) -> bool:

        job = self.get_job(
            fingerprint
        )

        if not job:
            return False

        old_status = job[
            "verification_status"
        ]

        self.connection.execute(
            """
            UPDATE jobs

            SET
                verification_status = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE fingerprint = ?
            """,
            (
                new_status,
                fingerprint,
            ),
        )

        self.connection.execute(
            """
            INSERT INTO verification_history (

                job_id,
                old_status,
                new_status,
                reason,
                checked_url

            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job["id"],
                old_status,
                new_status,
                reason,
                checked_url,
            ),
        )

        self.connection.commit()

        return True

    # ========================================================
    # STATUS
    # ========================================================

    def set_status(
        self,
        fingerprint: str,
        new_status: str,
        reason: str | None = None,
    ) -> bool:

        job = self.get_job(
            fingerprint
        )

        if not job:
            return False

        old_status = job["status"]

        if old_status == new_status:
            return True

        self.connection.execute(
            """
            UPDATE jobs

            SET
                status = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE fingerprint = ?
            """,
            (
                new_status,
                fingerprint,
            ),
        )

        self.connection.execute(
            """
            INSERT INTO job_status_history (

                job_id,
                old_status,
                new_status,
                reason

            )

            VALUES (?, ?, ?, ?)
            """,
            (
                job["id"],
                old_status,
                new_status,
                reason,
            ),
        )

        self.connection.commit()

        return True

    # ========================================================
    # SCAN RUN
    # ========================================================

    def start_scan(
        self,
        source: str,
    ) -> int:

        cursor = self.connection.execute(
            """
            INSERT INTO scan_runs (
                source,
                started_at
            )

            VALUES (?, ?)
            """,
            (
                source,
                self._current_timestamp(),
            ),
        )

        self.connection.commit()

        return int(cursor.lastrowid)

    def finish_scan(
        self,
        scan_id: int,
        jobs_found: int,
        new_jobs: int,
        updated_jobs: int,
        errors: int = 0,
        status: str = "COMPLETED",
    ) -> None:

        self.connection.execute(
            """
            UPDATE scan_runs

            SET

                finished_at = ?,
                jobs_found = ?,
                new_jobs = ?,
                updated_jobs = ?,
                errors = ?,
                status = ?

            WHERE id = ?
            """,
            (
                self._current_timestamp(),
                jobs_found,
                new_jobs,
                updated_jobs,
                errors,
                status,
                scan_id,
            ),
        )

        self.connection.commit()

    # ========================================================
    # MARK MISSING JOBS
    # ========================================================

    def mark_missing_jobs(
        self,
        source: str,
        seen_fingerprints: set[str],
    ) -> int:

        rows = self.connection.execute(
            """
            SELECT
                id,
                fingerprint

            FROM jobs

            WHERE source = ?
            AND status = 'ACTIVE'
            """,
            (source,),
        ).fetchall()

        changed = 0

        for row in rows:

            fingerprint = row[
                "fingerprint"
            ]

            if fingerprint not in seen_fingerprints:

                self.set_status(
                    fingerprint,
                    UNCERTAIN,
                    "Not present in latest source scan",
                )

                changed += 1

        return changed

    # ========================================================
    # TELEGRAM
    # ========================================================

    def mark_telegram_sent(
        self,
        fingerprint: str,
        success: bool,
        error: str | None = None,
    ) -> bool:

        job = self.get_job(
            fingerprint
        )

        if not job:
            return False

        self.connection.execute(
            """
            UPDATE jobs

            SET

                telegram_sent = ?,

                telegram_sent_at =
                    CASE
                        WHEN ? = 1
                        THEN ?
                        ELSE telegram_sent_at
                    END,

                updated_at = CURRENT_TIMESTAMP

            WHERE fingerprint = ?
            """,
            (
                int(success),
                int(success),
                self._current_timestamp(),
                fingerprint,
            ),
        )

        self.connection.execute(
            """
            INSERT INTO notification_history (

                job_id,
                channel,
                notification_type,
                success,
                error

            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job["id"],
                "telegram",
                "job_alert",
                int(success),
                error,
            ),
        )

        self.connection.commit()

        return True

    # ========================================================
    # STATISTICS
    # ========================================================

    def count_jobs(self) -> int:

        result = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM jobs
            """
        ).fetchone()

        return int(
            result["count"]
        )

    def statistics(self) -> dict[str, Any]:

        total = self.count_jobs()

        active = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE status = 'ACTIVE'
            """
        ).fetchone()[0]

        verified = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE verification_status = 'VERIFIED'
            """
        ).fetchone()[0]

        fresher = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE is_fresher_friendly = 1
            """
        ).fetchone()[0]

        high_match = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE match_score >= 75
            """
        ).fetchone()[0]

        telegram_sent = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM jobs
            WHERE telegram_sent = 1
            """
        ).fetchone()[0]

        return {
            "total_jobs": total,
            "active_jobs": active,
            "verified_jobs": verified,
            "fresher_friendly": fresher,
            "high_match_jobs": high_match,
            "telegram_sent": telegram_sent,
        }

    # ========================================================
    # DATABASE HEALTH
    # ========================================================

    def health_check(self) -> bool:

        try:

            result = self.connection.execute(
                "SELECT 1"
            ).fetchone()

            return result[0] == 1

        except sqlite3.Error:

            return False

    # ========================================================
    # TIMESTAMP
    # ========================================================

    @staticmethod
    def _current_timestamp() -> str:

        from datetime import datetime, timezone

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )



def smoke_test_insert() -> None:
    """Insert one temporary job to verify the complete SQLite write path."""
    test_job = {
        "global_id": "db-smoke-test",
        "fingerprint": "db-smoke-test-fingerprint",
        "source": "test",
        "source_url": "https://example.com/jobs/1",
        "application_url": "https://example.com/apply/1",
        "company": "Database Smoke Test",
        "title": "Test Job",
        "location": "Hyderabad, India",
        "country": "India",
        "country_iso": "IN",
        "is_remote": False,
        "work_mode": "On-site",
        "experience": "0-1 years",
        "experience_min": 0,
        "experience_max": 1,
        "is_fresher_friendly": True,
        "country_match": True,
        "role_match": True,
        "experience_match": True,
        "remote_match": False,
        "match_score": 90,
        "job_confidence": 95,
        "raw_json": {"test": True},
    }

    with JobDatabase() as db:
        result = db.upsert_job(test_job)
        print(f"Smoke insert: {result}")
        row = db.get_job(test_job["fingerprint"])
        if not row:
            raise RuntimeError("Smoke test failed: inserted job was not found.")
        print(f"Smoke lookup: OK (id={row['id']})")

        db.connection.execute(
            "DELETE FROM jobs WHERE fingerprint = ?",
            (test_job["fingerprint"],),
        )
        db.connection.commit()
        print("Smoke cleanup: OK")


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("JOB INTELLIGENCE AGENT")
    print("SQLite Database Test")
    print("=" * 60)

    with JobDatabase() as db:

        print()

        print(
            "Database:",
            db.db_path
        )

        print(
            "Health:",
            "✅ OK"
            if db.health_check()
            else "❌ FAILED"
        )

        stats = db.statistics()

        print()
        print("Statistics:")

        for key, value in stats.items():

            print(
                f"  {key}: {value}"
            )

        print()

        print("Running SQLite write-path smoke test...")

        smoke_job = {
            "global_id": "db-smoke-test",
            "fingerprint": "db-smoke-test-fingerprint",
            "source": "test",
            "source_url": "https://example.com/jobs/1",
            "application_url": "https://example.com/apply/1",
            "company": "Database Smoke Test",
            "title": "Test Job",
            "location": "Hyderabad, India",
            "country": "India",
            "country_iso": "IN",
            "is_remote": False,
            "work_mode": "On-site",
            "experience": "0-1 years",
            "experience_min": 0,
            "experience_max": 1,
            "is_fresher_friendly": True,
            "country_match": True,
            "role_match": True,
            "experience_match": True,
            "remote_match": False,
            "match_score": 90,
            "job_confidence": 95,
            "raw_json": {"test": True},
        }

        result = db.upsert_job(smoke_job)
        row = db.get_job("db-smoke-test-fingerprint")

        if result != "NEW" or row is None:
            raise RuntimeError("SQLite write-path smoke test failed.")

        print("  Insert:  ✅ OK")
        print("  Lookup:  ✅ OK")

        db.connection.execute(
            "DELETE FROM jobs WHERE fingerprint = ?",
            ("db-smoke-test-fingerprint",),
        )
        db.connection.commit()

        print("  Cleanup: ✅ OK")
        print()
        print("✅ Database layer initialized successfully")

        print("=" * 60)