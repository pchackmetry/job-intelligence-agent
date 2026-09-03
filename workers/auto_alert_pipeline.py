"""
Automatic Job -> Telegram Alert Pipeline
Version: 1.0.0

Flow:
1. Ingest a rotating batch of ATS companies.
2. Run technical/fresher matching.
3. Verify queued ACTIVE jobs.
4. Send eligible VERIFIED jobs to Telegram.
5. Save the next ATS offset so repeated runs continue across the registry.

Run from the project root:
    .\.venv\Scripts\python.exe .\workers\auto_alert_pipeline.py

This script is intentionally sequential and fail-safe:
- A failed ATS company does not stop the whole batch.
- Permanent ATS failures are handled by ingest_all_ats.py quarantine.
- Telegram failures do not delete jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "auto_alert_state.json"

INGEST = PROJECT_ROOT / "workers" / "ingest_all_ats.py"
MATCH = PROJECT_ROOT / "workers" / "match_jobs.py"
CONTINUOUS = PROJECT_ROOT / "workers" / "continuous_pipeline.py"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "version": VERSION,
            "greenhouse_start": 0,
            "last_run": None,
            "runs": 0,
        }

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state must be an object")
        return data
    except Exception:
        return {
            "version": VERSION,
            "greenhouse_start": 0,
            "last_run": None,
            "runs": 0,
        }


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(STATE_FILE)


def run_step(name: str, command: list[str], timeout: int) -> int:
    print("\n" + "=" * 72)
    print(f"STEP: {name}")
    print("=" * 72)
    print("COMMAND:")
    print(" ".join(f'"{x}"' if " " in x else x for x in command))

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=timeout,
        )

        print(f"\nExit code: {completed.returncode}")
        return completed.returncode

    except subprocess.TimeoutExpired:
        print(f"\n❌ {name} timed out after {timeout}s")
        return 124

    except OSError as exc:
        print(f"\n❌ Could not start {name}: {exc}")
        return 127


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run automatic ATS -> match -> verify -> Telegram alerts."
    )

    parser.add_argument(
        "--companies",
        type=int,
        default=250,
        help="ATS companies to scan per run.",
    )
    parser.add_argument(
        "--jobs-per-company",
        type=int,
        default=50,
        help="Maximum jobs ingested per company.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between ATS companies.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-company ATS timeout.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Temporary-failure retries.",
    )
    parser.add_argument(
        "--ats",
        action="append",
        default=["greenhouse"],
        help="ATS registry to scan. Repeatable.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the rotating ATS offset before this run.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    for value, name in (
        (args.companies, "companies"),
        (args.jobs_per_company, "jobs-per-company"),
        (args.timeout, "timeout"),
    ):
        if value < 1:
            print(f"ERROR: --{name} must be >= 1")
            return 2

    if args.delay < 0:
        print("ERROR: --delay must be >= 0")
        return 2

    if args.retries < 0:
        print("ERROR: --retries must be >= 0")
        return 2

    required = (INGEST, MATCH, CONTINUOUS)
    for path in required:
        if not path.exists():
            print(f"ERROR: missing pipeline file: {path}")
            return 2

    state = load_state()

    if args.reset:
        state["greenhouse_start"] = 0

    start = int(state.get("greenhouse_start", 0) or 0)

    print("=" * 72)
    print("JOB INTELLIGENCE AGENT - AUTO TELEGRAM ALERT PIPELINE")
    print("=" * 72)
    print(f"Version              : {VERSION}")
    print(f"ATS start offset     : {start}")
    print(f"Companies/run        : {args.companies}")
    print(f"Jobs/company         : {args.jobs_per_company}")
    print(f"Delay                : {args.delay}s")
    print(f"Timeout              : {args.timeout}s")
    print(f"Retries              : {args.retries}")
    print(f"ATS                  : {', '.join(args.ats)}")
    print(f"State file           : {STATE_FILE}")

    ingest_command = [
        sys.executable,
        str(INGEST),
        "--max-companies",
        str(args.companies),
        "--limit",
        str(args.jobs_per_company),
        "--delay",
        str(args.delay),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
        "--start",
        str(start),
    ]

    for ats in args.ats:
        # ingest_all_ats supports repeatable --ats; the default list is
        # intentionally normalized below.
        ingest_command.extend(["--ats", ats])

    # Remove accidental duplicate ATS values while preserving order.
    normalized = []
    seen = set()
    rebuilt = []
    index = 0
    while index < len(ingest_command):
        token = ingest_command[index]
        if token == "--ats" and index + 1 < len(ingest_command):
            ats = ingest_command[index + 1].strip().lower()
            if ats not in seen:
                seen.add(ats)
                normalized.append(ats)
                rebuilt.extend(["--ats", ats])
            index += 2
            continue
        rebuilt.append(token)
        index += 1

    ingest_command = rebuilt

    ingest_rc = run_step(
        "ATS INGESTION",
        ingest_command,
        timeout=max(300, args.timeout * args.companies + 120),
    )

    # Even when some companies fail, ingest_all_ats returns 0 after a completed
    # batch. A nonzero code here means the orchestrator itself failed.
    if ingest_rc != 0:
        print("❌ ATS ingestion step failed at the process level.")
        return ingest_rc

    match_rc = run_step(
        "TECHNICAL / FRESHER MATCHING",
        [sys.executable, str(MATCH)],
        timeout=900,
    )

    if match_rc != 0:
        print("❌ Matching step failed. Verification/alerts were not started.")
        return match_rc

    verify_rc = run_step(
        "VERIFICATION + TELEGRAM ALERTS",
        [sys.executable, str(CONTINUOUS)],
        timeout=1800,
    )

    if verify_rc != 0:
        print(
            "⚠️ Verification/Telegram step returned nonzero. "
            "Jobs remain in the database for the next run."
        )

    # Rotate to the next ATS slice. Greenhouse currently has ~6k companies;
    # the orchestrator itself safely clamps when the offset reaches the end.
    state["version"] = VERSION
    state["greenhouse_start"] = start + args.companies
    state["last_run"] = now_utc()
    state["runs"] = int(state.get("runs", 0) or 0) + 1
    state["last_ingest_exit_code"] = ingest_rc
    state["last_match_exit_code"] = match_rc
    state["last_verification_exit_code"] = verify_rc
    save_state(state)

    print("\n" + "=" * 72)
    print("AUTO ALERT RUN COMPLETE")
    print("=" * 72)
    print(f"Next ATS offset: {state['greenhouse_start']}")
    print(f"State saved    : {STATE_FILE}")

    if verify_rc == 0:
        print("✅ Verification + Telegram pipeline completed.")
        return 0

    print("⚠️ Ingestion and matching completed; Telegram step needs attention.")
    return verify_rc


if __name__ == "__main__":
    raise SystemExit(main())
