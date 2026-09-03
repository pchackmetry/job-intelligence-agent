"""
Job Intelligence Agent
Discovery Engine v1.1.1

Purpose:
    Generate structured job-discovery queries for:
      - India states
      - India union territories
      - Indian cities
      - India-wide / Pan India
      - India remote
      - Global remote jobs that may allow India

Policy:
    Third-party sites are discovery sources only.
    They are NOT trusted application sources.

    This engine does NOT:
      - bypass CAPTCHA
      - bypass authentication
      - bypass anti-bot systems
      - submit applications
      - claim that a foreign remote job is India-eligible

Final eligibility:
    discovery
      -> official verification
      -> remote eligibility
      -> direct application URL validation
      -> scoring
      -> database
      -> notification
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


# ============================================================
# VERSION / PATHS
# ============================================================

VERSION = "1.1.1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = PROJECT_ROOT / "config"

INDIA_LOCATION_FILE = CONFIG_DIR / "india_locations.py"

LOCATION_QUERY_FILE = (
    PROJECT_ROOT / "workers" / "location_queries.py"
)


# ============================================================
# DISCOVERY SOURCES
# ============================================================

DISCOVERY_SOURCES = (
    "linkedin",
    "indeed",
    "naukri",
    "glassdoor",
    "google",
    "jobspy",
    "ats",
)


# ============================================================
# ROLE CATALOG
# ============================================================

ROLE_GROUPS: dict[str, list[str]] = {
    "cybersecurity": [
        "Cybersecurity Analyst",
        "Cyber Security Analyst",
        "Information Security Analyst",
        "InfoSec Analyst",
        "Security Analyst",
        "Junior Security Analyst",
        "SOC Analyst",
        "SOC Analyst L1",
        "Security Operations Analyst",
        "Security Monitoring Analyst",
        "Security Engineer",
        "Junior Security Engineer",
        "Network Security Engineer",
        "Network Security Analyst",
        "Incident Response Analyst",
        "Threat Intelligence Analyst",
        "Threat Analyst",
        "Vulnerability Analyst",
        "Vulnerability Management Analyst",
        "VAPT Analyst",
        "VAPT Engineer",
        "Penetration Testing Intern",
        "Penetration Tester",
        "Application Security Analyst",
        "Application Security Engineer",
        "IAM Analyst",
        "IAM Engineer",
        "Identity and Access Management Analyst",
    ],
    "grc": [
        "GRC Analyst",
        "GRC Associate",
        "GRC Intern",
        "GRC Trainee",
        "Governance Risk Compliance Analyst",
        "Governance Risk and Compliance Analyst",
        "Risk and Compliance Analyst",
        "Risk Compliance Analyst",
        "Information Security GRC Analyst",
        "Information Security Risk Analyst",
        "Technology Risk Analyst",
        "IT Risk Analyst",
        "Cyber Risk Analyst",
        "Cybersecurity Risk Analyst",
        "Compliance Analyst",
        "Security Compliance Analyst",
        "Information Security Compliance Analyst",
        "IT Compliance Analyst",
        "Risk Analyst",
        "Technology Risk Associate",
        "IT Risk Associate",
    ],
    "financial_crime": [
        "KYC Analyst",
        "KYC Associate",
        "KYC Analyst Fresher",
        "AML Analyst",
        "AML Associate",
        "Anti Money Laundering Analyst",
        "CDD Analyst",
        "CDD Associate",
        "Customer Due Diligence Analyst",
        "Enhanced Due Diligence Analyst",
        "EDD Analyst",
        "Financial Crime Analyst",
        "Financial Crime Associate",
        "Transaction Monitoring Analyst",
        "Sanctions Analyst",
        "Regulatory Compliance Analyst",
        "Client Onboarding Analyst",
        "Client Due Diligence Analyst",
    ],
    "network": [
        "Network Security Engineer",
        "Network Security Analyst",
        "Network Engineer",
        "Junior Network Engineer",
        "Network Support Engineer",
        "NOC Engineer",
        "NOC Analyst",
        "L1 Network Engineer",
        "Network Operations Engineer",
        "Network Operations Analyst",
    ],
    "support": [
        "IT Support",
        "IT Support Engineer",
        "Technical Support Engineer",
        "Technical Support Analyst",
        "Desktop Support Engineer",
        "Desktop Support Analyst",
        "Service Desk Analyst",
        "Service Desk Engineer",
        "IT Helpdesk Analyst",
        "IT Help Desk Engineer",
        "Infrastructure Support Engineer",
        "Infrastructure Operations Engineer",
        "IT Operations Analyst",
        "Junior System Administrator",
        "Linux Support Engineer",
        "System Support Engineer",
    ],
}


# ============================================================
# FRESHER TERMS
# ============================================================

FRESHER_TERMS = (
    "fresher",
    "freshers",
    "entry level",
    "entry-level",
    "graduate",
    "recent graduate",
    "new graduate",
    "junior",
    "trainee",
    "associate",
    "intern",
    "internship",
    "apprentice",
    "apprenticeship",
    "0 years",
    "0-1 years",
    "0–1 years",
    "0 to 1 years",
    "0-2 years",
    "0–2 years",
    "0 to 2 years",
    "no experience",
    "experience not required",
)


# ============================================================
# INDIA SEARCH TERMS
# ============================================================

INDIA_REMOTE_TERMS = (
    "remote India",
    "remote - India",
    "work from home India",
    "work from India",
    "India remote jobs",
)

INDIA_WIDE_TERMS = (
    "India",
    "Pan India",
    "Pan-India",
    "all India",
    "India-wide",
)

# IMPORTANT:
# These are GLOBAL REMOTE discovery queries only.
# They do NOT mean the job is automatically eligible
# for someone working from India.
GLOBAL_REMOTE_TERMS = (
    "remote worldwide",
    "remote - worldwide",
    "remote any country",
    "remote anywhere",
    "work from anywhere",
    "global remote",
    "worldwide remote",
    "any country remote",
)


# ============================================================
# DATA MODELS
# ============================================================

@dataclass(frozen=True)
class DiscoveryQuery:
    query_id: str
    role: str
    role_group: str
    location: str
    scope: str
    source: str
    query: str
    priority: int
    fresher_focused: bool
    remote_focused: bool
    country: str
    generated_at: str


@dataclass
class DiscoveryBatch:
    version: str
    generated_at: str
    total_queries: int
    queries: list[DiscoveryQuery]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "total_queries": self.total_queries,
            "queries": [
                asdict(query)
                for query in self.queries
            ],
        }


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(value: str | None) -> str:
    """
    Basic text normalization.

    IMPORTANT:
    This function does NOT remove duplicate words.
    That allows duplicate-word detection to work correctly.
    """

    if not value:
        return ""

    value = str(value)

    value = value.lower()

    value = value.replace("–", "-")
    value = value.replace("—", "-")

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def contains_duplicate_words(query: str) -> bool:
    """
    Detect consecutive duplicate words.

    This function intentionally checks the text BEFORE
    duplicate-word removal.

    Examples:

        "security analyst fresher fresher"
            -> True

        "security analyst fresher"
            -> False
    """

    value = normalize_text(query)

    words = value.split()

    for index in range(1, len(words)):
        if words[index] == words[index - 1]:
            return True

    return False


def normalize_query(value: str) -> str:
    """
    Normalize generated search queries.

    Fixes:
      - entrylevel -> entry level
      - workfromhome -> work from home
      - duplicate consecutive words
      - duplicate whitespace
    """

    value = normalize_text(value)

    value = re.sub(
        r"[^\w\s\-+&./]",
        " ",
        value,
    )

    value = re.sub(
        r"\bentrylevel\b",
        "entry level",
        value,
    )

    value = re.sub(
        r"\bworkfromhome\b",
        "work from home",
        value,
    )

    words = value.split()

    cleaned: list[str] = []

    for word in words:
        if not cleaned or word != cleaned[-1]:
            cleaned.append(word)

    return " ".join(cleaned).strip()


# ============================================================
# QUERY ID
# ============================================================

def make_query_id(
    role: str,
    location: str,
    scope: str,
    source: str,
    query: str,
) -> str:

    raw = "|".join(
        [
            normalize_text(role),
            normalize_text(location),
            normalize_text(scope),
            normalize_text(source),
            normalize_text(query),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# LOCATION LOADING
# ============================================================

def load_india_locations() -> dict:
    """
    Load India location data from config/india_locations.py.

    Supported variable names:

        STATES
        INDIAN_STATES

        UNION_TERRITORIES
        INDIAN_UNION_TERRITORIES

        KNOWN_CITIES
        CITIES
    """

    if not INDIA_LOCATION_FILE.exists():
        return {
            "states": [],
            "union_territories": [],
            "cities": [],
        }

    try:
        namespace: dict = {}

        source = INDIA_LOCATION_FILE.read_text(
            encoding="utf-8"
        )

        exec(
            compile(
                source,
                str(INDIA_LOCATION_FILE),
                "exec",
            ),
            namespace,
        )

        states = namespace.get(
            "STATES",
            namespace.get(
                "INDIAN_STATES",
                [],
            ),
        )

        union_territories = namespace.get(
            "UNION_TERRITORIES",
            namespace.get(
                "INDIAN_UNION_TERRITORIES",
                [],
            ),
        )

        cities = namespace.get(
            "KNOWN_CITIES",
            namespace.get(
                "CITIES",
                [],
            ),
        )

        return {
            "states": _extract_names(states),
            "union_territories": _extract_names(
                union_territories
            ),
            "cities": _extract_names(cities),
        }

    except Exception as exc:
        print(
            f"WARNING: Could not load India locations: {exc}",
            file=sys.stderr,
        )

        return {
            "states": [],
            "union_territories": [],
            "cities": [],
        }


def _extract_names(value) -> list[str]:
    """
    Convert location structures into a clean list of names.
    """

    if value is None:
        return []

    if isinstance(value, dict):
        values = list(value.keys())

    elif isinstance(
        value,
        (list, tuple, set),
    ):
        values = list(value)

    else:
        return []

    result: list[str] = []

    for item in values:

        if isinstance(item, str):
            result.append(item)

        elif isinstance(item, dict):

            name = (
                item.get("name")
                or item.get("city")
                or item.get("location")
            )

            if name:
                result.append(str(name))

    return unique_preserve_order(result)


# ============================================================
# ROLE ITERATION
# ============================================================

def iter_roles(
    groups: Iterable[str] | None = None,
) -> Iterable[tuple[str, str]]:

    if groups is None:
        selected = set(
            ROLE_GROUPS.keys()
        )
    else:
        selected = {
            str(group).strip().lower()
            for group in groups
        }

    for group_name, roles in ROLE_GROUPS.items():

        if group_name not in selected:
            continue

        for role in roles:
            yield group_name, role


# ============================================================
# FRESHER VARIANTS
# ============================================================

def fresher_variants(
    role: str,
) -> list[str]:

    return [
        f'"{role}" fresher',
        f'"{role}" "entry level"',
        f'"{role}" junior',
        f'"{role}" trainee',
        f'"{role}" graduate',
        f'"{role}" "0-2 years"',
    ]


# ============================================================
# QUERY BUILDER
# ============================================================

def build_query(
    role: str,
    location: str = "",
    modifier: str = "",
) -> str:

    parts = [
        f'"{role}"',
    ]

    if location:
        parts.append(
            f'"{location}"'
        )

    if modifier:
        parts.append(
            modifier
        )

    return normalize_query(
        " ".join(parts)
    )


# ============================================================
# QUERY QUALITY
# ============================================================

def is_fresher_term(
    value: str,
) -> bool:

    normalized = normalize_text(
        value
    )

    normalized_terms = {
        normalize_text(term)
        for term in FRESHER_TERMS
    }

    return normalized in normalized_terms


def query_quality_errors(
    query: str,
) -> list[str]:

    errors: list[str] = []

    if not normalize_query(query):
        errors.append(
            "empty query"
        )

    if contains_duplicate_words(query):
        errors.append(
            "duplicate consecutive words"
        )

    normalized = normalize_query(query)

    if "entrylevel" in normalized:
        errors.append(
            "invalid entrylevel token"
        )

    if "fresher fresher" in normalized:
        errors.append(
            "duplicate fresher"
        )

    return errors


# ============================================================
# QUERY GENERATION
# ============================================================

def generate_queries(
    *,
    groups: Iterable[str] | None = None,
    sources: Iterable[str] | None = None,
    include_cities: bool = True,
    include_global_remote: bool = True,
    fresher_only: bool = False,
    max_queries: int = 0,
) -> list[DiscoveryQuery]:

    # --------------------------------------------------------
    # Sources
    # --------------------------------------------------------

    selected_sources = [
        str(source).lower().strip()
        for source in (
            sources
            if sources is not None
            else DISCOVERY_SOURCES
        )
    ]

    selected_sources = unique_preserve_order(
        selected_sources
    )

    selected_sources = [
        source
        for source in selected_sources
        if source in DISCOVERY_SOURCES
    ]

    # --------------------------------------------------------
    # Locations
    # --------------------------------------------------------

    locations = load_india_locations()

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).replace(
        microsecond=0
    ).isoformat()

    queries: list[DiscoveryQuery] = []

    seen: set[str] = set()

    # --------------------------------------------------------
    # Internal add function
    # --------------------------------------------------------

    def add_query(
        *,
        role: str,
        role_group: str,
        location: str,
        scope: str,
        source: str,
        query: str,
        priority: int,
        fresher_focused: bool,
        remote_focused: bool,
        country: str,
    ) -> None:

        # Normalize exactly once before storing.
        query = normalize_query(query)

        if not query:
            return

        # This should never happen because normalize_query()
        # removes duplicate consecutive words, but retaining
        # this guard makes the function defensive.
        if contains_duplicate_words(query):
            return

        query_id = make_query_id(
            role,
            location,
            scope,
            source,
            query,
        )

        if query_id in seen:
            return

        seen.add(query_id)

        queries.append(
            DiscoveryQuery(
                query_id=query_id,
                role=role,
                role_group=role_group,
                location=location,
                scope=scope,
                source=source,
                query=query,
                priority=priority,
                fresher_focused=fresher_focused,
                remote_focused=remote_focused,
                country=country,
                generated_at=now,
            )
        )

    # ========================================================
    # ROLE LOOP
    # ========================================================

    for role_group, role in iter_roles(groups):
        
                # ====================================================
        # INTERNET / SEARCH ENGINE DORKING
        # ====================================================

        INTERNET_DORKS = (
            'site:linkedin.com/jobs',
            'site:naukri.com',
            'site:indeed.com',
            'site:glassdoor.co.in',
            'site:foundit.in',
            'site:wellfound.com',
            'site:internshala.com',
            'site:jobs.lever.co',
            'site:boards.greenhouse.io',
            'site:myworkdayjobs.com',
            'site:jobs.smartrecruiters.com',
        )

        for dork in INTERNET_DORKS:
            add_query(
                role=role,
                role_group=role_group,
                location="India",
                scope="INDIA_PAN_INDIA",
                source="google",
                query=f'{dork} "{role}" India',
                priority=120,
                fresher_focused=False,
                remote_focused=False,
                country="India",
            )

            if fresher_only:
                add_query(
                    role=role,
                    role_group=role_group,
                    location="India",
                    scope="INDIA_PAN_INDIA",
                    source="google",
                    query=f'{dork} "{role}" India ("fresher" OR "entry level" OR "graduate" OR "intern")',
                    priority=130,
                    fresher_focused=True,
                    remote_focused=False,
                    country="India",
                )

        # ====================================================
        # INDIA REMOTE
        # ====================================================

        for source in selected_sources:

            for term in INDIA_REMOTE_TERMS:

                add_query(
                    role=role,
                    role_group=role_group,
                    location="India",
                    scope="INDIA_REMOTE",
                    source=source,
                    query=build_query(
                        role,
                        term,
                    ),
                    priority=100,
                    fresher_focused=False,
                    remote_focused=True,
                    country="India",
                )

                if fresher_only:

                    for fresher in (
                        "fresher",
                        "entry level",
                        "junior",
                    ):

                        add_query(
                            role=role,
                            role_group=role_group,
                            location="India",
                            scope="INDIA_REMOTE",
                            source=source,
                            query=build_query(
                                role,
                                term,
                                fresher,
                            ),
                            priority=110,
                            fresher_focused=True,
                            remote_focused=True,
                            country="India",
                        )

        # ====================================================
        # INDIA-WIDE / PAN INDIA
        # ====================================================

        for source in selected_sources:

            for location_term in INDIA_WIDE_TERMS:

                add_query(
                    role=role,
                    role_group=role_group,
                    location=location_term,
                    scope="INDIA_PAN_INDIA",
                    source=source,
                    query=build_query(
                        role,
                        location_term,
                    ),
                    priority=95,
                    fresher_focused=False,
                    remote_focused=False,
                    country="India",
                )

                if fresher_only:

                    for fresher in (
                        "fresher",
                        "entry level",
                        "junior",
                    ):

                        add_query(
                            role=role,
                            role_group=role_group,
                            location=location_term,
                            scope="INDIA_PAN_INDIA",
                            source=source,
                            query=build_query(
                                role,
                                location_term,
                                fresher,
                            ),
                            priority=105,
                            fresher_focused=True,
                            remote_focused=False,
                            country="India",
                        )

        # ====================================================
        # INDIA STATES
        # ====================================================

        for state in locations["states"]:

            for source in selected_sources:

                add_query(
                    role=role,
                    role_group=role_group,
                    location=state,
                    scope="INDIA",
                    source=source,
                    query=build_query(
                        role,
                        state,
                    ),
                    priority=90,
                    fresher_focused=False,
                    remote_focused=False,
                    country="India",
                )

                if fresher_only:

                    for fresher in (
                        "fresher",
                        "entry level",
                    ):

                        add_query(
                            role=role,
                            role_group=role_group,
                            location=state,
                            scope="INDIA",
                            source=source,
                            query=build_query(
                                role,
                                state,
                                fresher,
                            ),
                            priority=100,
                            fresher_focused=True,
                            remote_focused=False,
                            country="India",
                        )

        # ====================================================
        # INDIA UNION TERRITORIES
        # ====================================================

        for territory in locations[
            "union_territories"
        ]:

            for source in selected_sources:

                add_query(
                    role=role,
                    role_group=role_group,
                    location=territory,
                    scope="INDIA",
                    source=source,
                    query=build_query(
                        role,
                        territory,
                    ),
                    priority=90,
                    fresher_focused=False,
                    remote_focused=False,
                    country="India",
                )

                if fresher_only:

                    add_query(
                        role=role,
                        role_group=role_group,
                        location=territory,
                        scope="INDIA",
                        source=source,
                        query=build_query(
                            role,
                            territory,
                            "fresher",
                        ),
                        priority=100,
                        fresher_focused=True,
                        remote_focused=False,
                        country="India",
                    )

        # ====================================================
        # INDIAN CITIES
        # ====================================================

        if include_cities:

            for city in locations["cities"]:

                for source in selected_sources:

                    add_query(
                        role=role,
                        role_group=role_group,
                        location=city,
                        scope="INDIA",
                        source=source,
                        query=build_query(
                            role,
                            city,
                        ),
                        priority=85,
                        fresher_focused=False,
                        remote_focused=False,
                        country="India",
                    )

                    if fresher_only:

                        add_query(
                            role=role,
                            role_group=role_group,
                            location=city,
                            scope="INDIA",
                            source=source,
                            query=build_query(
                                role,
                                city,
                                "fresher",
                            ),
                            priority=95,
                            fresher_focused=True,
                            remote_focused=False,
                            country="India",
                        )

        # ====================================================
        # GLOBAL REMOTE
        # ====================================================

        if include_global_remote:

            for source in selected_sources:

                for term in GLOBAL_REMOTE_TERMS:

                    add_query(
                        role=role,
                        role_group=role_group,
                        location="GLOBAL_REMOTE",
                        scope="GLOBAL_REMOTE",
                        source=source,
                        query=build_query(
                            role,
                            term,
                        ),
                        priority=80,
                        fresher_focused=False,
                        remote_focused=True,
                        country="GLOBAL",
                    )

                    if fresher_only:

                        add_query(
                            role=role,
                            role_group=role_group,
                            location="GLOBAL_REMOTE",
                            scope="GLOBAL_REMOTE",
                            source=source,
                            query=build_query(
                                role,
                                term,
                                "fresher",
                            ),
                            priority=90,
                            fresher_focused=True,
                            remote_focused=True,
                            country="GLOBAL",
                        )

    # ========================================================
    # FINAL SORT
    # ========================================================

    queries.sort(
        key=lambda item: (
            -item.priority,
            item.role_group,
            item.role,
            item.location,
            item.source,
            item.query,
        )
    )

    # ========================================================
    # MAX QUERY LIMIT
    # ========================================================

    if max_queries > 0:
        queries = queries[:max_queries]

    return queries


# ============================================================
# DEDUPLICATION
# ============================================================

def unique_preserve_order(
    values: Iterable[str],
) -> list[str]:

    seen: set[str] = set()

    result: list[str] = []

    for value in values:

        key = normalize_text(value)

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        result.append(value)

    return result


def deduplicate_queries(
    queries: Iterable[DiscoveryQuery],
) -> list[DiscoveryQuery]:

    seen: set[tuple] = set()

    result: list[DiscoveryQuery] = []

    for query in queries:

        key = (
            normalize_text(query.role),
            normalize_text(query.location),
            normalize_text(query.scope),
            normalize_text(query.source),
            normalize_query(query.query),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(query)

    return result


# ============================================================
# STATISTICS
# ============================================================

def query_statistics(
    queries: Iterable[DiscoveryQuery],
) -> dict:

    queries = list(queries)

    by_source: dict[str, int] = {}

    by_scope: dict[str, int] = {}

    by_role_group: dict[str, int] = {}

    by_location: dict[str, int] = {}

    fresher_count = 0

    remote_count = 0

    for query in queries:

        by_source[query.source] = (
            by_source.get(
                query.source,
                0,
            )
            + 1
        )

        by_scope[query.scope] = (
            by_scope.get(
                query.scope,
                0,
            )
            + 1
        )

        by_role_group[query.role_group] = (
            by_role_group.get(
                query.role_group,
                0,
            )
            + 1
        )

        by_location[query.location] = (
            by_location.get(
                query.location,
                0,
            )
            + 1
        )

        if query.fresher_focused:
            fresher_count += 1

        if query.remote_focused:
            remote_count += 1

    return {
        "total": len(queries),
        "by_source": by_source,
        "by_scope": by_scope,
        "by_role_group": by_role_group,
        "unique_locations": len(
            by_location
        ),
        "fresher_focused": fresher_count,
        "remote_focused": remote_count,
    }


# ============================================================
# JSON EXPORT
# ============================================================

def save_json(
    queries: list[DiscoveryQuery],
    output: Path,
) -> None:

    batch = DiscoveryBatch(
        version=VERSION,
        generated_at=datetime.now(
            timezone.utc
        ).replace(
            microsecond=0
        ).isoformat(),
        total_queries=len(queries),
        queries=queries,
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            batch.to_dict(),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# VALIDATION
# ============================================================

VALID_SCOPES = {
    "INDIA",
    "INDIA_REMOTE",
    "INDIA_PAN_INDIA",
    "GLOBAL_REMOTE",
    "INTERNATIONAL_REMOTE",
    "FOREIGN_RESTRICTED",
    "UNKNOWN",
}


FOREIGN_LOCATIONS = {
    "usa",
    "united states",
    "canada",
    "uk",
    "united kingdom",
    "germany",
    "france",
    "australia",
}


def validate_query(
    query: DiscoveryQuery,
) -> list[str]:

    errors: list[str] = []

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not query.query:
        errors.append(
            "empty query"
        )

    if query.source not in DISCOVERY_SOURCES:
        errors.append(
            f"invalid source: {query.source}"
        )

    if query.scope not in VALID_SCOPES:
        errors.append(
            f"invalid scope: {query.scope}"
        )

    # --------------------------------------------------------
    # Query quality
    # --------------------------------------------------------

    errors.extend(
        query_quality_errors(
            query.query
        )
    )

    normalized_query = normalize_text(
        query.query
    )

    # --------------------------------------------------------
    # GLOBAL REMOTE protection
    # --------------------------------------------------------

    if query.scope == "GLOBAL_REMOTE":

        normalized_location = normalize_text(
            query.location
        )

        if normalized_location in FOREIGN_LOCATIONS:
            errors.append(
                "GLOBAL_REMOTE query contains "
                "foreign country location"
            )

        remote_words = (
            "remote",
            "work from anywhere",
            "any country",
            "worldwide",
            "global",
        )

        if not any(
            term in normalized_query
            for term in remote_words
        ):
            errors.append(
                "GLOBAL_REMOTE query is not "
                "remote-focused"
            )

    # --------------------------------------------------------
    # Remote-focused protection
    # --------------------------------------------------------

    if query.remote_focused:

        remote_words = (
            "remote",
            "work from home",
            "work from india",
            "work from anywhere",
        )

        if not any(
            term in normalized_query
            for term in remote_words
        ):
            errors.append(
                "remote-focused query lacks "
                "remote term"
            )

    # --------------------------------------------------------
    # Fresher-focused protection
    # --------------------------------------------------------

    if query.fresher_focused:

        fresher_words = (
            "fresher",
            "freshers",
            "entry level",
            "junior",
            "trainee",
            "graduate",
            "intern",
            "apprentice",
            "0-1 years",
            "0-2 years",
            "no experience",
        )

        if not any(
            term in normalized_query
            for term in fresher_words
        ):
            errors.append(
                "fresher-focused query lacks "
                "fresher term"
            )

    return errors


def validate_queries(
    queries: Iterable[DiscoveryQuery],
) -> tuple[bool, list[str]]:

    errors: list[str] = []

    for query in queries:

        query_errors = validate_query(
            query
        )

        if query_errors:

            errors.extend(
                [
                    (
                        f"{query.query_id}: "
                        f"{error}"
                    )
                    for error in query_errors
                ]
            )

    return (
        not errors,
        errors,
    )


# ============================================================
# TEST SUITE
# ============================================================

def run_tests() -> bool:

    print("=" * 72)
    print("JOB DISCOVERY ENGINE TEST SUITE")
    print("=" * 72)

    print(
        f"Version: {VERSION}"
    )

    print("-" * 72)

    passed = 0

    failed = 0

    test_errors: list[str] = []

    def check(
        name: str,
        condition: bool,
    ) -> None:

        nonlocal passed, failed

        if condition:

            print(
                f"✅ {name}"
            )

            passed += 1

        else:

            print(
                f"❌ {name}"
            )

            failed += 1

    # ========================================================
    # Generate test queries
    # ========================================================

    queries = generate_queries(
        groups=["cybersecurity"],
        sources=["google"],
        include_cities=False,
        include_global_remote=True,
        fresher_only=True,
        max_queries=0,
    )

    check(
        "Queries generated",
        len(queries) > 0,
    )

    check(
        "Query IDs are present",
        all(
            query.query_id
            for query in queries
        ),
    )

    check(
        "Queries contain role",
        all(
            query.role
            for query in queries
        ),
    )

    check(
        "Only valid sources",
        all(
            query.source
            in DISCOVERY_SOURCES
            for query in queries
        ),
    )

    # ========================================================
    # India remote
    # ========================================================

    india_remote = [
        query
        for query in queries
        if query.scope
        == "INDIA_REMOTE"
    ]

    check(
        "India remote queries generated",
        len(india_remote) > 0,
    )

    check(
        "India remote queries are remote-focused",
        all(
            query.remote_focused
            for query in india_remote
        ),
    )

    # ========================================================
    # Global remote
    # ========================================================

    global_remote = [
        query
        for query in queries
        if query.scope
        == "GLOBAL_REMOTE"
    ]

    check(
        "Global remote queries generated",
        len(global_remote) > 0,
    )

    check(
        "Global queries are remote-focused",
        all(
            query.remote_focused
            for query in global_remote
        ),
    )

    # ========================================================
    # Foreign search protection
    # ========================================================

    ordinary_foreign_search = [
        query
        for query in queries
        if normalize_text(
            query.location
        ) in FOREIGN_LOCATIONS
    ]

    check(
        "No ordinary foreign-country searches",
        len(ordinary_foreign_search) == 0,
    )

    # ========================================================
    # Fresher
    # ========================================================

    fresher_queries = [
        query
        for query in queries
        if query.fresher_focused
    ]

    check(
        "Fresher-focused queries generated",
        len(fresher_queries) > 0,
    )

    # ========================================================
    # Deduplication
    # ========================================================

    duplicate_input = [
        queries[0],
        queries[0],
        queries[0],
    ]

    deduped = deduplicate_queries(
        duplicate_input
    )

    check(
        "Duplicate queries removed",
        len(deduped) == 1,
    )

    # ========================================================
    # Query validation
    # ========================================================

    valid, errors = validate_queries(
        queries
    )

    if errors:
        test_errors.extend(errors)

    check(
        "Generated queries validate",
        valid and not errors,
    )

    # ========================================================
    # Deterministic query ID
    # ========================================================

    first = queries[0]

    second_id = make_query_id(
        first.role,
        first.location,
        first.scope,
        first.source,
        first.query,
    )

    check(
        "Query ID deterministic",
        first.query_id
        == second_id,
    )

    # ========================================================
    # Statistics
    # ========================================================

    stats = query_statistics(
        queries
    )

    check(
        "Statistics generated",
        stats["total"]
        == len(queries),
    )

    check(
        "Source statistics present",
        bool(
            stats["by_source"]
        ),
    )

    check(
        "Scope statistics present",
        bool(
            stats["by_scope"]
        ),
    )

    # ========================================================
    # Query normalization
    # ========================================================

    malformed = [
        "application security analyst entrylevel",
        "application security analyst fresher fresher",
        "application security analyst junior junior",
    ]

    cleaned = [
        normalize_query(query)
        for query in malformed
    ]

    check(
        "Query normalization works",
        cleaned[0]
        == "application security analyst entry level",
    )

    # ========================================================
    # Duplicate detection
    #
    # IMPORTANT:
    # Test the raw string because normalize_query()
    # intentionally removes duplicate words.
    # ========================================================

    check(
        "Duplicate consecutive words detected",
        contains_duplicate_words(
            "security analyst fresher fresher"
        ),
    )

    check(
        "Duplicate detection ignores clean query",
        not contains_duplicate_words(
            "security analyst fresher"
        ),
    )

    check(
        "Clean queries have no duplicate words",
        all(
            not contains_duplicate_words(
                query.query
            )
            for query in queries
        ),
    )

    # ========================================================
    # Query ID uniqueness
    # ========================================================

    query_ids = [
        query.query_id
        for query in queries
    ]

    check(
        "Generated query IDs are unique",
        len(query_ids)
        == len(set(query_ids)),
    )

    # ========================================================
    # Global remote query safety
    # ========================================================

    check(
        "Global remote queries contain remote signal",
        all(
            any(
                term
                in normalize_text(
                    query.query
                )
                for term in (
                    "remote",
                    "work from anywhere",
                    "any country",
                    "worldwide",
                    "global",
                )
            )
            for query in global_remote
        ),
    )

    # ========================================================
    # Final results
    # ========================================================

    print("-" * 72)

    print(
        f"Passed: {passed}"
    )

    print(
        f"Failed: {failed}"
    )

    print("-" * 72)

    if failed == 0:

        print(
            "✅ ALL DISCOVERY ENGINE TESTS PASSED"
        )

        return True

    print(
        "❌ DISCOVERY ENGINE TESTS FAILED"
    )

    if test_errors:

        print()

        for error in test_errors:

            print(
                f"   {error}"
            )

    return False


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Generate structured job discovery "
            "queries for the Job Intelligence Agent."
        )
    )

    parser.add_argument(
        "--version",
        action="version",
        version=VERSION,
    )

    parser.add_argument(
        "--tests",
        action="store_true",
        help="Run internal tests.",
    )

    parser.add_argument(
        "--groups",
        nargs="+",
        choices=sorted(
            ROLE_GROUPS.keys()
        ),
        help="Role groups to search.",
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        choices=DISCOVERY_SOURCES,
        help="Discovery sources.",
    )

    parser.add_argument(
        "--no-cities",
        action="store_true",
        help=(
            "Do not generate "
            "city-level queries."
        ),
    )

    parser.add_argument(
        "--no-global-remote",
        action="store_true",
        help=(
            "Do not generate "
            "global remote queries."
        ),
    )

    parser.add_argument(
        "--fresher-only",
        action="store_true",
        help=(
            "Add fresher-focused "
            "search variants."
        ),
    )

    parser.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help=(
            "Maximum queries to generate. "
            "0 = unlimited."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Write generated queries "
            "to JSON."
        ),
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help=(
            "Print query statistics."
        ),
    )

    parser.add_argument(
        "--preview",
        type=int,
        default=20,
        help=(
            "Number of queries to preview."
        ),
    )

    return parser


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = build_parser()

    args = parser.parse_args()

    # --------------------------------------------------------
    # Tests
    # --------------------------------------------------------

    if args.tests:

        return (
            0
            if run_tests()
            else 1
        )

    # --------------------------------------------------------
    # Generate
    # --------------------------------------------------------

    queries = generate_queries(
        groups=args.groups,
        sources=args.sources,
        include_cities=(
            not args.no_cities
        ),
        include_global_remote=(
            not args.no_global_remote
        ),
        fresher_only=args.fresher_only,
        max_queries=args.max_queries,
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    valid, errors = validate_queries(
        queries
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print("=" * 72)
    print("JOB INTELLIGENCE AGENT")
    print("DISCOVERY ENGINE")
    print("=" * 72)

    print(
        f"Version           : {VERSION}"
    )

    print(
        f"Project root      : {PROJECT_ROOT}"
    )

    print(
        f"Total queries     : {len(queries)}"
    )

    print(
        "Validation        : "
        f"{'✅ PASSED' if valid else '❌ FAILED'}"
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    print("-" * 72)

    stats = query_statistics(
        queries
    )

    print(
        "Fresher-focused   : "
        f"{stats['fresher_focused']}"
    )

    print(
        "Remote-focused    : "
        f"{stats['remote_focused']}"
    )

    print(
        "Unique locations  : "
        f"{stats['unique_locations']}"
    )

    # --------------------------------------------------------
    # Source statistics
    # --------------------------------------------------------

    print("-" * 72)

    print("By source:")

    for source, count in sorted(
        stats["by_source"].items()
    ):

        print(
            f"  {source:<15} {count}"
        )

    # --------------------------------------------------------
    # Scope statistics
    # --------------------------------------------------------

    print("-" * 72)

    print("By scope:")

    for scope, count in sorted(
        stats["by_scope"].items()
    ):

        print(
            f"  {scope:<22} {count}"
        )

    # --------------------------------------------------------
    # JSON statistics
    # --------------------------------------------------------

    if args.stats:

        print("-" * 72)

        print(
            json.dumps(
                stats,
                indent=2,
                ensure_ascii=False,
            )
        )

    # --------------------------------------------------------
    # Preview
    # --------------------------------------------------------

    if args.preview > 0:

        print("-" * 72)

        print(
            "Preview: first "
            f"{min(args.preview, len(queries))} "
            "queries"
        )

        for index, query in enumerate(
            queries[:args.preview],
            start=1,
        ):

            print()

            print(
                f"[{index}] "
                f"{query.role} | "
                f"{query.location} | "
                f"{query.scope}"
            )

            print(
                f"    Source   : "
                f"{query.source}"
            )

            print(
                f"    Query    : "
                f"{query.query}"
            )

            print(
                f"    Priority : "
                f"{query.priority}"
            )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    if args.output:

        save_json(
            queries,
            args.output,
        )

        print("-" * 72)

        print(
            f"Saved JSON: {args.output}"
        )

    # --------------------------------------------------------
    # Validation errors
    # --------------------------------------------------------

    if not valid:

        print("-" * 72)

        print(
            "Validation errors:"
        )

        for error in errors:

            print(
                f"  ❌ {error}"
            )

        return 1

    # --------------------------------------------------------
    # Ready
    # --------------------------------------------------------

    print("-" * 72)

    print(
        "✅ DISCOVERY ENGINE READY"
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )
