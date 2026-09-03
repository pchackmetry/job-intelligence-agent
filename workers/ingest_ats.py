from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS
# ============================================================

try:
    from ats_scrapers import get_scraper_for_url
except Exception as exc:
    raise RuntimeError(
        "Could not import ats_scrapers. "
        "Make sure the ats-scrapers package is installed in the virtual environment."
    ) from exc

from database.job_database import JobDatabase


# ============================================================
# VERSION
# ============================================================

INGESTION_VERSION = "2.2.0"


# ============================================================
# HELPERS
# ============================================================

def safe_string(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text if text else None


def safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_raw(value: Any) -> str | None:
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


def make_fingerprint(
    global_id: Any,
    source_url: Any,
    title: Any,
    company: Any,
    location: Any,
) -> str:
    """
    Deterministic fingerprint.

    global_id is included first because ATS global IDs are the
    strongest identity signal. Location remains part of the
    fingerprint so a changed location may produce a new fingerprint;
    database upsert still uses global_id first and therefore updates
    the existing record instead of inserting a duplicate.
    """

    parts = [
        safe_string(global_id) or "",
        safe_string(source_url) or "",
        safe_string(company) or "",
        safe_string(title) or "",
        safe_string(location) or "",
    ]

    raw = "|".join(parts).lower()

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# FRESHER / INDIA SIGNALS
# ============================================================

FRESHER_PATTERNS = (
    "fresher",
    "freshers",
    "entry level",
    "entry-level",
    "recent graduate",
    "new graduate",
    "graduate",
    "trainee",
    "junior",
    "intern",
    "internship",
    "apprentice",
    "0-1 year",
    "0–1 year",
    "0-2 years",
    "0–2 years",
    "0-3 years",
    "0–3 years",
    "1-2 years",
    "1–2 years",
    "1-3 years",
    "1–3 years",
    "no experience",
    "without experience",
    "experience not required",
)


INDIA_PATTERNS = (
    "india",
    "hyderabad",
    "bangalore",
    "bengaluru",
    "chennai",
    "mumbai",
    "pune",
    "delhi",
    "new delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "kolkata",
    "telangana",
    "karnataka",
    "tamil nadu",
    "maharashtra",
    "kerala",
    "gujarat",
    "rajasthan",
    "uttar pradesh",
    "punjab",
    "odisha",
    "west bengal",
)


# ============================================================
# ATS JOB NORMALIZATION
# ============================================================

def normalize_job(job: Any) -> dict[str, Any]:
    """
    Convert an ats-scrapers Job object into the normalized SQLite schema.
    """

    if not hasattr(job, "model_dump"):
        raise TypeError(
            "ATS job object does not support model_dump()."
        )

    data = job.model_dump()

    global_id = safe_string(
        data.get("global_id")
    )

    source_url = safe_string(
        data.get("url")
        or data.get("source_url")
    )

    company = safe_string(
        data.get("company")
    )

    title = safe_string(
        data.get("title")
    )

    location = safe_string(
        data.get("location")
    )

    description = safe_string(
        data.get("description")
    )

    # --------------------------------------------------------
    # REMOTE
    # --------------------------------------------------------

    is_remote = data.get("is_remote")

    if isinstance(is_remote, str):
        remote_value = is_remote.strip().lower()

        if remote_value in {
            "true",
            "yes",
            "1",
            "remote",
        }:
            is_remote = True

        elif remote_value in {
            "false",
            "no",
            "0",
            "on-site",
            "onsite",
        }:
            is_remote = False

    if is_remote is True:
        work_mode = "Remote"

    elif is_remote is False:
        work_mode = "On-site"

    else:
        work_mode = safe_string(
            data.get("work_mode")
        )

    # --------------------------------------------------------
    # FINGERPRINT
    # --------------------------------------------------------

    fingerprint = make_fingerprint(
        global_id=global_id,
        source_url=source_url,
        title=title,
        company=company,
        location=location,
    )

    # --------------------------------------------------------
    # FRESHER
    # --------------------------------------------------------

    experience = safe_string(
        data.get("experience")
    )

    combined_text = (
        f"{title or ''} "
        f"{experience or ''} "
        f"{description or ''}"
    ).lower()

    is_fresher_friendly = any(
        pattern in combined_text
        for pattern in FRESHER_PATTERNS
    )

    if data.get("is_fresher_friendly") is True:
        is_fresher_friendly = True

    # --------------------------------------------------------
    # INDIA
    # --------------------------------------------------------

    location_lower = (
        location or ""
    ).lower()

    country_lower = (
        safe_string(
            data.get("country")
        )
        or ""
    ).lower()

    combined_location = (
        f"{location_lower} {country_lower}"
    )

    country_match = any(
        pattern in combined_location
        for pattern in INDIA_PATTERNS
    )

    country_iso = safe_string(
        data.get("country_iso")
    )

    if country_iso and country_iso.upper() == "IN":
        country_match = True

    # --------------------------------------------------------
    # APPLICATION URL
    # --------------------------------------------------------

    application_url = safe_string(
        data.get("apply_url")
        or data.get("application_url")
        or data.get("applyUrl")
        or data.get("url")
    )

    # --------------------------------------------------------
    # ATS SOURCE
    # --------------------------------------------------------

    source = (
        safe_string(
            data.get("ats_type")
        )
        or safe_string(
            data.get("source")
        )
        or "ats"
    )

    # --------------------------------------------------------
    # RAW
    # --------------------------------------------------------

    raw_data = data.get("raw")

    # --------------------------------------------------------
    # NORMALIZED OBJECT
    # --------------------------------------------------------

    return {
        "global_id": global_id,
        "fingerprint": fingerprint,

        "source": source,

        "source_url": source_url,
        "application_url": application_url,

        "requisition_id": safe_string(
            data.get("requisition_id")
        ),

        "ats_id": safe_string(
            data.get("ats_id")
        ),

        "company": company,
        "employer_type": None,
        "agency_name": None,

        "title": title,
        "description": description,

        "department": safe_string(
            data.get("department")
        ),

        "team": safe_string(
            data.get("team")
        ),

        "employment_type": safe_string(
            data.get("employment_type")
        ),

        "commitment": safe_string(
            data.get("commitment")
        ),

        "location": location,

        "country": safe_string(
            data.get("country")
        ),

        "region": safe_string(
            data.get("region")
        ),

        "country_iso": country_iso,

        "latitude": safe_float(
            data.get("lat")
            if data.get("lat") is not None
            else data.get("latitude")
        ),

        "longitude": safe_float(
            data.get("lon")
            if data.get("lon") is not None
            else data.get("longitude")
        ),

        "is_remote": is_remote,
        "work_mode": work_mode,

        "experience": experience,

        "experience_min": safe_int(
            data.get("experience_min")
        ),

        "experience_max": safe_int(
            data.get("experience_max")
        ),

        "is_fresher_friendly":
            is_fresher_friendly,

        "salary_currency": safe_string(
            data.get("salary_currency")
        ),

        "salary_period": safe_string(
            data.get("salary_period")
        ),

        "salary_summary": safe_string(
            data.get("salary_summary")
        ),

        "salary_min": safe_float(
            data.get("salary_min")
        ),

        "salary_max": safe_float(
            data.get("salary_max")
        ),

        "posted_at": (
            str(data.get("posted_at"))
            if data.get("posted_at")
            else None
        ),

        "deadline": (
            str(data.get("application_deadline"))
            if data.get("application_deadline")
            else None
        ),

        "fetched_at": (
            str(data.get("fetched_at"))
            if data.get("fetched_at")
            else None
        ),

        "language": safe_string(
            data.get("language")
        ),

        "country_match": country_match,

        "role_match": False,

        "experience_match":
            is_fresher_friendly,

        "remote_match":
            is_remote is True,

        "match_score": 0,

        "job_confidence": 90,

        "hr_name": None,
        "hr_title": None,
        "hr_email": None,
        "hr_confidence": 0,

        "raw_json":
            serialize_raw(raw_data),
    }


# ============================================================
# DISPLAY
# ============================================================

def print_job_preview(
    job: dict[str, Any],
    number: int,
) -> None:

    print()
    print(
        f"--- JOB {number} ---"
    )

    print(
        f"Title:        {job.get('title')}"
    )

    print(
        f"Company:      {job.get('company')}"
    )

    print(
        f"Location:     {job.get('location')}"
    )

    print(
        f"Remote:       {job.get('is_remote')}"
    )

    print(
        f"Work mode:    {job.get('work_mode')}"
    )

    print(
        f"Experience:   {job.get('experience')}"
    )

    print(
        f"Fresher:      {job.get('is_fresher_friendly')}"
    )

    print(
        f"Department:   {job.get('department')}"
    )

    print(
        f"Confidence:   {job.get('job_confidence')}"
    )

    print(
        f"Application:  {job.get('application_url')}"
    )

    print(
        f"Source:       {job.get('source')}"
    )

    fingerprint = (
        job.get("fingerprint")
        or ""
    )

    print(
        f"Fingerprint:  {fingerprint[:20]}..."
    )


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "ATS -> normalized jobs -> SQLite"
        )
    )

    parser.add_argument(
        "url",
        help=(
            "Public careers URL supported "
            "by ats-scrapers"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Maximum jobs to process. "
            "Use 0 for all fetched jobs."
        ),
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "Show normalized jobs only. "
            "Preview mode is completely read-only."
        ),
    )

    return parser


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = build_parser()
    args = parser.parse_args()

    if args.limit < 0:
        print(
            "❌ --limit cannot be negative."
        )
        return 2

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "JOB INTELLIGENCE AGENT"
    )
    print(
        "ATS INGESTION ENGINE"
    )
    print("=" * 70)

    print(
        f"Version: {INGESTION_VERSION}"
    )

    print(
        f"URL:     {args.url}"
    )

    print(
        f"Limit:   "
        f"{'ALL' if args.limit == 0 else args.limit}"
    )

    print(
        f"Preview: "
        f"{'YES' if args.preview else 'NO'}"
    )

    # --------------------------------------------------------
    # ATS DETECTION
    # --------------------------------------------------------

    print()
    print(
        "🔎 Detecting ATS..."
    )

    try:

        scraper = get_scraper_for_url(
            args.url
        )

    except Exception as exc:

        print(
            f"❌ ATS detection failed: {exc}"
        )

        return 1

    print(
        f"✅ ATS detected: {scraper.ats}"
    )

    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    print()
    print(
        "🌐 Fetching live jobs..."
    )

    try:

        jobs = scraper.fetch()

    except Exception as exc:

        print(
            f"❌ Job fetch failed: {exc}"
        )

        return 1

    print(
        f"✅ Jobs fetched: {len(jobs)}"
    )

    if not jobs:

        print(
            "⚠️ No jobs returned."
        )

        return 0

    # --------------------------------------------------------
    # LIMIT
    # --------------------------------------------------------

    if args.limit == 0:
        selected_jobs = list(jobs)
    else:
        selected_jobs = list(
            jobs[:args.limit]
        )

    print(
        f"📦 Jobs selected: "
        f"{len(selected_jobs)}"
    )

    full_scan = (
        args.limit == 0
        or len(selected_jobs) == len(jobs)
    )

    # --------------------------------------------------------
    # NORMALIZE
    # --------------------------------------------------------

    print()
    print(
        "🧹 Normalizing jobs..."
    )

    normalized_jobs: list[
        dict[str, Any]
    ] = []

    normalization_errors = 0

    for job in selected_jobs:

        try:

            normalized = normalize_job(
                job
            )

            normalized_jobs.append(
                normalized
            )

        except Exception as exc:

            normalization_errors += 1

            print(
                "⚠️ Normalization error: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    print(
        f"✅ Normalized: "
        f"{len(normalized_jobs)}"
    )

    if normalization_errors:

        print(
            f"⚠️ Normalization errors: "
            f"{normalization_errors}"
        )

    # --------------------------------------------------------
    # PREVIEW
    # --------------------------------------------------------

    if args.preview:

        print()
        print(
            "🔍 NORMALIZED JOB PREVIEW"
        )

        for index, job in enumerate(
            normalized_jobs,
            start=1,
        ):

            print_job_preview(
                job,
                index,
            )

        print()
        print("=" * 70)
        print(
            "✅ PREVIEW COMPLETE"
        )
        print(
            "No database was opened."
        )
        print(
            "No jobs were inserted or updated."
        )
        print(
            "No jobs were marked missing."
        )
        print("=" * 70)

        return 0

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    print()
    print(
        "💾 Opening SQLite..."
    )

    try:

        with JobDatabase() as db:

            print(
                f"📁 Database: "
                f"{db.db_path}"
            )

            before = db.count_jobs()

            print(
                f"📊 Jobs before: "
                f"{before}"
            )

            # ------------------------------------------------
            # START SCAN
            # ------------------------------------------------

            scan_id = db.start_scan(
                str(scraper.ats)
            )

            # ------------------------------------------------
            # UPSERT
            # ------------------------------------------------

            print()
            print(
                "💾 Inserting / updating jobs..."
            )

            stats = db.upsert_jobs(
                normalized_jobs
            )

            # ------------------------------------------------
            # MARK MISSING
            # ------------------------------------------------
            #
            # Only a complete source scan may mark jobs missing.
            # ------------------------------------------------

            missing = 0

            if full_scan:

                seen_fingerprints = {
                    job["fingerprint"]
                    for job in normalized_jobs
                    if job.get("fingerprint")
                }

                missing = db.mark_missing_jobs(
                    str(scraper.ats),
                    seen_fingerprints,
                )

            else:

                print()
                print(
                    "ℹ️ Limited ingestion detected."
                )

                print(
                    "Skipping missing-job marking."
                )

            # ------------------------------------------------
            # FINISH SCAN
            # ------------------------------------------------

            db.finish_scan(
                scan_id=scan_id,
                jobs_found=len(jobs),
                new_jobs=stats["new"],
                updated_jobs=stats["updated"],
                errors=(
                    stats["errors"]
                    + normalization_errors
                ),
            )

            # ------------------------------------------------
            # AFTER
            # ------------------------------------------------

            after = db.count_jobs()

            # ------------------------------------------------
            # RESULT
            # ------------------------------------------------

            print()
            print(
                "=" * 70
            )

            print(
                "📊 INGESTION RESULT"
            )

            print(
                "=" * 70
            )

            print(
                f"Jobs fetched:       {len(jobs)}"
            )

            print(
                f"Jobs selected:      "
                f"{len(selected_jobs)}"
            )

            print(
                f"New jobs:           "
                f"{stats['new']}"
            )

            print(
                f"Updated jobs:       "
                f"{stats['updated']}"
            )

            print(
                f"Errors:             "
                f"{stats['errors']}"
            )

            print(
                f"Missing/uncertain:  "
                f"{missing}"
            )

            print(
                f"Database before:    "
                f"{before}"
            )

            print(
                f"Database after:     "
                f"{after}"
            )

            # ------------------------------------------------
            # STATISTICS
            # ------------------------------------------------

            database_stats = (
                db.statistics()
            )

            print()
            print(
                "📈 DATABASE STATISTICS"
            )

            print(
                "-" * 70
            )

            for key, value in (
                database_stats.items()
            ):

                print(
                    f"{key}: {value}"
                )

            print()
            print(
                "✅ ATS ingestion completed"
            )

    except Exception as exc:

        print()
        print(
            "❌ Database ingestion failed:"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1

    print()
    print(
        "=" * 70
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )