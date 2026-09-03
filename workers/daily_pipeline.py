from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from pathlib import Path


VERSION = "2.0.0"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

INGEST = PROJECT_ROOT / "workers" / "ingest_all_ats.py"
MATCH = PROJECT_ROOT / "workers" / "match_jobs.py"
VERIFY = PROJECT_ROOT / "workers" / "bulk_verify.py"
ALERTS = PROJECT_ROOT / "notifications" / "telegram" / "job_alerts.py"

SCAN_STATE = PROJECT_ROOT / "data" / "scan_state.json"

GREENHOUSE_REGISTRY = (
    PROJECT_ROOT
    / "workers"
    / "ats-scrapers"
    / "ats-companies"
    / "greenhouse.csv"
)

SCAN_BATCH_SIZE = 10


def load_scan_position() -> int:
    """Load the next Greenhouse company index to scan."""

    if not SCAN_STATE.exists():
        return 0

    try:
        data = json.loads(
            SCAN_STATE.read_text(encoding="utf-8")
        )

        position = int(data.get("greenhouse", 0))

        if position < 0:
            return 0

        return position

    except (ValueError, TypeError, json.JSONDecodeError, OSError):
        print("[WARNING] Invalid scan_state.json.")
        print("[INFO] Starting Greenhouse scan from position 0.")
        return 0


def save_scan_position(position: int) -> None:
    """Save the next Greenhouse company index."""

    SCAN_STATE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = SCAN_STATE.with_suffix(".tmp")

    temp_file.write_text(
        json.dumps(
            {
                "greenhouse": position,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    temp_file.replace(SCAN_STATE)


def get_greenhouse_company_count() -> int:
    """Return the number of companies in the Greenhouse registry."""

    if not GREENHOUSE_REGISTRY.exists():
        raise FileNotFoundError(
            f"Greenhouse registry not found: {GREENHOUSE_REGISTRY}"
        )

    count = 0

    with GREENHOUSE_REGISTRY.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            name = str(row.get("name", "")).strip()
            slug = str(row.get("slug", "")).strip()
            url = str(row.get("url", "")).strip()

            if name or slug or url:
                count += 1

    return count


def run_stage(
    name: str,
    script: Path,
    args: list[str] | None = None,
) -> bool:
    """Run one pipeline stage."""

    args = args or []

    print()
    print("=" * 70)
    print(f"PIPELINE STAGE: {name}")
    print("=" * 70)

    if not script.exists():
        print(f"[ERROR] Script not found: {script}")
        return False

    command = [
        str(PYTHON),
        str(script),
        *args,
    ]

    env = os.environ.copy()

    # Make project imports reliable.
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    # Prevent Windows Unicode console problems.
    env["PYTHONIOENCODING"] = "utf-8"

    started = time.monotonic()

    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    except Exception as exc:
        print(f"[ERROR] Could not start stage: {exc}")
        return False

    duration = time.monotonic() - started

    print()
    print(f"[STAGE] {name}")
    print(f"[EXIT CODE] {result.returncode}")
    print(f"[DURATION] {duration:.1f}s")

    if result.returncode != 0:
        print(f"[FAILED] {name}")
        return False

    print(f"[SUCCESS] {name}")
    return True


def main() -> int:
    print("=" * 70)
    print("JOB INTELLIGENCE AGENT - DAILY PIPELINE")
    print(f"Version: {VERSION}")
    print("=" * 70)

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python:       {PYTHON}")
    print(f"Scan state:   {SCAN_STATE}")

    # ------------------------------------------------------------
    # ENVIRONMENT CHECK
    # ------------------------------------------------------------

    if not PYTHON.exists():
        print()
        print("[ERROR] Virtual-environment Python not found.")
        print(f"[PATH] {PYTHON}")
        return 1

    if not INGEST.exists():
        print()
        print("[ERROR] ATS ingestion script not found.")
        print(f"[PATH] {INGEST}")
        return 1

    # ------------------------------------------------------------
    # GREENHOUSE ROTATION
    # ------------------------------------------------------------

    try:
        total_companies = get_greenhouse_company_count()
    except Exception as exc:
        print()
        print("[ERROR] Could not read Greenhouse registry.")
        print(f"[DETAIL] {exc}")
        return 1

    if total_companies == 0:
        print()
        print("[ERROR] Greenhouse registry contains no companies.")
        return 1

    current_position = load_scan_position()

    # Protect against a registry becoming smaller.
    if current_position >= total_companies:
        current_position = 0

    batch_start = current_position
    batch_end = min(
        batch_start + SCAN_BATCH_SIZE,
        total_companies,
    )

    companies_this_run = batch_end - batch_start

    # ------------------------------------------------------------
    # PIPELINE INFORMATION
    # ------------------------------------------------------------

    print()
    print("-" * 70)
    print("GREENHOUSE DAILY ROTATION")
    print("-" * 70)

    print(f"Total companies : {total_companies}")
    print(f"Current position: {batch_start}")
    print(f"Batch size      : {companies_this_run}")
    print(
        f"Scanning        : "
        f"{batch_start + 1}-{batch_end}"
    )

    # ------------------------------------------------------------
    # STAGE 1: ATS INGESTION
    # ------------------------------------------------------------

    ingest_args = [
        "--ats",
        "greenhouse",
        "--start",
        str(batch_start),
        "--max-companies",
        str(SCAN_BATCH_SIZE),
        "--limit",
        "100",
        "--delay",
        "2",
        "--timeout",
        "120",
        "--retries",
        "1",
    ]

    print()
    print(
        f"[GREENHOUSE] Starting batch "
        f"{batch_start + 1}-{batch_end} "
        f"of {total_companies}"
    )

    if not run_stage(
        "ATS INGESTION",
        INGEST,
        ingest_args,
    ):
        print()
        print("[WARNING] ATS ingestion failed.")
        print(
            "[INFO] Scan position will NOT advance."
        )
        print(
            f"[INFO] Next run will retry position "
            f"{batch_start}."
        )
        print("[STOP] Pipeline stopped before matching.")
        return 1

    # ------------------------------------------------------------
    # ADVANCE CHECKPOINT
    # ------------------------------------------------------------

    next_position = batch_end

    # If this was the final batch, start over next day.
    if next_position >= total_companies:
        next_position = 0

    try:
        save_scan_position(next_position)
    except Exception as exc:
        print()
        print("[ERROR] Could not save scan checkpoint.")
        print(f"[DETAIL] {exc}")
        return 1

    print()
    print("-" * 70)
    print("SCAN CHECKPOINT UPDATED")
    print("-" * 70)
    print(f"Completed position : {batch_start}")
    print(f"Completed companies: {companies_this_run}")
    print(f"Next position      : {next_position}")

    if next_position == 0:
        print("[INFO] Greenhouse registry cycle completed.")
        print("[INFO] Next run starts again from company 1.")

    # ------------------------------------------------------------
    # STAGE 2: FAST MATCHING
    # ------------------------------------------------------------

    if not run_stage(
        "JOB MATCHING",
        MATCH,
    ):
        print("[WARNING] Matching failed.")
        return 1

    # ------------------------------------------------------------
    # STAGE 3: VERIFICATION
    # ------------------------------------------------------------

    if not run_stage(
        "JOB VERIFICATION",
        VERIFY,
    ):
        print("[WARNING] Verification failed.")
        return 1

    # ------------------------------------------------------------
    # STAGE 4: TELEGRAM ALERTS
    # ------------------------------------------------------------

    if not run_stage(
        "TELEGRAM ALERTS",
        ALERTS,
    ):
        print("[WARNING] Telegram alert stage failed.")
        return 1

    # ------------------------------------------------------------
    # COMPLETE
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("DAILY PIPELINE COMPLETE")
    print("=" * 70)

    print("ATS ingestion : SUCCESS")
    print("Matching      : SUCCESS")
    print("Verification  : SUCCESS")
    print("Telegram      : SUCCESS")

    print()
    print(
        f"Greenhouse    : "
        f"{batch_start + 1}-{batch_end} "
        f"of {total_companies}"
    )

    print(
        f"Next scan     : "
        f"company {next_position + 1}"
    )

    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())