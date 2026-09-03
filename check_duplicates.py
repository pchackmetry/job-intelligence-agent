#!/usr/bin/env python3
"""
Job Intelligence Agent
Duplicate Checker / Cleaner
Version: 1.0.0

SAFE BY DEFAULT

- Detects duplicate jobs.
- Does not delete anything unless --apply is used.
- Creates a SQLite backup before deletion.
- Keeps the best record in each duplicate group.
- Prefers VERIFIED/ALERTED records.
- Uses multiple duplicate strategies.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import unicodedata

from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ============================================================================
# CONFIG
# ============================================================================

DB_PATH = Path("data/jobs.db")
BACKUP_DIR = Path("data/backups")


# ============================================================================
# HELPERS
# ============================================================================

def normalize(value: object) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    ).lower().strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def compact(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        normalize(value),
    )


def safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (
        TypeError,
        ValueError,
    ):
        return 0


# ============================================================================
# DATABASE
# ============================================================================

def connect_db() -> sqlite3.Connection:

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH.resolve()}"
        )

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def get_columns(
    connection: sqlite3.Connection,
) -> set[str]:

    return {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(jobs)"
        ).fetchall()
    }


# ============================================================================
# DUPLICATE KEY
# ============================================================================

def build_duplicate_key(
    row: sqlite3.Row,
) -> tuple[str, str]:
    """
    Conservative duplicate identification.

    Priority:

    1. global_id
    2. source + ats_id
    3. company + requisition_id
    4. company + title + location + application_url

    Same title alone is NEVER considered a duplicate.
    """

    # ------------------------------------------------------------
    # 1. GLOBAL ID
    # ------------------------------------------------------------

    global_id = normalize(
        row["global_id"]
    )

    if global_id:
        return (
            "GLOBAL_ID",
            global_id,
        )

    # ------------------------------------------------------------
    # 2. SOURCE + ATS ID
    # ------------------------------------------------------------

    source = normalize(
        row["source"]
    )

    ats_id = normalize(
        row["ats_id"]
    )

    if source and ats_id:
        return (
            "SOURCE_ATS_ID",
            f"{source}|{ats_id}",
        )

    # ------------------------------------------------------------
    # 3. COMPANY + REQUISITION
    # ------------------------------------------------------------

    company = compact(
        row["company"]
    )

    requisition_id = compact(
        row["requisition_id"]
    )

    if (
        company
        and requisition_id
    ):
        return (
            "COMPANY_REQUISITION",
            f"{company}|{requisition_id}",
        )

    # ------------------------------------------------------------
    # 4. COMPANY + TITLE + LOCATION + APPLICATION URL
    # ------------------------------------------------------------

    title = compact(
        row["title"]
    )

    location = compact(
        row["location"]
    )

    application_url = normalize(
        row["application_url"]
    )

    if (
        company
        and title
        and location
        and application_url
    ):
        return (
            "COMPANY_TITLE_LOCATION_URL",
            (
                f"{company}|"
                f"{title}|"
                f"{location}|"
                f"{application_url}"
            ),
        )

    return (
        "",
        "",
    )


# ============================================================================
# RECORD QUALITY
# ============================================================================

def record_priority(
    row: sqlite3.Row,
) -> tuple:
    """
    Higher values are preferred.
    """

    verification = normalize(
        row["verification_status"]
    )

    verification_rank = {
        "ALERTED": 6,
        "VERIFIED": 5,
        "UNCERTAIN": 4,
        "UNVERIFIED": 3,
        "PENDING": 2,
        "REJECTED": 1,
        "": 0,
    }.get(
        verification,
        0,
    )

    has_application_url = bool(
        normalize(
            row["application_url"]
        )
    )

    has_official_url = bool(
        normalize(
            row["source_url"]
        )
    )

    match_score = safe_int(
        row["match_score"]
    )

    job_confidence = safe_int(
        row["job_confidence"]
    )

    posted_at = normalize(
        row["posted_at"]
    )

    fetched_at = normalize(
        row["fetched_at"]
    )

    updated_at = normalize(
        row["updated_at"]
    )

    return (
        verification_rank,
        1 if has_application_url else 0,
        1 if has_official_url else 0,
        match_score,
        job_confidence,
        posted_at,
        fetched_at,
        updated_at,
        safe_int(row["id"]),
    )


# ============================================================================
# FIND DUPLICATES
# ============================================================================

def find_duplicate_groups(
    connection: sqlite3.Connection,
) -> dict[
    tuple[str, str],
    list[sqlite3.Row],
]:

    rows = connection.execute(
        """
        SELECT *
        FROM jobs
        ORDER BY id ASC
        """
    ).fetchall()

    groups: dict[
        tuple[str, str],
        list[sqlite3.Row],
    ] = defaultdict(list)

    for row in rows:

        method, key = build_duplicate_key(
            row
        )

        if method and key:
            groups[
                (method, key)
            ].append(row)

    return {
        key: members
        for key, members in groups.items()
        if len(members) > 1
    }


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    groups: dict[
        tuple[str, str],
        list[sqlite3.Row],
    ],
) -> int:

    print()
    print("=" * 100)
    print(
        "JOB INTELLIGENCE AGENT - DUPLICATE REPORT"
    )
    print("=" * 100)

    if not groups:
        print()
        print("✅ NO DUPLICATES FOUND")
        print()
        return 0

    total_groups = 0
    total_removable = 0

    method_counts: dict[
        str,
        int,
    ] = defaultdict(int)

    for (
        method,
        key,
    ), rows in sorted(
        groups.items()
    ):

        total_groups += 1
        total_removable += len(rows) - 1
        method_counts[method] += 1

        winner = max(
            rows,
            key=record_priority,
        )

        print()
        print(
            f"[{method}]"
        )

        print(
            f"KEY: {key}"
        )

        print(
            f"RECORDS: {len(rows)}"
        )

        print(
            "KEEP: "
            f"ID={winner['id']} | "
            f"{winner['company']} | "
            f"{winner['title']} | "
            f"{winner['location']} | "
            f"verification="
            f"{winner['verification_status']} | "
            f"match="
            f"{winner['match_score']}"
        )

        for row in sorted(
            rows,
            key=lambda item: safe_int(
                item["id"]
            ),
        ):

            marker = (
                "KEEP"
                if row["id"]
                == winner["id"]
                else "DUPLICATE"
            )

            print(
                f"  {marker:10} "
                f"ID={row['id']} | "
                f"{row['company']} | "
                f"{row['title']} | "
                f"{row['location']} | "
                f"status="
                f"{row['verification_status']}"
            )

    print()
    print("-" * 100)

    print(
        f"Duplicate groups : {total_groups}"
    )

    print(
        f"Rows removable   : {total_removable}"
    )

    print()
    print(
        "Groups by method:"
    )

    for method, count in sorted(
        method_counts.items()
    ):
        print(
            f"  {method:35} {count}"
        )

    return total_removable


# ============================================================================
# BACKUP
# ============================================================================

def create_backup() -> Path:

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    backup_path = (
        BACKUP_DIR
        / f"jobs_before_dedup_{timestamp}.db"
    )

    shutil.copy2(
        DB_PATH,
        backup_path,
    )

    return backup_path


# ============================================================================
# DELETE
# ============================================================================

def build_delete_ids(
    groups: dict[
        tuple[str, str],
        list[sqlite3.Row],
    ],
) -> list[int]:

    delete_ids: set[int] = set()

    for rows in groups.values():

        winner = max(
            rows,
            key=record_priority,
        )

        for row in rows:

            row_id = safe_int(
                row["id"]
            )

            if (
                row_id
                and row_id
                != winner["id"]
            ):
                delete_ids.add(
                    row_id
                )

    return sorted(
        delete_ids
    )


def delete_duplicates(
    connection: sqlite3.Connection,
    groups: dict[
        tuple[str, str],
        list[sqlite3.Row],
    ],
) -> int:

    delete_ids = build_delete_ids(
        groups
    )

    if not delete_ids:
        print(
            "✅ Nothing to delete."
        )
        return 0

    backup_path = create_backup()

    print()
    print(
        "✅ Backup created:"
    )

    print(
        backup_path.resolve()
    )

    placeholders = ",".join(
        "?"
        for _ in delete_ids
    )

    try:

        connection.execute(
            "BEGIN"
        )

        cursor = connection.execute(
            f"""
            DELETE FROM jobs
            WHERE id IN ({placeholders})
            """,
            delete_ids,
        )

        connection.commit()

        deleted = cursor.rowcount

        print()
        print(
            f"✅ Deleted duplicate rows: {deleted}"
        )

        return deleted

    except Exception:

        connection.rollback()
        raise


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    global DB_PATH

    parser = argparse.ArgumentParser(
        description=(
            "Detect and safely remove "
            "duplicate jobs."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually delete duplicates "
            "after backup and confirmation."
        ),
    )

    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help="SQLite database path.",
    )

    args = parser.parse_args()

    DB_PATH = Path(
        args.db
    )

    connection: Optional[
        sqlite3.Connection
    ] = None

    try:

        connection = connect_db()

        required_columns = {
            "id",
            "global_id",
            "fingerprint",
            "source",
            "ats_id",
            "requisition_id",
            "company",
            "title",
            "location",
            "application_url",
            "source_url",
            "verification_status",
            "match_score",
            "job_confidence",
            "posted_at",
            "fetched_at",
            "updated_at",
        }

        actual_columns = get_columns(
            connection
        )

        missing = sorted(
            required_columns
            - actual_columns
        )

        if missing:

            print(
                "❌ Missing database columns:"
            )

            for column in missing:
                print(
                    f"  - {column}"
                )

            return 2

        groups = find_duplicate_groups(
            connection
        )

        removable = print_report(
            groups
        )

        # ------------------------------------------------------------
        # SAFE MODE
        # ------------------------------------------------------------

        if not args.apply:

            print()
            print("=" * 100)
            print(
                "SAFE MODE - NOTHING DELETED"
            )
            print("=" * 100)

            print()
            print(
                "To apply the cleanup:"
            )

            print(
                r".\.venv\Scripts\python.exe .\check_duplicates.py --apply"
            )

            return 0

        # ------------------------------------------------------------
        # NOTHING TO DELETE
        # ------------------------------------------------------------

        if removable == 0:
            return 0

        # ------------------------------------------------------------
        # FINAL CONFIRMATION
        # ------------------------------------------------------------

        print()
        print(
            f"⚠️ {removable} duplicate rows "
            "will be deleted."
        )

        print(
            "A database backup will be created first."
        )

        confirmation = input(
            '\nType DELETE to continue: '
        ).strip()

        if confirmation != "DELETE":

            print(
                "❌ Cleanup cancelled."
            )

            return 0

        deleted = delete_duplicates(
            connection,
            groups,
        )

        print()
        print("=" * 100)
        print(
            "DUPLICATE CLEANUP COMPLETE"
        )
        print("=" * 100)

        print(
            f"Rows deleted: {deleted}"
        )

        return 0

    except Exception as exc:

        print()
        print(
            "❌ ERROR:"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1

    finally:

        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )