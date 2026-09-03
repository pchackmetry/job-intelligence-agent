"""
JOB INTELLIGENCE AGENT
======================

Verification / Job Correlator Engine

Version: 2.0.0

Purpose
-------
Correlate jobs discovered from third-party sources with an official
company careers page or public ATS posting.

IMPORTANT PIPELINE RULE

    Third-party discovery
            |
            v
       Job Correlator
            |
            v
    Official company / ATS
            |
            v
       Job Verifier
            |
            v
    Application URL validator
            |
            v
       VERIFIED JOB
            |
            v
        SQLite
            |
            v
        Telegram


DISCOVERY SOURCES
-----------------
LinkedIn
Indeed
Naukri
Glassdoor
Google Jobs
Other public job boards


FINAL APPLICATION URL RULE
--------------------------
Third-party URLs may be used for discovery.

Third-party URLs MUST NOT be sent to the user as the final
application URL.

Final application URLs must point to:
    - official company career pages
    - recognized ATS pages
    - official employer-hosted application pages


SAFETY
------
This module does NOT:
    - bypass CAPTCHA
    - bypass authentication
    - bypass anti-bot protections
    - bypass paywalls
    - submit applications
    - invent recruiter information
    - invent job deadlines
    - invent official domains
    - treat "Remote" as automatically worldwide
    - treat an uncertain correlation as verified


SUPPORTED PUBLIC ATS SOURCES
----------------------------
Greenhouse
Lever

The architecture is intentionally extensible for:
    Ashby
    Workday
    SmartRecruiters
    iCIMS
    SuccessFactors
    BambooHR
    Workable
    Jobvite
    Recruitee
    Teamtailor
    Pinpoint
    Rippling
    Personio


STATUS
------
VERIFIED
    Strong official evidence and verifier confirmation.

UNCERTAIN
    Official-looking candidate exists but evidence is insufficient.

NOT_FOUND
    No suitable official candidate found.

REJECTED
    Candidates were found but failed verification/safety rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time

from dataclasses import asdict, dataclass, field
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import (
    parse_qs,
    quote,
    urlencode,
    urlparse,
    urlunparse,
)
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


# ============================================================================
# VERSION / CONSTANTS
# ============================================================================

VERSION = "2.0.0"

DEFAULT_TIMEOUT = 15
MAX_BYTES = 4 * 1024 * 1024

USER_AGENT = (
    "JobIntelligenceAgent/2.0 "
    "(public-job-correlation)"
)


# ============================================================================
# THIRD-PARTY DISCOVERY SOURCES
# ============================================================================

THIRD_PARTY_DOMAINS = {
    "linkedin.com",
    "indeed.com",
    "naukri.com",
    "glassdoor.com",
    "foundit.in",
    "monster.com",
    "shine.com",
    "internshala.com",
    "cutshort.io",
    "wellfound.com",
    "ziprecruiter.com",
    "dice.com",
    "simplyhired.com",
    "jooble.org",
    "jobrapido.com",
    "adzuna.com",
    "careerbuilder.com",
    "talent.com",
    "grabjobs.co",
    "jora.com",
    "hirist.tech",
    "instahyre.com",
    "freshersworld.com",
    "fresherslive.com",
    "apna.co",
    "workindia.in",
}


# ============================================================================
# ATS DOMAINS
# ============================================================================

ATS_DOMAINS = {
    "greenhouse.io": "greenhouse",
    "boards.greenhouse.io": "greenhouse",
    "boards-api.greenhouse.io": "greenhouse",

    "lever.co": "lever",
    "jobs.lever.co": "lever",
    "api.lever.co": "lever",
    "jobs.eu.lever.co": "lever",
    "api.eu.lever.co": "lever",

    "ashbyhq.com": "ashby",
    "jobs.ashbyhq.com": "ashby",

    "myworkdayjobs.com": "workday",

    "smartrecruiters.com": "smartrecruiters",

    "icims.com": "icims",

    "successfactors.com": "successfactors",

    "bamboohr.com": "bamboohr",

    "workable.com": "workable",

    "jobvite.com": "jobvite",

    "recruitee.com": "recruitee",

    "teamtailor.com": "teamtailor",

    "pinpointhq.com": "pinpoint",

    "rippling.com": "rippling",

    "personio.com": "personio",
}


# ============================================================================
# TRACKING PARAMETERS
# ============================================================================

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",

    "gh_src",
    "gh_jid",

    "source",
    "src",
    "ref",
    "referrer",

    "trk",
    "trkcampaign",

    "lever-source",
    "lever_source",

    "fbclid",
    "gclid",
    "msclkid",

    "mc_cid",
    "mc_eid",
}


# ============================================================================
# CAREER URL PATTERNS
# ============================================================================

CAREER_PATH_PATTERNS = (
    "/careers",
    "/career",
    "/jobs",
    "/job",
    "/openings",
    "/positions",
    "/opportunities",
    "/work-with-us",
    "/join-us",
    "/join-our-team",
    "/vacancies",
    "/employment",
)


# ============================================================================
# REMOTE SIGNALS
# ============================================================================

REMOTE_POSITIVE_PATTERNS = (
    r"\bremote\b",
    r"\bfully remote\b",
    r"\bremote first\b",
    r"\bremote-first\b",
    r"\bdistributed\b",
    r"\bwork from home\b",
    r"\bwork-from-home\b",
)

REMOTE_NEGATIVE_PATTERNS = (
    r"\bon[- ]site\b",
    r"\bonsite\b",
    r"\bin[- ]office\b",
    r"\bhybrid\b",
    r"\bmust work from office\b",
    r"\bwork from office\b",
)


WORLDWIDE_PATTERNS = (
    r"\bworldwide\b",
    r"\bwork anywhere\b",
    r"\bwork from anywhere\b",
    r"\banywhere in the world\b",
    r"\bglobal remote\b",
    r"\bglobally remote\b",
    r"\bremote anywhere\b",
)


INDIA_REMOTE_PATTERNS = (
    r"\bremote from india\b",
    r"\bremote in india\b",
    r"\bindia remote\b",
    r"\bindia[- ]based remote\b",
    r"\bindia[- ]based employees\b",
    r"\bhire in india\b",
    r"\bcan work from india\b",
    r"\bworking from india\b",
)


FOREIGN_RESTRICTION_PATTERNS = (
    r"\bunited states only\b",
    r"\busa only\b",
    r"\bus only\b",
    r"\bmust be located in the united states\b",
    r"\bmust reside in the united states\b",
    r"\bmust reside in the us\b",
    r"\bmust be based in the united states\b",
    r"\bmust be based in the us\b",
    r"\bcanada only\b",
    r"\bmust reside in canada\b",
    r"\bmust be based in canada\b",
    r"\buk only\b",
    r"\bmust reside in the uk\b",
    r"\bmust be based in the uk\b",
    r"\beurope only\b",
    r"\beu only\b",
    r"\beu residents only\b",
)


# ============================================================================
# FRESHER SIGNALS
# ============================================================================

FRESHER_PATTERNS = (
    r"\bfreshers?\b",
    r"\bentry[- ]level\b",
    r"\bgraduate\b",
    r"\brecent graduate\b",
    r"\bnew graduate\b",
    r"\btrainee\b",
    r"\bjunior\b",
    r"\bassociate\b",
    r"\bapprentice\b",
    r"\bintern\b",
    r"\binternship\b",
    r"\bno experience required\b",
    r"\bwithout experience\b",
    r"\b0\s*[-–]\s*1\s*years?\b",
    r"\b0\s*[-–]\s*2\s*years?\b",
    r"\b0\s*years?\b",
)


# ============================================================================
# STALE / CLOSED SIGNALS
# ============================================================================

CLOSED_PATTERNS = (
    r"\bposition filled\b",
    r"\bposition has been filled\b",
    r"\bno longer accepting applications\b",
    r"\bjob is no longer available\b",
    r"\bjob has been closed\b",
    r"\bthis position is closed\b",
    r"\bthis job is closed\b",
    r"\brole has been filled\b",
)


# ============================================================================
# SCAM / SENSITIVE INFORMATION SIGNALS
# ============================================================================

SCAM_PATTERNS = (
    r"\bpay a fee\b",
    r"\bregistration fee\b",
    r"\bprocessing fee\b",
    r"\btraining fee\b",
    r"\bdeposit money\b",
    r"\bbuy equipment\b",
    r"\bgift card\b",
    r"\bcrypto\b",
    r"\bbitcoin\b",
    r"\bwire transfer\b",
    r"\bwestern union\b",
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DiscoveredJob:
    """
    Normalized job discovered from any source.
    """

    source: str
    source_url: str

    company: str
    title: str

    location: str = ""
    description: str = ""

    application_url: str = ""

    requisition_id: str = ""
    job_id: str = ""

    work_mode: str = ""
    experience_text: str = ""

    posted_at: str = ""
    deadline: str = ""

    employer_type: str = ""

    country: str = ""

    raw: Dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class OfficialCandidate:
    """
    Candidate official posting.
    """

    url: str
    source: str

    company: str = ""
    title: str = ""
    location: str = ""

    description: str = ""

    application_url: str = ""

    requisition_id: str = ""
    job_id: str = ""

    work_mode: str = ""
    country: str = ""

    posted_at: str = ""

    score: float = 0.0

    evidence: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )


@dataclass
class RemoteAssessment:
    status: str
    confidence: float

    evidence: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )


@dataclass
class CorrelationResult:
    status: str
    confidence: float

    discovered_job: Dict[str, Any]

    official_url: str = ""
    application_url: str = ""

    official_source: str = ""
    ats: str = ""

    company_match: float = 0.0
    title_match: float = 0.0
    location_match: float = 0.0
    requisition_match: float = 0.0

    remote_status: str = "UNKNOWN"

    fresher_friendly: bool = False

    evidence: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )

    candidates_checked: int = 0


@dataclass
class FetchResult:
    ok: bool

    status_code: int = 0

    url: str = ""

    content_type: str = ""

    body: str = ""

    error: str = ""


# ============================================================================
# HTTP FETCHER
# ============================================================================

class SafeRedirectHandler(
    HTTPRedirectHandler
):
    """
    Normal public redirects only.
    """

    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


class PublicFetcher:
    """
    Public HTTP GET client.

    No CAPTCHA bypass.
    No authentication.
    No anti-bot bypass.
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.timeout = timeout

        self.opener = build_opener(
            SafeRedirectHandler()
        )

    def get(
        self,
        url: str,
        accept: str = (
            "application/json,text/html,"
            "application/xhtml+xml;q=0.9,*/*;q=0.8"
        ),
    ) -> FetchResult:

        if not is_http_url(url):
            return FetchResult(
                ok=False,
                url=url,
                error="Not a HTTP/HTTPS URL",
            )

        request = Request(
            url=url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Accept-Language": (
                    "en-US,en;q=0.8"
                ),
            },
            method="GET",
        )

        try:
            with self.opener.open(
                request,
                timeout=self.timeout,
            ) as response:

                raw = response.read(
                    MAX_BYTES
                )

                content_type = (
                    response.headers.get(
                        "Content-Type",
                        "",
                    )
                    or ""
                )

                charset = (
                    response.headers.get_content_charset()
                    or "utf-8"
                )

                body = raw.decode(
                    charset,
                    errors="replace",
                )

                return FetchResult(
                    ok=True,
                    status_code=getattr(
                        response,
                        "status",
                        200,
                    ),
                    url=response.geturl(),
                    content_type=content_type,
                    body=body,
                )

        except HTTPError as exc:
            return FetchResult(
                ok=False,
                status_code=exc.code,
                url=url,
                error=f"HTTP {exc.code}",
            )

        except URLError as exc:
            return FetchResult(
                ok=False,
                url=url,
                error=(
                    "URL error: "
                    f"{exc.reason}"
                ),
            )

        except Exception as exc:
            return FetchResult(
                ok=False,
                url=url,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================

def normalize_text(
    value: Any,
) -> str:

    if value is None:
        return ""

    text = unescape(
        str(value)
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_company(
    value: Any,
) -> str:

    text = normalize_text(
        value
    ).lower()

    text = re.sub(
        r"\b("
        r"incorporated|inc|llc|ltd|limited|"
        r"corp|corporation|company|co|plc|"
        r"pvt|private"
        r")\b",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def normalize_title(
    value: Any,
) -> str:

    text = normalize_text(
        value
    ).lower()

    text = re.sub(
        r"\b(job|opening|position|vacancy)\b",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9+#/&.-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def normalize_location(
    value: Any,
) -> str:

    text = normalize_text(
        value
    ).lower()

    text = re.sub(
        r"[^a-z0-9,\-/ ]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def normalize_identifier(
    value: Any,
) -> str:

    text = normalize_text(
        value
    ).lower()

    return re.sub(
        r"[^a-z0-9]+",
        "",
        text,
    )


# ============================================================================
# TOKEN / SIMILARITY
# ============================================================================

def tokens(
    value: str,
) -> set[str]:

    return {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            value.lower(),
        )
        if len(token) >= 2
    }


def token_similarity(
    left: str,
    right: str,
) -> float:

    a = tokens(left)
    b = tokens(right)

    if not a or not b:
        return 0.0

    intersection = len(
        a & b
    )

    union = len(
        a | b
    )

    if union == 0:
        return 0.0

    return intersection / union


def company_similarity(
    discovered: str,
    official: str,
) -> float:

    a = normalize_company(
        discovered
    )

    b = normalize_company(
        official
    )

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a in b or b in a:
        return 0.90

    return token_similarity(
        a,
        b,
    )


def title_similarity(
    discovered: str,
    official: str,
) -> float:

    a = normalize_title(
        discovered
    )

    b = normalize_title(
        official
    )

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    similarity = token_similarity(
        a,
        b,
    )

    # Protect against unrelated titles sharing one generic word.
    if similarity < 0.40:
        return similarity

    return similarity


def location_similarity(
    discovered: str,
    official: str,
) -> float:

    a = normalize_location(
        discovered
    )

    b = normalize_location(
        official
    )

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a in b or b in a:
        return 0.90

    a_tokens = tokens(a)
    b_tokens = tokens(b)

    if (
        "remote" in a_tokens
        and "remote" in b_tokens
    ):
        return 1.0

    return token_similarity(
        a,
        b,
    )


def requisition_similarity(
    discovered: str,
    official: str,
) -> float:

    a = normalize_identifier(
        discovered
    )

    b = normalize_identifier(
        official
    )

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return 0.0


# ============================================================================
# URL FUNCTIONS
# ============================================================================

def is_http_url(
    url: str,
) -> bool:

    try:
        parsed = urlparse(
            url
        )

        return (
            parsed.scheme
            in {
                "http",
                "https",
            }
            and bool(
                parsed.netloc
            )
        )

    except Exception:
        return False


def hostname(
    url: str,
) -> str:

    try:
        return (
            urlparse(url)
            .hostname
            or ""
        ).lower()

    except Exception:
        return ""


def base_domain(
    url: str,
) -> str:

    host = hostname(
        url
    )

    if host.startswith(
        "www."
    ):
        host = host[4:]

    parts = host.split(
        "."
    )

    if len(parts) >= 2:
        return ".".join(
            parts[-2:]
        )

    return host


def domain_matches(
    url: str,
    domain: str,
) -> bool:

    host = hostname(
        url
    )

    return (
        host == domain
        or host.endswith(
            "." + domain
        )
    )


def classify_ats(
    url: str,
) -> str:

    host = hostname(
        url
    )

    for domain, ats in ATS_DOMAINS.items():

        if (
            host == domain
            or host.endswith(
                "." + domain
            )
        ):
            return ats

    return ""


def is_third_party_url(
    url: str,
) -> bool:

    host = hostname(
        url
    )

    for domain in THIRD_PARTY_DOMAINS:

        if (
            host == domain
            or host.endswith(
                "." + domain
            )
        ):
            return True

    return False


def clean_url(
    url: str,
) -> str:

    if not is_http_url(
        url
    ):
        return ""

    parsed = urlparse(
        url
    )

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    cleaned_query = {}

    for key, values in query.items():

        if key.lower() in TRACKING_PARAMS:
            continue

        cleaned_query[key] = values

    new_query = urlencode(
        cleaned_query,
        doseq=True,
    )

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            new_query,
            "",
        )
    )


def looks_like_career_url(
    url: str,
) -> bool:

    lower = url.lower()

    return any(
        pattern in lower
        for pattern in CAREER_PATH_PATTERNS
    )


def is_official_candidate_url(
    url: str,
    company: str,
) -> bool:

    if not is_http_url(
        url
    ):
        return False

    if is_third_party_url(
        url
    ):
        return False

    if classify_ats(
        url
    ):
        return True

    if looks_like_career_url(
        url
    ):
        return True

    company_tokens = tokens(
        normalize_company(
            company
        )
    )

    host_tokens = tokens(
        hostname(url).replace(
            ".",
            " ",
        )
    )

    return bool(
        company_tokens
        & host_tokens
    )


# ============================================================================
# FINAL APPLICATION URL SAFETY
# ============================================================================

def is_safe_final_application_url(
    url: str,
) -> bool:

    if not is_http_url(
        url
    ):
        return False

    if is_third_party_url(
        url
    ):
        return False

    if classify_ats(
        url
    ):
        return True

    if looks_like_career_url(
        url
    ):
        return True

    return False


# ============================================================================
# HTML HELPERS
# ============================================================================

def html_to_text(
    html: str,
) -> str:

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<noscript\b[^>]*>.*?</noscript>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    return normalize_text(
        text
    )


def extract_html_title(
    html: str,
) -> str:

    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        html,
        flags=re.I | re.S,
    )

    if not match:
        return ""

    return normalize_text(
        match.group(1)
    )


def extract_links(
    html: str,
    base_url: str,
) -> List[str]:

    links = []

    for match in re.finditer(
        r"""href\s*=\s*["']([^"']+)["']""",
        html,
        flags=re.I,
    ):

        href = unescape(
            match.group(1).strip()
        )

        if href.startswith(
            "/"
        ):

            parsed = urlparse(
                base_url
            )

            href = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    href,
                    "",
                    "",
                    "",
                )
            )

        elif href.startswith(
            "//"
        ):

            parsed = urlparse(
                base_url
            )

            href = (
                parsed.scheme
                + ":"
                + href
            )

        if is_http_url(
            href
        ):

            cleaned = clean_url(
                href
            )

            if cleaned:
                links.append(
                    cleaned
                )

    return list(
        dict.fromkeys(
            links
        )
    )


def extract_apply_links(
    html: str,
    base_url: str,
) -> List[str]:

    results = []

    for link in extract_links(
        html,
        base_url,
    ):

        lower = link.lower()

        if any(
            marker in lower
            for marker in (
                "/apply",
                "apply?",
                "/application",
                "candidate",
            )
        ):
            results.append(
                link
            )

    return list(
        dict.fromkeys(
            results
        )
    )


# ============================================================================
# REMOTE ELIGIBILITY
# ============================================================================

def search_patterns(
    text: str,
    patterns: Iterable[str],
) -> List[str]:

    matches = []

    for pattern in patterns:

        if re.search(
            pattern,
            text,
            flags=re.I,
        ):
            matches.append(
                pattern
            )

    return matches


def assess_remote(
    location: str,
    work_mode: str,
    description: str,
) -> RemoteAssessment:

    # IMPORTANT:
    # Location and explicit workplace metadata receive higher priority
    # than generic company-description text.

    location_text = normalize_text(
        location
    ).lower()

    work_mode_text = normalize_text(
        work_mode
    ).lower()

    # First: explicit non-remote metadata.
    if any(
        value in work_mode_text
        for value in (
            "on-site",
            "onsite",
            "hybrid",
        )
    ):
        return RemoteAssessment(
            status="NOT_REMOTE",
            confidence=0.98,
            evidence=[
                "Official workplace metadata says non-remote"
            ],
        )

    # Explicit remote metadata.
    explicit_remote = (
        "remote"
        in work_mode_text
    )

    india_matches = search_patterns(
        location_text,
        INDIA_REMOTE_PATTERNS,
    )

    worldwide_matches = search_patterns(
        location_text,
        WORLDWIDE_PATTERNS,
    )

    restricted_matches = search_patterns(
        location_text,
        FOREIGN_RESTRICTION_PATTERNS,
    )

    remote_matches = search_patterns(
        location_text,
        REMOTE_POSITIVE_PATTERNS,
    )

    nonremote_matches = search_patterns(
        location_text,
        REMOTE_NEGATIVE_PATTERNS,
    )

    if nonremote_matches:
        return RemoteAssessment(
            status="NOT_REMOTE",
            confidence=0.96,
            evidence=[
                "Location contains non-remote signal"
            ],
        )

    if restricted_matches:
        return RemoteAssessment(
            status="COUNTRY_RESTRICTED",
            confidence=0.96,
            evidence=[
                "Location contains country restriction"
            ],
        )

    if india_matches:
        return RemoteAssessment(
            status="INDIA_ELIGIBLE",
            confidence=0.98,
            evidence=[
                "Location explicitly permits remote work from India"
            ],
        )

    if worldwide_matches:
        return RemoteAssessment(
            status="WORLDWIDE",
            confidence=0.96,
            evidence=[
                "Location explicitly indicates worldwide/global remote"
            ],
        )

    if explicit_remote:
        return RemoteAssessment(
            status="UNKNOWN",
            confidence=0.70,
            evidence=[
                "Workplace metadata says remote"
            ],
            warnings=[
                "Remote eligibility from India is not established"
            ],
        )

    if remote_matches:
        return RemoteAssessment(
            status="UNKNOWN",
            confidence=0.60,
            evidence=[
                "Location contains remote signal"
            ],
            warnings=[
                "Remote eligibility from India is not established"
            ],
        )

    # Description-only signals are deliberately weak.
    description_text = normalize_text(
        description
    ).lower()

    if search_patterns(
        description_text,
        INDIA_REMOTE_PATTERNS,
    ):
        return RemoteAssessment(
            status="INDIA_ELIGIBLE",
            confidence=0.75,
            evidence=[
                "Description contains India remote eligibility signal"
            ],
            warnings=[
                "Eligibility should be confirmed from job-location metadata"
            ],
        )

    if search_patterns(
        description_text,
        WORLDWIDE_PATTERNS,
    ):
        return RemoteAssessment(
            status="WORLDWIDE",
            confidence=0.70,
            evidence=[
                "Description contains worldwide remote signal"
            ],
            warnings=[
                "Eligibility should be confirmed from job-location metadata"
            ],
        )

    return RemoteAssessment(
        status="UNKNOWN",
        confidence=0.30,
        warnings=[
            "Remote eligibility could not be established"
        ],
    )


# ============================================================================
# FRESHER DETECTION
# ============================================================================

def detect_fresher(
    title: str,
    description: str,
    experience_text: str,
) -> bool:

    combined = " ".join(
        [
            normalize_text(title),
            normalize_text(
                experience_text
            ),
            normalize_text(
                description
            ),
        ]
    ).lower()

    return bool(
        search_patterns(
            combined,
            FRESHER_PATTERNS,
        )
    )


# ============================================================================
# CLOSED DETECTION
# ============================================================================

def detect_closed(
    text: str,
) -> bool:

    return bool(
        search_patterns(
            normalize_text(
                text
            ).lower(),
            CLOSED_PATTERNS,
        )
    )


# ============================================================================
# SCAM DETECTION
# ============================================================================

def detect_scam_signals(
    text: str,
) -> List[str]:

    matches = []

    lower = normalize_text(
        text
    ).lower()

    for pattern in SCAM_PATTERNS:

        if re.search(
            pattern,
            lower,
            flags=re.I,
        ):
            matches.append(
                pattern
            )

    return matches


# ============================================================================
# GREENHOUSE
# ============================================================================

def greenhouse_board_token_from_url(
    url: str,
) -> str:

    parsed = urlparse(
        url
    )

    host = (
        parsed.hostname
        or ""
    ).lower()

    if host != (
        "boards.greenhouse.io"
    ):
        return ""

    parts = [
        part
        for part in parsed.path.split(
            "/"
        )
        if part
    ]

    if not parts:
        return ""

    if parts[0] in {
        "embed",
        "job_app",
    }:
        return ""

    return parts[0]


def greenhouse_api_url(
    board_token: str,
) -> str:

    return (
        "https://boards-api.greenhouse.io/"
        f"v1/boards/{quote(board_token)}/jobs"
        "?content=true"
    )


def greenhouse_candidates(
    job: DiscoveredJob,
    fetcher: PublicFetcher,
    board_token: str,
) -> List[OfficialCandidate]:

    if not board_token:
        return []

    result = fetcher.get(
        greenhouse_api_url(
            board_token
        ),
        accept=(
            "application/json"
        ),
    )

    if not result.ok:
        return []

    try:
        payload = json.loads(
            result.body
        )

    except json.JSONDecodeError:
        return []

    jobs = payload.get(
        "jobs",
        [],
    )

    if not isinstance(
        jobs,
        list,
    ):
        return []

    candidates = []

    for item in jobs:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = normalize_text(
            item.get(
                "title",
                "",
            )
        )

        location_obj = item.get(
            "location",
            {},
        )

        if isinstance(
            location_obj,
            dict,
        ):
            location = normalize_text(
                location_obj.get(
                    "name",
                    "",
                )
            )
        else:
            location = normalize_text(
                location_obj
            )

        description = normalize_text(
            item.get(
                "content",
                "",
            )
        )

        requisition_id = normalize_text(
            item.get(
                "requisition_id",
                "",
            )
        )

        job_id = normalize_text(
            item.get(
                "id",
                "",
            )
        )

        official_url = clean_url(
            normalize_text(
                item.get(
                    "absolute_url",
                    "",
                )
            )
        )

        if not official_url:
            continue

        score = preliminary_candidate_score(
            job=job,
            company=job.company,
            title=title,
            location=location,
            requisition_id=requisition_id,
            job_id=job_id,
            url=official_url,
        )

        evidence = [
            "Public Greenhouse posting found"
        ]

        if requisition_similarity(
            job.requisition_id,
            requisition_id,
        ) == 1.0:
            evidence.append(
                "Requisition ID matched"
            )

        if title_similarity(
            job.title,
            title,
        ) >= 0.85:
            evidence.append(
                "Title matched strongly"
            )

        if location_similarity(
            job.location,
            location,
        ) >= 0.80:
            evidence.append(
                "Location matched strongly"
            )

        candidates.append(
            OfficialCandidate(
                url=official_url,
                source="greenhouse",
                company=job.company,
                title=title,
                location=location,
                description=description,
                application_url=official_url,
                requisition_id=requisition_id,
                job_id=job_id,
                score=score,
                evidence=evidence,
            )
        )

    candidates.sort(
        key=lambda x: x.score,
        reverse=True,
    )

    return candidates


# ============================================================================
# LEVER
# ============================================================================

def lever_site_from_url(
    url: str,
) -> str:

    parsed = urlparse(
        url
    )

    host = (
        parsed.hostname
        or ""
    ).lower()

    if host not in {
        "jobs.lever.co",
        "jobs.eu.lever.co",
    }:
        return ""

    parts = [
        part
        for part in parsed.path.split(
            "/"
        )
        if part
    ]

    if not parts:
        return ""

    return parts[0]


def lever_api_url(
    site: str,
    eu: bool = False,
) -> str:

    base = (
        "https://api.eu.lever.co"
        if eu
        else
        "https://api.lever.co"
    )

    return (
        f"{base}/v0/postings/"
        f"{quote(site)}"
        "?mode=json"
    )


def lever_candidates(
    job: DiscoveredJob,
    fetcher: PublicFetcher,
    site: str,
    eu: bool = False,
) -> List[OfficialCandidate]:

    if not site:
        return []

    result = fetcher.get(
        lever_api_url(
            site,
            eu=eu,
        ),
        accept=(
            "application/json"
        ),
    )

    if not result.ok:
        return []

    try:
        payload = json.loads(
            result.body
        )

    except json.JSONDecodeError:
        return []

    if not isinstance(
        payload,
        list,
    ):
        return []

    candidates = []

    for item in payload:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = normalize_text(
            item.get(
                "text",
                "",
            )
        )

        categories = item.get(
            "categories",
            {},
        )

        if not isinstance(
            categories,
            dict,
        ):
            categories = {}

        location = normalize_text(
            categories.get(
                "location",
                "",
            )
        )

        description = normalize_text(
            item.get(
                "descriptionPlain",
                item.get(
                    "description",
                    "",
                ),
            )
        )

        requisition_id = normalize_text(
            item.get(
                "reqCode",
                "",
            )
        )

        if not requisition_id:

            codes = item.get(
                "requisitionCodes",
                [],
            )

            if isinstance(
                codes,
                list,
            ) and codes:

                requisition_id = normalize_text(
                    codes[0]
                )

        official_url = clean_url(
            normalize_text(
                item.get(
                    "hostedUrl",
                    "",
                )
            )
        )

        application_url = clean_url(
            normalize_text(
                item.get(
                    "applyUrl",
                    "",
                )
            )
        )

        job_id = normalize_text(
            item.get(
                "id",
                "",
            )
        )

        workplace_type = normalize_text(
            item.get(
                "workplaceType",
                "",
            )
        )

        country = normalize_text(
            item.get(
                "country",
                "",
            )
        )

        created_at = item.get(
            "createdAt",
            "",
        )

        if not official_url:
            continue

        score = preliminary_candidate_score(
            job=job,
            company=job.company,
            title=title,
            location=location,
            requisition_id=requisition_id,
            job_id=job_id,
            url=official_url,
        )

        evidence = [
            "Public Lever posting found"
        ]

        if requisition_similarity(
            job.requisition_id,
            requisition_id,
        ) == 1.0:
            evidence.append(
                "Requisition ID matched"
            )

        if title_similarity(
            job.title,
            title,
        ) >= 0.85:
            evidence.append(
                "Title matched strongly"
            )

        if location_similarity(
            job.location,
            location,
        ) >= 0.80:
            evidence.append(
                "Location matched strongly"
            )

        if workplace_type:
            evidence.append(
                "Lever workplace type available"
            )

        if country:
            evidence.append(
                "Lever country metadata available"
            )

        candidates.append(
            OfficialCandidate(
                url=official_url,
                source="lever",
                company=job.company,
                title=title,
                location=location,
                description=description,
                application_url=application_url,
                requisition_id=requisition_id,
                job_id=job_id,
                work_mode=workplace_type,
                country=country,
                posted_at=(
                    str(created_at)
                    if created_at
                    else ""
                ),
                score=score,
                evidence=evidence,
            )
        )

    candidates.sort(
        key=lambda x: x.score,
        reverse=True,
    )

    return candidates


# ============================================================================
# CANDIDATE SCORING
# ============================================================================

def preliminary_candidate_score(
    job: DiscoveredJob,
    company: str,
    title: str,
    location: str,
    requisition_id: str,
    job_id: str,
    url: str,
) -> float:

    company_score = company_similarity(
        job.company,
        company,
    )

    title_score = title_similarity(
        job.title,
        title,
    )

    location_score = location_similarity(
        job.location,
        location,
    )

    requisition_score = requisition_similarity(
        job.requisition_id,
        requisition_id,
    )

    score = 0.0

    score += (
        company_score * 30
    )

    score += (
        title_score * 35
    )

    score += (
        location_score * 20
    )

    score += (
        requisition_score * 15
    )

    # Exact job ID is very strong evidence.
    if (
        job.job_id
        and job_id
        and normalize_identifier(
            job.job_id
        )
        == normalize_identifier(
            job_id
        )
    ):
        score += 20

    # Official ATS evidence.
    if classify_ats(
        url
    ):
        score += 5

    elif looks_like_career_url(
        url
    ):
        score += 3

    return round(
        min(
            score,
            100.0,
        ),
        2,
    )


# ============================================================================
# CANDIDATE DEDUPLICATION
# ============================================================================

def deduplicate_candidates(
    candidates: Sequence[OfficialCandidate],
) -> List[OfficialCandidate]:

    unique: Dict[
        str,
        OfficialCandidate,
    ] = {}

    for candidate in candidates:

        key = clean_url(
            candidate.url
        )

        if not key:
            continue

        existing = unique.get(
            key
        )

        if (
            existing is None
            or candidate.score
            > existing.score
        ):
            unique[key] = candidate

    return sorted(
        unique.values(),
        key=lambda x: (
            x.score,
            len(x.evidence),
        ),
        reverse=True,
    )


# ============================================================================
# VERIFIER INTEGRATION
# ============================================================================

def load_job_verifier():
    """
    Import the existing job_verifier.py.

    This supports running the file:
        python verification/job_correlator.py

    as well as importing it as a package.
    """

    try:

        from job_verifier import (
            JobVerifier,
        )

        return JobVerifier

    except ImportError:

        from verification.job_verifier import (
            JobVerifier,
        )

        return JobVerifier


def run_job_verifier(
    job: DiscoveredJob,
    candidate: OfficialCandidate,
    timeout: int,
) -> Optional[Dict[str, Any]]:

    try:

        JobVerifier = (
            load_job_verifier()
        )

    except Exception:
        return None

    try:

        verifier = JobVerifier(
            timeout=timeout
        )

    except TypeError:

        try:
            verifier = JobVerifier()

        except Exception:
            return None

    verification_kwargs = {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "description": job.description,
        "source_url": job.source_url,
        "official_url": candidate.url,
        "application_url": (
            candidate.application_url
        ),
        "requisition_id": (
            candidate.requisition_id
            or job.requisition_id
        ),
    }

    # Preferred API.
    try:

        result = verifier.verify(
            **verification_kwargs
        )

        return result_to_dict(
            result
        )

    except TypeError:
        pass

    except Exception:
        return None

    # Compatibility fallback.
    try:

        result = verifier.verify(
            company=job.company,
            title=job.title,
            location=job.location,
            source_url=job.source_url,
            official_url=candidate.url,
        )

        return result_to_dict(
            result
        )

    except Exception:
        return None


def result_to_dict(
    result: Any,
) -> Optional[Dict[str, Any]]:

    if result is None:
        return None

    if isinstance(
        result,
        dict,
    ):
        return result

    if hasattr(
        result,
        "__dict__",
    ):
        return dict(
            result.__dict__
        )

    return None


# ============================================================================
# OFFICIAL PAGE ENRICHMENT
# ============================================================================

def enrich_candidate_from_page(
    candidate: OfficialCandidate,
    fetcher: PublicFetcher,
) -> OfficialCandidate:

    result = fetcher.get(
        candidate.url,
        accept=(
            "text/html,"
            "application/xhtml+xml;q=0.9,*/*;q=0.8"
        ),
    )

    if not result.ok:
        candidate.warnings.append(
            "Official page could not be fetched"
        )
        return candidate

    final_url = clean_url(
        result.url
    )

    if final_url:
        candidate.url = final_url

    page_text = html_to_text(
        result.body
    )

    page_title = extract_html_title(
        result.body
    )

    # Only fill missing fields.
    if not candidate.title:
        candidate.title = page_title

    if not candidate.description:
        candidate.description = page_text

    # Find official apply links.
    if not candidate.application_url:

        apply_links = extract_apply_links(
            result.body,
            candidate.url,
        )

        for link in apply_links:

            if is_safe_final_application_url(
                link
            ):
                candidate.application_url = (
                    link
                )
                candidate.evidence.append(
                    "Official apply link found on page"
                )
                break

    # Closed posting.
    if detect_closed(
        page_text
    ):
        candidate.warnings.append(
            "Official page contains closed-position signal"
        )

    # Scam signals.
    scam_signals = detect_scam_signals(
        page_text
    )

    if scam_signals:
        candidate.warnings.append(
            "Potential scam signal found"
        )

    return candidate


# ============================================================================
# FINGERPRINT
# ============================================================================

def job_fingerprint(
    job: DiscoveredJob,
) -> str:

    normalized = "|".join(
        [
            normalize_company(
                job.company
            ),
            normalize_title(
                job.title
            ),
            normalize_location(
                job.location
            ),
            normalize_identifier(
                job.requisition_id
            ),
            clean_url(
                job.application_url
            ),
        ]
    )

    return hashlib.sha256(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================================
# CORRELATOR
# ============================================================================

class JobCorrelator:

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        min_candidate_score: float = 60.0,
        max_candidates_to_verify: int = 5,
    ):

        self.timeout = timeout

        self.min_candidate_score = (
            min_candidate_score
        )

        self.max_candidates_to_verify = (
            max_candidates_to_verify
        )

        self.fetcher = PublicFetcher(
            timeout=timeout
        )

    # ------------------------------------------------------------------------
    # Candidate collection
    # ------------------------------------------------------------------------

    def collect_candidates(
        self,
        job: DiscoveredJob,
        official_urls: Optional[
            Sequence[str]
        ] = None,
        greenhouse_boards: Optional[
            Sequence[str]
        ] = None,
        lever_sites: Optional[
            Sequence[str]
        ] = None,
    ) -> List[OfficialCandidate]:

        candidates = []

        # --------------------------------------------------------------------
        # Explicit official URLs
        # --------------------------------------------------------------------

        for url in (
            official_urls
            or []
        ):

            cleaned = clean_url(
                url
            )

            if not cleaned:
                continue

            if not is_official_candidate_url(
                cleaned,
                job.company,
            ):
                continue

            candidates.append(
                OfficialCandidate(
                    url=cleaned,
                    source="explicit_official",
                    score=55.0,
                    evidence=[
                        "Official URL supplied explicitly"
                    ],
                )
            )

        # --------------------------------------------------------------------
        # Greenhouse
        # --------------------------------------------------------------------

        greenhouse_boards_to_check = list(
            greenhouse_boards
            or []
        )

        detected_greenhouse = (
            greenhouse_board_token_from_url(
                job.source_url
            )
        )

        if detected_greenhouse:

            greenhouse_boards_to_check.insert(
                0,
                detected_greenhouse,
            )

        seen_greenhouse = set()

        for board in (
            greenhouse_boards_to_check
        ):

            board = normalize_text(
                board
            ).strip("/")

            if not board:
                continue

            if board in seen_greenhouse:
                continue

            seen_greenhouse.add(
                board
            )

            candidates.extend(
                greenhouse_candidates(
                    job=job,
                    fetcher=self.fetcher,
                    board_token=board,
                )
            )

        # --------------------------------------------------------------------
        # Lever
        # --------------------------------------------------------------------

        lever_sites_to_check = list(
            lever_sites
            or []
        )

        detected_lever = (
            lever_site_from_url(
                job.source_url
            )
        )

        if detected_lever:

            lever_sites_to_check.insert(
                0,
                detected_lever,
            )

        seen_lever = set()

        for site in (
            lever_sites_to_check
        ):

            site = normalize_text(
                site
            ).strip("/")

            if not site:
                continue

            if site in seen_lever:
                continue

            seen_lever.add(
                site
            )

            # Global endpoint.
            candidates.extend(
                lever_candidates(
                    job=job,
                    fetcher=self.fetcher,
                    site=site,
                    eu=False,
                )
            )

            # EU endpoint can contain the same employer's EU postings.
            candidates.extend(
                lever_candidates(
                    job=job,
                    fetcher=self.fetcher,
                    site=site,
                    eu=True,
                )
            )

        return deduplicate_candidates(
            candidates
        )

    # ------------------------------------------------------------------------
    # Main correlation
    # ------------------------------------------------------------------------

    def correlate(
        self,
        job: DiscoveredJob,
        official_urls: Optional[
            Sequence[str]
        ] = None,
        greenhouse_boards: Optional[
            Sequence[str]
        ] = None,
        lever_sites: Optional[
            Sequence[str]
        ] = None,
        run_verifier: bool = True,
    ) -> CorrelationResult:

        candidates = self.collect_candidates(
            job=job,
            official_urls=official_urls,
            greenhouse_boards=greenhouse_boards,
            lever_sites=lever_sites,
        )

        if not candidates:

            return CorrelationResult(
                status="NOT_FOUND",
                confidence=0.0,
                discovered_job=asdict(
                    job
                ),
                warnings=[
                    "No official candidate was found"
                ],
            )

        best_uncertain = None

        checked = 0

        # Only verify strongest candidates.
        candidates_to_check = [
            candidate
            for candidate in candidates
            if (
                candidate.score
                >= self.min_candidate_score
            )
        ][
            : self.max_candidates_to_verify
        ]

        for candidate in (
            candidates_to_check
        ):

            checked += 1

            # ---------------------------------------------------------------
            # Enrich official page
            # ---------------------------------------------------------------

            candidate = (
                enrich_candidate_from_page(
                    candidate,
                    self.fetcher,
                )
            )

            # ---------------------------------------------------------------
            # Matching metrics
            # ---------------------------------------------------------------

            company_match = (
                company_similarity(
                    job.company,
                    candidate.company
                    or job.company,
                )
            )

            title_match = (
                title_similarity(
                    job.title,
                    candidate.title,
                )
            )

            location_match = (
                location_similarity(
                    job.location,
                    candidate.location,
                )
            )

            requisition_match = (
                requisition_similarity(
                    job.requisition_id,
                    candidate.requisition_id,
                )
            )

            # ---------------------------------------------------------------
            # Remote assessment
            # ---------------------------------------------------------------

            remote_assessment = (
                assess_remote(
                    location=(
                        candidate.location
                        or job.location
                    ),
                    work_mode=(
                        candidate.work_mode
                        or job.work_mode
                    ),
                    description=(
                        candidate.description
                        or job.description
                    ),
                )
            )

            # ---------------------------------------------------------------
            # Fresher
            # ---------------------------------------------------------------

            fresher = detect_fresher(
                title=candidate.title
                or job.title,
                description=(
                    candidate.description
                    or job.description
                ),
                experience_text=(
                    job.experience_text
                ),
            )

            # ---------------------------------------------------------------
            # Closed / scam checks
            # ---------------------------------------------------------------

            closed = detect_closed(
                " ".join(
                    [
                        candidate.title,
                        candidate.description,
                    ]
                )
            )

            scam_signals = detect_scam_signals(
                candidate.description
            )

            # ---------------------------------------------------------------
            # Build correlation score
            # ---------------------------------------------------------------

            correlation_score = (
                company_match * 30
                + title_match * 35
                + location_match * 15
                + requisition_match * 20
            )

            # Exact requisition is powerful.
            if requisition_match == 1.0:
                correlation_score += 10

            # Strong ATS evidence.
            if classify_ats(
                candidate.url
            ):
                correlation_score += 5

            correlation_score = round(
                min(
                    correlation_score,
                    100.0,
                ),
                2,
            )

            evidence = list(
                candidate.evidence
            )

            warnings = list(
                candidate.warnings
            )

            if company_match >= 0.90:
                evidence.append(
                    "Company identity matched"
                )

            if title_match >= 0.85:
                evidence.append(
                    "Job title matched strongly"
                )

            if location_match >= 0.80:
                evidence.append(
                    "Job location matched"
                )

            if requisition_match == 1.0:
                evidence.append(
                    "Requisition ID matched exactly"
                )

            evidence.extend(
                remote_assessment.evidence
            )

            warnings.extend(
                remote_assessment.warnings
            )

            if fresher:
                evidence.append(
                    "Fresher/entry-level signal detected"
                )

            if closed:
                warnings.append(
                    "Official page appears closed"
                )

            if scam_signals:
                warnings.append(
                    "Potential scam signals detected"
                )

            # ---------------------------------------------------------------
            # Hard safety gates
            # ---------------------------------------------------------------

            if is_third_party_url(
                candidate.url
            ):
                warnings.append(
                    "Candidate URL is third-party"
                )
                continue

            if closed:
                continue

            if scam_signals:
                continue

            # ---------------------------------------------------------------
            # Run existing JobVerifier
            # ---------------------------------------------------------------

            verifier_result = None

            if run_verifier:

                verifier_result = (
                    run_job_verifier(
                        job=job,
                        candidate=candidate,
                        timeout=self.timeout,
                    )
                )

            # ---------------------------------------------------------------
            # VERIFIED
            # ---------------------------------------------------------------

            if verifier_result:

                verifier_status = str(
                    verifier_result.get(
                        "status",
                        "",
                    )
                ).upper()

                verifier_confidence = float(
                    verifier_result.get(
                        "confidence",
                        0,
                    )
                    or 0
                )

                verifier_application_url = (
                    verifier_result.get(
                        "application_url",
                        "",
                    )
                    or candidate.application_url
                )

                verifier_official_url = (
                    verifier_result.get(
                        "official_url",
                        "",
                    )
                    or candidate.url
                )

                if (
                    verifier_status
                    == "VERIFIED"
                ):

                    if (
                        is_safe_final_application_url(
                            verifier_application_url
                        )
                    ):

                        final_confidence = round(
                            min(
                                max(
                                    verifier_confidence,
                                    correlation_score,
                                ),
                                100.0,
                            ),
                            2,
                        )

                        return CorrelationResult(
                            status="VERIFIED",
                            confidence=final_confidence,
                            discovered_job=asdict(
                                job
                            ),
                            official_url=(
                                verifier_official_url
                            ),
                            application_url=(
                                verifier_application_url
                            ),
                            official_source=(
                                candidate.source
                            ),
                            ats=classify_ats(
                                verifier_official_url
                            ),
                            company_match=(
                                round(
                                    company_match * 100,
                                    2,
                                )
                            ),
                            title_match=(
                                round(
                                    title_match * 100,
                                    2,
                                )
                            ),
                            location_match=(
                                round(
                                    location_match * 100,
                                    2,
                                )
                            ),
                            requisition_match=(
                                round(
                                    requisition_match * 100,
                                    2,
                                )
                            ),
                            remote_status=(
                                remote_assessment.status
                            ),
                            fresher_friendly=fresher,
                            evidence=evidence
                            + [
                                "JobVerifier returned VERIFIED",
                            ],
                            warnings=warnings,
                            candidates_checked=checked,
                        )

                # -----------------------------------------------------------
                # UNCERTAIN
                # -----------------------------------------------------------

                if (
                    verifier_status
                    == "UNCERTAIN"
                ):

                    uncertainty_score = max(
                        correlation_score,
                        verifier_confidence,
                    )

                    if (
                        best_uncertain
                        is None
                        or uncertainty_score
                        > best_uncertain[
                            "score"
                        ]
                    ):

                        best_uncertain = {
                            "candidate": candidate,
                            "score": uncertainty_score,
                            "evidence": evidence,
                            "warnings": warnings,
                            "remote": remote_assessment,
                            "fresher": fresher,
                            "company_match": company_match,
                            "title_match": title_match,
                            "location_match": location_match,
                            "requisition_match": requisition_match,
                        }

                    continue

                # REJECTED
                if (
                    verifier_status
                    == "REJECTED"
                ):
                    continue

            # ---------------------------------------------------------------
            # Structural fallback
            # ---------------------------------------------------------------
            #
            # IMPORTANT:
            # Structural evidence NEVER becomes VERIFIED.
            #
            # It can only create an UNCERTAIN result.
            # ---------------------------------------------------------------

            final_candidate_url = (
                candidate.application_url
                or candidate.url
            )

            if (
                correlation_score >= 88.0
                and is_safe_final_application_url(
                    final_candidate_url
                )
            ):

                if (
                    best_uncertain
                    is None
                    or correlation_score
                    > best_uncertain[
                        "score"
                    ]
                ):

                    best_uncertain = {
                        "candidate": candidate,
                        "score": correlation_score,
                        "evidence": evidence,
                        "warnings": warnings
                        + [
                            "Structural correlation only"
                        ],
                        "remote": remote_assessment,
                        "fresher": fresher,
                        "company_match": company_match,
                        "title_match": title_match,
                        "location_match": location_match,
                        "requisition_match": requisition_match,
                    }

        # ====================================================================
        # BEST UNCERTAIN
        # ====================================================================

        if best_uncertain:

            candidate = (
                best_uncertain[
                    "candidate"
                ]
            )

            application_url = (
                candidate.application_url
            )

            if not is_safe_final_application_url(
                application_url
            ):
                application_url = ""

            return CorrelationResult(
                status="UNCERTAIN",
                confidence=round(
                    best_uncertain[
                        "score"
                    ],
                    2,
                ),
                discovered_job=asdict(
                    job
                ),
                official_url=candidate.url,
                application_url=application_url,
                official_source=candidate.source,
                ats=classify_ats(
                    candidate.url
                ),
                company_match=round(
                    best_uncertain[
                        "company_match"
                    ] * 100,
                    2,
                ),
                title_match=round(
                    best_uncertain[
                        "title_match"
                    ] * 100,
                    2,
                ),
                location_match=round(
                    best_uncertain[
                        "location_match"
                    ] * 100,
                    2,
                ),
                requisition_match=round(
                    best_uncertain[
                        "requisition_match"
                    ] * 100,
                    2,
                ),
                remote_status=(
                    best_uncertain[
                        "remote"
                    ].status
                ),
                fresher_friendly=(
                    best_uncertain[
                        "fresher"
                    ]
                ),
                evidence=best_uncertain[
                    "evidence"
                ],
                warnings=best_uncertain[
                    "warnings"
                ]
                + [
                    "Do not send as VERIFIED Telegram alert"
                ],
                candidates_checked=checked,
            )

        # ====================================================================
        # NOTHING PASSED
        # ====================================================================

        return CorrelationResult(
            status="REJECTED",
            confidence=0.0,
            discovered_job=asdict(
                job
            ),
            warnings=[
                "No official candidate passed correlation and verification"
            ],
            candidates_checked=checked,
        )


# ============================================================================
# JSON INPUT
# ============================================================================

def load_job_json(
    path: str,
) -> DiscoveredJob:

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as handle:

        data = json.load(
            handle
        )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "JSON must contain an object"
        )

    return DiscoveredJob(
        source=normalize_text(
            data.get(
                "source",
                "",
            )
        ),
        source_url=normalize_text(
            data.get(
                "source_url",
                data.get(
                    "sourceUrl",
                    "",
                ),
            )
        ),
        company=normalize_text(
            data.get(
                "company",
                "",
            )
        ),
        title=normalize_text(
            data.get(
                "title",
                "",
            )
        ),
        location=normalize_text(
            data.get(
                "location",
                "",
            )
        ),
        description=normalize_text(
            data.get(
                "description",
                "",
            )
        ),
        application_url=normalize_text(
            data.get(
                "application_url",
                data.get(
                    "applicationUrl",
                    "",
                ),
            )
        ),
        requisition_id=normalize_text(
            data.get(
                "requisition_id",
                data.get(
                    "requisitionId",
                    "",
                ),
            )
        ),
        job_id=normalize_text(
            data.get(
                "job_id",
                data.get(
                    "jobId",
                    "",
                ),
            )
        ),
        work_mode=normalize_text(
            data.get(
                "work_mode",
                data.get(
                    "workMode",
                    "",
                ),
            )
        ),
        experience_text=normalize_text(
            data.get(
                "experience_text",
                data.get(
                    "experienceText",
                    "",
                ),
            )
        ),
        posted_at=normalize_text(
            data.get(
                "posted_at",
                data.get(
                    "postedAt",
                    "",
                ),
            )
        ),
        deadline=normalize_text(
            data.get(
                "deadline",
                "",
            )
        ),
        employer_type=normalize_text(
            data.get(
                "employer_type",
                data.get(
                    "employerType",
                    "",
                ),
            )
        ),
        country=normalize_text(
            data.get(
                "country",
                "",
            )
        ),
        raw=(
            data.get(
                "raw",
                {},
            )
            if isinstance(
                data.get(
                    "raw",
                    {},
                ),
                dict,
            )
            else {}
        ),
    )


# ============================================================================
# TESTS
# ============================================================================

def run_tests() -> bool:

    passed = 0
    failed = 0

    def check(
        name: str,
        condition: bool,
    ):

        nonlocal passed
        nonlocal failed

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

    print(
        "=" * 76
    )

    print(
        "JOB CORRELATOR TEST SUITE"
    )

    print(
        "=" * 76
    )

    print(
        f"Version: {VERSION}"
    )

    print()

    # ------------------------------------------------------------------------
    # URL
    # ------------------------------------------------------------------------

    check(
        "HTTP URL accepted",
        is_http_url(
            "https://example.com/jobs/123"
        ),
    )

    check(
        "Invalid URL rejected",
        not is_http_url(
            "not-a-url"
        ),
    )

    check(
        "Greenhouse recognized",
        classify_ats(
            "https://boards.greenhouse.io/example/jobs/123"
        )
        == "greenhouse",
    )

    check(
        "Lever recognized",
        classify_ats(
            "https://jobs.lever.co/example/123"
        )
        == "lever",
    )

    check(
        "Workday recognized",
        classify_ats(
            "https://example.wd1.myworkdayjobs.com/en-US/jobs/123"
        )
        == "workday",
    )

    check(
        "LinkedIn is discovery source",
        is_third_party_url(
            "https://www.linkedin.com/jobs/view/123"
        ),
    )

    check(
        "Indeed is discovery source",
        is_third_party_url(
            "https://www.indeed.com/viewjob?jk=123"
        ),
    )

    check(
        "Third-party URL cannot be final application",
        not is_safe_final_application_url(
            "https://www.linkedin.com/jobs/view/123"
        ),
    )

    # ------------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------------

    check(
        "Company normalization",
        normalize_company(
            "Example Technologies Pvt Ltd"
        )
        == "example technologies",
    )

    check(
        "Identifier normalization",
        normalize_identifier(
            "REQ-123 / ABC"
        )
        == "req123abc",
    )

    # ------------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------------

    check(
        "Exact company match",
        company_similarity(
            "Airbnb",
            "Airbnb",
        )
        == 1.0,
    )

    check(
        "Exact title match",
        title_similarity(
            "Cybersecurity Analyst",
            "Cybersecurity Analyst",
        )
        == 1.0,
    )

    check(
        "Exact location match",
        location_similarity(
            "Hyderabad, India",
            "Hyderabad, India",
        )
        == 1.0,
    )

    check(
        "Exact requisition match",
        requisition_similarity(
            "REQ-123",
            "REQ-123",
        )
        == 1.0,
    )

    check(
        "Different titles are not exact",
        title_similarity(
            "Security Analyst",
            "Marketing Manager",
        )
        < 0.50,
    )

    # ------------------------------------------------------------------------
    # Remote
    # ------------------------------------------------------------------------

    remote_india = assess_remote(
        location="Remote from India",
        work_mode="remote",
        description="Work remotely from India.",
    )

    check(
        "India remote detected",
        remote_india.status
        == "INDIA_ELIGIBLE",
    )

    worldwide = assess_remote(
        location="Worldwide Remote",
        work_mode="remote",
        description="Work anywhere.",
    )

    check(
        "Worldwide remote detected",
        worldwide.status
        == "WORLDWIDE",
    )

    restricted = assess_remote(
        location="Remote - United States only",
        work_mode="remote",
        description="Must reside in the United States.",
    )

    check(
        "Country restricted remote detected",
        restricted.status
        == "COUNTRY_RESTRICTED",
    )

    unknown_remote = assess_remote(
        location="Remote",
        work_mode="remote",
        description="Remote position.",
    )

    check(
        "Generic remote remains unknown",
        unknown_remote.status
        == "UNKNOWN",
    )

    hybrid = assess_remote(
        location="Bangalore",
        work_mode="hybrid",
        description="Hybrid role.",
    )

    check(
        "Hybrid rejected as non-remote",
        hybrid.status
        == "NOT_REMOTE",
    )

    # ------------------------------------------------------------------------
    # Fresher
    # ------------------------------------------------------------------------

    check(
        "Fresher detected",
        detect_fresher(
            "Junior Security Analyst",
            "Entry-level position.",
            "",
        ),
    )

    check(
        "Experienced role not automatically fresher",
        not detect_fresher(
            "Senior Security Architect",
            "5+ years experience required.",
            "5+ years",
        ),
    )

    # ------------------------------------------------------------------------
    # Closed
    # ------------------------------------------------------------------------

    check(
        "Closed posting detected",
        detect_closed(
            "This position is no longer accepting applications."
        ),
    )

    check(
        "Open posting not closed",
        not detect_closed(
            "Applications are currently open."
        ),
    )

    # ------------------------------------------------------------------------
    # Scam
    # ------------------------------------------------------------------------

    check(
        "Fee scam signal detected",
        bool(
            detect_scam_signals(
                "Pay a registration fee to continue."
            )
        ),
    )

    check(
        "Normal job description no scam",
        not detect_scam_signals(
            "Apply through our official careers page."
        ),
    )

    # ------------------------------------------------------------------------
    # Greenhouse
    # ------------------------------------------------------------------------

    check(
        "Greenhouse board extracted",
        greenhouse_board_token_from_url(
            "https://boards.greenhouse.io/airbnb"
        )
        == "airbnb",
    )

    check(
        "Greenhouse job board extracted",
        greenhouse_board_token_from_url(
            "https://boards.greenhouse.io/airbnb/jobs/12345"
        )
        == "airbnb",
    )

    # ------------------------------------------------------------------------
    # Lever
    # ------------------------------------------------------------------------

    check(
        "Lever site extracted",
        lever_site_from_url(
            "https://jobs.lever.co/example/abc"
        )
        == "example",
    )

    # ------------------------------------------------------------------------
    # Career URL
    # ------------------------------------------------------------------------

    check(
        "Career URL recognized",
        looks_like_career_url(
            "https://example.com/careers/security"
        ),
    )

    check(
        "ATS URL recognized as official candidate",
        is_official_candidate_url(
            "https://jobs.lever.co/example/abc",
            "Example",
        ),
    )

    check(
        "LinkedIn rejected as official candidate",
        not is_official_candidate_url(
            "https://linkedin.com/jobs/view/123",
            "Example",
        ),
    )

    # ------------------------------------------------------------------------
    # Candidate score
    # ------------------------------------------------------------------------

    test_job = DiscoveredJob(
        source="linkedin",
        source_url=(
            "https://linkedin.com/jobs/view/123"
        ),
        company="Example",
        title="Cybersecurity Analyst",
        location="Hyderabad, India",
        requisition_id="REQ-123",
        job_id="abc",
    )

    candidate_score = (
        preliminary_candidate_score(
            job=test_job,
            company="Example",
            title="Cybersecurity Analyst",
            location="Hyderabad, India",
            requisition_id="REQ-123",
            job_id="abc",
            url=(
                "https://jobs.lever.co/"
                "example/abc"
            ),
        )
    )

    check(
        "Strong candidate scores highly",
        candidate_score >= 85.0,
    )

    # ------------------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------------------

    fingerprint_one = (
        job_fingerprint(
            test_job
        )
    )

    fingerprint_two = (
        job_fingerprint(
            test_job
        )
    )

    check(
        "Fingerprint deterministic",
        fingerprint_one
        == fingerprint_two
        and len(
            fingerprint_one
        )
        == 64,
    )

    # ------------------------------------------------------------------------
    # Final application safety
    # ------------------------------------------------------------------------

    check(
        "Lever apply URL accepted",
        is_safe_final_application_url(
            "https://jobs.lever.co/example/abc/apply"
        ),
    )

    check(
        "Greenhouse job URL accepted",
        is_safe_final_application_url(
            "https://boards.greenhouse.io/example/jobs/123"
        ),
    )

    check(
        "Naukri application rejected",
        not is_safe_final_application_url(
            "https://www.naukri.com/job-listings/123"
        ),
    )

    # ------------------------------------------------------------------------
    # Candidate deduplication
    # ------------------------------------------------------------------------

    duplicate_candidates = [
        OfficialCandidate(
            url="https://jobs.lever.co/example/abc",
            source="lever",
            score=80,
        ),
        OfficialCandidate(
            url="https://jobs.lever.co/example/abc",
            source="lever",
            score=90,
        ),
    ]

    deduped = deduplicate_candidates(
        duplicate_candidates
    )

    check(
        "Duplicate official URLs removed",
        len(deduped) == 1
        and deduped[0].score == 90,
    )

    # ------------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------------

    print()

    print(
        "-" * 76
    )

    print(
        f"Passed: {passed}"
    )

    print(
        f"Failed: {failed}"
    )

    print(
        "-" * 76
    )

    if failed == 0:

        print(
            "✅ ALL CORRELATOR TESTS PASSED"
        )

        return True

    print(
        "❌ SOME CORRELATOR TESTS FAILED"
    )

    return False


# ============================================================================
# CLI
# ============================================================================

def build_parser():

    parser = argparse.ArgumentParser(
        description=(
            "Correlate discovered jobs with "
            "official company/ATS postings."
        )
    )

    parser.add_argument(
        "--version",
        action="store_true",
    )

    parser.add_argument(
        "--tests",
        action="store_true",
    )

    parser.add_argument(
        "--json-file",
        default="",
    )

    parser.add_argument(
        "--json-output",
        default="",
    )

    parser.add_argument(
        "--source",
        default="",
    )

    parser.add_argument(
        "--source-url",
        default="",
    )

    parser.add_argument(
        "--company",
        default="",
    )

    parser.add_argument(
        "--title",
        default="",
    )

    parser.add_argument(
        "--location",
        default="",
    )

    parser.add_argument(
        "--description",
        default="",
    )

    parser.add_argument(
        "--application-url",
        default="",
    )

    parser.add_argument(
        "--requisition-id",
        default="",
    )

    parser.add_argument(
        "--job-id",
        default="",
    )

    parser.add_argument(
        "--work-mode",
        default="",
    )

    parser.add_argument(
        "--experience",
        default="",
    )

    parser.add_argument(
        "--country",
        default="",
    )

    parser.add_argument(
        "--official-url",
        action="append",
        default=[],
    )

    parser.add_argument(
        "--greenhouse-board",
        action="append",
        default=[],
    )

    parser.add_argument(
        "--lever-site",
        action="append",
        default=[],
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
    )

    parser.add_argument(
        "--min-candidate-score",
        type=float,
        default=60.0,
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--no-verifier",
        action="store_true",
    )

    return parser


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    parser = build_parser()

    args = parser.parse_args()

    # ------------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------------

    if args.version:

        print(
            f"Job Correlator {VERSION}"
        )

        return 0

    # ------------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------------

    if args.tests:

        return (
            0
            if run_tests()
            else 1
        )

    # ------------------------------------------------------------------------
    # Load job
    # ------------------------------------------------------------------------

    if args.json_file:

        try:

            job = load_job_json(
                args.json_file
            )

        except Exception as exc:

            print(
                "ERROR: Could not load "
                f"JSON: {exc}",
                file=sys.stderr,
            )

            return 2

    else:

        job = DiscoveredJob(
            source=(
                args.source
            ),
            source_url=(
                args.source_url
            ),
            company=(
                args.company
            ),
            title=(
                args.title
            ),
            location=(
                args.location
            ),
            description=(
                args.description
            ),
            application_url=(
                args.application_url
            ),
            requisition_id=(
                args.requisition_id
            ),
            job_id=(
                args.job_id
            ),
            work_mode=(
                args.work_mode
            ),
            experience_text=(
                args.experience
            ),
            country=(
                args.country
            ),
        )

    # ------------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------------

    if not job.company:

        print(
            "ERROR: company is required",
            file=sys.stderr,
        )

        return 2

    if not job.title:

        print(
            "ERROR: title is required",
            file=sys.stderr,
        )

        return 2

    # ------------------------------------------------------------------------
    # Correlator
    # ------------------------------------------------------------------------

    correlator = JobCorrelator(
        timeout=args.timeout,
        min_candidate_score=(
            args.min_candidate_score
        ),
        max_candidates_to_verify=(
            args.max_candidates
        ),
    )

    result = correlator.correlate(
        job=job,
        official_urls=(
            args.official_url
        ),
        greenhouse_boards=(
            args.greenhouse_board
        ),
        lever_sites=(
            args.lever_site
        ),
        run_verifier=(
            not args.no_verifier
        ),
    )

    payload = asdict(
        result
    )

    payload["version"] = VERSION

    payload["fingerprint"] = (
        job_fingerprint(
            job
        )
    )

    payload["generated_at"] = (
        time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        )
    )

    output = json.dumps(
        payload,
        indent=2,
        ensure_ascii=False,
    )

    print(
        output
    )

    # ------------------------------------------------------------------------
    # JSON output
    # ------------------------------------------------------------------------

    if args.json_output:

        with open(
            args.json_output,
            "w",
            encoding="utf-8",
        ) as handle:

            handle.write(
                output
            )

    # ------------------------------------------------------------------------
    # Exit code
    # ------------------------------------------------------------------------

    if result.status == "VERIFIED":
        return 0

    if result.status == "UNCERTAIN":
        return 1

    return 2


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )