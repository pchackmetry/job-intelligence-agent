"""
Search Collector v2.3.0
Public web job-search result collector.

Policy:
- Public pages only.
- No CAPTCHA bypass.
- No authentication bypass.
- No anti-bot bypass.
- Search-engine blocking/interstitials are detected and handled safely.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import (
    parse_qs,
    quote_plus,
    unquote,
    urlencode,
    urljoin,
    urlparse,
)

import requests
from bs4 import BeautifulSoup


VERSION = "2.3.0"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 20

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "google.co.in",
    "bing.com",
    "search.yahoo.com",
    "duckduckgo.com",
}

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
    "applytojob.com",
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

BLOCK_STATUS_CODES = {403, 429, 503}

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

GENERIC_TITLES = {
    "",
    "google search",
    "bing",
    "search",
    "yahoo",
}


@dataclass
class SearchResult:
    query: str
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    source: str = ""
    rank: int = 0
    result_type: str = "unknown"
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
    by_source: dict[str, int] = field(default_factory=dict)
    by_domain: dict[str, int] = field(default_factory=dict)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unescape(str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_title(value: Any) -> str:
    text = normalize_text(value)

    if " - Google Search" in text:
        text = text.replace(" - Google Search", "")

    if " | Google Search" in text:
        text = text.replace(" | Google Search", "")

    return text.strip()


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)

        hostname = (parsed.hostname or "").lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:
        return ""


def normalize_url(url: str) -> str:
    if not url:
        return ""

    url = unescape(str(url)).strip()

    if url.startswith("//"):
        url = "https:" + url

    try:
        parsed = urlparse(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return ""

        hostname = (parsed.hostname or "").lower()

        if not hostname:
            return ""

        if hostname.startswith("www."):
            hostname = hostname[4:]

        path = parsed.path or "/"

        if path != "/" and not path.endswith("/"):
            path += "/"

        query_values = parse_qs(
            parsed.query,
            keep_blank_values=True,
        )

        clean_query = {}

        for key, values in query_values.items():
            if key.lower() in TRACKING_PARAMETERS:
                continue

            clean_query[key] = values[-1] if values else ""

        query = urlencode(clean_query)

        return urlparse("")._replace(
            scheme=parsed.scheme.lower(),
            netloc=hostname,
            path=path,
            query=query,
            fragment="",
        ).geturl()

    except Exception:
        return ""


def classify_domain(url: str) -> str:
    domain = extract_domain(url)

    if not domain:
        return "unknown"

    for candidate in ATS_DOMAINS:
        if domain == candidate or domain.endswith("." + candidate):
            return "ats"

    for candidate in THIRD_PARTY_JOB_DOMAINS:
        if domain == candidate or domain.endswith("." + candidate):
            return "third_party_job"

    for candidate in SEARCH_ENGINE_DOMAINS:
        if domain == candidate or domain.endswith("." + candidate):
            return "search_engine"

    return "other"


def build_google_url(query: str) -> str:
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


def build_bing_url(query: str) -> str:
    # Bing may ignore site: operators. Remove the operator before
    # searching; parse_bing_results() applies the domain restriction.
    search_query = re.sub(r"(?:^|\s)site:[^\s]+", " ", query, flags=re.I)
    search_query = re.sub(r"\s+", " ", search_query).strip()

    # Quote the most specific job-role phrase so Bing prioritizes
    # the actual role instead of generic words such as India/remote.
    role_phrases = (
        "application security analyst",
        "security operations center analyst",
        "cybersecurity analyst",
        "cyber security analyst",
        "information security analyst",
        "network security analyst",
        "identity and access management",
        "iam analyst",
        "soc analyst",
        "grc analyst",
        "risk and compliance analyst",
        "compliance analyst",
        "financial crime analyst",
        "anti money laundering analyst",
        "aml analyst",
        "kyc analyst",
        "cdd analyst",
        "penetration tester",
        "vulnerability analyst",
        "security engineer",
    )

    lower_query = search_query.lower()

    for phrase in role_phrases:
        if phrase in lower_query:
            search_query = search_query.replace(
                phrase,
                '"' + phrase + '"',
                1,
            )
            break

    return (
        "https://www.bing.com/search?"
        + urlencode(
            {
                "q": search_query,
                "count": "20",
                "setlang": "en-IN",
            }
        )
    )


def detect_google_interstitial(
    html: str,
    url: str = "",
) -> bool:
    if not html:
        return True

    lowered = html.lower()

    parsed = urlparse(url)

    if "/httpservice/retry/" in parsed.path.lower():
        return True

    if "enablejs" in lowered and "httpservice/retry" in lowered:
        return True

    if "javascript is required" in lowered:
        return True

    soup = BeautifulSoup(html, "html.parser")

    title = normalize_text(
        soup.title.get_text(" ", strip=True)
        if soup.title
        else ""
    ).lower()

    links = soup.find_all("a")
    h3_tags = soup.find_all("h3")

    if (
        title in GENERIC_TITLES
        and len(links) <= 10
        and len(h3_tags) == 0
    ):
        return True

    if (
        title == "google search"
        and len(h3_tags) == 0
        and len(links) <= 10
    ):
        return True

    return False


def is_blocked_page(
    html: str,
    status_code: int = 200,
    url: str = "",
) -> bool:
    if status_code in BLOCK_STATUS_CODES:
        return True

    if not html:
        return True

    if detect_google_interstitial(html, url):
        return True

    lowered = normalize_text(
        BeautifulSoup(
            html,
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )
    ).lower()

    for signal in BLOCK_SIGNALS:
        if signal in lowered:
            return True

    return False


def unwrap_google_url(href: str) -> str:
    href = unescape(href).strip()

    if not href:
        return ""

    if href.startswith("//"):
        href = "https:" + href

    if href.startswith("/url?"):
        parsed = urlparse(href)
        params = parse_qs(parsed.query)

        for key in ("q", "url"):
            values = params.get(key)

            if values:
                return normalize_url(
                    unquote(values[0])
                )

    if href.startswith(
        "https://www.google.com/url?"
    ):
        parsed = urlparse(href)
        params = parse_qs(parsed.query)

        for key in ("q", "url"):
            values = params.get(key)

            if values:
                return normalize_url(
                    unquote(values[0])
                )

    return normalize_url(href)


def unwrap_bing_url(href: str) -> str:
    """
    Safely unwrap Bing result redirect URLs.

    Bing commonly returns URLs such as:

    https://www.bing.com/ck/a/?...&u=a1<encoded-target>

    The destination is decoded locally. No bypass or
    browser automation is performed.
    """

    href = unescape(href).strip()

    if not href:
        return ""

    if href.startswith("//"):
        href = "https:" + href

    try:
        parsed = urlparse(href)

        hostname = (parsed.hostname or "").lower()

        if (
            hostname in {"bing.com", "www.bing.com"}
            and parsed.path.lower().startswith("/ck/a")
        ):
            params = parse_qs(
                parsed.query,
                keep_blank_values=True,
            )

            values = params.get("u", [])

            if values:
                encoded_target = values[0]

                candidates = [
                    encoded_target
                ]

                if encoded_target.startswith("a1"):
                    candidates.append(
                        encoded_target[2:]
                    )

                for candidate in candidates:
                    try:
                        decoded = unquote(candidate)

                        padding = "=" * (
                            -len(decoded) % 4
                        )

                        raw = base64.urlsafe_b64decode(
                            (
                                decoded + padding
                            ).encode("ascii")
                        )

                        target = raw.decode(
                            "utf-8",
                            errors="ignore",
                        ).strip()

                        if target.startswith(
                            ("http://", "https://")
                        ):
                            return normalize_url(
                                target
                            )

                    except Exception:
                        continue

                decoded = unquote(
                    encoded_target
                )

                if decoded.startswith(
                    ("http://", "https://")
                ):
                    return normalize_url(
                        decoded
                    )

        return normalize_url(href)

    except Exception:
        return normalize_url(href)


def fetch_page(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, int, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
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

        html = response.text or ""

        if is_blocked_page(
            html,
            response.status_code,
            response.url,
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
            f"ERROR: {exc}",
        )


def extract_google_result_nodes(
    soup: BeautifulSoup,
) -> list[Any]:
    selectors = [
        "div.MjjYud",
        "div.Gx5Zad",
        "div.tF2Cxc",
        "div.g",
    ]

    for selector in selectors:
        nodes = soup.select(selector)

        if nodes:
            return nodes

    return []


def parse_google_results(
    html: str,
    query: str,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    if detect_google_interstitial(
        html,
        "https://www.google.com/search",
    ):
        return []

    results: list[dict[str, Any]] = []

    nodes = extract_google_result_nodes(
        soup
    )

    for node in nodes:
        anchor = None

        for candidate in node.find_all(
            "a",
            href=True,
        ):
            href = candidate.get(
                "href",
                "",
            )

            final_url = unwrap_google_url(
                href
            )

            if not final_url:
                continue

            domain_type = classify_domain(
                final_url
            )

            if domain_type == "search_engine":
                continue

            anchor = candidate
            break

        if anchor is None:
            continue

        url = unwrap_google_url(
            anchor.get(
                "href",
                "",
            )
        )

        if not url:
            continue

        heading = node.find("h3")

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

        if not title:
            continue

        if not title:
            continue

        snippet_node = node.select_one(
            ".b_caption p"
        )

        snippet = normalize_text(
            snippet_node.get_text(
                " ",
                strip=True,
            )
            if snippet_node
            else ""
        )

        results.append(
            {
                "query": query,
                "title": title,
                "url": url,
                "snippet": snippet,
                "domain": extract_domain(url),
            }
        )

        if len(results) >= max_results:
            break

    return results


def parse_search_results(
    html: str,
    query: str,
    engine: str,
    max_results: int,
) -> list[dict[str, Any]]:
    engine = engine.lower()

    if engine == "google":
        return parse_google_results(
            html,
            query,
            max_results,
        )

    if engine == "bing":
        return []

    return []

def load_discovery(
    path: str,
) -> list[dict[str, Any]]:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Discovery file not found: {file_path}"
        )

    data = json.loads(
        file_path.read_text(
            encoding="utf-8"
        )
    )

    if isinstance(data, dict):
        queries = data.get(
            "queries",
            [],
        )

        if isinstance(queries, list):
            return queries

        return []

    if isinstance(data, list):
        return data

    return []


def extract_query(item: Any) -> str:
    if isinstance(item, str):
        return normalize_text(item)

    if not isinstance(item, dict):
        return ""

    for key in (
        "query",
        "search_query",
        "searchQuery",
        "normalized_query",
    ):
        value = item.get(key)

        if value:
            return normalize_text(value)

    return ""


def extract_engine(item: Any) -> str:
    if not isinstance(item, dict):
        return "google"

    value = (
        item.get("engine")
        or item.get("source")
        or item.get("search_engine")
        or "google"
    )

    value = str(value).lower()

    if "bing" in value:
        return "bing"

    return "google"


def make_fingerprint(
    title: str,
    url: str,
    company: str = "",
) -> str:
    raw = "|".join(
        [
            normalize_text(
                company
            ).lower(),
            normalize_title(
                title
            ).lower(),
            normalize_url(
                url
            ).lower(),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def convert_result(
    item: dict[str, Any],
    source: str,
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

    domain = extract_domain(url)

    result = SearchResult(
        query=normalize_text(
            item.get(
                "query",
                "",
            )
        ),
        title=title,
        url=url,
        snippet=normalize_text(
            item.get(
                "snippet",
                "",
            )
        ),
        domain=domain,
        source=source,
        rank=rank,
        result_type=classify_domain(
            url
        ),
        discovered_at=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
    )

    result.fingerprint = make_fingerprint(
        result.title,
        result.url,
    )

    return result


def collect(
    discovery_items: list[dict[str, Any]],
    max_queries: int = 20,
    max_results: int = 10,
    delay: float = 2.0,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[
    list[SearchResult],
    CollectorStats,
]:
    stats = CollectorStats()

    results: list[SearchResult] = []

    stats.queries_requested = min(
        len(discovery_items),
        max_queries,
    )

    seen_urls: set[str] = set()

    for index, item in enumerate(
        discovery_items[:max_queries],
        start=1,
    ):
        query = extract_query(item)

        if not query:
            stats.errors += 1
            continue

        engine = extract_engine(item)

        if engine == "bing":
            search_url = build_bing_url(
                query
            )
        else:
            engine = "google"
            search_url = build_google_url(
                query
            )

        print(
            f"[{index}/{stats.queries_requested}] "
            f"{engine.upper()}: {query}"
        )

        html, status_code, status = fetch_page(
            search_url,
            timeout=timeout,
        )

        if status == "BLOCKED":
            stats.blocked_queries += 1

            print(
                f"   {engine.upper()} "
                "BLOCK/CAPTCHA DETECTED"
            )

            # Google may block automated public HTML
            # requests. Use Bing as a normal public
            # search-engine fallback. No bypass.
            if engine == "google":
                fallback_engine = "bing"
                fallback_url = build_bing_url(
                    query
                )

                print(
                    "   Falling back safely to BING..."
                )

                (
                    fallback_html,
                    fallback_code,
                    fallback_status,
                ) = fetch_page(
                    fallback_url,
                    timeout=timeout,
                )

                if fallback_status == "OK":
                    engine = fallback_engine
                    html = fallback_html
                    status_code = fallback_code
                    status = fallback_status
                    search_url = fallback_url

                    print(
                        "   BING fallback succeeded."
                    )

                else:
                    print(
                        "   BING fallback unavailable; "
                        "query skipped."
                    )

                    if delay > 0:
                        time.sleep(delay)

                    continue

            else:
                print(
                    "   Query skipped safely."
                )

                if delay > 0:
                    time.sleep(delay)

                continue

        if status != "OK":
            stats.failed_queries += 1

            print(
                f"   Request failed: "
                f"{status_code or status}"
            )

            if delay > 0:
                time.sleep(delay)

            continue

        parsed = parse_search_results(
            html,
            query,
            engine,
            max_results,
        )

        stats.raw_results += len(parsed)

        for rank, item_data in enumerate(
            parsed,
            start=1,
        ):
            result = convert_result(
                item_data,
                engine,
                rank,
            )

            if result is None:
                continue

            if result.url in seen_urls:
                continue

            seen_urls.add(result.url)

            results.append(result)

            stats.by_source[engine] = (
                stats.by_source.get(
                    engine,
                    0,
                )
                + 1
            )

            stats.by_domain[result.domain] = (
                stats.by_domain.get(
                    result.domain,
                    0,
                )
                + 1
            )

        stats.queries_completed += 1

        print(
            f"   Results: {len(parsed)}"
        )

        if delay > 0:
            time.sleep(delay)

    stats.unique_results = len(results)

    return results, stats


def save_output(
    path: str,
    results: list[SearchResult],
    stats: CollectorStats,
) -> None:
    output = {
        "version": VERSION,
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "stats": asdict(stats),
        "results": [
            asdict(result)
            for result in results
        ],
    }

    output_path = Path(path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_tests() -> int:
    print("=" * 72)
    print("SEARCH COLLECTOR TEST SUITE")
    print("=" * 72)
    print(f"Version: {VERSION}")
    print("-" * 72)

    passed = 0
    failed = 0

    def check(
        name: str,
        condition: bool,
    ) -> None:
        nonlocal passed, failed

        if condition:
            print(
                f"[PASS] {name}"
            )
            passed += 1
        else:
            print(
                f"[FAIL] {name}"
            )
            failed += 1

    # ------------------------------------------------------------
    # Text normalization
    # ------------------------------------------------------------

    check(
        "Text whitespace normalized",
        normalize_text(
            "  hello   world  "
        )
        == "hello world",
    )

    check(
        "Empty text handled",
        normalize_text("") == "",
    )

    check(
        "None text handled",
        normalize_text(None) == "",
    )

    # ------------------------------------------------------------
    # Domain
    # ------------------------------------------------------------

    check(
        "Domain extraction",
        extract_domain(
            "https://www.example.com/test"
        )
        == "example.com",
    )

    check(
        "WWW removed",
        extract_domain(
            "https://www.google.com/search"
        )
        == "google.com",
    )

    check(
        "ATS domain recognized",
        classify_domain(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        )
        == "ats",
    )

    check(
        "Third-party job domain recognized",
        classify_domain(
            "https://www.linkedin.com/"
            "jobs/view/123"
        )
        == "third_party_job",
    )

    check(
        "Search engine recognized",
        classify_domain(
            "https://www.google.com/"
            "search?q=test"
        )
        == "search_engine",
    )

    check(
        "Unknown domain recognized",
        classify_domain(
            "https://example.com/job/1"
        )
        == "other",
    )

    # ------------------------------------------------------------
    # URL normalization
    # ------------------------------------------------------------

    check(
        "HTTPS URL accepted",
        normalize_url(
            "https://example.com/job"
        )
        == "https://example.com/job/",
    )

    check(
        "WWW removed from URL",
        normalize_url(
            "https://www.example.com/job"
        )
        == "https://example.com/job/",
    )

    tracking_url = normalize_url(
        "https://example.com/job/1?"
        "utm_source=google&"
        "gclid=123&"
        "page=2"
    )

    check(
        "Tracking parameters removed",
        tracking_url
        == "https://example.com/job/1/?page=2",
    )

    check(
        "Fragment removed",
        normalize_url(
            "https://example.com/job#section"
        )
        == "https://example.com/job/",
    )

    check(
        "Invalid scheme rejected",
        normalize_url(
            "ftp://example.com/job"
        )
        == "",
    )

    check(
        "Empty URL rejected",
        normalize_url("") == "",
    )

    # ------------------------------------------------------------
    # Google URL
    # ------------------------------------------------------------

    google_url = build_google_url(
        "SOC Analyst India fresher"
    )

    check(
        "Google URL created",
        google_url.startswith(
            "https://www.google.com/search?"
        ),
    )

    check(
        "Google query encoded",
        "SOC+Analyst+India+fresher"
        in google_url,
    )

    # ------------------------------------------------------------
    # Google redirect
    # ------------------------------------------------------------

    redirect_url = unwrap_google_url(
        "/url?q=https%3A%2F%2Fexample.com%2Fjob"
    )

    check(
        "Google redirect unwrapped",
        redirect_url
        == "https://example.com/job/",
    )

    check(
        "Normal URL preserved",
        unwrap_google_url(
            "https://example.com/job"
        )
        == "https://example.com/job/",
    )

    # ------------------------------------------------------------
    # Bing redirect
    # ------------------------------------------------------------

    bing_target = (
        "https://example.com/job"
    )

    bing_encoded = (
        base64.urlsafe_b64encode(
            bing_target.encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )

    bing_redirect = (
        "https://www.bing.com/ck/a/?"
        + urlencode(
            {
                "u": "a1" + bing_encoded
            }
        )
    )

    check(
        "Bing redirect unwrapped",
        unwrap_bing_url(
            bing_redirect
        )
        == "https://example.com/job/",
    )

    check(
        "Normal Bing URL preserved",
        unwrap_bing_url(
            "https://example.com/job"
        )
        == "https://example.com/job/",
    )

    # ------------------------------------------------------------
    # Google interstitial detection
    # ------------------------------------------------------------

    interstitial_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Google Search</title>
    </head>
    <body>
      <div>
        JavaScript is required to continue.
      </div>
      <a href="/httpservice/retry/enablejs">
        Retry
      </a>
    </body>
    </html>
    """

    check(
        "Google JS interstitial detected",
        detect_google_interstitial(
            interstitial_html,
            "https://www.google.com/"
            "httpservice/retry/enablejs",
        ),
    )

    check(
        "Google normal page not falsely blocked",
        not detect_google_interstitial(
            """
            <html>
            <head>
              <title>Results</title>
            </head>
            <body>
              <div class="MjjYud">
                <a href="https://example.com/job">
                  <h3>Example Job</h3>
                </a>
              </div>
            </body>
            </html>
            """,
            "https://www.google.com/"
            "search?q=test",
        ),
    )

    # ------------------------------------------------------------
    # Google parsing
    # ------------------------------------------------------------

    google_html = """
    <html>
    <head>
      <title>Search Results</title>
    </head>
    <body>
      <div class="MjjYud">
        <a href="https://example.com/job">
          <h3>Cybersecurity Analyst</h3>
        </a>
        <div class="VwiC3b">
          Security analyst role in Hyderabad.
        </div>
      </div>
    </body>
    </html>
    """

    parsed = parse_google_results(
        google_html,
        "SOC Analyst",
        10,
    )

    check(
        "Google result parsed",
        len(parsed) == 1,
    )

    check(
        "Google result URL parsed",
        parsed[0]["url"]
        == "https://example.com/job/",
    )

    check(
        "Google result title parsed",
        parsed[0]["title"]
        == "Cybersecurity Analyst",
    )

    # ------------------------------------------------------------
    # Bing parsing
    # ------------------------------------------------------------
 

    # ------------------------------------------------------------
    # Block detection
    # ------------------------------------------------------------

    check(
        "403 detected as blocked",
        is_blocked_page(
            "<html>Access denied</html>",
            403,
            "https://example.com",
        ),
    )

    check(
        "429 detected as blocked",
        is_blocked_page(
            "<html>Too many requests</html>",
            429,
            "https://example.com",
        ),
    )

    check(
        "CAPTCHA signal detected",
        is_blocked_page(
            "<html>captcha verification</html>",
            200,
            "https://example.com",
        ),
    )

    # ------------------------------------------------------------
    # Fingerprint
    # ------------------------------------------------------------

    fp1 = make_fingerprint(
        "SOC Analyst",
        "https://example.com/job",
    )

    fp2 = make_fingerprint(
        "SOC Analyst",
        "https://example.com/job/",
    )

    check(
        "Fingerprint deterministic",
        fp1 == fp2,
    )

    check(
        "Fingerprint is SHA256",
        len(fp1) == 64
        and all(
            char
            in "0123456789abcdef"
            for char in fp1
        ),
    )

    # ------------------------------------------------------------
    # Result conversion
    # ------------------------------------------------------------

    converted = convert_result(
        {
            "query": "SOC Analyst India",
            "title": "SOC Analyst",
            "url": "https://www.example.com/job",
            "snippet": "Security operations role",
        },
        "google",
        1,
    )

    check(
        "Result conversion works",
        converted is not None,
    )

    check(
        "Converted URL normalized",
        converted is not None
        and converted.url
        == "https://example.com/job/",
    )

    check(
        "Converted domain detected",
        converted is not None
        and converted.domain
        == "example.com",
    )

    check(
        "Converted fingerprint generated",
        converted is not None
        and len(converted.fingerprint) == 64,
    )

    # ------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------

    check(
        "String query extracted",
        extract_query(
            "SOC Analyst India"
        )
        == "SOC Analyst India",
    )

    check(
        "Dictionary query extracted",
        extract_query(
            {
                "query": "GRC Analyst Hyderabad"
            }
        )
        == "GRC Analyst Hyderabad",
    )

    check(
        "Default engine is Google",
        extract_engine(
            {
                "query": "SOC Analyst"
            }
        )
        == "google",
    )

    check(
        "Bing engine detected",
        extract_engine(
            {
                "query": "SOC Analyst",
                "engine": "bing",
            }
        )
        == "bing",
    )

    # ------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------

    print("-" * 72)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("-" * 72)

    if failed == 0:
        print(
            "ALL SEARCH COLLECTOR TESTS PASSED"
        )
        return 0

    print(
        "SEARCH COLLECTOR TESTS FAILED"
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Public web search collector "
            "for the Job Intelligence Agent."
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
        help="Run built-in tests.",
    )

    parser.add_argument(
        "--input",
        help="Discovery JSON file.",
    )

    parser.add_argument(
        "--output",
        default="./data/search_results.json",
        help="Output JSON file.",
    )

    parser.add_argument(
        "--max-queries",
        type=int,
        default=20,
        help="Maximum discovery queries.",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum results per query.",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between queries.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )

    return parser


def main() -> int:
    parser = build_parser()

    args = parser.parse_args()

    if args.tests:
        return run_tests()

    if not args.input:
        parser.error(
            "--input is required unless "
            "--tests is used"
        )

    try:
        discovery_items = load_discovery(
            args.input
        )

    except Exception as exc:
        print(
            f"ERROR loading discovery file: {exc}"
        )
        return 1

    if not discovery_items:
        print(
            "ERROR: No discovery queries found."
        )
        return 1

    print("=" * 72)
    print("JOB INTELLIGENCE AGENT")
    print("SEARCH COLLECTOR")
    print("=" * 72)
    print(f"Version: {VERSION}")
    print(
        f"Discovery items: "
        f"{len(discovery_items)}"
    )
    print(
        f"Max queries: "
        f"{args.max_queries}"
    )
    print(
        f"Max results/query: "
        f"{args.max_results}"
    )
    print("=" * 72)

    results, stats = collect(
        discovery_items=discovery_items,
        max_queries=max(
            0,
            args.max_queries,
        ),
        max_results=max(
            1,
            args.max_results,
        ),
        delay=max(
            0.0,
            args.delay,
        ),
        timeout=max(
            1,
            args.timeout,
        ),
    )

    save_output(
        args.output,
        results,
        stats,
    )

    print("=" * 72)
    print("SEARCH COLLECTION SUMMARY")
    print("=" * 72)
    print(
        f"Queries requested: "
        f"{stats.queries_requested}"
    )
    print(
        f"Queries completed: "
        f"{stats.queries_completed}"
    )
    print(
        f"Blocked queries: "
        f"{stats.blocked_queries}"
    )
    print(
        f"Failed queries: "
        f"{stats.failed_queries}"
    )
    print(
        f"Raw results: "
        f"{stats.raw_results}"
    )
    print(
        f"Unique results: "
        f"{stats.unique_results}"
    )
    print(
        f"Errors: "
        f"{stats.errors}"
    )
    print(
        f"Output: {args.output}"
    )

    if stats.blocked_queries > 0:
        print()
        print(
            "SEARCH COLLECTION COMPLETED "
            "WITH SAFE SEARCH-ENGINE FALLBACKS."
        )

    else:
        print()
        print(
            "SEARCH COLLECTION COMPLETE"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
