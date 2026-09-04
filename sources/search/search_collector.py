"""
Job Intelligence Agent
Search Collector v3.1.0

Reads discovery queries, performs public web searches,
extracts candidate job URLs, deduplicates them, and
writes data/search_results.json.

Safety:
- Public pages only
- No login
- No CAPTCHA bypass
- No authentication bypass
- No anti-bot bypass
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "3.1.0"

DEFAULT_TIMEOUT = 20
DEFAULT_DELAY = 2.0
DEFAULT_MAX_QUERIES = 20
DEFAULT_MAX_RESULTS = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ============================================================
# SEARCH ENGINE DOMAINS
# ============================================================

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "google.co.in",
    "bing.com",
    "search.yahoo.com",
    "duckduckgo.com",
}


# ============================================================
# JOB DOMAINS
# ============================================================

ATS_DOMAINS = {
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "icims.com",
    "successfactors.com",
    "bamboohr.com",
    "workable.com",
    "jobvite.com",
    "recruitee.com",
    "teamtailor.com",
    "pinpointhq.com",
    "rippling.com",
    "personio.com",
}


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
    "adzuna.com",
    "careerbuilder.com",
    "talent.com",
    "freshersworld.com",
    "fresherslive.com",
    "hirist.tech",
    "instahyre.com",
    "apna.co",
    "workindia.in",
}


# ============================================================
# TRACKING PARAMETERS
# ============================================================

TRACKING_PARAMETERS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "src",
}


# ============================================================
# BLOCK SIGNALS
# ============================================================

BLOCK_STATUS_CODES = {
    403,
    429,
    503,
}


BLOCK_SIGNALS = {
    "captcha",
    "verify you are human",
    "unusual traffic",
    "automated queries",
    "robot check",
    "access denied",
    "too many requests",
    "security check",
    "are you a robot",
}


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SearchResult:
    query: str
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    engine: str = ""
    rank: int = 0
    result_type: str = "other"
    discovered_at: str = ""
    fingerprint: str = ""


@dataclass
class CollectorStats:
    queries_requested: int = 0
    queries_completed: int = 0
    blocked_queries: int = 0
    failed_queries: int = 0
    raw_results: int = 0
    unique_results: int = 0
    errors: int = 0
    by_engine: dict[str, int] = field(default_factory=dict)
    by_domain: dict[str, int] = field(default_factory=dict)


# ============================================================
# TEXT
# ============================================================

def normalize_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    result = unescape(
        str(value)
    )

    result = re.sub(
        r"\s+",
        " ",
        result,
    )

    return result.strip()


def normalize_title(
    value: Any,
) -> str:
    title = normalize_text(
        value
    )

    for suffix in (
        " - Google Search",
        " | Google Search",
        " - Bing",
    ):
        if title.endswith(suffix):
            title = title[
                : -len(suffix)
            ].strip()

    return title


# ============================================================
# URL
# ============================================================

def extract_domain(
    url: str,
) -> str:

    try:
        hostname = (
            urlparse(url).hostname
            or ""
        ).lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:
        return ""


def normalize_url(
    url: str,
) -> str:

    if not url:
        return ""

    url = unescape(
        str(url)
    ).strip()

    if url.startswith("//"):
        url = "https:" + url

    try:
        parsed = urlparse(
            url
        )

        if parsed.scheme.lower() not in {
            "http",
            "https",
        }:
            return ""

        hostname = (
            parsed.hostname
            or ""
        ).lower()

        if not hostname:
            return ""

        if hostname.startswith("www."):
            hostname = hostname[4:]

        query_values = parse_qs(
            parsed.query,
            keep_blank_values=True,
        )

        clean_query: dict[str, str] = {}

        for key, values in query_values.items():

            if (
                key.lower()
                in TRACKING_PARAMETERS
            ):
                continue

            clean_query[key] = (
                values[-1]
                if values
                else ""
            )

        path = (
            parsed.path
            or "/"
        )

        return urlparse(
            ""
        )._replace(
            scheme=parsed.scheme.lower(),
            netloc=hostname,
            path=path,
            query=urlencode(
                clean_query
            ),
            fragment="",
        ).geturl()

    except Exception:
        return ""


def classify_url(
    url: str,
) -> str:

    hostname = extract_domain(
        url
    )

    if not hostname:
        return "unknown"

    for candidate in ATS_DOMAINS:

        if (
            hostname == candidate
            or hostname.endswith(
                "." + candidate
            )
        ):
            return "ats"

    for candidate in THIRD_PARTY_JOB_DOMAINS:

        if (
            hostname == candidate
            or hostname.endswith(
                "." + candidate
            )
        ):
            return "third_party_job"

    for candidate in SEARCH_ENGINE_DOMAINS:

        if (
            hostname == candidate
            or hostname.endswith(
                "." + candidate
            )
        ):
            return "search_engine"

    return "other"


# ============================================================
# SEARCH URLS
# ============================================================

def build_google_url(
    query: str,
) -> str:

    return (
        "https://www.google.com/search?"
        + urlencode(
            {
                "q": query,
                "num": "20",
                "hl": "en",
                "gl": "in",
            }
        )
    )


def build_bing_url(
    query: str,
) -> str:

    return (
        "https://www.bing.com/search?"
        + urlencode(
            {
                "q": query,
                "count": "20",
                "setlang": "en-IN",
            }
        )
    )


# ============================================================
# BLOCK DETECTION
# ============================================================

def is_blocked_page(
    html: str,
    status_code: int,
) -> bool:

    if status_code in BLOCK_STATUS_CODES:
        return True

    if not html:
        return True

    lowered = html.lower()

    for signal in BLOCK_SIGNALS:

        if signal in lowered:
            return True

    return False


# ============================================================
# HTTP
# ============================================================

def fetch_page(
    url: str,
    timeout: int,
) -> tuple[str, int, str]:

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )

        html = (
            response.text
            or ""
        )

        if is_blocked_page(
            html,
            response.status_code,
        ):
            return (
                html,
                response.status_code,
                "BLOCKED",
            )

        if response.status_code >= 400:
            return (
                html,
                response.status_code,
                "ERROR",
            )

        return (
            html,
            response.status_code,
            "OK",
        )

    except requests.RequestException as exc:

        return (
            "",
            0,
            f"ERROR:{exc}",
        )


# ============================================================
# GOOGLE REDIRECT
# ============================================================

def unwrap_google_url(
    href: str,
) -> str:

    href = unescape(
        href
    ).strip()

    if not href:
        return ""

    if href.startswith("//"):
        href = "https:" + href

    if (
        href.startswith("/url?")
        or href.startswith(
            "https://www.google.com/url?"
        )
    ):

        params = parse_qs(
            urlparse(href).query
        )

        for key in (
            "q",
            "url",
        ):

            values = params.get(
                key,
                [],
            )

            if values:

                return normalize_url(
                    unquote(
                        values[0]
                    )
                )

    return normalize_url(
        href
    )


# ============================================================
# BING REDIRECT
# ============================================================

def unwrap_bing_url(
    href: str,
) -> str:

    href = unescape(
        href
    ).strip()

    if not href:
        return ""

    if href.startswith("//"):
        href = "https:" + href

    try:

        parsed = urlparse(
            href
        )

        hostname = (
            parsed.hostname
            or ""
        ).lower()

        if (
            hostname in {
                "bing.com",
                "www.bing.com",
            }
            and parsed.path.startswith(
                "/ck/a"
            )
        ):

            params = parse_qs(
                parsed.query
            )

            values = params.get(
                "u",
                [],
            )

            if values:

                encoded = values[0]

                if encoded.startswith(
                    "a1"
                ):
                    encoded = encoded[2:]

                decoded = unquote(
                    encoded
                )

                if decoded.startswith(
                    (
                        "http://",
                        "https://",
                    )
                ):

                    return normalize_url(
                        decoded
                    )

        return normalize_url(
            href
        )

    except Exception:
        return normalize_url(
            href
        )


# ============================================================
# GENERIC RESULT EXTRACTION
# ============================================================

def extract_generic_results(
    soup: BeautifulSoup,
    query: str,
    engine: str,
    limit: int,
) -> list[dict[str, Any]]:

    results: list[
        dict[str, Any]
    ] = []

    seen_urls: set[str] = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        href = anchor.get(
            "href",
            "",
        )

        if engine == "google":
            url = unwrap_google_url(
                href
            )
        else:
            url = unwrap_bing_url(
                href
            )

        if not url:
            continue

        if (
            classify_url(url)
            == "search_engine"
        ):
            continue

        if url in seen_urls:
            continue

        heading = anchor.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
            ]
        )

        if heading:

            title = normalize_title(
                heading.get_text(
                    " ",
                    strip=True,
                )
            )

        else:

            title = normalize_title(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

        if (
            len(title) < 4
            or len(title) > 300
        ):
            continue

        lowered = title.lower()

        if lowered in {
            "images",
            "videos",
            "news",
            "maps",
            "shopping",
            "more",
            "settings",
            "tools",
            "sign in",
            "next",
            "previous",
        }:
            continue

        parent = anchor.parent

        snippet = ""

        if parent:

            snippet = normalize_text(
                parent.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(snippet) > 500:
                snippet = snippet[:500]

        results.append(
            {
                "query": query,
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )

        seen_urls.add(
            url
        )

        if len(results) >= limit:
            break

    return results


# ============================================================
# GOOGLE PARSER
# ============================================================

def parse_google_results(
    html: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:

    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    results: list[
        dict[str, Any]
    ] = []

    seen_urls: set[str] = set()

    selectors = (
        "div.MjjYud",
        "div.tF2Cxc",
        "div.g",
        "div[data-snhf]",
    )

    nodes = []

    for selector in selectors:

        found = soup.select(
            selector
        )

        if found:
            nodes.extend(
                found
            )

    for node in nodes:

        heading = node.find(
            "h3"
        )

        if heading is None:
            continue

        url = ""

        for anchor in node.find_all(
            "a",
            href=True,
        ):

            candidate = (
                unwrap_google_url(
                    anchor.get(
                        "href",
                        "",
                    )
                )
            )

            if not candidate:
                continue

            if (
                classify_url(
                    candidate
                )
                == "search_engine"
            ):
                continue

            url = candidate
            break

        if not url:
            continue

        if url in seen_urls:
            continue

        title = normalize_title(
            heading.get_text(
                " ",
                strip=True,
            )
        )

        if not title:
            continue

        snippet_node = (
            node.select_one(
                ".VwiC3b"
            )
            or node.select_one(
                ".yXK7lf"
            )
            or node.select_one(
                ".b_caption p"
            )
        )

        snippet = ""

        if snippet_node:

            snippet = normalize_text(
                snippet_node.get_text(
                    " ",
                    strip=True,
                )
            )

        results.append(
            {
                "query": query,
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )

        seen_urls.add(
            url
        )

        if len(results) >= limit:
            return results

    # --------------------------------------------------------
    # GENERIC FALLBACK
    # --------------------------------------------------------

    fallback = (
        extract_generic_results(
            soup,
            query,
            "google",
            limit,
        )
    )

    for item in fallback:

        if item["url"] in seen_urls:
            continue

        results.append(
            item
        )

        seen_urls.add(
            item["url"]
        )

        if len(results) >= limit:
            break

    return results


# ============================================================
# BING PARSER
# ============================================================

def parse_bing_results(
    html: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:

    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    results: list[
        dict[str, Any]
    ] = []

    seen_urls: set[str] = set()

    nodes = soup.select(
        "li.b_algo"
    )

    for node in nodes:

        anchor = node.select_one(
            "h2 a[href]"
        )

        if anchor is None:
            continue

        url = unwrap_bing_url(
            anchor.get(
                "href",
                "",
            )
        )

        if not url:
            continue

        if (
            classify_url(url)
            == "search_engine"
        ):
            continue

        if url in seen_urls:
            continue

        title = normalize_title(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not title:
            continue

        snippet_node = (
            node.select_one(
                ".b_caption p"
            )
            or node.select_one(
                "p"
            )
        )

        snippet = ""

        if snippet_node:

            snippet = normalize_text(
                snippet_node.get_text(
                    " ",
                    strip=True,
                )
            )

        results.append(
            {
                "query": query,
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )

        seen_urls.add(
            url
        )

        if len(results) >= limit:
            return results

    # --------------------------------------------------------
    # GENERIC FALLBACK
    # --------------------------------------------------------

    fallback = (
        extract_generic_results(
            soup,
            query,
            "bing",
            limit,
        )
    )

    for item in fallback:

        if item["url"] in seen_urls:
            continue

        results.append(
            item
        )

        seen_urls.add(
            item["url"]
        )

        if len(results) >= limit:
            break

    return results


# ============================================================
# SEARCH DISPATCH
# ============================================================

def parse_results(
    html: str,
    query: str,
    engine: str,
    limit: int,
) -> list[dict[str, Any]]:

    if engine == "google":

        return parse_google_results(
            html,
            query,
            limit,
        )

    if engine == "bing":

        return parse_bing_results(
            html,
            query,
            limit,
        )

    return []


# ============================================================
# DISCOVERY INPUT
# ============================================================

def load_discovery(
    path: str,
) -> list[Any]:

    file_path = Path(
        path
    )

    if not file_path.exists():

        raise FileNotFoundError(
            "Discovery file not found: "
            f"{file_path}"
        )

    data = json.loads(
        file_path.read_text(
            encoding="utf-8"
        )
    )

    if isinstance(
        data,
        dict,
    ):

        queries = data.get(
            "queries",
            [],
        )

    elif isinstance(
        data,
        list,
    ):

        queries = data

    else:

        queries = []

    if not isinstance(
        queries,
        list,
    ):

        return []

    return queries


def extract_query(
    item: Any,
) -> str:

    if isinstance(
        item,
        str,
    ):

        return normalize_text(
            item
        )

    if isinstance(
        item,
        dict,
    ):

        for key in (
            "query",
            "search_query",
            "searchQuery",
            "normalized_query",
        ):

            value = item.get(
                key
            )

            if value:

                return normalize_text(
                    value
                )

    return ""


def extract_engine(
    item: Any,
) -> str:

    if not isinstance(
        item,
        dict,
    ):

        return "google"

    raw = (
        item.get(
            "engine"
        )
        or item.get(
            "search_engine"
        )
        or item.get(
            "source"
        )
        or "google"
    )

    raw = str(
        raw
    ).lower()

    if "bing" in raw:
        return "bing"

    return "google"


# ============================================================
# FINGERPRINT
# ============================================================

def make_fingerprint(
    title: str,
    url: str,
) -> str:

    raw = (
        normalize_title(
            title
        ).lower()
        + "|"
        + normalize_url(
            url
        ).lower()
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# RESULT CONVERSION
# ============================================================

def convert_result(
    item: dict[str, Any],
    query: str,
    engine: str,
    rank: int,
) -> SearchResult | None:

    title = normalize_title(
        item.get(
            "title",
            "",
        )
    )

    url = normalize_url(
        item.get(
            "url",
            "",
        )
    )

    if not title or not url:
        return None

    fingerprint = (
        make_fingerprint(
            title,
            url,
        )
    )

    return SearchResult(
        query=query,
        title=title,
        url=url,
        snippet=normalize_text(
            item.get(
                "snippet",
                "",
            )
        ),
        domain=extract_domain(
            url
        ),
        engine=engine,
        rank=rank,
        result_type=classify_url(
            url
        ),
        discovered_at=(
            datetime.now(
                timezone.utc
            )
            .replace(
                microsecond=0
            )
            .isoformat()
        ),
        fingerprint=fingerprint,
    )


# ============================================================
# COLLECTION
# ============================================================

def collect(
    discovery_items: list[Any],
    max_queries: int,
    max_results: int,
    delay: float,
    timeout: int,
) -> tuple[
    list[SearchResult],
    CollectorStats,
]:

    stats = CollectorStats()

    results: list[
        SearchResult
    ] = []

    seen_fingerprints: set[
        str
    ] = set()

    selected = (
        discovery_items[
            :max_queries
        ]
    )

    stats.queries_requested = (
        len(selected)
    )

    for index, item in enumerate(
        selected,
        start=1,
    ):

        query = extract_query(
            item
        )

        if not query:

            stats.errors += 1

            print(
                f"[{index}/"
                f"{stats.queries_requested}] "
                "SKIP: empty query"
            )

            continue

        engine = extract_engine(
            item
        )

        if engine not in {
            "google",
            "bing",
        }:

            engine = "google"

        if engine == "bing":

            search_url = (
                build_bing_url(
                    query
                )
            )

        else:

            search_url = (
                build_google_url(
                    query
                )
            )

        print()
        print(
            f"[{index}/"
            f"{stats.queries_requested}] "
            f"{engine.upper()}: "
            f"{query}"
        )

        (
            html,
            status_code,
            status,
        ) = fetch_page(
            search_url,
            timeout,
        )

        # ----------------------------------------------------
        # GOOGLE -> BING FALLBACK
        # ----------------------------------------------------

        if (
            status == "BLOCKED"
            and engine == "google"
        ):

            stats.blocked_queries += 1

            print(
                "   Google blocked/interstitial."
            )

            print(
                "   Falling back to Bing."
            )

            engine = "bing"

            search_url = build_bing_url(
                query
            )

            (
                html,
                status_code,
                status,
            ) = fetch_page(
                search_url,
                timeout,
            )

        # ----------------------------------------------------
        # BLOCKED
        # ----------------------------------------------------

        if status == "BLOCKED":

            stats.blocked_queries += 1

            print(
                "   Search blocked."
            )

            print(
                "   Query skipped safely."
            )

            if delay > 0:

                time.sleep(
                    delay
                )

            continue

        # ----------------------------------------------------
        # REQUEST ERROR
        # ----------------------------------------------------

        if status != "OK":

            stats.failed_queries += 1

            print(
                "   Request failed:"
            )

            print(
                f"   HTTP/status: "
                f"{status_code or status}"
            )

            if delay > 0:

                time.sleep(
                    delay
                )

            continue

        # ----------------------------------------------------
        # PARSE
        # ----------------------------------------------------

        parsed = parse_results(
            html,
            query,
            engine,
            max_results,
        )

        stats.raw_results += (
            len(parsed)
        )

        print(
            f"   Parsed results: "
            f"{len(parsed)}"
        )

        if not parsed:

            print(
                "   WARNING: Request succeeded "
                "but parser found no job links."
            )

        # ----------------------------------------------------
        # CONVERT / DEDUP
        # ----------------------------------------------------

        for rank, raw in enumerate(
            parsed,
            start=1,
        ):

            result = convert_result(
                raw,
                query,
                engine,
                rank,
            )

            if result is None:
                continue

            if (
                result.fingerprint
                in seen_fingerprints
            ):
                continue

            seen_fingerprints.add(
                result.fingerprint
            )

            results.append(
                result
            )

            stats.by_engine[
                engine
            ] = (
                stats.by_engine.get(
                    engine,
                    0,
                )
                + 1
            )

            stats.by_domain[
                result.domain
            ] = (
                stats.by_domain.get(
                    result.domain,
                    0,
                )
                + 1
            )

        stats.queries_completed += 1

        if delay > 0:

            time.sleep(
                delay
            )

    stats.unique_results = (
        len(results)
    )

    return (
        results,
        stats,
    )


# ============================================================
# SAVE
# ============================================================

def save_output(
    path: str,
    results: list[SearchResult],
    stats: CollectorStats,
) -> None:

    output_path = Path(
        path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "version": VERSION,
        "generated_at": (
            datetime.now(
                timezone.utc
            )
            .replace(
                microsecond=0
            )
            .isoformat()
        ),
        "stats": asdict(
            stats
        ),
        "results": [
            asdict(
                result
            )
            for result in results
        ],
    }

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Public web job-search "
            "collector."
        )
    )

    parser.add_argument(
        "--version",
        action="version",
        version=VERSION,
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Discovery JSON file."
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "data/search_results.json"
        ),
        help=(
            "Search results JSON file."
        ),
    )

    parser.add_argument(
        "--max-queries",
        type=int,
        default=DEFAULT_MAX_QUERIES,
        help=(
            "Maximum discovery queries."
        ),
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help=(
            "Maximum results per query."
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=(
            "Delay between requests."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=(
            "HTTP timeout in seconds."
        ),
    )

    return parser


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = build_parser()

    args = parser.parse_args()

    try:

        discovery_items = load_discovery(
            args.input
        )

    except Exception as exc:

        print(
            "ERROR loading discovery file:"
        )

        print(
            exc
        )

        return 1

    if not discovery_items:

        print(
            "ERROR: No discovery queries found."
        )

        return 1

    max_queries = max(
        1,
        args.max_queries,
    )

    max_results = max(
        1,
        args.max_results,
    )

    delay = max(
        0.0,
        args.delay,
    )

    timeout = max(
        1,
        args.timeout,
    )

    print()
    print(
        "=" * 72
    )

    print(
        "JOB INTELLIGENCE AGENT"
    )

    print(
        "SEARCH COLLECTOR"
    )

    print(
        "=" * 72
    )

    print(
        f"Version: {VERSION}"
    )

    print(
        f"Discovery items: "
        f"{len(discovery_items)}"
    )

    print(
        f"Max queries: "
        f"{max_queries}"
    )

    print(
        f"Max results/query: "
        f"{max_results}"
    )

    print(
        f"Delay: "
        f"{delay}s"
    )

    print(
        f"Timeout: "
        f"{timeout}s"
    )

    print(
        "=" * 72
    )

    results, stats = collect(
        discovery_items=discovery_items,
        max_queries=max_queries,
        max_results=max_results,
        delay=delay,
        timeout=timeout,
    )

    save_output(
        args.output,
        results,
        stats,
    )

    print()
    print(
        "=" * 72
    )

    print(
        "SEARCH COLLECTION SUMMARY"
    )

    print(
        "=" * 72
    )

    print(
        f"Queries requested : "
        f"{stats.queries_requested}"
    )

    print(
        f"Queries completed : "
        f"{stats.queries_completed}"
    )

    print(
        f"Blocked queries   : "
        f"{stats.blocked_queries}"
    )

    print(
        f"Failed queries    : "
        f"{stats.failed_queries}"
    )

    print(
        f"Raw results       : "
        f"{stats.raw_results}"
    )

    print(
        f"Unique results    : "
        f"{stats.unique_results}"
    )

    print(
        f"Errors            : "
        f"{stats.errors}"
    )

    print(
        f"Output            : "
        f"{args.output}"
    )

    print(
        "=" * 72
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
