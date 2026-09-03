from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime
from typing import Any

from ats_scrapers import get_scraper_for_url


VERSION = "3.0.0"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def clean_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = re.sub(r"<[^>]+>", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value or None

    return str(value).strip() or None


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


def serialize(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(k): serialize(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            serialize(v)
            for v in value
        ]

    if isinstance(value, (datetime,)):
        return value.isoformat()

    if hasattr(value, "model_dump"):
        try:
            return serialize(value.model_dump())
        except Exception:
            pass

    if hasattr(value, "dict"):
        try:
            return serialize(value.dict())
        except Exception:
            pass

    if hasattr(value, "value"):
        try:
            return serialize(value.value)
        except Exception:
            pass

    return value


def model_to_dict(job: Any) -> dict[str, Any]:
    if isinstance(job, dict):
        return serialize(job)

    if hasattr(job, "model_dump"):
        try:
            data = job.model_dump()
            if isinstance(data, dict):
                return serialize(data)
        except Exception:
            pass

    if hasattr(job, "dict"):
        try:
            data = job.dict()
            if isinstance(data, dict):
                return serialize(data)
        except Exception:
            pass

    if hasattr(job, "__dict__"):
        return serialize(vars(job))

    raise TypeError(
        "ATS job could not be converted to a dictionary"
    )


def normalize_for_matching(value: Any) -> str:
    text = clean_text(value) or ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_pattern(
    text: str,
    patterns: list[str],
) -> bool:
    for pattern in patterns:
        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            return True

    return False


# ============================================================
# EXPERIENCE EXTRACTION
# ============================================================

EXPERIENCE_PATTERNS = [
    r"\b\d+\s*[-–]\s*\d+\s*(?:years?|yrs?)\s+of\s+experience\b",
    r"\b\d+\+?\s*(?:years?|yrs?)\s+of\s+experience\b",
    r"\b\d+\s*(?:years?|yrs?)\s+experience\b",
    r"\bexperience\s+of\s+\d+\+?\s*(?:years?|yrs?)\b",
    r"\bminimum\s+of\s+\d+\+?\s*(?:years?|yrs?)\b",
]


def extract_experience_requirement(
    job: dict[str, Any],
) -> str | None:
    """
    Extract the clearest experience requirement.

    Priority:
    1. ATS-provided experience field
    2. Explicit requirement in description
    """

    experience = clean_text(
        job.get("experience")
    )

    if experience:
        return experience

    description = clean_text(
        job.get("description")
    ) or ""

    for pattern in EXPERIENCE_PATTERNS:
        match = re.search(
            pattern,
            description,
            flags=re.IGNORECASE,
        )

        if match:
            return clean_text(
                match.group(0)
            )

    return None


def extract_experience_range(
    experience: str | None,
) -> tuple[int | None, int | None]:
    if not experience:
        return None, None

    text = experience.lower()

    range_match = re.search(
        r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)",
        text,
    )

    if range_match:
        return (
            int(range_match.group(1)),
            int(range_match.group(2)),
        )

    plus_match = re.search(
        r"(\d+)\s*\+\s*(?:years?|yrs?)",
        text,
    )

    if plus_match:
        return (
            int(plus_match.group(1)),
            None,
        )

    single_match = re.search(
        r"\b(\d+)\s*(?:years?|yrs?)\b",
        text,
    )

    if single_match:
        years = int(
            single_match.group(1)
        )
        return years, years

    return None, None


# ============================================================
# FRESHER DETECTION
# ============================================================

def detect_fresher(
    title: str | None,
    description: str | None,
    experience: str | None,
) -> bool:
    """
    Conservative fresher detection.

    Explicit experience requirements have priority
    over generic words such as graduate, associate,
    junior, or internship.
    """

    title_text = title or ""
    description_text = description or ""

    combined = (
        f"{title_text} "
        f"{description_text}"
    )

    extracted_experience = (
        experience
        or extract_experience_requirement(
            {
                "experience": experience,
                "description": description_text,
            }
        )
    )

    if extracted_experience:
        exp_lower = (
            extracted_experience.lower()
        )

        minimum_years, maximum_years = (
            extract_experience_range(
                extracted_experience
            )
        )

        # 3+ years is not fresher friendly.
        if (
            minimum_years is not None
            and minimum_years >= 3
        ):
            return False

        # 0–1 / 0–2 years.
        if (
            minimum_years == 0
            and (
                maximum_years is None
                or maximum_years <= 2
            )
        ):
            return True

        # Explicit zero years.
        if re.search(
            r"\b0\s*(?:years?|yrs?)\b",
            exp_lower,
        ):
            return True

    explicit_fresher_patterns = [
        r"\bfreshers?\b",
        r"\bno experience\b",
        r"\bno prior experience\b",
        r"\bexperience not required\b",
        r"\bentry[\s-]?level\b",
        r"\btrainee\b",
        r"\bapprentice\b",
        r"\b0\s*[-–]?\s*1\s*(?:year|years|yr|yrs)\b",
        r"\b0\s*[-–]?\s*2\s*(?:year|years|yr|yrs)\b",
    ]

    if contains_pattern(
        combined,
        explicit_fresher_patterns,
    ):
        return True

    graduate_welcome_patterns = [
        r"\brecent graduates?.{0,120}\bwelcome\b",
        r"\brecent graduates?.{0,120}\bencouraged to apply\b",
        r"\bgraduates?.{0,120}\bwelcome\b",
        r"\bnew graduates?.{0,120}\bwelcome\b",
        r"\brecent grads?.{0,120}\bwelcome\b",
    ]

    if contains_pattern(
        combined,
        graduate_welcome_patterns,
    ):
        return True

    return False


# ============================================================
# GREENHOUSE METADATA
# ============================================================

def extract_metadata(
    raw: dict[str, Any],
) -> dict[str, Any]:
    metadata = raw.get(
        "metadata"
    ) or []

    result: dict[str, Any] = {}

    if not isinstance(
        metadata,
        list,
    ):
        return result

    for item in metadata:
        if not isinstance(
            item,
            dict,
        ):
            continue

        name = clean_text(
            item.get("name")
        )

        if not name:
            continue

        result[
            name.lower()
        ] = item.get("value")

    return result


def extract_workplace_type(
    raw: dict[str, Any],
) -> str | None:
    metadata = extract_metadata(
        raw
    )

    return clean_text(
        metadata.get(
            "workplace type"
        )
    )


def extract_department(
    data: dict[str, Any],
    raw: dict[str, Any],
) -> str | None:

    department = clean_text(
        data.get("department")
    )

    if department:
        return department

    departments = (
        raw.get("departments")
        or []
    )

    if (
        isinstance(
            departments,
            list,
        )
        and departments
    ):
        return clean_text(
            departments[0]
        )

    return None


def extract_location(
    data: dict[str, Any],
    raw: dict[str, Any],
) -> str | None:

    location = clean_text(
        data.get("location")
    )

    if location:
        return location

    offices = (
        raw.get("offices")
        or []
    )

    if (
        isinstance(
            offices,
            list,
        )
        and offices
    ):
        return clean_text(
            offices[0]
        )

    return None


# ============================================================
# INDIA DETECTION
# ============================================================

INDIA_PATTERNS = [
    r"\bindia\b",
    r"\bindian\b",
    r"\bhyderabad\b",
    r"\bbengaluru\b",
    r"\bbangalore\b",
    r"\bchennai\b",
    r"\bpune\b",
    r"\bmumbai\b",
    r"\bdelhi\b",
    r"\bnoida\b",
    r"\bgurgaon\b",
    r"\bgurugram\b",
    r"\bkolkata\b",
    r"\bkochi\b",
    r"\bahmedabad\b",
]


def detect_india(
    location: str | None,
    country: str | None,
) -> bool:

    combined = (
        f"{location or ''} "
        f"{country or ''}"
    )

    return contains_pattern(
        combined,
        INDIA_PATTERNS,
    )


# ============================================================
# REMOTE DETECTION
# ============================================================

def detect_remote(
    is_remote: bool | None,
    work_mode: str | None,
    location: str | None,
) -> bool:

    if is_remote is True:
        return True

    mode = (
        work_mode or ""
    ).lower()

    if "remote" in mode:
        return True

    location_text = (
        location or ""
    ).lower()

    if (
        "remote" in location_text
        or "worldwide" in location_text
    ):
        return True

    return False


# ============================================================
# FINGERPRINT
# ============================================================

def generate_fingerprint(
    job: dict[str, Any],
) -> str:

    global_id = clean_text(
        job.get("global_id")
    )

    if global_id:
        source = global_id
    else:
        source = "|".join(
            [
                normalize_for_matching(
                    job.get("company")
                ),
                normalize_for_matching(
                    job.get("title")
                ),
                normalize_for_matching(
                    job.get("location")
                ),
                normalize_for_matching(
                    job.get("requisition_id")
                ),
            ]
        )

    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(
    job: dict[str, Any],
) -> int:

    score = 50

    if job.get("global_id"):
        score += 15

    if job.get("source_url"):
        score += 10

    if job.get("company"):
        score += 5

    if job.get("title"):
        score += 5

    if job.get("location"):
        score += 5

    if job.get("posted_at"):
        score += 5

    if job.get("application_url"):
        score += 5

    return min(
        score,
        100,
    )


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_job(
    job: Any,
) -> dict[str, Any]:

    data = model_to_dict(
        job
    )

    raw = data.get(
        "raw"
    ) or {}

    if not isinstance(
        raw,
        dict,
    ):
        raw = {}

    # --------------------------------------------------------
    # Basic fields
    # --------------------------------------------------------

    global_id = clean_text(
        data.get("global_id")
    )

    source = (
        clean_text(
            data.get("ats_type")
        )
        or clean_text(
            data.get("source")
        )
        or "ats"
    )

    source_url = clean_text(
        data.get("url")
    )

    application_url = clean_text(
        data.get("apply_url")
    )

    company = clean_text(
        data.get("company")
    )

    title = clean_text(
        data.get("title")
    )

    description = clean_text(
        data.get("description")
    )

    # --------------------------------------------------------
    # Greenhouse metadata
    # --------------------------------------------------------

    workplace_type = (
        extract_workplace_type(
            raw
        )
    )

    location = extract_location(
        data,
        raw,
    )

    country = (
        clean_text(
            data.get("country")
        )
        or clean_text(
            data.get("country_iso")
        )
    )

    region = clean_text(
        data.get("region")
    )

    department = (
        extract_department(
            data,
            raw,
        )
    )

    # --------------------------------------------------------
    # Work mode
    # --------------------------------------------------------

    raw_is_remote = data.get(
        "is_remote"
    )

    is_remote = (
        raw_is_remote
        if isinstance(
            raw_is_remote,
            bool,
        )
        else None
    )

    work_mode = clean_text(
        data.get("work_mode")
    )

    if workplace_type:
        workplace_lower = (
            workplace_type.lower()
        )

        if (
            "remote"
            in workplace_lower
        ):
            is_remote = True
            work_mode = "Remote"

        elif (
            "hybrid"
            in workplace_lower
        ):
            is_remote = False
            work_mode = "Hybrid"

        elif (
            "on-site"
            in workplace_lower
            or "onsite"
            in workplace_lower
            or "on site"
            in workplace_lower
        ):
            is_remote = False
            work_mode = "On-site"

    if not work_mode:
        if is_remote is True:
            work_mode = "Remote"
        elif is_remote is False:
            work_mode = "On-site"
        else:
            work_mode = "Unknown"

    # --------------------------------------------------------
    # EXPERIENCE
    # --------------------------------------------------------

    experience = (
        extract_experience_requirement(
            {
                "experience": data.get(
                    "experience"
                ),
                "description": description,
            }
        )
    )

    experience_min = safe_int(
        data.get("experience_min")
    )

    experience_max = safe_int(
        data.get("experience_max")
    )

    extracted_min, extracted_max = (
        extract_experience_range(
            experience
        )
    )

    if experience_min is None:
        experience_min = extracted_min

    if experience_max is None:
        experience_max = extracted_max

    # --------------------------------------------------------
    # FRESHER
    # --------------------------------------------------------

    is_fresher_friendly = (
        detect_fresher(
            title,
            description,
            experience,
        )
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    posted_at = serialize(
        data.get("posted_at")
    )

    deadline = serialize(
        data.get(
            "application_deadline"
        )
    )

    fetched_at = serialize(
        data.get("fetched_at")
    )

    # --------------------------------------------------------
    # Normalized record
    # --------------------------------------------------------

    normalized = {
        "global_id": global_id,
        "fingerprint": None,

        "source": source,
        "source_url": source_url,
        "application_url": application_url,

        "company": company,
        "employer_type": "company",
        "agency_name": None,

        "title": title,
        "description": description,

        "location": location,
        "country": country,
        "region": region,

        "is_remote": is_remote,
        "work_mode": work_mode,

        "experience": experience,
        "experience_min": experience_min,
        "experience_max": experience_max,
        "is_fresher_friendly":
            is_fresher_friendly,

        "salary_currency": clean_text(
            data.get(
                "salary_currency"
            )
        ),

        "salary_period": clean_text(
            data.get(
                "salary_period"
            )
        ),

        "salary_summary": clean_text(
            data.get(
                "salary_summary"
            )
        ),

        "salary_min": safe_float(
            data.get("salary_min")
        ),

        "salary_max": safe_float(
            data.get("salary_max")
        ),

        "department": department,

        "team": clean_text(
            data.get("team")
        ),

        "requisition_id": clean_text(
            data.get(
                "requisition_id"
            )
        ),

        "ats_id": clean_text(
            data.get("ats_id")
        ),

        "posted_at": posted_at,
        "deadline": deadline,
        "fetched_at": fetched_at,

        "language": clean_text(
            data.get("language")
        ),

        "country_match": detect_india(
            location,
            country,
        ),

        "role_match": False,

        "experience_match":
            is_fresher_friendly,

        "remote_match":
            is_remote is True,

        "match_score": 0,

        "job_confidence": 0,

        "hr_name": None,
        "hr_title": None,
        "hr_email": None,
        "hr_confidence": 0,

        "raw": raw,
    }

    # --------------------------------------------------------
    # Remote normalization
    # --------------------------------------------------------

    if detect_remote(
        normalized["is_remote"],
        normalized["work_mode"],
        normalized["location"],
    ):
        normalized["is_remote"] = True
        normalized["work_mode"] = "Remote"
        normalized["remote_match"] = True

    # --------------------------------------------------------
    # Fingerprint
    # --------------------------------------------------------

    normalized["fingerprint"] = (
        generate_fingerprint(
            normalized
        )
    )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    normalized["job_confidence"] = (
        calculate_confidence(
            normalized
        )
    )

    return normalized


# ============================================================
# SCRAPER
# ============================================================

def fetch_jobs(
    careers_url: str,
    retries: int = DEFAULT_RETRIES,
) -> list[Any]:

    last_error: Exception | None = None

    for attempt in range(
        1,
        retries + 1,
    ):
        try:
            logger.info(
                "Creating ATS scraper: %s",
                careers_url,
            )

            scraper = (
                get_scraper_for_url(
                    careers_url,
                    timeout=DEFAULT_TIMEOUT,
                )
            )

            logger.info(
                "Detected ATS: %s",
                getattr(
                    scraper,
                    "ats",
                    "unknown",
                ),
            )

            logger.info(
                "Fetching jobs: attempt %d/%d",
                attempt,
                retries,
            )

            jobs = scraper.fetch()

            logger.info(
                "Fetched %d jobs",
                len(jobs),
            )

            return jobs

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Fetch failed: %s",
                exc,
            )

            if attempt < retries:
                time.sleep(
                    attempt * 2
                )

    raise RuntimeError(
        f"Failed to fetch jobs after "
        f"{retries} attempts: "
        f"{last_error}"
    )


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Job Intelligence Agent - "
            "Greenhouse/ATS worker"
        )
    )

    parser.add_argument(
        "careers_url",
        help="Public ATS careers URL",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of jobs",
    )

    parser.add_argument(
        "--fresher-only",
        action="store_true",
        help=(
            "Return only fresher-friendly jobs"
        ),
    )

    parser.add_argument(
        "--india-only",
        action="store_true",
        help=(
            "Return only India-related jobs"
        ),
    )

    parser.add_argument(
        "--remote-only",
        action="store_true",
        help="Return only remote jobs",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON",
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    args = parse_args()

    try:
        jobs = fetch_jobs(
            args.careers_url
        )

        normalized_jobs = [
            normalize_job(job)
            for job in jobs
        ]

        if args.fresher_only:
            normalized_jobs = [
                job
                for job in normalized_jobs
                if job[
                    "is_fresher_friendly"
                ]
            ]

        if args.india_only:
            normalized_jobs = [
                job
                for job in normalized_jobs
                if job[
                    "country_match"
                ]
            ]

        if args.remote_only:
            normalized_jobs = [
                job
                for job in normalized_jobs
                if job[
                    "work_mode"
                ] == "Remote"
            ]

        if args.limit is not None:
            normalized_jobs = (
                normalized_jobs[
                    :args.limit
                ]
            )

        output = {
            "success": True,
            "version": VERSION,
            "source_url": args.careers_url,
            "fetched_count": len(jobs),
            "returned_count": len(
                normalized_jobs
            ),
            "fetched_at": (
                datetime.now()
                .astimezone()
                .isoformat()
            ),
            "jobs": normalized_jobs,
        }

        print(
            json.dumps(
                output,
                indent=2 if args.pretty else None,
                ensure_ascii=False,
                default=serialize,
            )
        )

    except KeyboardInterrupt:
        logger.warning(
            "Interrupted by user"
        )
        sys.exit(130)

    except Exception as exc:
        error_output = {
            "success": False,
            "version": VERSION,
            "source_url": args.careers_url,
            "error": str(exc),
            "error_type": type(
                exc
            ).__name__,
        }

        print(
            json.dumps(
                error_output,
                indent=2,
                ensure_ascii=False,
            )
        )

        sys.exit(1)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()