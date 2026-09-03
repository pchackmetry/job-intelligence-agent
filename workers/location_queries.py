"""
India Job Location Query Engine
================================

Purpose:
    Generate a reliable, deduplicated India-wide job-search queue.

Coverage:
    - 28 Indian states
    - 8 Union Territories
    - Known cities
    - Location aliases
    - Remote India
    - Work From Home
    - Pan India
    - Anywhere in India

Important distinction:

    search_location
        = location used by our discovery engine

    job_location
        = actual location extracted from the job listing

Never assume search_location == job_location.
"""

from __future__ import annotations

import sys
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# LOCATION CONFIG
# ============================================================

from config.india_locations import (
    INDIA_STATES,
    INDIA_UTS,
    ALL_STATES,
    ALL_UTS,
    LOCATION_ALIASES,
    REMOTE_LOCATION_TERMS,
    ALL_INDIA_TERMS,
    normalize_location,
    find_state_for_city,
)


# ============================================================
# VERSION
# ============================================================

QUERY_ENGINE_VERSION = "2.0.0"


# ============================================================
# QUERY TYPES
# ============================================================

QUERY_STATE = "state"
QUERY_UT = "union_territory"
QUERY_CITY = "city"
QUERY_ALIAS = "alias"
QUERY_REMOTE = "remote"
QUERY_INDIA_WIDE = "india_wide"


# ============================================================
# DATA MODEL
# ============================================================

@dataclass(frozen=True)
class LocationQuery:
    """
    Represents one search operation.

    Example:

        location = Hyderabad
        query_type = city
        parent_region = Telangana
    """

    location: str
    query_type: str
    parent_region: str | None = None
    normalized_location: str | None = None
    country: str = "India"
    priority: int = 50
    search_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)

        data["search_terms"] = list(self.search_terms)

        data["normalized_location"] = (
            self.normalized_location
            or normalize_location(self.location)
        )

        return data


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value: str | None) -> str:
    """
    Normalize whitespace.
    """

    if not value:
        return ""

    return " ".join(str(value).strip().split())


def normalize_key(value: str | None) -> str:
    """
    Create a case-insensitive comparison key.
    """

    return clean_text(value).casefold()


def make_query_id(
    location: str,
    query_type: str,
    parent_region: str | None = None,
) -> str:
    """
    Generate deterministic ID for a search query.
    """

    raw = "|".join(
        [
            normalize_key(location),
            normalize_key(query_type),
            normalize_key(parent_region),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# SEARCH TERMS
# ============================================================

def build_search_terms(
    location: str,
    query_type: str,
) -> tuple[str, ...]:
    """
    Generate useful search-engine variations.

    Example:

        Hyderabad
        "Hyderabad jobs"
        "jobs in Hyderabad"

    We keep the actual query construction simple here.
    Individual discovery adapters can build their own
    source-specific queries.
    """

    location = clean_text(location)

    if not location:
        return ()

    if query_type == QUERY_REMOTE:
        return (
            location,
            f"{location} jobs",
            f"{location} cybersecurity jobs",
            f"{location} fresher jobs",
        )

    if query_type == QUERY_INDIA_WIDE:
        return (
            location,
            f"{location} jobs",
            f"{location} cybersecurity jobs",
            f"{location} fresher jobs",
        )

    return (
        location,
        f"{location} jobs",
        f"jobs in {location}",
        f"{location} fresher jobs",
        f"{location} cybersecurity jobs",
        f"{location} GRC jobs",
    )


# ============================================================
# STATE QUERIES
# ============================================================

def generate_state_queries() -> list[LocationQuery]:
    """
    Generate one query for every Indian state.
    """

    queries: list[LocationQuery] = []

    for state in ALL_STATES:

        queries.append(
            LocationQuery(
                location=state,
                query_type=QUERY_STATE,
                parent_region=state,
                normalized_location=state,
                priority=80,
                search_terms=build_search_terms(
                    state,
                    QUERY_STATE,
                ),
            )
        )

    return queries


# ============================================================
# UNION TERRITORY QUERIES
# ============================================================

def generate_ut_queries() -> list[LocationQuery]:
    """
    Generate one query for every Union Territory.
    """

    queries: list[LocationQuery] = []

    for ut in ALL_UTS:

        queries.append(
            LocationQuery(
                location=ut,
                query_type=QUERY_UT,
                parent_region=ut,
                normalized_location=ut,
                priority=80,
                search_terms=build_search_terms(
                    ut,
                    QUERY_UT,
                ),
            )
        )

    return queries


# ============================================================
# CITY QUERIES
# ============================================================

def generate_city_queries() -> list[LocationQuery]:
    """
    Generate queries for every city currently defined
    in india_locations.py.
    """

    queries: list[LocationQuery] = []

    for state, cities in INDIA_STATES.items():

        for city in cities:

            canonical = normalize_location(city)

            queries.append(
                LocationQuery(
                    location=city,
                    query_type=QUERY_CITY,
                    parent_region=state,
                    normalized_location=canonical,
                    priority=90,
                    search_terms=build_search_terms(
                        city,
                        QUERY_CITY,
                    ),
                )
            )

    for ut, cities in INDIA_UTS.items():

        for city in cities:

            canonical = normalize_location(city)

            queries.append(
                LocationQuery(
                    location=city,
                    query_type=QUERY_CITY,
                    parent_region=ut,
                    normalized_location=canonical,
                    priority=90,
                    search_terms=build_search_terms(
                        city,
                        QUERY_CITY,
                    ),
                )
            )

    return queries


# ============================================================
# ALIAS QUERIES
# ============================================================

def generate_alias_queries() -> list[LocationQuery]:
    """
    Generate searches for alternate city names.

    Example:

        Bangalore -> Bengaluru
        Gurgaon -> Gurugram
        Bombay -> Mumbai
    """

    queries: list[LocationQuery] = []

    for alias, canonical in LOCATION_ALIASES.items():

        alias = clean_text(alias)
        canonical = clean_text(canonical)

        if not alias or not canonical:
            continue

        if normalize_key(alias) == normalize_key(canonical):
            continue

        parent_region = find_state_for_city(canonical)

        queries.append(
            LocationQuery(
                location=alias,
                query_type=QUERY_ALIAS,
                parent_region=parent_region,
                normalized_location=canonical,
                priority=70,
                search_terms=build_search_terms(
                    alias,
                    QUERY_ALIAS,
                ),
            )
        )

    return queries


# ============================================================
# REMOTE QUERIES
# ============================================================

def generate_remote_queries() -> list[LocationQuery]:
    """
    Generate India-wide remote searches.
    """

    queries: list[LocationQuery] = []

    for term in REMOTE_LOCATION_TERMS:

        queries.append(
            LocationQuery(
                location=term,
                query_type=QUERY_REMOTE,
                parent_region="India",
                normalized_location="Remote - India",
                priority=100,
                search_terms=build_search_terms(
                    term,
                    QUERY_REMOTE,
                ),
            )
        )

    return queries


# ============================================================
# INDIA-WIDE QUERIES
# ============================================================

def generate_india_wide_queries() -> list[LocationQuery]:
    """
    Generate searches that are not tied to one state/city.
    """

    queries: list[LocationQuery] = []

    for term in ALL_INDIA_TERMS:

        queries.append(
            LocationQuery(
                location=term,
                query_type=QUERY_INDIA_WIDE,
                parent_region="India",
                normalized_location="India",
                priority=100,
                search_terms=build_search_terms(
                    term,
                    QUERY_INDIA_WIDE,
                ),
            )
        )

    return queries


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_queries(
    queries: list[LocationQuery],
) -> list[LocationQuery]:
    """
    Remove duplicate search instructions.

    Duplicate matching is based on:

        location
        query type
        parent region
    """

    unique: list[LocationQuery] = []
    seen: set[str] = set()

    for query in queries:

        query_id = make_query_id(
            location=query.location,
            query_type=query.query_type,
            parent_region=query.parent_region,
        )

        if query_id in seen:
            continue

        seen.add(query_id)
        unique.append(query)

    return unique


# ============================================================
# MASTER QUEUE
# ============================================================

def generate_all_location_queries() -> list[LocationQuery]:
    """
    Generate the complete India discovery queue.
    """

    queries: list[LocationQuery] = []

    # Highest-value broad searches first.
    queries.extend(generate_remote_queries())
    queries.extend(generate_india_wide_queries())

    # Regional coverage.
    queries.extend(generate_state_queries())
    queries.extend(generate_ut_queries())

    # City-level coverage.
    queries.extend(generate_city_queries())

    # Alternate names.
    queries.extend(generate_alias_queries())

    queries = deduplicate_queries(queries)

    # Highest priority first.
    queries.sort(
        key=lambda query: (
            -query.priority,
            query.query_type,
            normalize_key(query.location),
        )
    )

    return queries


# ============================================================
# FILTERS
# ============================================================

def filter_queries(
    queries: list[LocationQuery],
    query_type: str | None = None,
    region: str | None = None,
) -> list[LocationQuery]:
    """
    Generic query filter.
    """

    result = queries

    if query_type:

        result = [
            q
            for q in result
            if q.query_type == query_type
        ]

    if region:

        region_key = normalize_key(region)

        result = [
            q
            for q in result
            if normalize_key(q.parent_region) == region_key
        ]

    return result


def get_state_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_STATE,
    )


def get_ut_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_UT,
    )


def get_city_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_CITY,
    )


def get_alias_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_ALIAS,
    )


def get_remote_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_REMOTE,
    )


def get_india_wide_queries() -> list[LocationQuery]:
    return filter_queries(
        generate_all_location_queries(),
        query_type=QUERY_INDIA_WIDE,
    )


# ============================================================
# REGION SEARCH
# ============================================================

def get_queries_for_region(
    region: str,
) -> list[LocationQuery]:
    """
    Return every query belonging to a state/UT.
    """

    return filter_queries(
        generate_all_location_queries(),
        region=region,
    )


# ============================================================
# FIND QUERY
# ============================================================

def find_queries(
    location: str,
) -> list[LocationQuery]:
    """
    Find all search queries associated with a location.

    Example:

        find_queries("Bangalore")

    may return the alias and canonical city queries.
    """

    key = normalize_key(location)

    queries = generate_all_location_queries()

    return [
        q
        for q in queries
        if (
            normalize_key(q.location) == key
            or normalize_key(q.normalized_location) == key
        )
    ]


# ============================================================
# STATISTICS
# ============================================================

def get_query_statistics() -> dict:
    """
    Return queue statistics.
    """

    queries = generate_all_location_queries()

    stats = {
        "engine_version": QUERY_ENGINE_VERSION,
        "total_queries": len(queries),
        "states": 0,
        "union_territories": 0,
        "cities": 0,
        "aliases": 0,
        "remote": 0,
        "india_wide": 0,
        "unique_locations": 0,
        "unique_regions": 0,
    }

    locations: set[str] = set()
    regions: set[str] = set()

    for query in queries:

        if query.query_type == QUERY_STATE:
            stats["states"] += 1

        elif query.query_type == QUERY_UT:
            stats["union_territories"] += 1

        elif query.query_type == QUERY_CITY:
            stats["cities"] += 1

        elif query.query_type == QUERY_ALIAS:
            stats["aliases"] += 1

        elif query.query_type == QUERY_REMOTE:
            stats["remote"] += 1

        elif query.query_type == QUERY_INDIA_WIDE:
            stats["india_wide"] += 1

        locations.add(
            normalize_key(query.normalized_location)
        )

        if query.parent_region:
            regions.add(
                normalize_key(query.parent_region)
            )

    stats["unique_locations"] = len(locations)
    stats["unique_regions"] = len(regions)

    return stats


# ============================================================
# VALIDATION
# ============================================================

def validate_location_engine() -> list[str]:
    """
    Validate the basic India location structure.

    Returns:
        List of validation errors.

    Empty list means validation passed.
    """

    errors: list[str] = []

    # --------------------------------------------------------
    # State count
    # --------------------------------------------------------

    if len(ALL_STATES) != 28:
        errors.append(
            f"Expected 28 states, found {len(ALL_STATES)}"
        )

    # --------------------------------------------------------
    # UT count
    # --------------------------------------------------------

    if len(ALL_UTS) != 8:
        errors.append(
            f"Expected 8 Union Territories, found {len(ALL_UTS)}"
        )

    # --------------------------------------------------------
    # Query generation
    # --------------------------------------------------------

    queries = generate_all_location_queries()

    if not queries:
        errors.append(
            "No location queries were generated"
        )

    # --------------------------------------------------------
    # State queries
    # --------------------------------------------------------

    state_queries = get_state_queries()

    if len(state_queries) != 28:
        errors.append(
            f"Expected 28 state queries, found {len(state_queries)}"
        )

    # --------------------------------------------------------
    # UT queries
    # --------------------------------------------------------

    ut_queries = get_ut_queries()

    if len(ut_queries) != 8:
        errors.append(
            f"Expected 8 UT queries, found {len(ut_queries)}"
        )

    # --------------------------------------------------------
    # Alias tests
    # --------------------------------------------------------

    alias_tests = {
        "Bangalore": "Bengaluru",
        "Gurgaon": "Gurugram",
        "Bombay": "Mumbai",
        "Calcutta": "Kolkata",
        "Madras": "Chennai",
    }

    for alias, expected in alias_tests.items():

        actual = normalize_location(alias)

        if actual != expected:
            errors.append(
                f"Alias error: {alias} -> "
                f"{actual}; expected {expected}"
            )

    # --------------------------------------------------------
    # Required remote terms
    # --------------------------------------------------------

    required_remote_terms = [
        "Remote",
        "Remote - India",
        "Work From Home",
        "Pan India",
    ]

    all_remote_text = {
        normalize_key(x)
        for x in REMOTE_LOCATION_TERMS + ALL_INDIA_TERMS
    }

    for term in required_remote_terms:

        if normalize_key(term) not in all_remote_text:
            errors.append(
                f"Missing remote/India-wide term: {term}"
            )

    return errors


# ============================================================
# JSON EXPORT
# ============================================================

def export_queries_json(
    output_path: str | Path,
) -> Path:
    """
    Export the complete search queue to JSON.

    Useful later for:
        - debugging
        - dashboards
        - worker queues
        - scheduled jobs
    """

    output = Path(output_path)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    queries = generate_all_location_queries()

    payload = {
        "engine_version": QUERY_ENGINE_VERSION,
        "statistics": get_query_statistics(),
        "queries": [
            query.to_dict()
            for query in queries
        ],
    }

    output.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return output


# ============================================================
# PREVIEW
# ============================================================

def print_preview(limit: int = 30) -> None:
    """
    Print a human-readable preview.
    """

    queries = generate_all_location_queries()

    stats = get_query_statistics()

    print()
    print("=" * 72)
    print("INDIA JOB LOCATION QUERY ENGINE")
    print("=" * 72)

    print(f"Engine version      : {stats['engine_version']}")
    print(f"Total queries       : {stats['total_queries']}")
    print(f"States              : {stats['states']}")
    print(f"Union Territories   : {stats['union_territories']}")
    print(f"Cities              : {stats['cities']}")
    print(f"Aliases             : {stats['aliases']}")
    print(f"Remote              : {stats['remote']}")
    print(f"India-wide          : {stats['india_wide']}")
    print(f"Unique locations    : {stats['unique_locations']}")
    print(f"Unique regions      : {stats['unique_regions']}")

    print()
    print("Validation")
    print("-" * 72)

    errors = validate_location_engine()

    if errors:
        print("❌ FAILED")

        for error in errors:
            print(f"   - {error}")

    else:
        print("✅ PASSED")
        print("   28 states validated")
        print("   8 Union Territories validated")
        print("   Location aliases validated")
        print("   Remote/India-wide terms validated")
        print("   Query generation validated")

    print()
    print(f"First {min(limit, len(queries))} queries")
    print("-" * 72)

    for index, query in enumerate(
        queries[:limit],
        start=1,
    ):

        print(
            f"{index:03d} | "
            f"{query.query_type:<16} | "
            f"{query.location:<35} | "
            f"priority={query.priority}"
        )

    print("=" * 72)
    print()


# ============================================================
# COMMAND LINE
# ============================================================

def main() -> None:
    """
    Command-line interface.
    """

    print_preview(limit=30)


if __name__ == "__main__":
    main()