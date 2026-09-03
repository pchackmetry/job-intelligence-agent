"""
Multi-ATS Job Intelligence Ingestion Orchestrator
Version 1.2.0

Hardening included:
- Skips permanently broken/stale ATS boards after first failure.
- Stores permanent failures in a quarantine JSON file.
- Does not mutate quarantine during --preview.
- Supports --retry-quarantined to test skipped boards again.
- Retries only temporary failures.
- Uses the project root as subprocess cwd.
- Forces UTF-8 subprocess output.
- Keeps reports for every run.
- Never marks jobs missing from limited/company-batch runs because that logic
  remains inside ingest_ats.py.
- Returns exit code 0 after a completed batch so one bad company does not stop
  the whole run.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

VERSION = "1.2.0"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATS_REGISTRY_DIR = PROJECT_ROOT / "workers" / "ats-scrapers" / "ats-companies"
INGEST_SCRIPT = PROJECT_ROOT / "workers" / "ingest_ats.py"
REPORT_DIR = PROJECT_ROOT / "data"
QUARANTINE_FILE = REPORT_DIR / "ats_quarantine.json"

SUPPORTED_ATS_FILES = (
    "greenhouse.csv",
    "lever.csv",
    "ashby.csv",
    "workday.csv",
    "smartrecruiters.csv",
    "icims.csv",
    "bamboohr.csv",
    "teamtailor.csv",
    "successfactors.csv",
    "taleo.csv",
    "oracle.csv",
    "personio.csv",
    "recruitee.csv",
    "rippling.csv",
    "workable.csv",
    "jobvite.csv",
    "pinpointhq.csv",
    "applytojob.csv",
)

# These indicate the board itself / scraper mapping is unusable.
# Temporary network failures should NOT be quarantined.
PERMANENT_FAILURE_SIGNALS = (
    "not found",
    "company not found",
    "board not found",
    "ats board unavailable",
    "does not exist",
    "no such board",
    "unknown board",
    "greenhousescraper(",
    "leverscraper(",
    "ashbyscraper(",
    "workdayscraper(",
    "smartrecruitersscraper(",
    "icimsscraper(",
    "scraper(",
)

TRANSIENT_FAILURE_SIGNALS = (
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "temporary failure",
    "too many requests",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
)

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True)
class Company:
    name: str
    ats: str
    url: str


@dataclass
class RunResult:
    company: str
    ats: str
    url: str
    status: str
    duration_seconds: float
    jobs_fetched: int = 0
    jobs_selected: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    errors: int = 0
    output_tail: str = ""
    quarantined: bool = False
    skipped_reason: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = ANSI_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value: object) -> str:
    url = clean_text(value)
    return url.rstrip("/")


def detect_ats_from_filename(filename: str) -> str:
    return Path(filename).stem.strip().lower()


def load_companies(selected_ats: Iterable[str] | None = None) -> list[Company]:
    wanted = {x.strip().lower() for x in (selected_ats or []) if x.strip()}

    companies: list[Company] = []

    for filename in SUPPORTED_ATS_FILES:
        ats = detect_ats_from_filename(filename)
        if wanted and ats not in wanted:
            continue

        path = ATS_REGISTRY_DIR / filename
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)

            for row in reader:
                lowered = {
                    str(k).strip().lower(): clean_text(v)
                    for k, v in row.items()
                    if k is not None
                }

                name = (
                    lowered.get("company")
                    or lowered.get("company_name")
                    or lowered.get("name")
                    or lowered.get("employer")
                )
                url = (
                    lowered.get("url")
                    or lowered.get("board_url")
                    or lowered.get("jobs_url")
                    or lowered.get("careers_url")
                )

                if not name or not url:
                    continue

                companies.append(
                    Company(
                        name=name,
                        ats=ats,
                        url=normalize_url(url),
                    )
                )

    return companies


def deduplicate_companies(companies: list[Company]) -> list[Company]:
    seen: set[tuple[str, str, str]] = set()
    output: list[Company] = []

    for company in companies:
        key = (
            company.ats.lower(),
            company.name.casefold(),
            company.url.casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(company)

    return output


def company_key(company: Company) -> str:
    return f"{company.ats.lower()}|{company.url.rstrip('/').casefold()}"


def load_quarantine() -> dict[str, dict]:
    if not QUARANTINE_FILE.exists():
        return {}

    try:
        payload = json.loads(QUARANTINE_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return payload
    except (OSError, json.JSONDecodeError):
        return {}


def save_quarantine(data: dict[str, dict]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = QUARANTINE_FILE.with_suffix(".tmp")

    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(QUARANTINE_FILE)


def quarantine_company(
    quarantine: dict[str, dict],
    company: Company,
    reason: str,
) -> None:
    key = company_key(company)
    previous = quarantine.get(key, {})

    quarantine[key] = {
        "company": company.name,
        "ats": company.ats,
        "url": company.url,
        "reason": clean_text(reason),
        "first_failed_at": previous.get("first_failed_at", utc_now()),
        "last_failed_at": utc_now(),
        "failure_count": int(previous.get("failure_count", 0)) + 1,
        "version": VERSION,
    }


def remove_from_quarantine(
    quarantine: dict[str, dict],
    company: Company,
) -> None:
    quarantine.pop(company_key(company), None)


def tail_text(text: str, lines: int = 18) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    parts = cleaned.split(" ")
    if len(parts) <= 100:
        return cleaned
    return " ".join(parts[-100:])


def is_permanent_failure(output: str) -> bool:
    text = clean_text(output).casefold()

    if not text:
        return False

    # Hard permanent signals win.
    if any(signal in text for signal in PERMANENT_FAILURE_SIGNALS):
        return True

    # Explicit transient conditions are never quarantined.
    if any(signal in text for signal in TRANSIENT_FAILURE_SIGNALS):
        return False

    return False


def build_command(
    company: Company,
    limit: int,
    preview: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(INGEST_SCRIPT),
        company.url,
        "--limit",
        str(limit),
    ]

    if preview:
        cmd.append("--preview")

    return cmd


def parse_ingest_output(output: str) -> dict[str, int]:
    result = {
        "jobs_fetched": 0,
        "jobs_selected": 0,
        "new_jobs": 0,
        "updated_jobs": 0,
        "errors": 0,
    }

    patterns = {
        "jobs_fetched": (
            r"Jobs fetched:\s*(\d+)",
            r"Jobs fetched:\s*(\d+)",
        ),
        "jobs_selected": (
            r"Jobs selected:\s*(\d+)",
        ),
        "new_jobs": (
            r"New jobs:\s*(\d+)",
        ),
        "updated_jobs": (
            r"Updated jobs:\s*(\d+)",
        ),
        "errors": (
            r"Errors:\s*(\d+)",
        ),
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, output, flags=re.IGNORECASE)
            if match:
                result[field] = int(match.group(1))
                break

    return result


def run_company(
    company: Company,
    *,
    limit: int,
    delay: float,
    timeout: int,
    retries: int,
    preview: bool,
    quarantine: dict[str, dict],
    retry_quarantined: bool,
) -> RunResult:
    key = company_key(company)

    if key in quarantine and not retry_quarantined:
        item = quarantine[key]
        return RunResult(
            company=company.name,
            ats=company.ats,
            url=company.url,
            status="SKIPPED_QUARANTINED",
            duration_seconds=0.0,
            skipped_reason=clean_text(item.get("reason", "Permanent ATS failure")),
        )

    command = build_command(company, limit, preview)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    started = time.monotonic()
    last_output = ""

    for attempt in range(retries + 1):
        if attempt > 0 and delay > 0:
            time.sleep(delay)

        try:
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            combined = f"{stdout}\n{stderr}".strip()
            last_output = combined

            if completed.returncode == 0:
                stats = parse_ingest_output(combined)

                if not preview:
                    remove_from_quarantine(quarantine, company)

                return RunResult(
                    company=company.name,
                    ats=company.ats,
                    url=company.url,
                    status="SUCCESS",
                    duration_seconds=time.monotonic() - started,
                    **stats,
                )

            if is_permanent_failure(combined):
                if not preview:
                    quarantine_company(quarantine, company, combined)
                    save_quarantine(quarantine)

                return RunResult(
                    company=company.name,
                    ats=company.ats,
                    url=company.url,
                    status="FAILED_PERMANENT",
                    duration_seconds=time.monotonic() - started,
                    output_tail=tail_text(combined),
                    quarantined=not preview,
                )

            # Temporary/non-classified failure: retry.
            if attempt < retries:
                continue

            return RunResult(
                company=company.name,
                ats=company.ats,
                url=company.url,
                status="FAILED",
                duration_seconds=time.monotonic() - started,
                output_tail=tail_text(combined),
            )

        except subprocess.TimeoutExpired as exc:
            last_output = f"TIMEOUT: {exc}"

            if attempt < retries:
                continue

            return RunResult(
                company=company.name,
                ats=company.ats,
                url=company.url,
                status="FAILED_TIMEOUT",
                duration_seconds=time.monotonic() - started,
                output_tail=last_output,
            )

        except OSError as exc:
            last_output = f"OS ERROR: {exc}"

            if attempt < retries:
                continue

            return RunResult(
                company=company.name,
                ats=company.ats,
                url=company.url,
                status="FAILED_OS",
                duration_seconds=time.monotonic() - started,
                output_tail=last_output,
            )

        except Exception as exc:
            last_output = f"EXCEPTION: {type(exc).__name__}: {exc}"

            if attempt < retries:
                continue

            return RunResult(
                company=company.name,
                ats=company.ats,
                url=company.url,
                status="FAILED_EXCEPTION",
                duration_seconds=time.monotonic() - started,
                output_tail=last_output,
            )

    return RunResult(
        company=company.name,
        ats=company.ats,
        url=company.url,
        status="FAILED",
        duration_seconds=time.monotonic() - started,
        output_tail=tail_text(last_output),
    )


def save_report(
    *,
    companies_discovered: int,
    companies_selected: int,
    results: list[RunResult],
    args: argparse.Namespace,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"ats_ingestion_{timestamp}.json"

    payload = {
        "version": VERSION,
        "started_at_utc": utc_now(),
        "project_root": str(PROJECT_ROOT),
        "companies_discovered": companies_discovered,
        "companies_selected": companies_selected,
        "arguments": {
            "ats": args.ats,
            "max_companies": args.max_companies,
            "limit": args.limit,
            "delay": args.delay,
            "timeout": args.timeout,
            "retries": args.retries,
            "preview": args.preview,
            "start": args.start,
            "retry_quarantined": args.retry_quarantined,
        },
        "results": [asdict(item) for item in results],
        "quarantine_file": str(QUARANTINE_FILE),
    }

    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report_path


def print_result(index: int, total: int, result: RunResult) -> None:
    print(f"[{index}/{total}] {result.company}")
    print(f"    ATS  : {result.ats}")
    print(f"    URL  : {result.url}")

    if result.status == "SKIPPED_QUARANTINED":
        print("    ⏭️  SKIPPED — quarantined permanent failure")
        print(f"    Why  : {result.skipped_reason}")
        return

    if result.status == "SUCCESS":
        print(f"    OK   ({result.duration_seconds:.2f}s)")
        print(f"    Jobs fetched:   {result.jobs_fetched}")
        print(f"    Jobs selected:  {result.jobs_selected}")
        print(f"    New jobs:       {result.new_jobs}")
        print(f"    Updated jobs:   {result.updated_jobs}")
        print(f"    Errors:         {result.errors}")
        if result.status == "SUCCESS" and result.quarantined:
            print("    ⚠️  Quarantined")
        return

    print(f"    ❌ {result.status}")
    if result.quarantined:
        print("    🧯 Board added to quarantine")
    if result.output_tail:
        print(f"    Detail: {result.output_tail}")


def print_summary(
    discovered: int,
    selected: int,
    results: list[RunResult],
    elapsed: float,
    report_path: Path,
) -> None:
    successful = sum(r.status == "SUCCESS" for r in results)
    permanent = sum(r.status == "FAILED_PERMANENT" for r in results)
    failed = sum(
        r.status.startswith("FAILED") and r.status != "FAILED_PERMANENT"
        for r in results
    )
    skipped = sum(r.status == "SKIPPED_QUARANTINED" for r in results)

    print("\n" + "=" * 70)
    print("MULTI-ATS INGESTION COMPLETE")
    print("=" * 70)
    print(f"Companies discovered : {discovered}")
    print(f"Companies selected   : {selected}")
    print(f"Successful           : {successful}")
    print(f"Permanent failures   : {permanent}")
    print(f"Other failures       : {failed}")
    print(f"Quarantined skipped  : {skipped}")
    print(f"Duration             : {elapsed:.1f}s")

    ats_counts: dict[str, int] = {}
    for result in results:
        ats_counts[result.ats] = ats_counts.get(result.ats, 0) + 1

    if ats_counts:
        print("\nATS coverage:")
        for ats, count in sorted(ats_counts.items()):
            print(f"  {ats:<20} {count}")

    permanent_failures = [r for r in results if r.status == "FAILED_PERMANENT"]
    if permanent_failures:
        print("\nNew permanent failures:")
        for result in permanent_failures:
            print(f"  - {result.company} [{result.ats}]")

    other_failures = [
        r for r in results
        if r.status.startswith("FAILED") and r.status != "FAILED_PERMANENT"
    ]
    if other_failures:
        print("\nOther failures:")
        for result in other_failures:
            print(f"  - {result.company} [{result.ats}] -> {result.status}")

    print(f"\nQuarantine file: {QUARANTINE_FILE}")
    print(f"Run report:      {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run job ingestion across multiple ATS company registries."
    )

    parser.add_argument(
        "--ats",
        action="append",
        help="ATS registry name, repeatable. Example: --ats greenhouse --ats lever",
    )
    parser.add_argument(
        "--max-companies",
        type=int,
        default=10,
        help="Maximum companies to process.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum jobs to ingest per company. 0 means all jobs.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between companies.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-company timeout in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retries for temporary failures only.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Read-only preview mode.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start offset in the discovered company list.",
    )
    parser.add_argument(
        "--retry-quarantined",
        action="store_true",
        help="Retry companies currently in quarantine.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.max_companies < 1:
        print("ERROR: --max-companies must be >= 1")
        return 2

    if args.limit < 0:
        print("ERROR: --limit must be >= 0")
        return 2

    if args.delay < 0:
        print("ERROR: --delay must be >= 0")
        return 2

    if args.timeout < 1:
        print("ERROR: --timeout must be >= 1")
        return 2

    if args.retries < 0:
        print("ERROR: --retries must be >= 0")
        return 2

    if not ATS_REGISTRY_DIR.exists():
        print(f"ERROR: ATS registry directory not found: {ATS_REGISTRY_DIR}")
        return 2

    if not INGEST_SCRIPT.exists():
        print(f"ERROR: ingest script not found: {INGEST_SCRIPT}")
        return 2

    companies = deduplicate_companies(load_companies(args.ats))
    discovered = len(companies)
    quarantine = load_quarantine()
    if args.start < 0:
        print("ERROR: --start must be >= 0")
        return 2

    companies = companies[args.start:]
    selected = [c for c in companies if args.retry_quarantined or company_key(c) not in quarantine][: args.max_companies]

    quarantine = load_quarantine()

    print("=" * 70)
    print("MULTI-ATS JOB INTELLIGENCE INGESTION")
    print("=" * 70)
    print(f"Version: {VERSION}")
    print(f"ATS registry directory : {ATS_REGISTRY_DIR}")
    print(f"Companies limit       : {args.max_companies}")
    print(f"Jobs/company limit    : {args.limit}")
    print(f"Delay                 : {args.delay}s")
    print(f"Timeout               : {args.timeout}s")
    print(f"Retries               : {args.retries}")
    print(f"Preview mode          : {args.preview}")
    print(f"Retry quarantined     : {args.retry_quarantined}")
    print(f"Companies discovered  : {discovered}")
    print(f"Companies selected    : {len(selected)}")
    print(f"Quarantine entries    : {len(quarantine)}")

    if args.preview:
        print("\nREAD-ONLY PREVIEW: quarantine and database will not be modified.")

    started = time.monotonic()
    results: list[RunResult] = []

    for index, company in enumerate(selected, start=1):
        if args.delay > 0 and index > 1:
            time.sleep(args.delay)

        result = run_company(
            company,
            limit=args.limit,
            delay=args.delay,
            timeout=args.timeout,
            retries=args.retries,
            preview=args.preview,
            quarantine=quarantine,
            retry_quarantined=args.retry_quarantined,
        )
        results.append(result)
        print_result(index, len(selected), result)

    elapsed = time.monotonic() - started

    report_path = save_report(
        companies_discovered=discovered,
        companies_selected=len(selected),
        results=results,
        args=args,
    )

    print_summary(
        discovered=discovered,
        selected=len(selected),
        results=results,
        elapsed=elapsed,
        report_path=report_path,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())



