"""
JOB INTELLIGENCE AGENT
======================

Job Verification Engine v1.0.0

Purpose
-------
Third-party websites are DISCOVERY sources.

They are NOT trusted as proof that a job is genuine.

The verification pipeline is:

    Third-party listing
            |
            v
    Extract company/title/location
            |
            v
    Candidate official/ATS URLs
            |
            v
    Fetch official page
            |
            v
    Compare company
    Compare job title
    Compare location
    Compare job description
    Detect direct application
            |
            v
    VERIFIED / UNCERTAIN / REJECTED

Important
---------
This engine cannot mathematically prove that a job is legitimate.

Instead, it produces an evidence-based confidence score.

VERIFIED
--------
Strong evidence that the same job exists on the employer's
official career site or recognized ATS.

UNCERTAIN
---------
Some evidence exists, but not enough to safely notify.

REJECTED
--------
Evidence strongly indicates that the listing cannot be verified.

Third-party sources can be used for DISCOVERY, but their URLs
are never treated as the final application URL.

Final application URL must come from:
    - official company careers
    - recognized ATS
    - verified direct employer application

No CAPTCHA bypass.
No login bypass.
No anti-bot bypass.

Version: 1.0.0
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse


# ============================================================================
# VERSION
# ============================================================================

VERIFIER_VERSION = "1.0.0"

TARGET_COUNTRY = "India"

DEFAULT_TIMEOUT = 15

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36 "
    "JobIntelligenceAgent/1.0"
)


# ============================================================================
# ENUMS
# ============================================================================

class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"


class EvidenceLevel(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"
    NONE = "NONE"


# ============================================================================
# RECOGNIZED ATS
# ============================================================================

ATS_DOMAINS = {
    "greenhouse.io": "Greenhouse",
    "boards.greenhouse.io": "Greenhouse",
    "job-boards.greenhouse.io": "Greenhouse",

    "lever.co": "Lever",
    "jobs.lever.co": "Lever",

    "ashbyhq.com": "Ashby",
    "jobs.ashbyhq.com": "Ashby",

    "myworkdayjobs.com": "Workday",

    "smartrecruiters.com": "SmartRecruiters",

    "icims.com": "iCIMS",

    "successfactors.com": "SAP SuccessFactors",
    "successfactors.eu": "SAP SuccessFactors",

    "bamboohr.com": "BambooHR",

    "workable.com": "Workable",
    "apply.workable.com": "Workable",

    "jobvite.com": "Jobvite",

    "recruitee.com": "Recruitee",

    "teamtailor.com": "Teamtailor",

    "pinpointhq.com": "Pinpoint",

    "personio.com": "Personio",
}


# ============================================================================
# THIRD-PARTY DISCOVERY SOURCES
# ============================================================================

THIRD_PARTY_SOURCES = {
    "linkedin",
    "indeed",
    "naukri",
    "glassdoor",
    "foundit",
    "shine",
    "internshala",
    "freshersworld",
    "hirist",
    "cutshort",
    "wellfound",
    "ziprecruiter",
    "dice",
    "simplyhired",
    "jobrapido",
    "adzuna",
    "talent",
    "jora",
    "google_jobs",
    "youtube",
    "reddit",
    "job_aggregator",
    "search",
}


# ============================================================================
# THIRD-PARTY DOMAINS
# ============================================================================

THIRD_PARTY_DOMAINS = {
    "linkedin.com",
    "linkedin.co.in",

    "indeed.com",
    "indeed.co.in",

    "naukri.com",
    "naukri.co.in",

    "glassdoor.com",
    "glassdoor.co.in",

    "foundit.in",

    "shine.com",

    "internshala.com",

    "freshersworld.com",

    "hirist.tech",

    "cutshort.io",

    "wellfound.com",

    "ziprecruiter.com",

    "dice.com",

    "simplyhired.com",

    "jobrapido.com",

    "adzuna.com",

    "talent.com",

    "jora.com",

    "reddit.com",

    "youtube.com",

    "google.com",
}


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_text(value: object) -> str:
    """
    Normalize arbitrary text for comparison.
    """
    if value is None:
        return ""

    value = html.unescape(str(value))

    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )

    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9+#.\- ]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_company(value: object) -> str:
    """
    Normalize company name.
    """
    text = normalize_text(value)

    removable = {
        "inc",
        "inc.",
        "llc",
        "ltd",
        "limited",
        "pvt",
        "pvt.",
        "private",
        "corp",
        "corporation",
        "company",
        "co",
        "co.",
        "technologies",
        "technology",
    }

    words = [
        word
        for word in text.split()
        if word not in removable
    ]

    return " ".join(words).strip()


def normalize_title(value: object) -> str:
    """
    Normalize job title.
    """
    text = normalize_text(value)

    text = re.sub(
        r"\b(job|career|careers|position|opening)\b",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================================
# TOKENIZATION
# ============================================================================

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "at",
    "from",
    "by",
    "as",
    "is",
    "are",
    "be",
    "this",
    "that",
    "job",
    "role",
}


def tokens(value: object) -> set[str]:
    """
    Convert text to useful comparison tokens.
    """
    text = normalize_text(value)

    result = set()

    for token in re.findall(
        r"[a-z0-9+#.]+",
        text,
    ):
        if len(token) <= 1:
            continue

        if token in STOPWORDS:
            continue

        result.add(token)

    return result


def token_similarity(
    first: object,
    second: object,
) -> float:
    """
    Jaccard-style token similarity.
    """
    first_tokens = tokens(first)
    second_tokens = tokens(second)

    if not first_tokens or not second_tokens:
        return 0.0

    intersection = first_tokens.intersection(second_tokens)

    union = first_tokens.union(second_tokens)

    if not union:
        return 0.0

    return len(intersection) / len(union)


# ============================================================================
# COMPANY MATCH
# ============================================================================

def company_match(
    discovered_company: str,
    official_text: str,
) -> tuple[bool, int, str]:
    """
    Determine whether company name appears on official page.
    """
    company = normalize_company(discovered_company)

    if not company:
        return (
            False,
            0,
            "Discovery listing does not contain a company name",
        )

    official = normalize_company(official_text)

    if not official:
        return (
            False,
            0,
            "Official page contains no usable text",
        )

    company_tokens = tokens(company)
    page_tokens = tokens(official_text)

    if not company_tokens:
        return (
            False,
            0,
            "Company name could not be normalized",
        )

    matches = company_tokens.intersection(page_tokens)

    ratio = len(matches) / len(company_tokens)

    if ratio >= 1.0:
        return (
            True,
            30,
            "Company name strongly matches official page",
        )

    if ratio >= 0.5:
        return (
            True,
            15,
            "Company name partially matches official page",
        )

    return (
        False,
        0,
        "Company name not sufficiently matched",
    )


# ============================================================================
# TITLE MATCH
# ============================================================================

def title_match(
    discovered_title: str,
    official_text: str,
) -> tuple[bool, int, str]:
    """
    Compare discovered title against official page.
    """
    title = normalize_title(discovered_title)

    if not title:
        return (
            False,
            0,
            "Discovery listing does not contain a job title",
        )

    official = normalize_text(official_text)

    title_tokens = tokens(title)

    if not title_tokens:
        return (
            False,
            0,
            "Job title could not be normalized",
        )

    matched = title_tokens.intersection(
        tokens(official)
    )

    ratio = len(matched) / len(title_tokens)

    if ratio >= 0.80:
        return (
            True,
            30,
            "Job title strongly matches official page",
        )

    if ratio >= 0.55:
        return (
            True,
            18,
            "Job title reasonably matches official page",
        )

    if ratio >= 0.35:
        return (
            True,
            8,
            "Job title weakly matches official page",
        )

    return (
        False,
        0,
        "Job title does not sufficiently match official page",
    )


# ============================================================================
# LOCATION MATCH
# ============================================================================

INDIA_LOCATION_TERMS = {
    "india",
    "remote india",
    "india remote",
    "remote - india",
    "work from home india",
    "pan india",
    "anywhere in india",
    "hyderabad",
    "bangalore",
    "bengaluru",
    "chennai",
    "mumbai",
    "pune",
    "delhi",
    "new delhi",
    "gurugram",
    "gurgaon",
    "noida",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "thiruvananthapuram",
    "lucknow",
    "chandigarh",
    "indore",
    "bhubaneswar",
    "visakhapatnam",
    "vishakhapatnam",
}


def location_match(
    discovered_location: str,
    official_text: str,
) -> tuple[bool, int, str]:
    """
    Compare discovered location against official page.

    This is deliberately conservative.
    """
    discovered = normalize_text(
        discovered_location
    )

    official = normalize_text(
        official_text
    )

    if not discovered:
        return (
            False,
            0,
            "Discovery listing has no location",
        )

    if not official:
        return (
            False,
            0,
            "Official page has no usable location text",
        )

    # Exact phrase.
    if discovered in official:
        return (
            True,
            20,
            "Location appears on official page",
        )

    # India-specific matching.
    if discovered in INDIA_LOCATION_TERMS:
        if any(
            term in official
            for term in INDIA_LOCATION_TERMS
        ):
            return (
                True,
                15,
                "India/location evidence appears on official page",
            )

    # Token comparison.
    discovered_tokens = tokens(discovered)
    official_tokens = tokens(official)

    if discovered_tokens:
        overlap = discovered_tokens.intersection(
            official_tokens
        )

        ratio = len(overlap) / len(discovered_tokens)

        if ratio >= 0.60:
            return (
                True,
                10,
                "Location has meaningful overlap with official page",
            )

    return (
        False,
        0,
        "Location could not be sufficiently verified",
    )


# ============================================================================
# APPLICATION URL
# ============================================================================

APPLICATION_PATHS = (
    "/apply",
    "/application",
    "/apply-now",
    "/candidate",
    "/candidates",
    "/job-application",
)


def domain_matches(
    hostname: str,
    domain: str,
) -> bool:
    hostname = hostname.lower().strip()
    domain = domain.lower().strip()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    if hostname == domain:
        return True

    return hostname.endswith("." + domain)


def detect_ats(
    url: str,
) -> Optional[str]:
    """
    Detect recognized ATS.
    """
    try:
        hostname = urlparse(url).hostname

        if not hostname:
            return None

        hostname = hostname.lower()

        for domain, name in ATS_DOMAINS.items():
            if domain_matches(
                hostname,
                domain,
            ):
                return name

    except Exception:
        pass

    return None


def is_third_party_url(
    url: str,
) -> bool:
    """
    Detect known third-party discovery URL.
    """
    try:
        hostname = urlparse(url).hostname

        if not hostname:
            return True

        hostname = hostname.lower()

        return any(
            domain_matches(
                hostname,
                domain,
            )
            for domain in THIRD_PARTY_DOMAINS
        )

    except Exception:
        return True


def looks_like_direct_application(
    url: str,
) -> bool:
    """
    Detect likely direct application URL.
    """
    if not url:
        return False

    ats = detect_ats(url)

    if ats or "careers.airbnb.com" in url.lower():`n        path = (
            urlparse(url).path or ""
        ).lower()

        if any(
            marker in path
            for marker in APPLICATION_PATHS
        ):
            return True

        # Greenhouse job pages are generally employer-hosted
        # application flows even when /apply is not in the URL.
        if ats == "Greenhouse":
            return True

        if ats == "Lever":
            return True

        if ats == "Ashby":
            return True

        if ats == "Workable":
            return True

    path = (
        urlparse(url).path or ""
    ).lower()

    return any(
        marker in path
        for marker in APPLICATION_PATHS
    )


# ============================================================================
# OFFICIAL URL CHECK
# ============================================================================

def is_probably_official_url(
    url: str,
    company: str,
) -> tuple[bool, str]:
    """
    Determine whether URL is likely an official employer/ATS URL.

    This does NOT prove ownership.
    """
    if not url:
        return (
            False,
            "No official URL supplied",
        )

    if is_third_party_url(url):
        return (
            False,
            "URL belongs to a third-party discovery platform",
        )

    ats = detect_ats(url)

    if ats or "careers.airbnb.com" in url.lower():`n        return (
            True,
            f"Recognized official ATS: {ats}",
        )

    try:
        hostname = urlparse(url).hostname

        if not hostname:
            return (
                False,
                "URL has no hostname",
            )

        hostname = hostname.lower()

        company_normalized = normalize_company(
            company
        )

        company_parts = [
            part
            for part in company_normalized.split()
            if len(part) >= 3
        ]

        hostname_text = hostname.replace(
            "-",
            " ",
        ).replace(
            ".",
            " ",
        )

        matches = [
            part
            for part in company_parts
            if part in hostname_text
        ]

        path = (
            urlparse(url).path or ""
        ).lower()

        career_path = any(
            word in path
            for word in (
                "career",
                "careers",
                "jobs",
                "job",
                "position",
                "opportunity",
                "recruit",
            )
        )

        if matches and career_path:
            return (
                True,
                "Company name and career path appear in official domain",
            )

        if career_path:
            return (
                True,
                "Career/job path detected; company ownership still requires verification",
            )

    except Exception:
        pass

    return (
        False,
        "Official employer domain could not be established",
    )


# ============================================================================
# FETCH
# ============================================================================

@dataclass
class FetchResult:
    url: str
    final_url: Optional[str]
    status_code: Optional[int]
    content_type: Optional[str]
    text: str
    success: bool
    error: Optional[str]
    fetched_at: float


def fetch_page(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    max_bytes: int = 2_000_000,
) -> FetchResult:
    """
    Fetch a public page.

    Does not bypass:
        - CAPTCHA
        - authentication
        - bot protection
        - robots restrictions
        - access controls
    """
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/json;q=0.9,"
                "*/*;q=0.8"
            ),
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=timeout,
        ) as response:

            raw = response.read(
                max_bytes
            )

            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            charset = "utf-8"

            match = re.search(
                r"charset=([A-Za-z0-9._-]+)",
                content_type,
                re.IGNORECASE,
            )

            if match:
                charset = match.group(1)

            try:
                text = raw.decode(
                    charset,
                    errors="replace",
                )
            except LookupError:
                text = raw.decode(
                    "utf-8",
                    errors="replace",
                )

            return FetchResult(
                url=url,
                final_url=response.geturl(),
                status_code=response.status,
                content_type=content_type,
                text=text,
                success=True,
                error=None,
                fetched_at=time.time(),
            )

    except HTTPError as exc:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=exc.code,
            content_type=None,
            text="",
            success=False,
            error=f"HTTP {exc.code}",
            fetched_at=time.time(),
        )

    except URLError as exc:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            text="",
            success=False,
            error=f"URL error: {exc.reason}",
            fetched_at=time.time(),
        )

    except TimeoutError:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            text="",
            success=False,
            error="Request timeout",
            fetched_at=time.time(),
        )

    except Exception as exc:
        return FetchResult(
            url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            text="",
            success=False,
            error=str(exc),
            fetched_at=time.time(),
        )


# ============================================================================
# CONTENT EXTRACTION
# ============================================================================

def extract_visible_text(
    page: str,
) -> str:
    """
    Convert HTML to approximately visible text.
    """
    if not page:
        return ""

    page = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    page = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    page = re.sub(
        r"<noscript\b[^>]*>.*?</noscript>",
        " ",
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )

    page = re.sub(
        r"<[^>]+>",
        " ",
        page,
    )

    page = html.unescape(page)

    page = re.sub(
        r"\s+",
        " ",
        page,
    )

    return page.strip()


# ============================================================================
# FRAUD / SCAM SIGNALS
# ============================================================================

SCAM_PATTERNS = {
    "pay a fee": (
        r"\bpay\b.{0,60}"
        r"\bfee\b"
    ),

    "registration fee": (
        r"\bregistration\s+fee\b"
    ),

    "training fee": (
        r"\btraining\s+fee\b"
    ),

    "security deposit": (
        r"\bsecurity\s+deposit\b"
    ),

    "buy equipment": (
        r"\bbuy\b.{0,40}"
        r"\bequipment\b"
    ),

    "gift card": (
        r"\bgift\s+card\b"
    ),

    "crypto payment": (
        r"\bcrypto(?:currency)?\b.{0,50}"
        r"\bpayment\b"
    ),

    "send money": (
        r"\bsend\b.{0,30}"
        r"\bmoney\b"
    ),

    "deposit check": (
        r"\bdeposit\b.{0,30}"
        r"\bcheck\b"
    ),

    "send money back": (
        r"\bsend\b.{0,30}"
        r"\bmoney\b.{0,30}"
        r"\bback\b"
    ),

    "telegram interview": (
        r"\btelegram\b.{0,60}"
        r"\binterview\b"
    ),

    "whatsapp interview": (
        r"\bwhatsapp\b.{0,60}"
        r"\binterview\b"
    ),
}


def detect_scam_signals(
    text: str,
) -> list[str]:
    """
    Detect obvious job-scam signals.

    These are warning signals, NOT proof.
    """
    normalized = normalize_text(text)

    signals = []

    for name, pattern in SCAM_PATTERNS.items():
        if re.search(
            pattern,
            normalized,
            re.IGNORECASE,
        ):
            signals.append(name)

    return signals


# ============================================================================
# EVIDENCE
# ============================================================================

@dataclass
class VerificationEvidence:
    company_verified: bool
    company_score: int

    title_verified: bool
    title_score: int

    location_verified: bool
    location_score: int

    official_url_verified: bool
    official_url_score: int

    application_url_verified: bool
    application_url_score: int

    scam_signals: list[str]

    source_url_is_third_party: bool

    official_url: Optional[str]
    application_url: Optional[str]

    notes: list[str]


# ============================================================================
# FINAL RESULT
# ============================================================================

@dataclass
class JobVerificationResult:
    status: VerificationStatus
    evidence_level: EvidenceLevel
    confidence: int

    company: str
    title: str
    discovered_location: str

    source_url: Optional[str]
    official_url: Optional[str]
    application_url: Optional[str]

    source_is_third_party: bool
    application_is_direct: bool

    reason: str

    evidence: VerificationEvidence

    fingerprint: str

    def to_dict(self) -> dict:
        data = asdict(self)

        data["status"] = self.status.value
        data["evidence_level"] = self.evidence_level.value

        return data


# ============================================================================
# FINGERPRINT
# ============================================================================

def make_fingerprint(
    company: str,
    title: str,
    location: str,
) -> str:
    """
    Stable job fingerprint.
    """
    raw = "|".join(
        [
            normalize_company(company),
            normalize_title(title),
            normalize_text(location),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================================
# OFFICIAL PAGE VERIFICATION
# ============================================================================

def verify_official_page(
    *,
    company: str,
    title: str,
    location: str,
    official_url: str,
    application_url: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> JobVerificationResult:
    """
    Verify one candidate official page.
    """

    fingerprint = make_fingerprint(
        company,
        title,
        location,
    )

    source_is_third_party = False

    official_ok, official_reason = (
        is_probably_official_url(
            official_url,
            company,
        )
    )

    if not official_ok:
        evidence = VerificationEvidence(
            company_verified=False,
            company_score=0,
            title_verified=False,
            title_score=0,
            location_verified=False,
            location_score=0,
            official_url_verified=False,
            official_url_score=0,
            application_url_verified=False,
            application_url_score=0,
            scam_signals=[],
            source_url_is_third_party=False,
            official_url=official_url,
            application_url=None,
            notes=[
                official_reason,
            ],
        )

        return JobVerificationResult(
            status=VerificationStatus.REJECTED,
            evidence_level=EvidenceLevel.NONE,
            confidence=0,
            company=company,
            title=title,
            discovered_location=location,
            source_url=None,
            official_url=official_url,
            application_url=None,
            source_is_third_party=False,
            application_is_direct=False,
            reason=official_reason,
            evidence=evidence,
            fingerprint=fingerprint,
        )

    page = fetch_page(
        official_url,
        timeout=timeout,
    )

    if not page.success:
        evidence = VerificationEvidence(
            company_verified=False,
            company_score=0,
            title_verified=False,
            title_score=0,
            location_verified=False,
            location_score=0,
            official_url_verified=True,
            official_url_score=15,
            application_url_verified=False,
            application_url_score=0,
            scam_signals=[],
            source_url_is_third_party=False,
            official_url=official_url,
            application_url=None,
            notes=[
                f"Official page could not be fetched: {page.error}",
            ],
        )

        return JobVerificationResult(
            status=VerificationStatus.UNCERTAIN,
            evidence_level=EvidenceLevel.WEAK,
            confidence=25,
            company=company,
            title=title,
            discovered_location=location,
            source_url=None,
            official_url=official_url,
            application_url=None,
            source_is_third_party=False,
            application_is_direct=False,
            reason=(
                "Official-looking page found, "
                "but it could not be fetched"
            ),
            evidence=evidence,
            fingerprint=fingerprint,
        )

    visible_text = extract_visible_text(
        page.text
    )

    # ------------------------------------------------------------
    # Company
    # ------------------------------------------------------------

    company_ok, company_score, company_reason = (
        company_match(
            company,
            visible_text,
        )
    )

    # ------------------------------------------------------------
    # Title
    # ------------------------------------------------------------

    title_ok, title_score, title_reason = (
        title_match(
            title,
            visible_text,
        )
    )

    # ------------------------------------------------------------
    # Location
    # ------------------------------------------------------------

    location_ok, location_score, location_reason = (
        location_match(
            location,
            visible_text,
        )
    )

    # ------------------------------------------------------------
    # Official URL
    # ------------------------------------------------------------

    official_url_score = 20

    # Recognized ATS gets stronger evidence.
    ats = detect_ats(
        page.final_url or official_url
    )

    if ats or "careers.airbnb.com" in url.lower():`n        official_url_score = 25

    # ------------------------------------------------------------
    # Application URL
    # ------------------------------------------------------------

    final_application_url = None

    application_ok = False
    application_score = 0

    if application_url:

        app_official, app_reason = (
            is_probably_official_url(
                application_url,
                company,
            )
        )

        app_direct = looks_like_direct_application(
            application_url
        )

        if app_official and app_direct:
            final_application_url = application_url
            application_ok = True
            application_score = 20

        else:
            application_score = 0

    # If official page itself is a direct ATS application.
    if not final_application_url:
        candidate_url = (
            page.final_url
            or official_url
        )

        if (
            detect_ats(candidate_url)
            and looks_like_direct_application(
                candidate_url
            )
        ):
            final_application_url = candidate_url
            application_ok = True
            application_score = 20

    # ------------------------------------------------------------
    # Scam signals
    # ------------------------------------------------------------

    scam_signals = detect_scam_signals(
        visible_text
    )

    # ------------------------------------------------------------
    # Score
    # ------------------------------------------------------------

    total_score = (
        company_score
        + title_score
        + location_score
        + official_url_score
        + application_score
    )

    # Scam signals reduce confidence.
    scam_penalty = min(
        len(scam_signals) * 10,
        40,
    )

    total_score -= scam_penalty

    total_score = max(
        0,
        min(
            total_score,
            100,
        ),
    )

    notes = [
        official_reason,
        company_reason,
        title_reason,
        location_reason,
    ]

    if application_ok:
        notes.append(
            "Direct employer/ATS application URL verified"
        )
    else:
        notes.append(
            "Direct application URL not established"
        )

    if scam_signals:
        notes.append(
            "Potential scam signals detected: "
            + ", ".join(scam_signals)
        )

    # ------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------

    strong_match = (
        company_ok
        and title_ok
        and location_ok
    )

    verified = (
        strong_match
        and application_ok
        and total_score >= 75
        and not scam_signals
    )

    if verified:

        status = VerificationStatus.VERIFIED
        evidence_level = EvidenceLevel.STRONG

        reason = (
            "Same company, job title and location were "
            "verified on an official employer/ATS page, "
            "with a direct application URL."
        )

    elif (
        strong_match
        and total_score >= 55
    ):

        status = VerificationStatus.UNCERTAIN
        evidence_level = EvidenceLevel.MEDIUM

        reason = (
            "The job appears to match an official page, "
            "but verification evidence is incomplete."
        )

    elif (
        company_ok
        and title_ok
        and total_score >= 40
    ):

        status = VerificationStatus.UNCERTAIN
        evidence_level = EvidenceLevel.WEAK

        reason = (
            "Company and title appear to match, "
            "but location or application evidence "
            "is insufficient."
        )

    else:

        status = VerificationStatus.REJECTED
        evidence_level = EvidenceLevel.NONE

        reason = (
            "The discovered job could not be sufficiently "
            "matched to the official employer/ATS page."
        )

    evidence = VerificationEvidence(
        company_verified=company_ok,
        company_score=company_score,

        title_verified=title_ok,
        title_score=title_score,

        location_verified=location_ok,
        location_score=location_score,

        official_url_verified=True,
        official_url_score=official_url_score,

        application_url_verified=application_ok,
        application_url_score=application_score,

        scam_signals=scam_signals,

        source_url_is_third_party=source_is_third_party,

        official_url=official_url,
        application_url=final_application_url,

        notes=notes,
    )

    return JobVerificationResult(
        status=status,
        evidence_level=evidence_level,
        confidence=total_score,

        company=company,
        title=title,
        discovered_location=location,

        source_url=None,
        official_url=official_url,
        application_url=final_application_url,

        source_is_third_party=source_is_third_party,
        application_is_direct=application_ok,

        reason=reason,

        evidence=evidence,

        fingerprint=fingerprint,
    )


# ============================================================================
# THIRD-PARTY LISTING VERIFICATION
# ============================================================================

def verify_discovered_job(
    *,
    company: str,
    title: str,
    location: str,
    source_url: str,
    official_url: str,
    application_url: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> JobVerificationResult:
    """
    Verify a job discovered from a third-party source.

    Third-party URL is retained as evidence only.

    It is NEVER returned as application_url.
    """

    source_is_third_party = is_third_party_url(
        source_url
    )

    result = verify_official_page(
        company=company,
        title=title,
        location=location,
        official_url=official_url,
        application_url=application_url,
        timeout=timeout,
    )

    result.source_url = source_url
    result.source_is_third_party = (
        source_is_third_party
    )

    return result


# ============================================================================
# JSON INPUT
# ============================================================================

def load_job_json(
    path: str,
) -> dict:
    """
    Load one discovered job from JSON.
    """
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Job JSON must contain an object"
        )

    return data


# ============================================================================
# PRINT
# ============================================================================

def print_result(
    result: JobVerificationResult,
) -> None:

    print("=" * 72)
    print("JOB VERIFICATION RESULT")
    print("=" * 72)

    print(
        f"Status             : "
        f"{result.status.value}"
    )

    print(
        f"Evidence level     : "
        f"{result.evidence_level.value}"
    )

    print(
        f"Confidence         : "
        f"{result.confidence}/100"
    )

    print("-" * 72)

    print(
        f"Company            : "
        f"{result.company}"
    )

    print(
        f"Title              : "
        f"{result.title}"
    )

    print(
        f"Location           : "
        f"{result.discovered_location}"
    )

    print(
        f"Discovery source   : "
        f"{result.source_url}"
    )

    print(
        f"Third-party source : "
        f"{result.source_is_third_party}"
    )

    print(
        f"Official URL       : "
        f"{result.official_url}"
    )

    print(
        f"Application URL    : "
        f"{result.application_url}"
    )

    print(
        f"Direct application: "
        f"{result.application_is_direct}"
    )

    print("-" * 72)

    print("EVIDENCE")
    print(
        f"Company            : "
        f"{result.evidence.company_verified} "
        f"({result.evidence.company_score})"
    )

    print(
        f"Title              : "
        f"{result.evidence.title_verified} "
        f"({result.evidence.title_score})"
    )

    print(
        f"Location           : "
        f"{result.evidence.location_verified} "
        f"({result.evidence.location_score})"
    )

    print(
        f"Official URL       : "
        f"{result.evidence.official_url_verified} "
        f"({result.evidence.official_url_score})"
    )

    print(
        f"Application URL    : "
        f"{result.evidence.application_url_verified} "
        f"({result.evidence.application_url_score})"
    )

    print(
        f"Scam signals       : "
        f"{result.evidence.scam_signals or 'None'}"
    )

    print("-" * 72)

    print(
        f"Reason             : "
        f"{result.reason}"
    )

    print("-" * 72)

    print("NOTES")

    for note in result.evidence.notes:
        print(f"  - {note}")

    print("-" * 72)

    print(
        f"Fingerprint        : "
        f"{result.fingerprint}"
    )

    print("=" * 72)


# ============================================================================
# TEST SUITE
# ============================================================================

def test_normalization() -> bool:

    assert (
        normalize_company(
            "ABC Technologies Pvt. Ltd."
        )
        == "abc"
    )

    assert (
        normalize_title(
            "SOC Analyst - Job"
        )
        == "soc analyst"
    )

    return True


def test_domain_detection() -> bool:

    assert (
        detect_ats(
            "https://boards.greenhouse.io/example/jobs/123"
        )
        == "Greenhouse"
    )

    assert (
        detect_ats(
            "https://jobs.lever.co/example/123/apply"
        )
        == "Lever"
    )

    assert (
        detect_ats(
            "https://example.wd1.myworkdayjobs.com/careers"
        )
        == "Workday"
    )

    assert (
        detect_ats(
            "https://unknown.example.com/jobs/123"
        )
        is None
    )

    return True


def test_third_party_detection() -> bool:

    assert is_third_party_url(
        "https://www.linkedin.com/jobs/view/123"
    )

    assert is_third_party_url(
        "https://www.indeed.com/viewjob?jk=123"
    )

    assert is_third_party_url(
        "https://www.naukri.com/job-listings/123"
    )

    assert not is_third_party_url(
        "https://boards.greenhouse.io/example/jobs/123"
    )

    return True


def test_application_detection() -> bool:

    assert looks_like_direct_application(
        "https://boards.greenhouse.io/example/jobs/123/apply"
    )

    assert looks_like_direct_application(
        "https://jobs.lever.co/example/123/apply"
    )

    assert looks_like_direct_application(
        "https://jobs.ashbyhq.com/example/123/apply"
    )

    assert not looks_like_direct_application(
        "https://www.linkedin.com/jobs/view/123"
    )

    return True


def test_scam_detection() -> bool:

    signals = detect_scam_signals(
        """
        Pay a registration fee.
        Buy equipment.
        Send money back.
        """
    )

    assert len(signals) >= 2

    clean = detect_scam_signals(
        """
        This is an ordinary software engineering position.
        Apply through the company's official careers website.
        """
    )

    assert len(clean) == 0

    return True


def test_fingerprint() -> bool:

    first = make_fingerprint(
        "ABC Technologies",
        "SOC Analyst",
        "Hyderabad",
    )

    second = make_fingerprint(
        "ABC Technologies",
        "SOC Analyst",
        "Hyderabad",
    )

    third = make_fingerprint(
        "ABC Technologies",
        "SOC Analyst",
        "Bangalore",
    )

    assert first == second
    assert first != third

    return True


def test_url_policy() -> bool:

    cases = [
        (
            "https://www.linkedin.com/jobs/view/123",
            False,
        ),

        (
            "https://www.indeed.com/viewjob?jk=123",
            False,
        ),

        (
            "https://www.naukri.com/job-listings/123",
            False,
        ),

        (
            "https://boards.greenhouse.io/example/jobs/123/apply",
            True,
        ),

        (
            "https://jobs.lever.co/example/123/apply",
            True,
        ),
    ]

    for url, expected in cases:

        result = (
            is_probably_official_url(
                url,
                "Example",
            )[0]
        )

        assert result == expected, url

    return True


def run_tests() -> bool:

    print("=" * 72)
    print("JOB VERIFICATION ENGINE")
    print("=" * 72)

    print(
        f"Engine version : "
        f"{VERIFIER_VERSION}"
    )

    print(
        f"Target country : "
        f"{TARGET_COUNTRY}"
    )

    print("-" * 72)

    tests = [
        (
            "Text normalization",
            test_normalization,
        ),
        (
            "ATS detection",
            test_domain_detection,
        ),
        (
            "Third-party detection",
            test_third_party_detection,
        ),
        (
            "Application detection",
            test_application_detection,
        ),
        (
            "Scam signal detection",
            test_scam_detection,
        ),
        (
            "Fingerprint generation",
            test_fingerprint,
        ),
        (
            "URL policy",
            test_url_policy,
        ),
    ]

    passed = 0
    failed = 0

    for name, test in tests:

        try:
            test()

            print(
                f"âœ… {name}"
            )

            passed += 1

        except Exception as exc:

            print(
                f"âŒ {name}"
            )

            print(
                f"   Error: {exc}"
            )

            failed += 1

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
            "âœ… ALL VERIFICATION ENGINE TESTS PASSED"
        )
        return True

    print(
        "âŒ SOME VERIFICATION ENGINE TESTS FAILED"
    )

    return False


# ============================================================================
# CLI
# ============================================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Verify third-party discovered jobs "
            "against official employer/ATS pages."
        )
    )

    parser.add_argument(
        "--tests",
        action="store_true",
        help="Run internal tests",
    )

    parser.add_argument(
        "--company",
        help="Company name",
    )

    parser.add_argument(
        "--title",
        help="Job title",
    )

    parser.add_argument(
        "--location",
        default="",
        help="Job location",
    )

    parser.add_argument(
        "--source-url",
        help="Third-party discovery URL",
    )

    parser.add_argument(
        "--official-url",
        help="Official employer/ATS job URL",
    )

    parser.add_argument(
        "--application-url",
        default=None,
        help="Candidate direct application URL",
    )

    parser.add_argument(
        "--json-file",
        help="Load discovered job from JSON",
    )

    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Print JSON result",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds",
    )

    args = parser.parse_args()

    # ----------------------------------------------------------------------
    # TESTS
    # ----------------------------------------------------------------------

    if args.tests:
        return 0 if run_tests() else 1

    # ----------------------------------------------------------------------
    # JSON FILE
    # ----------------------------------------------------------------------

    if args.json_file:

        try:
            job = load_job_json(
                args.json_file
            )

        except Exception as exc:

            print(
                f"ERROR: Could not load JSON: {exc}"
            )

            return 1

        company = job.get(
            "company",
            "",
        )

        title = job.get(
            "title",
            "",
        )

        location = job.get(
            "location",
            "",
        )

        source_url = job.get(
            "source_url"
            or "sourceUrl",
            "",
        )

        official_url = job.get(
            "official_url"
            or "officialUrl",
            "",
        )

        application_url = job.get(
            "application_url"
            or "applicationUrl"
        )

    else:

        company = args.company
        title = args.title
        location = args.location
        source_url = args.source_url
        official_url = args.official_url
        application_url = args.application_url

    # ----------------------------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------------------------

    required = {
        "company": company,
        "title": title,
        "source_url": source_url,
        "official_url": official_url,
    }

    missing = [
        key
        for key, value in required.items()
        if not value
    ]

    if missing:

        print(
            "ERROR: Missing required fields:"
        )

        for field in missing:
            print(
                f"  - {field}"
            )

        return 1

    # ----------------------------------------------------------------------
    # VERIFY
    # ----------------------------------------------------------------------

    result = verify_discovered_job(
        company=company,
        title=title,
        location=location,
        source_url=source_url,
        official_url=official_url,
        application_url=application_url,
        timeout=args.timeout,
    )

    # ----------------------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------------------

    if args.json_output:

        print(
            json.dumps(
                result.to_dict(),
                indent=2,
                ensure_ascii=False,
            )
        )

    else:

        print_result(
            result
        )

    # ----------------------------------------------------------------------
    # EXIT CODE
    # ----------------------------------------------------------------------

    if result.status == VerificationStatus.VERIFIED:
        return 0

    if result.status == VerificationStatus.UNCERTAIN:
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
