"""
Global Remote Job Eligibility Configuration
=============================================

Purpose:
    Classify foreign/international remote jobs for a candidate
    working from India.

Core rule:

    FOREIGN + REMOTE + INDIA ELIGIBLE
        -> potentially accepted

    FOREIGN + ON-SITE
        -> rejected

    FOREIGN + HYBRID
        -> rejected

    FOREIGN + REMOTE + COUNTRY RESTRICTED
        -> rejected

    FOREIGN + REMOTE + UNKNOWN ELIGIBILITY
        -> send to verification

IMPORTANT:
    "Remote" does NOT automatically mean worldwide.

The verification layer must inspect the original job
description before a job is marked as VERIFIED.
"""

from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass


# ============================================================
# VERSION
# ============================================================

GLOBAL_REMOTE_VERSION = "1.0.0"


# ============================================================
# ELIGIBILITY STATUS
# ============================================================

class RemoteEligibility(str, Enum):

    WORLDWIDE = "WORLDWIDE"

    INDIA_ELIGIBLE = "INDIA_ELIGIBLE"

    REGION_ELIGIBLE = "REGION_ELIGIBLE"

    COUNTRY_RESTRICTED = "COUNTRY_RESTRICTED"

    INDIA_RESTRICTED = "INDIA_RESTRICTED"

    NOT_REMOTE = "NOT_REMOTE"

    UNKNOWN = "UNKNOWN"


# ============================================================
# JOB SCOPE
# ============================================================

class JobScope(str, Enum):

    INDIA = "INDIA"

    INDIA_REMOTE = "INDIA_REMOTE"

    INDIA_PAN_INDIA = "INDIA_PAN_INDIA"

    GLOBAL_REMOTE = "GLOBAL_REMOTE"

    INTERNATIONAL_REMOTE = "INTERNATIONAL_REMOTE"

    FOREIGN_RESTRICTED = "FOREIGN_RESTRICTED"

    UNKNOWN = "UNKNOWN"


# ============================================================
# STRONG POSITIVE SIGNALS
# ============================================================

WORLDWIDE_POSITIVE_PATTERNS = [

    r"\bworldwide\b",

    r"\bwork\s+from\s+anywhere\b",

    r"\bwork\s+anywhere\b",

    r"\banywhere\s+in\s+the\s+world\b",

    r"\banywhere\s+around\s+the\s+world\b",

    r"\bopen\s+to\s+applicants\s+worldwide\b",

    r"\bopen\s+to\s+candidates\s+worldwide\b",

    r"\bhiring\s+worldwide\b",

    r"\bhire\s+worldwide\b",

    r"\bglobal\s+remote\b",

    r"\bremote\s*[-–—]\s*worldwide\b",

    r"\bremote\s+worldwide\b",

    r"\bremote\s+anywhere\b",

    r"\bremote\s+from\s+anywhere\b",

    r"\bremote\s+from\s+any\s+country\b",

    r"\bany\s+country\b",

    r"\ball\s+countries\b",

    r"\binternational\s+applicants\b",

    r"\binternational\s+candidates\b",

    r"\bglobal\s+applicants\b",

    r"\bglobal\s+candidates\b",
]


# ============================================================
# INDIA POSITIVE SIGNALS
# ============================================================

INDIA_POSITIVE_PATTERNS = [

    r"\bindia\b",

    r"\bremote\s*[-–—]\s*india\b",

    r"\bremote\s+india\b",

    r"\bindia\s*[-–—]\s*remote\b",

    r"\bwork\s+from\s+india\b",

    r"\bworking\s+from\s+india\b",

    r"\bhiring\s+in\s+india\b",

    r"\bhire\s+in\s+india\b",

    r"\bindia\s+eligible\b",

    r"\bindia\s+is\s+eligible\b",

    r"\bindian\s+applicants\b",

    r"\bindian\s+candidates\b",
]


# ============================================================
# REMOTE POSITIVE SIGNALS
# ============================================================

REMOTE_POSITIVE_PATTERNS = [

    r"\bremote\b",

    r"\bfully\s+remote\b",

    r"\b100%\s+remote\b",

    r"\bwork\s+from\s+home\b",

    r"\bwfh\b",

    r"\bdistributed\s+team\b",

    r"\bremote-first\b",

    r"\bremote\s+first\b",

    r"\bhome-based\b",

    r"\bhome\s+based\b",
]


# ============================================================
# HYBRID / ON-SITE NEGATIVE SIGNALS
# ============================================================

NON_REMOTE_PATTERNS = [

    r"\bon[- ]site\b",

    r"\bonsite\b",

    r"\bin[- ]office\b",

    r"\bin\s+office\b",

    r"\boffice[- ]based\b",

    r"\bmust\s+work\s+from\s+office\b",

    r"\brequires\s+office\s+attendance\b",

    r"\bhybrid\b",

    r"\bhybrid\s+role\b",

    r"\bhybrid\s+position\b",

    r"\bhybrid\s+schedule\b",
]


# ============================================================
# COUNTRY / REGION RESTRICTIONS
# ============================================================

COUNTRY_RESTRICTION_PATTERNS = [

    r"\bus\s+only\b",

    r"\busa\s+only\b",

    r"\bunited\s+states\s+only\b",

    r"\bremote\s*[-–—]\s*us\b",

    r"\bremote\s*\(\s*us\s*\)",

    r"\bremote\s+within\s+the\s+us\b",

    r"\bmust\s+reside\s+in\s+the\s+us\b",

    r"\bmust\s+be\s+located\s+in\s+the\s+us\b",

    r"\bcanada\s+only\b",

    r"\bremote\s*[-–—]\s*canada\b",

    r"\bmust\s+reside\s+in\s+canada\b",

    r"\buk\s+only\b",

    r"\bunited\s+kingdom\s+only\b",

    r"\bremote\s*[-–—]\s*uk\b",

    r"\beurope\s+only\b",

    r"\beu\s+only\b",

    r"\bremote\s*[-–—]\s*eu\b",

    r"\bremote\s*[-–—]\s*europe\b",

    r"\bemea\s+only\b",

    r"\bremote\s*[-–—]\s*emea\b",

    r"\bapac\s+only\b",

    r"\bremote\s*[-–—]\s*apac\b",

    r"\blatam\s+only\b",

    r"\bremote\s*[-–—]\s*latam\b",
]


# ============================================================
# INDIA RESTRICTION PATTERNS
# ============================================================

INDIA_RESTRICTION_PATTERNS = [

    r"\bnot\s+available\s+in\s+india\b",

    r"\bnot\s+open\s+to\s+india\b",

    r"\bindia\s+not\s+eligible\b",

    r"\bindia\s+is\s+not\s+eligible\b",

    r"\bexcluding\s+india\b",

    r"\bexcept\s+india\b",

    r"\bno\s+hiring\s+in\s+india\b",
]


# ============================================================
# WORK AUTHORIZATION RESTRICTIONS
# ============================================================

WORK_AUTH_RESTRICTION_PATTERNS = [

    r"\bmust\s+be\s+authorized\s+to\s+work\s+in\s+the\s+us\b",

    r"\bmust\s+have\s+us\s+work\s+authorization\b",

    r"\bus\s+work\s+authorization\s+required\b",

    r"\bmust\s+have\s+the\s+right\s+to\s+work\s+in\s+the\s+us\b",

    r"\bwork\s+authorization\s+required\b",

    r"\bright\s+to\s+work\s+required\b",

    r"\bno\s+visa\s+sponsorship\b",
]


# ============================================================
# TIMEZONE RESTRICTIONS
# ============================================================

TIMEZONE_PATTERNS = [

    r"\bus\s+time\s+zones?\s+only\b",

    r"\bpst\s+only\b",

    r"\best\s+only\b",

    r"\bcst\s+only\b",

    r"\bmst\s+only\b",

    r"\beuropean\s+time\s+zones?\s+only\b",

    r"\beu\s+time\s+zones?\s+only\b",
]


# ============================================================
# RESULT MODEL
# ============================================================

@dataclass
class EligibilityResult:

    eligibility: RemoteEligibility

    job_scope: JobScope

    is_remote: bool

    india_allowed: bool | None

    confidence: int

    matched_positive_signals: list[str]

    matched_negative_signals: list[str]

    reasons: list[str]

    requires_verification: bool

    def to_dict(self) -> dict:

        return {
            "eligibility": self.eligibility.value,
            "job_scope": self.job_scope.value,
            "is_remote": self.is_remote,
            "india_allowed": self.india_allowed,
            "confidence": self.confidence,
            "matched_positive_signals": (
                self.matched_positive_signals
            ),
            "matched_negative_signals": (
                self.matched_negative_signals
            ),
            "reasons": self.reasons,
            "requires_verification": (
                self.requires_verification
            ),
        }


# ============================================================
# TEXT MATCHING
# ============================================================

def clean_text(text: str | None) -> str:

    if not text:
        return ""

    return " ".join(
        str(text).lower().split()
    )


def find_matches(
    text: str,
    patterns: list[str],
) -> list[str]:

    matches: list[str] = []

    for pattern in patterns:

        try:

            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                matches.append(pattern)

        except re.error:
            continue

    return matches


# ============================================================
# REMOTE DETECTION
# ============================================================

def detect_remote(text: str) -> tuple[bool, list[str]]:

    remote_matches = find_matches(
        text,
        REMOTE_POSITIVE_PATTERNS,
    )

    non_remote_matches = find_matches(
        text,
        NON_REMOTE_PATTERNS,
    )

    # Hybrid/on-site overrides generic remote signals.
    if non_remote_matches:

        return False, non_remote_matches

    return bool(remote_matches), remote_matches


# ============================================================
# WORLDWIDE DETECTION
# ============================================================

def detect_worldwide(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        WORLDWIDE_POSITIVE_PATTERNS,
    )


# ============================================================
# INDIA DETECTION
# ============================================================

def detect_india_positive(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        INDIA_POSITIVE_PATTERNS,
    )


def detect_india_restrictions(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        INDIA_RESTRICTION_PATTERNS,
    )


# ============================================================
# COUNTRY RESTRICTION DETECTION
# ============================================================

def detect_country_restrictions(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        COUNTRY_RESTRICTION_PATTERNS,
    )


# ============================================================
# WORK AUTHORIZATION
# ============================================================

def detect_work_auth_restrictions(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        WORK_AUTH_RESTRICTION_PATTERNS,
    )


# ============================================================
# TIMEZONE RESTRICTIONS
# ============================================================

def detect_timezone_restrictions(
    text: str,
) -> list[str]:

    return find_matches(
        text,
        TIMEZONE_PATTERNS,
    )


# ============================================================
# MAIN CLASSIFIER
# ============================================================

def classify_remote_eligibility(
    title: str = "",
    location: str = "",
    description: str = "",
) -> EligibilityResult:
    """
    Classify whether a foreign remote job can potentially
    be worked from India.

    IMPORTANT:

        This is a RULE-BASED PRE-FILTER.

        It is NOT final verification.

    The original job listing must still be checked.
    """

    combined_text = clean_text(
        f"{title} {location} {description}"
    )

    matched_positive: list[str] = []
    matched_negative: list[str] = []
    reasons: list[str] = []

    # --------------------------------------------------------
    # Detect remote
    # --------------------------------------------------------

    is_remote, remote_signals = detect_remote(
        combined_text
    )

    matched_positive.extend(remote_signals)

    non_remote_signals = find_matches(
        combined_text,
        NON_REMOTE_PATTERNS,
    )

    matched_negative.extend(
        non_remote_signals
    )

    if not is_remote:

        return EligibilityResult(
            eligibility=RemoteEligibility.NOT_REMOTE,
            job_scope=JobScope.FOREIGN_RESTRICTED,
            is_remote=False,
            india_allowed=False,
            confidence=95,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=[
                "Job does not appear to be fully remote."
            ],
            requires_verification=False,
        )

    # --------------------------------------------------------
    # India restriction
    # --------------------------------------------------------

    india_restrictions = detect_india_restrictions(
        combined_text
    )

    if india_restrictions:

        matched_negative.extend(
            india_restrictions
        )

        return EligibilityResult(
            eligibility=RemoteEligibility.INDIA_RESTRICTED,
            job_scope=JobScope.FOREIGN_RESTRICTED,
            is_remote=True,
            india_allowed=False,
            confidence=95,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=[
                "Listing contains a restriction excluding India."
            ],
            requires_verification=True,
        )

    # --------------------------------------------------------
    # Country restrictions
    # --------------------------------------------------------

    country_restrictions = detect_country_restrictions(
        combined_text
    )

    if country_restrictions:

        matched_negative.extend(
            country_restrictions
        )

        return EligibilityResult(
            eligibility=RemoteEligibility.COUNTRY_RESTRICTED,
            job_scope=JobScope.FOREIGN_RESTRICTED,
            is_remote=True,
            india_allowed=False,
            confidence=90,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=[
                "Job appears to be restricted to "
                "another country or region."
            ],
            requires_verification=True,
        )

    # --------------------------------------------------------
    # Work authorization
    # --------------------------------------------------------

    work_auth = detect_work_auth_restrictions(
        combined_text
    )

    if work_auth:

        matched_negative.extend(
            work_auth
        )

        return EligibilityResult(
            eligibility=RemoteEligibility.COUNTRY_RESTRICTED,
            job_scope=JobScope.FOREIGN_RESTRICTED,
            is_remote=True,
            india_allowed=False,
            confidence=85,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=[
                "Work authorization appears restricted "
                "to a specific country."
            ],
            requires_verification=True,
        )

    # --------------------------------------------------------
    # Worldwide
    # --------------------------------------------------------

    worldwide_signals = detect_worldwide(
        combined_text
    )

    if worldwide_signals:

        matched_positive.extend(
            worldwide_signals
        )

        reasons.append(
            "Listing contains a worldwide or "
            "work-from-anywhere signal."
        )

        # India positive signals increase confidence.
        india_signals = detect_india_positive(
            combined_text
        )

        if india_signals:

            matched_positive.extend(
                india_signals
            )

            reasons.append(
                "Listing explicitly references India eligibility."
            )

            confidence = 98

        else:

            confidence = 90

        return EligibilityResult(
            eligibility=RemoteEligibility.WORLDWIDE,
            job_scope=JobScope.GLOBAL_REMOTE,
            is_remote=True,
            india_allowed=True,
            confidence=confidence,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=reasons,
            requires_verification=True,
        )

    # --------------------------------------------------------
    # India explicitly allowed
    # --------------------------------------------------------

    india_signals = detect_india_positive(
        combined_text
    )

    if india_signals:

        matched_positive.extend(
            india_signals
        )

        return EligibilityResult(
            eligibility=RemoteEligibility.INDIA_ELIGIBLE,
            job_scope=JobScope.INTERNATIONAL_REMOTE,
            is_remote=True,
            india_allowed=True,
            confidence=95,
            matched_positive_signals=matched_positive,
            matched_negative_signals=matched_negative,
            reasons=[
                "Remote job explicitly references "
                "India eligibility."
            ],
            requires_verification=True,
        )

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    reasons.append(
        "Job is remote, but India/global eligibility "
        "was not explicitly established."
    )

    return EligibilityResult(
        eligibility=RemoteEligibility.UNKNOWN,
        job_scope=JobScope.UNKNOWN,
        is_remote=True,
        india_allowed=None,
        confidence=40,
        matched_positive_signals=matched_positive,
        matched_negative_signals=matched_negative,
        reasons=reasons,
        requires_verification=True,
    )


# ============================================================
# ACCEPTANCE RULE
# ============================================================

def should_accept_for_india(
    result: EligibilityResult,
) -> bool:
    """
    Determine whether the job is safe to continue
    into the verification pipeline.

    VERIFIED acceptance happens later.

    We allow:
        WORLDWIDE
        INDIA_ELIGIBLE

    We reject:
        NOT_REMOTE
        COUNTRY_RESTRICTED
        INDIA_RESTRICTED

    UNKNOWN goes to verification.
    """

    if result.eligibility in {
        RemoteEligibility.WORLDWIDE,
        RemoteEligibility.INDIA_ELIGIBLE,
    }:
        return True

    if result.eligibility == RemoteEligibility.UNKNOWN:
        return True

    return False


# ============================================================
# FINAL VERIFICATION RULE
# ============================================================

def is_verified_india_remote(
    result: EligibilityResult,
) -> bool:
    """
    Strict final acceptance rule.

    Only explicit worldwide or India-eligible
    results can become verified.

    UNKNOWN is NOT verified.
    """

    return result.eligibility in {
        RemoteEligibility.WORLDWIDE,
        RemoteEligibility.INDIA_ELIGIBLE,
    }


# ============================================================
# TEST CASES
# ============================================================

TEST_CASES = [

    {
        "name": "Worldwide",
        "title": "Cybersecurity Analyst",
        "location": "Remote - Worldwide",
        "description": "",
        "expected": RemoteEligibility.WORLDWIDE,
    },

    {
        "name": "Work Anywhere",
        "title": "Security Engineer",
        "location": "Work from anywhere",
        "description": "",
        "expected": RemoteEligibility.WORLDWIDE,
    },

    {
        "name": "India Eligible",
        "title": "GRC Analyst",
        "location": "Remote",
        "description": "Candidates can work from India.",
        "expected": RemoteEligibility.INDIA_ELIGIBLE,
    },

    {
        "name": "US Only",
        "title": "Security Analyst",
        "location": "Remote - US",
        "description": "Must reside in the United States.",
        "expected": RemoteEligibility.COUNTRY_RESTRICTED,
    },

    {
        "name": "Canada Only",
        "title": "SOC Analyst",
        "location": "Remote - Canada",
        "description": "",
        "expected": RemoteEligibility.COUNTRY_RESTRICTED,
    },

    {
        "name": "Hybrid",
        "title": "GRC Analyst",
        "location": "Hybrid - London",
        "description": "",
        "expected": RemoteEligibility.NOT_REMOTE,
    },

    {
        "name": "On Site",
        "title": "Security Engineer",
        "location": "New York",
        "description": "On-site position.",
        "expected": RemoteEligibility.NOT_REMOTE,
    },

    {
        "name": "Unknown Remote",
        "title": "Security Analyst",
        "location": "Remote",
        "description": "Flexible remote position.",
        "expected": RemoteEligibility.UNKNOWN,
    },
]


# ============================================================
# SELF TEST
# ============================================================

def run_tests() -> bool:

    print("=" * 72)
    print("GLOBAL REMOTE ELIGIBILITY TEST")
    print("=" * 72)

    passed = 0
    failed = 0

    for test in TEST_CASES:

        result = classify_remote_eligibility(
            title=test["title"],
            location=test["location"],
            description=test["description"],
        )

        expected = test["expected"]

        if result.eligibility == expected:

            print(
                f"✅ {test['name']:<20} "
                f"{result.eligibility.value}"
            )

            passed += 1

        else:

            print(
                f"❌ {test['name']:<20} "
                f"expected={expected.value} "
                f"got={result.eligibility.value}"
            )

            failed += 1

    print("-" * 72)

    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:

        print("✅ ALL TESTS PASSED")

        return True

    print("❌ SOME TESTS FAILED")

    return False


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    success = run_tests()

    raise SystemExit(
        0 if success else 1
    )