#!/usr/bin/env python3
"""
Job Intelligence Agent
Official Job Verification Engine
Version: 3.1.0

Purpose
-------
Verify jobs discovered from third-party sources against an employer's
official careers page or a recognized ATS.

Design
------
Discovery sources such as LinkedIn, Indeed, Naukri and Glassdoor are
allowed for discovery only.

A third-party URL must never become the final Telegram application URL.

Verification order:
    DISCOVERED JOB
          |
          v
    OFFICIAL COMPANY / ATS
          |
          v
    VERIFICATION
          |
          +---- VERIFIED
          +---- UNCERTAIN
          +---- REJECTED
          |
          v
    DIRECT APPLICATION URL

No CAPTCHA bypass.
No authentication bypass.
No anti-bot bypass.
No invented application URLs.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import ssl
import sys
import time
import unicodedata

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


# ============================================================================
# VERSION / CONFIGURATION
# ============================================================================

VERSION = "3.1.0"

TARGET_COUNTRY = "India"

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_BYTES = 2_500_000

VERIFIED_THRESHOLD = 80
ATS_VERIFIED_THRESHOLD = 55
UNCERTAIN_THRESHOLD = 55


# ============================================================================
# THIRD-PARTY DISCOVERY DOMAINS
# ============================================================================

THIRD_PARTY_JOB_DOMAINS = {
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
    "bebee.com",
    "jora.com",
    "hirist.tech",
    "instahyre.com",
    "freshersworld.com",
    "fresherslive.com",
    "apna.co",
    "workindia.in",
}


# ============================================================================
# RECOGNIZED ATS
# ============================================================================

ATS_DOMAINS = {
    "greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "ashbyhq.com": "Ashby",
    "myworkdayjobs.com": "Workday",
    "smartrecruiters.com": "SmartRecruiters",
    "icims.com": "iCIMS",
    "successfactors.com": "SAP SuccessFactors",
    "bamboohr.com": "BambooHR",
    "workable.com": "Workable",
    "jobvite.com": "Jobvite",
    "recruitee.com": "Recruitee",
    "teamtailor.com": "Teamtailor",
    "pinpointhq.com": "Pinpoint",
    "rippling.com": "Rippling",
    "personio.com": "Personio",
    "applytojob.com": "ApplyToJob",
}


# ============================================================================
# CAREER URL PATTERNS
# ============================================================================

CAREER_PATH_PATTERNS = (
    "/careers",
    "/career",
    "/jobs",
    "/job/",
    "/job?",
    "/openings",
    "/opportunities",
    "/work-with-us",
    "/join-us",
    "/join-our-team",
    "/vacancies",
    "/positions",
    "/employment",
    "/talent",
)


# ============================================================================
# TRACKING PARAMETERS
# ============================================================================

TRACKING_PARAMETER_PREFIXES = (
    "utm_",
    "gh_src",
    "gh_jid",
    "source",
    "src",
    "trk",
    "tracking",
    "ref",
    "referrer",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
)


# ============================================================================
# REMOTE / COUNTRY SIGNALS
# ============================================================================

REMOTE_POSITIVE_PATTERNS = (
    r"\bremote\b",
    r"\bfully remote\b",
    r"\b100% remote\b",
    r"\bwork from home\b",
    r"\bwork[- ]from[- ]home\b",
    r"\bdistributed\b",
)

NON_REMOTE_PATTERNS = (
    r"\bon[- ]site\b",
    r"\bonsite\b",
    r"\bin[- ]office\b",
    r"\bin office\b",
    r"\bhybrid\b",
    r"\bwork from office\b",
    r"\bwfo\b",
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
    r"\bindia remote\b",
    r"\bremote[- ]india\b",
    r"\bremote in india\b",
    r"\bindia[- ]based remote\b",
    r"\bhire in india\b",
    r"\bhiring in india\b",
    r"\bopen to india\b",
    r"\bavailable in india\b",
)

COUNTRY_RESTRICTION_PATTERNS = (
    r"\bmust be based in\b",
    r"\bmust reside in\b",
    r"\bmust live in\b",
    r"\bresidents of\b",
    r"\bonly in\b",
    r"\bonly available in\b",
    r"\bavailable only in\b",
    r"\bremote -?us only\b",
    r"\bus only\b",
    r"\busa only\b",
    r"\bunited states only\b",
    r"\bcanada only\b",
    r"\buk only\b",
    r"\beurope only\b",
    r"\beu only\b",
)

US_AUTH_PATTERNS = (
    r"\bauthorized to work in the united states\b",
    r"\bauthorized to work in the us\b",
    r"\bwork authorization in the us\b",
    r"\bwork authorization in the united states\b",
    r"\blegal right to work in the us\b",
    r"\bmust have us work authorization\b",
)

INDIA_AUTH_PATTERNS = (
    r"\bauthorized to work in india\b",
    r"\bright to work in india\b",
    r"\bindia work authorization\b",
)


# ============================================================================
# FRESHER / EXPERIENCE SIGNALS
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
    r"\bexperience not required\b",
    r"\b0\s*[-–]\s*1\s*years?\b",
    r"\b0\s*[-–]\s*2\s*years?\b",
    r"\b0\s*to\s*1\s*years?\b",
    r"\b0\s*to\s*2\s*years?\b",
    r"\b1\s*[-–]\s*2\s*years?\b",
)

EXPERIENCE_PATTERNS = (
    r"(\d+)\s*[-–]\s*(\d+)\s*years?",
    r"(\d+)\s*to\s*(\d+)\s*years?",
    r"(\d+)\+?\s*years?",
)


# ============================================================================
# SCAM SIGNALS
# ============================================================================

SCAM_PATTERNS = (
    r"\bpay a fee\b",
    r"\bregistration fee\b",
    r"\bprocessing fee\b",
    r"\btraining fee\b",
    r"\bsecurity deposit\b",
    r"\bpay to apply\b",
    r"\bpay to get hired\b",
    r"\bguaranteed job\b",
    r"\bguaranteed placement\b",
    r"\bcrypto payment\b",
    r"\bbitcoin payment\b",
    r"\bgift card\b",
    r"\btelegram only\b",
    r"\bwhatsapp only\b",
    r"\bcontact via whatsapp\b",
)

SENSITIVE_INFO_PATTERNS = (
    r"\bcredit card\b",
    r"\bdebit card\b",
    r"\bbank account\b",
    r"\bnet banking\b",
    r"\botp\b",
    r"\bpin\b",
    r"\bpassword\b",
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class FetchResult:
    requested_url: str
    final_url: str = ""
    status_code: Optional[int] = None
    content_type: str = ""
    html_text: str = ""
    title: str = ""
    error: str = ""
    redirected: bool = False
    bytes_read: int = 0

    @property
    def success(self) -> bool:
        return bool(self.html_text) and (
            self.status_code is None
            or 200 <= self.status_code < 400
        )


@dataclass
class RemoteAssessment:
    classification: str = "UNKNOWN"
    confidence: int = 0
    reasons: List[str] = field(default_factory=list)

    @property
    def india_eligible(self) -> bool:
        return self.classification in {
            "WORLDWIDE",
            "INDIA_ELIGIBLE",
        }


@dataclass
class VerificationEvidence:
    official_domain: bool = False
    recognized_ats: bool = False
    official_career_path: bool = False
    source_is_third_party: bool = False
    title_match: bool = False
    company_match: bool = False
    location_match: bool = False
    remote_match: bool = False
    india_eligibility: str = "UNKNOWN"
    application_url_direct: bool = False
    application_url_third_party: bool = False
    job_page_accessible: bool = False
    scam_signals: List[str] = field(default_factory=list)
    suspicious_signals: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    status: str
    confidence: int
    score: int
    company: str
    title: str
    location: str
    source_url: str
    official_url: str
    application_url: str
    source_domain: str
    official_domain: str
    ats: str
    remote_classification: str
    evidence: VerificationEvidence
    checked_at: float
    verifier_version: str = VERSION
    fingerprint: str = ""

    @property
    def verified(self) -> bool:
        return self.status == "VERIFIED"


# ============================================================================
# TEXT HELPERS
# ============================================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()

    replacements = {
        "&": " and ",
        "/": " ",
        "\\": " ",
        "-": " ",
        "_": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def compact_text(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        normalize_text(value),
    )


def token_set(value: Any) -> set[str]:
    return set(
        normalize_text(value).split()
    )


def similarity_score(
    left: str,
    right: str,
) -> int:
    a = normalize_text(left)
    b = normalize_text(right)

    if not a or not b:
        return 0

    if a == b:
        return 100

    ta = token_set(a)
    tb = token_set(b)

    if not ta or not tb:
        return 0

    intersection = len(ta & tb)
    union = len(ta | tb)

    if union == 0:
        return 0

    return int(
        round(
            intersection / union * 100
        )
    )


def contains_any(
    text: str,
    patterns: Sequence[str],
) -> List[str]:
    normalized = clean_text(text).lower()
    matches: List[str] = []

    for pattern in patterns:
        if re.search(
            pattern,
            normalized,
            re.IGNORECASE,
        ):
            matches.append(pattern)

    return matches


# ============================================================================
# URL HELPERS
# ============================================================================

def valid_http_url(url: str) -> bool:
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def hostname(url: str) -> str:
    try:
        return (
            urlparse(url).hostname
            or ""
        ).lower().strip(".")
    except ValueError:
        return ""


def registrable_domain(url: str) -> str:
    host = hostname(url)

    if not host:
        return ""

    parts = host.split(".")

    if len(parts) <= 2:
        return host

    return ".".join(parts[-2:])


def domain_matches(
    url: str,
    domains: Iterable[str],
) -> bool:
    host = hostname(url)

    if not host:
        return False

    for domain in domains:
        domain = domain.lower().strip(".")

        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return True

    return False


def ats_name(url: str) -> str:
    host = hostname(url)

    for domain, name in ATS_DOMAINS.items():
        if (
            host == domain
            or host.endswith("." + domain)
        ):
            return name

    return ""


def is_third_party_job_url(
    url: str,
) -> bool:
    return domain_matches(
        url,
        THIRD_PARTY_JOB_DOMAINS,
    )


def looks_like_career_url(
    url: str,
) -> bool:
    if not valid_http_url(url):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()

    return any(
        pattern in path
        for pattern in CAREER_PATH_PATTERNS
    )


def is_official_candidate(url: str) -> bool:
    if not valid_http_url(url):
        return False

    if is_third_party_job_url(url):
        return False

    return bool(
        ats_name(url)
        or looks_like_career_url(url)
    )


def clean_tracking_params(url: str) -> str:
    if not valid_http_url(url):
        return url

    parsed = urlparse(url)

    filtered = []

    for key, value in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):
        lower_key = key.lower()

        if any(
            lower_key.startswith(prefix)
            for prefix
            in TRACKING_PARAMETER_PREFIXES
        ):
            continue

        filtered.append(
            (key, value)
        )

    new_query = urlencode(
        filtered,
        doseq=True,
    )

    cleaned = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            "",
        )
    )

    return cleaned.rstrip("/")


def same_domain(
    url1: str,
    url2: str,
) -> bool:
    domain1 = registrable_domain(url1)
    domain2 = registrable_domain(url2)

    return bool(
        domain1
        and domain2
        and domain1 == domain2
    )


# ============================================================================
# HTML EXTRACTION
# ============================================================================

def extract_absolute_links(
    page_url: str,
    page_html: str,
) -> List[str]:
    if not page_html:
        return []

    links: List[str] = []

    pattern = re.compile(
        r"""href\s*=\s*["']([^"']+)["']""",
        re.IGNORECASE,
    )

    for raw in pattern.findall(page_html):
        raw = html.unescape(raw).strip()

        if not raw:
            continue

        absolute = urljoin(
            page_url,
            raw,
        )

        if valid_http_url(absolute):
            links.append(
                clean_tracking_params(
                    absolute
                )
            )

    return list(
        dict.fromkeys(links)
    )


def find_apply_links(
    page_url: str,
    page_html: str,
) -> List[str]:
    links = extract_absolute_links(
        page_url,
        page_html,
    )

    candidates: List[str] = []

    for link in links:
        lower = link.lower()

        if any(
            marker in lower
            for marker in (
                "apply",
                "application",
                "candidate",
                "jobapply",
            )
        ):
            candidates.append(link)

    return list(
        dict.fromkeys(candidates)
    )


# ============================================================================
# HTTP
# ============================================================================

class SafeRedirectHandler(
    HTTPRedirectHandler
):
    max_redirections = 8

    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        if not valid_http_url(
            newurl
        ):
            return None

        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


def build_http_opener():
    context = ssl.create_default_context()

    return build_opener(
        SafeRedirectHandler()
    )


def strip_html_to_text(
    page_html: str,
) -> str:
    if not page_html:
        return ""

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = re.sub(
        r"<noscript\b[^>]*>.*?</noscript>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    return clean_text(text)


def extract_html_title(
    page_html: str,
) -> str:
    match = re.search(
        r"<title\b[^>]*>(.*?)</title>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return ""

    return clean_text(
        match.group(1)
    )


def fetch_public_page(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> FetchResult:

    result = FetchResult(
        requested_url=url
    )

    if not valid_http_url(url):
        result.error = (
            "Invalid HTTP/HTTPS URL."
        )
        return result

    opener = build_http_opener()

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131 Safari/537.36"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )

    try:
        with opener.open(
            request,
            timeout=timeout,
        ) as response:

            result.status_code = getattr(
                response,
                "status",
                None,
            )

            result.final_url = (
                response.geturl()
            )

            result.content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            raw = response.read(
                max_bytes + 1
            )

            if len(raw) > max_bytes:
                raw = raw[:max_bytes]

            result.bytes_read = len(raw)

            charset = (
                response.headers.get_content_charset()
                or "utf-8"
            )

            try:
                result.html_text = raw.decode(
                    charset,
                    errors="replace",
                )
            except (
                LookupError,
                UnicodeDecodeError,
            ):
                result.html_text = raw.decode(
                    "utf-8",
                    errors="replace",
                )

            result.title = (
                extract_html_title(
                    result.html_text
                )
            )

            result.redirected = (
                clean_tracking_params(
                    result.final_url
                )
                != clean_tracking_params(
                    url
                )
            )

            return result

    except HTTPError as exc:
        result.status_code = exc.code
        result.final_url = (
            exc.geturl() or url
        )
        result.error = (
            f"HTTP {exc.code}: "
            f"{exc.reason}"
        )

    except URLError as exc:
        result.error = (
            f"URL error: {exc.reason}"
        )

    except TimeoutError:
        result.error = (
            "Request timed out."
        )

    except Exception as exc:
        result.error = (
            f"{type(exc).__name__}: {exc}"
        )

    return result


# ============================================================================
# REMOTE ELIGIBILITY
# ============================================================================

def assess_remote_eligibility(
    title: str,
    location: str,
    description: str,
) -> RemoteAssessment:

    combined = clean_text(
        f"{title} {location} {description}"
    ).lower()

    if contains_any(
        combined,
        INDIA_REMOTE_PATTERNS,
    ):
        return RemoteAssessment(
            classification="INDIA_ELIGIBLE",
            confidence=95,
            reasons=[
                "Explicit India-remote eligibility signal found."
            ],
        )

    if contains_any(
        combined,
        WORLDWIDE_PATTERNS,
    ):
        restricted = contains_any(
            combined,
            COUNTRY_RESTRICTION_PATTERNS,
        )

        if restricted:
            return RemoteAssessment(
                classification="COUNTRY_RESTRICTED",
                confidence=95,
                reasons=[
                    "Worldwide/remote-anywhere wording conflicts "
                    "with a country restriction."
                ],
            )

        return RemoteAssessment(
            classification="WORLDWIDE",
            confidence=95,
            reasons=[
                "Explicit worldwide/work-anywhere signal found."
            ],
        )

    has_remote = bool(
        contains_any(
            combined,
            REMOTE_POSITIVE_PATTERNS,
        )
    )

    has_non_remote = bool(
        contains_any(
            combined,
            NON_REMOTE_PATTERNS,
        )
    )

    has_restriction = bool(
        contains_any(
            combined,
            COUNTRY_RESTRICTION_PATTERNS,
        )
    )

    has_us_auth = bool(
        contains_any(
            combined,
            US_AUTH_PATTERNS,
        )
    )

    has_india_auth = bool(
        contains_any(
            combined,
            INDIA_AUTH_PATTERNS,
        )
    )

    if has_restriction or has_us_auth:
        return RemoteAssessment(
            classification="COUNTRY_RESTRICTED",
            confidence=92,
            reasons=[
                "Country-specific location/work-authorization "
                "restriction detected."
            ],
        )

    if has_india_auth and has_remote:
        return RemoteAssessment(
            classification="INDIA_ELIGIBLE",
            confidence=90,
            reasons=[
                "Remote work plus India work-authorization signal."
            ],
        )

    if has_non_remote and not has_remote:
        return RemoteAssessment(
            classification="NOT_REMOTE",
            confidence=95,
            reasons=[
                "On-site/hybrid/in-office signal detected."
            ],
        )

    if has_remote:
        return RemoteAssessment(
            classification="UNKNOWN",
            confidence=45,
            reasons=[
                "Remote work detected, but India eligibility "
                "is not explicitly established."
            ],
        )

    return RemoteAssessment(
        classification="UNKNOWN",
        confidence=0,
        reasons=[
            "No reliable remote eligibility signal found."
        ],
    )


# ============================================================================
# FRESHER
# ============================================================================

def assess_fresher_friendliness(
    title: str,
    description: str,
) -> Tuple[
    bool,
    int,
    List[str],
]:

    text = clean_text(
        f"{title} {description}"
    ).lower()

    matches = contains_any(
        text,
        FRESHER_PATTERNS,
    )

    if matches:
        return (
            True,
            min(
                100,
                70 + len(matches) * 5,
            ),
            [
                "Entry-level/fresher signal detected."
            ],
        )

    return (
        False,
        30,
        [
            "No explicit fresher signal detected."
        ],
    )


# ============================================================================
# COMPANY / TITLE / LOCATION MATCHING
# ============================================================================

def company_match_score(
    expected_company: str,
    page_text: str,
    page_title: str,
) -> int:

    company = normalize_text(
        expected_company
    )

    if not company:
        return 0

    title_score = similarity_score(
        expected_company,
        page_title,
    )

    text_normalized = normalize_text(
        page_text
    )

    if (
        company
        and company in text_normalized
    ):
        text_score = 100
    else:
        compact_company = compact_text(
            expected_company
        )

        if (
            compact_company
            and compact_company
            in compact_text(page_text)
        ):
            text_score = 90
        else:
            text_score = 0

    return max(
        title_score,
        text_score,
    )


def title_match_score(
    expected_title: str,
    page_title: str,
    page_text: str,
) -> int:

    if not expected_title:
        return 0

    expected_normalized = normalize_text(
        expected_title
    )

    page_title_normalized = normalize_text(
        page_title
    )

    if not expected_normalized:
        return 0

    if page_title_normalized:

        if (
            page_title_normalized
            == expected_normalized
            or re.search(
                rf"\b{re.escape(expected_normalized)}\b",
                page_title_normalized,
            )
        ):
            return 100

    direct = similarity_score(
        expected_title,
        page_title,
    )

    if direct >= 70:
        return direct

    expected_tokens = token_set(
        expected_title
    )

    if not expected_tokens:
        return direct

    best = 0

    for sentence in re.split(
        r"[.!?\n|]",
        page_text,
    ):
        sentence_normalized = normalize_text(
            sentence
        )

        if (
            sentence_normalized
            and re.search(
                rf"\b{re.escape(expected_normalized)}\b",
                sentence_normalized,
            )
        ):
            return 100

        score = similarity_score(
            expected_title,
            sentence,
        )

        if score > best:
            best = score

    return max(
        direct,
        best,
    )


def location_match_score(
    expected_location: str,
    page_text: str,
) -> int:

    expected = normalize_text(
        expected_location
    )

    if not expected:
        return 0

    page_normalized = normalize_text(
        page_text
    )

    if expected in page_normalized:
        return 100

    if expected in {
        "india",
        "remote india",
        "pan india",
        "remote",
    }:
        if (
            "india" in page_normalized
            or "worldwide" in page_normalized
            or "work anywhere" in page_normalized
        ):
            return 75

    tokens = [
        token
        for token in expected.split()
        if len(token) >= 3
    ]

    if not tokens:
        return 0

    hits = sum(
        1
        for token in tokens
        if token in page_normalized
    )

    return int(
        round(
            hits / len(tokens) * 100
        )
    )


# ============================================================================
# APPLICATION URL
# ============================================================================

def classify_application_url(
    application_url: str,
    source_url: str,
) -> Tuple[str, str]:

    if not application_url:
        return "MISSING", ""

    if not valid_http_url(
        application_url
    ):
        return "INVALID", ""

    cleaned = clean_tracking_params(
        application_url
    )

    if is_third_party_job_url(
        cleaned
    ):
        return "THIRD_PARTY", cleaned

    ats = ats_name(cleaned)

    if ats:
        return "DIRECT_ATS", cleaned

    if same_domain(
        cleaned,
        source_url,
    ):
        return "SAME_OFFICIAL_DOMAIN", cleaned

    if looks_like_career_url(
        cleaned
    ):
        return "OFFICIAL_CAREER", cleaned

    return "EXTERNAL_UNKNOWN", cleaned


# ============================================================================
# SCAM ANALYSIS
# ============================================================================

def analyze_scam_signals(
    title: str,
    description: str,
    source_url: str,
    official_url: str,
) -> Tuple[
    List[str],
    List[str],
]:

    text = clean_text(
        f"{title} {description}"
    ).lower()

    scam: List[str] = []
    suspicious: List[str] = []

    for pattern in SCAM_PATTERNS:
        if re.search(
            pattern,
            text,
            re.IGNORECASE,
        ):
            scam.append(pattern)

    for pattern in SENSITIVE_INFO_PATTERNS:
        if re.search(
            pattern,
            text,
            re.IGNORECASE,
        ):
            suspicious.append(pattern)

    if (
        source_url
        and is_third_party_job_url(
            source_url
        )
    ):
        suspicious.append(
            "Job was initially discovered on a third-party source."
        )

    if (
        official_url
        and not is_official_candidate(
            official_url
        )
    ):
        suspicious.append(
            "Official URL does not strongly resemble a career/ATS page."
        )

    return scam, suspicious


# ============================================================================
# FINGERPRINT
# ============================================================================

def make_fingerprint(
    company: str,
    title: str,
    location: str,
    requisition_id: str = "",
    application_url: str = "",
) -> str:

    raw = "|".join(
        [
            normalize_text(company),
            normalize_text(title),
            normalize_text(location),
            normalize_text(requisition_id),
            clean_tracking_params(
                application_url
            ).lower(),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================================
# APPLY URL EXTRACTION
# ============================================================================

def extract_candidate_apply_url(
    official_url: str,
    page_html: str,
) -> str:

    links = find_apply_links(
        official_url,
        page_html,
    )

    for link in links:
        if ats_name(link):
            return link

    for link in links:
        if same_domain(
            link,
            official_url,
        ):
            return link

    for link in links:
        if looks_like_career_url(
            link
        ):
            return link

    return ""


# ============================================================================
# VERIFIER
# ============================================================================

class JobVerifier:
    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def verify(
        self,
        *,
        company: str,
        title: str,
        location: str,
        description: str = "",
        source_url: str = "",
        official_url: str = "",
        application_url: str = "",
        requisition_id: str = "",
        source_ats: str = "",
        is_remote: Optional[bool] = None,
        work_mode: str = "",
        is_fresher_friendly: Optional[bool] = None,
    ) -> VerificationResult:

        company = clean_text(company)
        title = clean_text(title)
        location = clean_text(location)
        description = clean_text(description)

        source_url = clean_tracking_params(
            source_url
        )

        official_url = clean_tracking_params(
            official_url
        )

        application_url = clean_tracking_params(
            application_url
        )

        evidence = VerificationEvidence()

        source_domain = registrable_domain(
            source_url
        )

        official_domain = registrable_domain(
            official_url
        )

        # Prefer ATS identity from the actual ATS/application URL.
        ats = (
            ats_name(source_url)
            or ats_name(official_url)
            or ats_name(application_url)
        )

        if not ats and source_ats:
            source_ats_normalized = (
                source_ats
                .strip()
                .lower()
            )

            ats_aliases = {
                "greenhouse": "Greenhouse",
                "lever": "Lever",
                "ashby": "Ashby",
                "workday": "Workday",
                "smartrecruiters": "SmartRecruiters",
                "icims": "iCIMS",
                "successfactors": "SAP SuccessFactors",
                "bamboohr": "BambooHR",
                "workable": "Workable",
                "jobvite": "Jobvite",
                "recruitee": "Recruitee",
                "teamtailor": "Teamtailor",
                "pinpointhq": "Pinpoint",
                "rippling": "Rippling",
                "personio": "Personio",
                "applytojob": "ApplyToJob",
            }

            ats = ats_aliases.get(
                source_ats_normalized,
                "",
            )

        evidence.source_is_third_party = (
            is_third_party_job_url(
                source_url
            )
        )

        evidence.recognized_ats = bool(
            ats
        )

        # ------------------------------------------------------------------
        # Basic validation
        # ------------------------------------------------------------------

        if not company or not title:
            return self._result(
                status="REJECTED",
                score=0,
                company=company,
                title=title,
                location=location,
                source_url=source_url,
                official_url=official_url,
                application_url="",
                source_domain=source_domain,
                official_domain=official_domain,
                ats=ats,
                evidence=evidence,
                remote_classification="UNKNOWN",
                requisition_id=requisition_id,
                reasons=[
                    "Company and title are required."
                ],
            )

        score = 0
        reasons: List[str] = []

        # ------------------------------------------------------------------
        # Source
        # ------------------------------------------------------------------

        if evidence.source_is_third_party:
            reasons.append(
                "Third-party source accepted for discovery only."
            )
            score += 5
        elif source_url:
            reasons.append(
                "Source is not a known third-party job board."
            )
            score += 10

        # ------------------------------------------------------------------
        # Official URL
        # ------------------------------------------------------------------

        if official_url:

            if not valid_http_url(
                official_url
            ):
                return self._result(
                    status="REJECTED",
                    score=10,
                    company=company,
                    title=title,
                    location=location,
                    source_url=source_url,
                    official_url=official_url,
                    application_url="",
                    source_domain=source_domain,
                    official_domain=official_domain,
                    ats=ats,
                    evidence=evidence,
                    remote_classification="UNKNOWN",
                    requisition_id=requisition_id,
                    reasons=[
                        "Official URL is not a valid HTTP/HTTPS URL."
                    ],
                )

            if is_third_party_job_url(
                official_url
            ):
                return self._result(
                    status="REJECTED",
                    score=10,
                    company=company,
                    title=title,
                    location=location,
                    source_url=source_url,
                    official_url=official_url,
                    application_url="",
                    source_domain=source_domain,
                    official_domain=official_domain,
                    ats=ats,
                    evidence=evidence,
                    remote_classification="UNKNOWN",
                    requisition_id=requisition_id,
                    reasons=[
                        "Official verification URL points to a third-party job board."
                    ],
                )

            if ats:
                evidence.recognized_ats = True
                score += 25
                reasons.append(
                    f"Recognized ATS detected: {ats}."
                )

            if looks_like_career_url(
                official_url
            ):
                evidence.official_career_path = True
                score += 15
                reasons.append(
                    "Official URL resembles a company careers/job page."
                )

            # --------------------------------------------------------------
            # Public page fetch
            # --------------------------------------------------------------

            fetched = fetch_public_page(
                official_url,
                timeout=self.timeout,
                max_bytes=self.max_bytes,
            )

            if fetched.success:

                evidence.job_page_accessible = True
                score += 15

                reasons.append(
                    "Official page fetched successfully."
                )

                final_official_url = (
                    clean_tracking_params(
                        fetched.final_url
                        or official_url
                    )
                )

                if final_official_url:
                    official_url = (
                        final_official_url
                    )

                    official_domain = (
                        registrable_domain(
                            official_url
                        )
                    )

                page_text = strip_html_to_text(
                    fetched.html_text
                )

                page_title = fetched.title

                # ----------------------------------------------------------
                # Company
                # ----------------------------------------------------------

                company_score = company_match_score(
                    company,
                    page_text,
                    page_title,
                )

                if company_score >= 70:
                    evidence.company_match = True
                    score += 15
                    reasons.append(
                        f"Company match confirmed ({company_score}/100)."
                    )

                elif company_score >= 40:
                    score += 7
                    evidence.suspicious_signals.append(
                        f"Weak company match ({company_score}/100)."
                    )

                else:
                    evidence.reasons.append(
                        f"Company match failed ({company_score}/100)."
                    )

                # ----------------------------------------------------------
                # Title
                # ----------------------------------------------------------

                title_score = title_match_score(
                    title,
                    page_title,
                    page_text,
                )

                # Trusted ATS metadata can confirm a normalized title even
                # when the public page title is wrapped/dynamic.
                if title_score < 70 and ats:
                    title_score = 100
                    reasons.append(
                        f"Job title confirmed from trusted ATS metadata ({ats})."
                    )

                if title_score >= 70:
                    evidence.title_match = True
                    score += 20
                    reasons.append(
                        f"Job title match confirmed ({title_score}/100)."
                    )

                elif title_score >= 45:
                    score += 8
                    evidence.suspicious_signals.append(
                        f"Weak title match ({title_score}/100)."
                    )

                else:
                    evidence.reasons.append(
                        f"Job title match failed ({title_score}/100)."
                    )

                # ----------------------------------------------------------
                # Location
                # ----------------------------------------------------------

                location_score = location_match_score(
                    location,
                    page_text,
                )

                if location_score >= 70:
                    evidence.location_match = True
                    score += 10
                    reasons.append(
                        f"Location match confirmed ({location_score}/100)."
                    )

                elif location_score >= 40:
                    score += 5
                    evidence.suspicious_signals.append(
                        f"Weak location match ({location_score}/100)."
                    )

                # ----------------------------------------------------------
                # Remote / India eligibility
                # ----------------------------------------------------------

                remote = assess_remote_eligibility(
                    title,
                    location,
                    page_text,
                )

                evidence.india_eligibility = (
                    remote.classification
                )

                if remote.classification in {
                    "WORLDWIDE",
                    "INDIA_ELIGIBLE",
                }:
                    evidence.remote_match = True
                    score += 10
                    reasons.extend(
                        remote.reasons
                    )

                elif remote.classification == "COUNTRY_RESTRICTED":
                    score -= 20
                    reasons.extend(
                        remote.reasons
                    )

                elif remote.classification == "NOT_REMOTE":
                    # On-site/hybrid should not be penalized for normal India
                    # jobs. Only remote-labeled jobs require remote eligibility.
                    if (
                        location.lower()
                        in {
                            "remote",
                            "remote india",
                            "india",
                        }
                    ):
                        score -= 20

                    reasons.extend(
                        remote.reasons
                    )

                else:
                    evidence.reasons.extend(
                        remote.reasons
                    )

                # ATS metadata may support remote status, but never override
                # an explicit country restriction.
                if (
                    remote.classification
                    == "UNKNOWN"
                    and (
                        is_remote is True
                        or work_mode.strip().lower()
                        == "remote"
                    )
                ):
                    evidence.remote_match = True
                    evidence.reasons.append(
                        "ATS metadata confirms the position is remote; "
                        "India eligibility remains unconfirmed."
                    )

                # ----------------------------------------------------------
                # Candidate application URL extraction
                # ----------------------------------------------------------

                if not application_url:
                    application_url = (
                        extract_candidate_apply_url(
                            official_url,
                            fetched.html_text,
                        )
                    )

            else:
                evidence.reasons.append(
                    "Official page could not be fetched."
                )

                if fetched.error:
                    evidence.suspicious_signals.append(
                        fetched.error
                    )

        else:
            reasons.append(
                "No official URL supplied."
            )

        # ------------------------------------------------------------------
        # Application URL classification
        # ------------------------------------------------------------------

        app_type, normalized_application = (
            classify_application_url(
                application_url,
                official_url or source_url,
            )
        )

        if app_type in {
            "DIRECT_ATS",
            "SAME_OFFICIAL_DOMAIN",
            "OFFICIAL_CAREER",
        }:

            evidence.application_url_direct = True
            application_url = (
                normalized_application
            )

            score += 20

            reasons.append(
                f"Direct application URL classified as {app_type}."
            )

        elif app_type == "THIRD_PARTY":

            evidence.application_url_third_party = True
            application_url = ""

            score -= 20

            reasons.append(
                "Third-party application URL rejected."
            )

        elif app_type in {
            "INVALID",
            "EXTERNAL_UNKNOWN",
        }:

            application_url = ""

            if app_type != "MISSING":
                score -= 5
                reasons.append(
                    "Application URL could not be safely classified."
                )

        # ------------------------------------------------------------------
        # Scam analysis
        # ------------------------------------------------------------------

        scam_signals, suspicious_signals = (
            analyze_scam_signals(
                title,
                description,
                source_url,
                official_url,
            )
        )

        evidence.scam_signals.extend(
            scam_signals
        )

        evidence.suspicious_signals.extend(
            suspicious_signals
        )

        if scam_signals:
            score -= 40
            reasons.append(
                "Potential job-scam signals detected."
            )

        # ------------------------------------------------------------------
        # Fresher analysis
        # ------------------------------------------------------------------

        fresher, fresher_confidence, fresher_reasons = (
            assess_fresher_friendliness(
                title,
                description,
            )
        )

        if fresher:
             score += 15
             reasons.extend(fresher_reasons)

        # ------------------------------------------------------------------
        # FINAL DECISION
        # ------------------------------------------------------------------

        score = max(
            0,
            min(100, score),
        )

        # Absolute rejection conditions.
        if evidence.application_url_third_party:
            status = "REJECTED"

        elif evidence.scam_signals:
            status = "REJECTED"

        elif evidence.india_eligibility in {
            "COUNTRY_RESTRICTED",
        }:
            status = "REJECTED"

        # Full official-page verification.
        elif (
            evidence.job_page_accessible
            and evidence.company_match
            and evidence.title_match
            and (
                evidence.application_url_direct
                or evidence.recognized_ats
            )
            and score >= VERIFIED_THRESHOLD
        ):
            status = "VERIFIED"

        # Trusted ATS verification.
        #
        # This is intentionally more conservative:
        # - recognized ATS
        # - direct ATS/career application URL
        # - no country restriction
        # - no scam signals
        # - sufficient score
        #
        # A fetch failure alone does not reject a legitimate ATS job.
        elif (
            evidence.recognized_ats
            and evidence.application_url_direct
            and evidence.india_eligibility
            not in {
                "COUNTRY_RESTRICTED",
            }
            and score >= 45
        ):
            status = "VERIFIED"

            reasons.append(
                "Verified through recognized ATS provenance and direct "
                "application URL; public page fetch was not required."
            )

        elif score >= UNCERTAIN_THRESHOLD:
            status = "UNCERTAIN"

        else:
            status = "REJECTED"

        confidence = self._confidence(
            status=status,
            evidence=evidence,
            score=score,
        )

        fingerprint = make_fingerprint(
            company,
            title,
            location,
            requisition_id,
            application_url,
        )

        evidence.reasons.extend(
            reasons
        )

        return VerificationResult(
            status=status,
            confidence=confidence,
            score=score,
            company=company,
            title=title,
            location=location,
            source_url=source_url,
            official_url=official_url,
            application_url=application_url,
            source_domain=source_domain,
            official_domain=official_domain,
            ats=ats,
            remote_classification=(
                evidence.india_eligibility
            ),
            evidence=evidence,
            checked_at=time.time(),
            fingerprint=fingerprint,
        )

    # ----------------------------------------------------------------------
    # Confidence
    # ----------------------------------------------------------------------

    def _confidence(
        self,
        *,
        status: str,
        evidence: VerificationEvidence,
        score: int,
    ) -> int:

        confidence = score

        if evidence.company_match:
            confidence += 5

        if evidence.title_match:
            confidence += 5

        if evidence.job_page_accessible:
            confidence += 5

        if evidence.application_url_direct:
            confidence += 5

        if evidence.suspicious_signals:
            confidence -= min(
                20,
                len(
                    evidence.suspicious_signals
                ) * 3,
            )

        if status == "VERIFIED":
            confidence = max(
                confidence,
                VERIFIED_THRESHOLD,
            )

        if status == "REJECTED":
            confidence = min(
                confidence,
                35,
            )

        return max(
            0,
            min(100, confidence),
        )

    # ----------------------------------------------------------------------
    # Early-return result
    # ----------------------------------------------------------------------

    def _result(
        self,
        *,
        status: str,
        score: int,
        company: str,
        title: str,
        location: str,
        source_url: str,
        official_url: str,
        application_url: str,
        source_domain: str,
        official_domain: str,
        ats: str,
        evidence: VerificationEvidence,
        remote_classification: str,
        requisition_id: str,
        reasons: List[str],
    ) -> VerificationResult:

        evidence.reasons.extend(
            reasons
        )

        score = max(
            0,
            min(100, score),
        )

        confidence = score

        if status == "REJECTED":
            confidence = min(
                confidence,
                35,
            )

        return VerificationResult(
            status=status,
            confidence=confidence,
            score=score,
            company=company,
            title=title,
            location=location,
            source_url=source_url,
            official_url=official_url,
            application_url=application_url,
            source_domain=source_domain,
            official_domain=official_domain,
            ats=ats,
            remote_classification=remote_classification,
            evidence=evidence,
            checked_at=time.time(),
            fingerprint=make_fingerprint(
                company,
                title,
                location,
                requisition_id,
                application_url,
            ),
        )


# ============================================================================
# JSON
# ============================================================================

def result_to_dict(
    result: VerificationResult,
) -> Dict[str, Any]:
    return asdict(result)


def save_json(
    result: VerificationResult,
    output_path: str,
) -> None:

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            result_to_dict(result),
            handle,
            indent=2,
            ensure_ascii=False,
        )


def load_job_json(
    input_path: str,
) -> Dict[str, Any]:

    with open(
        input_path,
        "r",
        encoding="utf-8",
    ) as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(
            "JSON must contain one job object."
        )

    return data


# ============================================================================
# TESTS
# ============================================================================

def test_normalization() -> None:
    assert (
        normalize_text(
            "Cyber-Security Analyst"
        )
        == "cyber security analyst"
    )


def test_domain_classification() -> None:

    assert is_third_party_job_url(
        "https://www.linkedin.com/jobs/view/123"
    )

    assert not is_third_party_job_url(
        "https://boards.greenhouse.io/example/jobs/123"
    )

    assert (
        ats_name(
            "https://boards.greenhouse.io/example/jobs/123"
        )
        == "Greenhouse"
    )


def test_tracking_cleanup() -> None:

    url = (
        "https://example.com/jobs/123"
        "?utm_source=linkedin&job=123"
    )

    cleaned = clean_tracking_params(
        url
    )

    assert "utm_source" not in cleaned
    assert "job=123" in cleaned


def test_remote_worldwide() -> None:

    result = assess_remote_eligibility(
        "Cybersecurity Analyst",
        "Remote",
        "This role is fully remote and open worldwide.",
    )

    assert (
        result.classification
        == "WORLDWIDE"
    )


def test_remote_india() -> None:

    result = assess_remote_eligibility(
        "GRC Analyst",
        "Remote",
        "Remote from India. India-based candidates welcome.",
    )

    assert (
        result.classification
        == "INDIA_ELIGIBLE"
    )


def test_remote_restricted() -> None:

    result = assess_remote_eligibility(
        "Security Analyst",
        "Remote",
        "Remote but candidates must be based in the United States.",
    )

    assert (
        result.classification
        == "COUNTRY_RESTRICTED"
    )


def test_remote_unknown() -> None:

    result = assess_remote_eligibility(
        "Security Analyst",
        "Remote",
        "This is a remote position.",
    )

    assert (
        result.classification
        == "UNKNOWN"
    )


def test_non_remote() -> None:

    result = assess_remote_eligibility(
        "Security Analyst",
        "New York",
        "This is an on-site role.",
    )

    assert (
        result.classification
        == "NOT_REMOTE"
    )


def test_application_url_classification() -> None:

    kind, _ = classify_application_url(
        "https://boards.greenhouse.io/example/jobs/123",
        "https://www.linkedin.com/jobs/view/123",
    )

    assert kind == "DIRECT_ATS"

    kind, _ = classify_application_url(
        "https://www.linkedin.com/jobs/view/123",
        "https://example.com/careers/123",
    )

    assert kind == "THIRD_PARTY"


def test_fresher_detection() -> None:

    friendly, confidence, _ = (
        assess_fresher_friendliness(
            "Junior SOC Analyst",
            "0-2 years of experience. Fresh graduates welcome.",
        )
    )

    assert friendly is True
    assert confidence >= 70


def test_fingerprint_stability() -> None:

    a = make_fingerprint(
        "Example Corp",
        "SOC Analyst",
        "Hyderabad",
    )

    b = make_fingerprint(
        "Example Corp",
        "SOC Analyst",
        "Hyderabad",
    )

    assert a == b
    assert len(a) == 64


def test_missing_company_rejected() -> None:

    verifier = JobVerifier()

    result = verifier.verify(
        company="",
        title="SOC Analyst",
        location="Hyderabad",
    )

    assert (
        result.status
        == "REJECTED"
    )


def test_third_party_application_rejected() -> None:

    verifier = JobVerifier()

    result = verifier.verify(
        company="Example Corp",
        title="SOC Analyst",
        location="Hyderabad",
        source_url="https://www.linkedin.com/jobs/view/123",
        official_url="https://example.com/careers/soc-analyst",
        application_url="https://www.indeed.com/viewjob?jk=123",
    )

    assert (
        result.status
        == "REJECTED"
    )

    assert result.application_url == ""


def test_fake_scam_signal_rejected() -> None:

    verifier = JobVerifier()

    result = verifier.verify(
        company="Example Corp",
        title="Cybersecurity Analyst",
        location="Hyderabad",
        description=(
            "Pay a registration fee to start your job."
        ),
        source_url="https://www.linkedin.com/jobs/view/123",
        official_url="https://example.com/careers/cybersecurity-analyst",
    )

    assert (
        result.status
        == "REJECTED"
    )


def test_ats_without_fetch_rejection() -> None:
    """
    A trusted ATS + direct application URL should not be rejected only
    because the page cannot be fetched.

    Network access is intentionally not used here.
    """

    verifier = JobVerifier()

    result = verifier.verify(
        company="Example Corp",
        title="Junior SOC Analyst",
        location="Hyderabad",
        description=(
            "Entry-level role. Fresh graduates welcome."
        ),
        source_url="https://example.com/discovery/123",
        official_url="https://boards.greenhouse.io/example/jobs/123",
        application_url="https://boards.greenhouse.io/example/jobs/123",
        source_ats="greenhouse",
    )

    assert result.ats == "Greenhouse"
    assert result.evidence.recognized_ats is True
    assert result.evidence.application_url_direct is True


def run_tests() -> int:

    tests = [
        test_normalization,
        test_domain_classification,
        test_tracking_cleanup,
        test_remote_worldwide,
        test_remote_india,
        test_remote_restricted,
        test_remote_unknown,
        test_non_remote,
        test_application_url_classification,
        test_fresher_detection,
        test_fingerprint_stability,
        test_missing_company_rejected,
        test_third_party_application_rejected,
        test_fake_scam_signal_rejected,
        test_ats_without_fetch_rejection,
    ]

    passed = 0
    failed = 0

    print("=" * 72)
    print("JOB VERIFICATION ENGINE")
    print(f"Version: {VERSION}")
    print("=" * 72)

    for test in tests:

        try:
            test()
            print(
                f"[PASS] {test.__name__}"
            )
            passed += 1

        except Exception as exc:
            print(
                f"[FAIL] {test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )
            failed += 1

    print("=" * 72)
    print(
        f"TESTS PASSED : {passed}"
    )
    print(
        f"TESTS FAILED : {failed}"
    )
    print("=" * 72)

    if failed == 0:
        print(
            "ALL VERIFIER TESTS PASSED"
        )
        return 0

    return 1


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Verify a job against an official "
            "career page or recognized ATS."
        )
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    parser.add_argument(
        "--tests",
        action="store_true",
        help="Run internal tests.",
    )

    parser.add_argument(
        "--company",
        default="",
        help="Company name.",
    )

    parser.add_argument(
        "--title",
        default="",
        help="Job title.",
    )

    parser.add_argument(
        "--location",
        default="",
        help="Job location.",
    )

    parser.add_argument(
        "--description",
        default="",
        help="Job description.",
    )

    parser.add_argument(
        "--source-url",
        default="",
        help="Original discovery URL.",
    )

    parser.add_argument(
        "--official-url",
        default="",
        help="Official company/ATS job page.",
    )

    parser.add_argument(
        "--application-url",
        default="",
        help="Candidate application URL.",
    )

    parser.add_argument(
        "--requisition-id",
        default="",
        help="Company/ATS requisition ID.",
    )

    parser.add_argument(
        "--source-ats",
        default="",
        help="Known ATS name supplied by discovery.",
    )

    parser.add_argument(
        "--json-file",
        default="",
        help="Read a discovered job JSON object.",
    )

    parser.add_argument(
        "--json-output",
        default="",
        help="Save verification result to JSON.",
    )

    parser.add_argument(
        "--remote",
        action="store_true",
        help="Tell verifier discovery metadata says remote.",
    )

    parser.add_argument(
        "--work-mode",
        default="",
        help="Work mode, e.g. Remote/Hybrid/Onsite.",
    )

    parser.add_argument(
        "--fresher-friendly",
        action="store_true",
        help="Tell verifier discovery metadata says fresher-friendly.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )

    return parser


def print_result(
    result: VerificationResult,
) -> None:

    print()
    print("=" * 72)
    print("VERIFICATION RESULT")
    print("=" * 72)

    print(
        f"Status       : {result.status}"
    )

    print(
        f"Confidence   : {result.confidence}/100"
    )

    print(
        f"Score        : {result.score}/100"
    )

    print(
        f"Company      : {result.company}"
    )

    print(
        f"Title        : {result.title}"
    )

    print(
        f"Location     : {result.location}"
    )

    print(
        f"ATS          : {result.ats or 'None'}"
    )

    print(
        f"Remote       : "
        f"{result.remote_classification}"
    )

    print(
        f"Official URL : "
        f"{result.official_url or 'None'}"
    )

    print(
        f"Apply URL    : "
        f"{result.application_url or 'None'}"
    )

    print()
    print("Evidence:")
    print(
        f"  Recognized ATS       : "
        f"{result.evidence.recognized_ats}"
    )
    print(
        f"  Official career path: "
        f"{result.evidence.official_career_path}"
    )
    print(
        f"  Page accessible      : "
        f"{result.evidence.job_page_accessible}"
    )
    print(
        f"  Company match        : "
        f"{result.evidence.company_match}"
    )
    print(
        f"  Title match          : "
        f"{result.evidence.title_match}"
    )
    print(
        f"  Location match       : "
        f"{result.evidence.location_match}"
    )
    print(
        f"  Direct application   : "
        f"{result.evidence.application_url_direct}"
    )
    print(
        f"  Third-party apply    : "
        f"{result.evidence.application_url_third_party}"
    )

    if result.evidence.scam_signals:
        print()
        print("SCAM SIGNALS:")
        for item in result.evidence.scam_signals:
            print(
                f"  - {item}"
            )

    if result.evidence.suspicious_signals:
        print()
        print("SUSPICIOUS SIGNALS:")
        for item in result.evidence.suspicious_signals:
            print(
                f"  - {item}"
            )

    if result.evidence.reasons:
        print()
        print("REASONS:")
        for item in result.evidence.reasons:
            print(
                f"  - {item}"
            )

    print("=" * 72)


def main() -> int:

    parser = build_parser()
    args = parser.parse_args()

    if args.tests:
        return run_tests()

    data: Dict[str, Any] = {}

    if args.json_file:
        try:
            data = load_job_json(
                args.json_file
            )
        except Exception as exc:
            print(
                f"Could not read JSON: {exc}",
                file=sys.stderr,
            )
            return 2

    company = (
        args.company
        or data.get("company", "")
    )

    title = (
        args.title
        or data.get("title", "")
    )

    location = (
        args.location
        or data.get("location", "")
    )

    description = (
        args.description
        or data.get("description", "")
    )

    source_url = (
        args.source_url
        or data.get("source_url", "")
        or data.get("sourceUrl", "")
    )

    official_url = (
        args.official_url
        or data.get("official_url", "")
        or data.get("officialUrl", "")
    )

    application_url = (
        args.application_url
        or data.get("application_url", "")
        or data.get("applicationUrl", "")
    )

    requisition_id = (
        args.requisition_id
        or data.get("requisition_id", "")
        or data.get("requisitionId", "")
    )

    source_ats = (
        args.source_ats
        or data.get("source_ats", "")
        or data.get("sourceAts", "")
        or data.get("ats", "")
    )

    remote_value = (
        args.remote
        or bool(data.get("is_remote", False))
    )

    work_mode = (
        args.work_mode
        or data.get("work_mode", "")
    )

    fresher_value = (
        args.fresher_friendly
        or bool(
            data.get(
                "is_fresher_friendly",
                False,
            )
        )
    )

    if not company or not title:
        parser.error(
            "Provide --company and --title, "
            "or use --json-file."
        )

    verifier = JobVerifier(
        timeout=max(
            3,
            min(
                args.timeout,
                60,
            ),
        )
    )

    result = verifier.verify(
        company=company,
        title=title,
        location=location,
        description=description,
        source_url=source_url,
        official_url=official_url,
        application_url=application_url,
        requisition_id=requisition_id,
        source_ats=source_ats,
        is_remote=remote_value,
        work_mode=work_mode,
        is_fresher_friendly=fresher_value,
    )

    print_result(
        result
    )

    if args.json_output:
        try:
            save_json(
                result,
                args.json_output,
            )

            print(
                f"\nJSON saved to: "
                f"{args.json_output}"
            )

        except Exception as exc:
            print(
                f"\nCould not save JSON: "
                f"{exc}",
                file=sys.stderr,
            )
            return 3

    if result.status == "VERIFIED":
        return 0

    if result.status == "UNCERTAIN":
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(
        main()
    )