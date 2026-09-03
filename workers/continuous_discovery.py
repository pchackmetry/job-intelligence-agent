"""
Job Intelligence Agent
FAST PARALLEL CONTINUOUS DISCOVERY WORKER
Version: 4.0.0

Flow:

    ATS sources run in parallel
              ↓
        ingest_all_ats.py
              ↓
           SQLite
              ↓
    continuous_pipeline.py
              ↓
      Match → Verify → Telegram

This worker ONLY discovers/ingests jobs.

Key upgrades:
    - Parallel ATS execution
    - Per-ATS timeout
    - Persistent checkpoint
    - Broken ATS cannot block others
    - Detects 0-success runs correctly
    - Automatic continuous cycles
    - Safe state-file writes
    - Detailed logging
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime
from pathlib import Path
from threading import Lock


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

INGESTOR = ROOT / "workers" / "ingest_all_ats.py"

DATA_DIR = ROOT / "data"

STATE_FILE = DATA_DIR / "continuous_discovery_state.json"

LOG_DIR = DATA_DIR / "discovery_logs"


# ============================================================
# PERFORMANCE SETTINGS
# ============================================================

# Number of companies handled by one ATS process.
COMPANIES_PER_RUN = 10

# Job limit passed to existing ingestion worker.
JOBS_PER_COMPANY = 100

# Maximum parallel ATS processes.
#
# 6 is a safer starting point for a normal Windows PC.
# Increase later to 8 if the machine/network handles it well.
MAX_PARALLEL_ATS = 8

# Hard timeout for ONE ATS ingestion process.
ATS_TIMEOUT = 60
# Wait after ALL ATS processes finish before next cycle.
DISCOVERY_INTERVAL = 10

# Small delay before launching another group after a batch.
LAUNCH_DELAY = 0.5


# ============================================================
# ATS SOURCES
# ============================================================

ATS_TYPES = [
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
    "icims",
    "bamboohr",
    "teamtailor",
    "successfactors",
    "taleo",
    "oracle",
    "personio",
    "recruitee",
    "rippling",
    "workable",
    "jobvite",
    "pinpointhq",
    "applytojob",
]


# ============================================================
# ENVIRONMENT
# ============================================================

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

os.chdir(ROOT)

ENV = os.environ.copy()

ENV["PYTHONPATH"] = str(ROOT)

ENV["PYTHONIOENCODING"] = "utf-8"

# Prevent Python subprocesses from buffering logs too heavily.
ENV["PYTHONUNBUFFERED"] = "1"


# ============================================================
# LOGGING
# ============================================================

LOG_LOCK = Lock()


def log(message: str) -> None:
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = f"[{timestamp}] {message}"

    with LOG_LOCK:

        print(
            line,
            flush=True,
        )

        try:
            logfile = (
                LOG_DIR
                / (
                    "discovery_"
                    f"{datetime.now().strftime('%Y%m%d')}"
                    ".log"
                )
            )

            with logfile.open(
                "a",
                encoding="utf-8",
            ) as handle:

                handle.write(
                    line + "\n"
                )

        except Exception:
            pass


# ============================================================
# STATE
# ============================================================

def default_state() -> dict:
    return {
        "version": "4.0.0",
        "cycles": 0,
        "started_at": None,
        "last_cycle_at": None,
        "last_cycle_completed_at": None,
        "last_success_at": None,
        "last_error_at": None,
        "ats": {},
    }


def load_state() -> dict:

    if not STATE_FILE.exists():

        state = default_state()

        save_state(state)

        return state

    try:

        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as handle:

            state = json.load(handle)

        if not isinstance(
            state,
            dict,
        ):
            raise ValueError(
                "State file is not a dictionary."
            )

    except Exception as exc:

        log(
            f"⚠ State read failed: {exc}"
        )

        backup = (
            STATE_FILE.with_suffix(
                ".corrupt"
            )
        )

        try:

            if STATE_FILE.exists():
                STATE_FILE.replace(
                    backup
                )

        except Exception:
            pass

        state = default_state()

        save_state(state)

    base = default_state()

    for key, value in base.items():

        if key not in state:
            state[key] = value

    if not isinstance(
        state.get("ats"),
        dict,
    ):
        state["ats"] = {}

    return state


def save_state(state: dict) -> None:

    temporary = STATE_FILE.with_suffix(
        ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            state,
            handle,
            indent=2,
            ensure_ascii=False,
        )

        handle.flush()

        os.fsync(
            handle.fileno()
        )

    temporary.replace(
        STATE_FILE
    )


# ============================================================
# ATS STATE
# ============================================================

def get_ats_state(
    state: dict,
    ats_name: str,
) -> dict:

    item = state["ats"].get(
        ats_name
    )

    if not isinstance(
        item,
        dict,
    ):

        item = {
            "start": 0,
            "cycles": 0,
            "successes": 0,
            "failures": 0,
            "timeouts": 0,
            "companies_attempted": 0,
            "last_run": None,
            "last_success": None,
            "last_error": None,
        }

        state["ats"][ats_name] = item

    defaults = {
        "start": 0,
        "cycles": 0,
        "successes": 0,
        "failures": 0,
        "timeouts": 0,
        "companies_attempted": 0,
        "last_run": None,
        "last_success": None,
        "last_error": None,
    }

    for key, value in defaults.items():

        item.setdefault(
            key,
            value,
        )

    return item


# ============================================================
# PARSE SUMMARY
# ============================================================

def parse_summary(
    output: str,
) -> dict:

    result = {
        "discovered": None,
        "processed": None,
        "successful": None,
        "failed": None,
    }

    patterns = {
        "discovered": (
            r"Companies discovered\s*:\s*(\d+)"
        ),
        "processed": (
            r"Companies processed\s*:\s*(\d+)"
        ),
        "successful": (
            r"Successful\s*:\s*(\d+)"
        ),
        "failed": (
            r"Failed\s*:\s*(\d+)"
        ),
    }

    for key, pattern in patterns.items():

        match = re.search(
            pattern,
            output,
            flags=re.IGNORECASE,
        )

        if match:

            try:
                result[key] = int(
                    match.group(1)
                )
            except Exception:
                result[key] = None

    return result


# ============================================================
# RUN ONE ATS
# ============================================================

def run_one_ats(
    ats_name: str,
    start: int,
) -> dict:

    started = time.time()

    command = [
        sys.executable,
        "-u",
        str(INGESTOR),
        "--ats",
        ats_name,
        "--limit",
        str(JOBS_PER_COMPANY),
        "--max-companies",
        str(COMPANIES_PER_RUN),
        "--start",
        str(start),
    ]

    log(
        f"🚀 {ats_name.upper()} started "
        f"(position {start})"
    )

    try:

        process = subprocess.run(
            command,
            cwd=ROOT,
            env=ENV,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=ATS_TIMEOUT,
        )

    except subprocess.TimeoutExpired as exc:

        elapsed = time.time() - started

        partial_stdout = (
            exc.stdout
            if isinstance(
                exc.stdout,
                str,
            )
            else ""
        )

        partial_stderr = (
            exc.stderr
            if isinstance(
                exc.stderr,
                str,
            )
            else ""
        )

        combined = (
            partial_stdout
            + "\n"
            + partial_stderr
        )

        if combined.strip():

            print(
                combined.rstrip(),
                flush=True,
            )

        log(
            f"⏰ {ats_name.upper()} TIMEOUT "
            f"after {elapsed:.1f}s"
        )

        return {
            "ats": ats_name,
            "success": False,
            "timeout": True,
            "returncode": None,
            "processed": None,
            "summary": parse_summary(
                combined
            ),
            "elapsed": elapsed,
        }

    except Exception as exc:

        elapsed = time.time() - started

        log(
            f"❌ {ats_name.upper()} "
            f"process error: {exc}"
        )

        return {
            "ats": ats_name,
            "success": False,
            "timeout": False,
            "returncode": None,
            "processed": None,
            "summary": {},
            "elapsed": elapsed,
        }

    stdout = process.stdout or ""

    stderr = process.stderr or ""

    combined = (
        stdout
        + "\n"
        + stderr
    )

    # Print source output safely.
    if stdout.strip():

        print(
            stdout.rstrip(),
            flush=True,
        )

    if stderr.strip():

        print(
            stderr.rstrip(),
            flush=True,
        )

    elapsed = time.time() - started

    summary = parse_summary(
        combined
    )

    successful = summary.get(
        "successful"
    )

    failed = summary.get(
        "failed"
    )

    processed = summary.get(
        "processed"
    )

    # --------------------------------------------------------
    # REAL SUCCESS CHECK
    # --------------------------------------------------------

    if successful is not None:

        if successful > 0:

            log(
                f"✅ {ats_name.upper()} "
                f"{successful} successful, "
                f"{failed or 0} failed "
                f"({elapsed:.1f}s)"
            )

            return {
                "ats": ats_name,
                "success": True,
                "timeout": False,
                "returncode": process.returncode,
                "processed": processed,
                "summary": summary,
                "elapsed": elapsed,
            }

        # Successful == 0
        log(
            f"❌ {ats_name.upper()} "
            f"0 successful companies"
        )

        if failed is not None:

            log(
                f"   Failed: {failed}"
            )

        return {
            "ats": ats_name,
            "success": False,
            "timeout": False,
            "returncode": process.returncode,
            "processed": processed,
            "summary": summary,
            "elapsed": elapsed,
        }

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if process.returncode == 0:

        log(
            f"✅ {ats_name.upper()} "
            f"completed "
            f"({elapsed:.1f}s)"
        )

        return {
            "ats": ats_name,
            "success": True,
            "timeout": False,
            "returncode": 0,
            "processed": processed,
            "summary": summary,
            "elapsed": elapsed,
        }

    log(
        f"❌ {ats_name.upper()} "
        f"exit code {process.returncode}"
    )

    return {
        "ats": ats_name,
        "success": False,
        "timeout": False,
        "returncode": process.returncode,
        "processed": processed,
        "summary": summary,
        "elapsed": elapsed,
    }


# ============================================================
# UPDATE ATS STATE
# ============================================================

def update_ats_state(
    state: dict,
    result: dict,
) -> None:

    ats_name = result[
        "ats"
    ]

    item = get_ats_state(
        state,
        ats_name,
    )

    item["cycles"] = (
        int(
            item.get(
                "cycles",
                0,
            )
        )
        + 1
    )

    item["last_run"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    if result.get(
        "success"
    ):

        item["successes"] = (
            int(
                item.get(
                    "successes",
                    0,
                )
            )
            + 1
        )

        item["last_success"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        item["last_error"] = None

    else:

        item["failures"] = (
            int(
                item.get(
                    "failures",
                    0,
                )
            )
            + 1
        )

        item["last_error"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        if result.get(
            "timeout"
        ):

            item["timeouts"] = (
                int(
                    item.get(
                        "timeouts",
                        0,
                    )
                )
                + 1
            )

    processed = result.get(
        "processed"
    )

    if (
        isinstance(
            processed,
            int,
        )
        and processed > 0
    ):

        attempted = processed

    else:

        attempted = COMPANIES_PER_RUN

    item["companies_attempted"] = (
        int(
            item.get(
                "companies_attempted",
                0,
            )
        )
        + attempted
    )

    # Always advance past the attempted registry section.
    #
    # This prevents one broken company from blocking the
    # continuous scanner forever.
    current = int(
        item.get(
            "start",
            0,
        )
    )

    item["start"] = (
        current
        + max(
            attempted,
            1,
        )
    )


# ============================================================
# PARALLEL DISCOVERY CYCLE
# ============================================================

def run_discovery_cycle(
    state: dict,
) -> None:

    cycle_number = int(
        state.get(
            "cycles",
            0,
        )
    )

    log("")
    log("=" * 78)
    log(
        f"🚀 FAST DISCOVERY CYCLE #{cycle_number}"
    )
    log("=" * 78)

    cycle_started = time.time()

    state["last_cycle_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    save_state(state)

    results: list[dict] = []

    # --------------------------------------------------------
    # PARALLEL EXECUTION
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=MAX_PARALLEL_ATS,
        thread_name_prefix="ats",
    ) as executor:

        futures = {}

        for ats_name in ATS_TYPES:

            ats_state = get_ats_state(
                state,
                ats_name,
            )

            start = int(
                ats_state.get(
                    "start",
                    0,
                )
            )

            future = executor.submit(
                run_one_ats,
                ats_name,
                start,
            )

            futures[future] = (
                ats_name,
                start,
            )

            time.sleep(
                LAUNCH_DELAY
            )

        # ----------------------------------------------------
        # COLLECT RESULTS
        # ----------------------------------------------------

        for future in as_completed(
            futures
        ):

            ats_name, start = (
                futures[future]
            )

            try:

                result = future.result()

            except Exception as exc:

                log(
                    f"❌ {ats_name.upper()} "
                    f"worker exception: {exc}"
                )

                result = {
                    "ats": ats_name,
                    "success": False,
                    "timeout": False,
                    "returncode": None,
                    "processed": None,
                    "summary": {},
                    "elapsed": 0,
                }

            results.append(
                result
            )

            update_ats_state(
                state,
                result,
            )

            save_state(state)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    successful_sources = sum(
        1
        for item in results
        if item.get("success")
    )

    failed_sources = sum(
        1
        for item in results
        if not item.get("success")
    )

    timed_out = sum(
        1
        for item in results
        if item.get("timeout")
    )

    elapsed = (
        time.time()
        - cycle_started
    )

    state["last_cycle_completed_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    if successful_sources > 0:

        state["last_success_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

    if failed_sources > 0:

        state["last_error_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

    save_state(state)

    log("")
    log("=" * 78)
    log(
        f"✅ DISCOVERY CYCLE #{cycle_number} COMPLETE"
    )
    log("=" * 78)

    log(
        f"ATS successful : {successful_sources}"
    )

    log(
        f"ATS failed    : {failed_sources}"
    )

    log(
        f"ATS timeouts  : {timed_out}"
    )

    log(
        f"Duration      : {elapsed:.1f}s"
    )

    # Fast source-by-source summary.
    for result in sorted(
        results,
        key=lambda x: x.get(
            "ats",
            "",
        ),
    ):

        ats_name = result.get(
            "ats",
            "unknown",
        )

        summary = result.get(
            "summary",
            {},
        )

        successful = summary.get(
            "successful"
        )

        failed = summary.get(
            "failed"
        )

        if result.get(
            "timeout"
        ):

            status = "TIMEOUT"

        elif result.get(
            "success"
        ):

            status = "OK"

        else:

            status = "FAILED"

        details = []

        if successful is not None:
            details.append(
                f"ok={successful}"
            )

        if failed is not None:
            details.append(
                f"failed={failed}"
            )

        suffix = (
            f" ({', '.join(details)})"
            if details
            else ""
        )

        log(
            f"  {ats_name:<18} "
            f"{status}{suffix}"
        )

    log("=" * 78)


# ============================================================
# MAIN LOOP
# ============================================================

def main() -> None:

    log("=" * 78)
    log(
        "JOB INTELLIGENCE AGENT"
    )
    log(
        "FAST PARALLEL CONTINUOUS DISCOVERY v4.0.0"
    )
    log("=" * 78)

    log(
        f"Project             : {ROOT}"
    )

    log(
        f"Ingestor            : {INGESTOR}"
    )

    log(
        f"ATS sources         : {len(ATS_TYPES)}"
    )

    log(
        f"Companies / ATS run : {COMPANIES_PER_RUN}"
    )

    log(
        f"Parallel ATS workers: {MAX_PARALLEL_ATS}"
    )

    log(
        f"ATS timeout         : {ATS_TIMEOUT}s"
    )

    log(
        f"Cycle wait          : {DISCOVERY_INTERVAL}s"
    )

    log(
        "Mode                : PARALLEL + CONTINUOUS"
    )

    log("=" * 78)

    if not INGESTOR.exists():

        log(
            f"❌ Ingestor not found: {INGESTOR}"
        )

        return

    state = load_state()

    if not state.get(
        "started_at"
    ):

        state["started_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        save_state(state)

    while True:

        try:

            state["cycles"] = (
                int(
                    state.get(
                        "cycles",
                        0,
                    )
                )
                + 1
            )

            run_discovery_cycle(
                state
            )

            log(
                f"⏳ Next discovery cycle "
                f"in {DISCOVERY_INTERVAL}s..."
            )

            time.sleep(
                DISCOVERY_INTERVAL
            )

        except KeyboardInterrupt:

            log("")
            log(
                "🛑 Discovery worker stopped."
            )

            save_state(state)

            break

        except Exception as exc:

            log(
                f"❌ MAIN LOOP ERROR: {exc}"
            )

            state["last_error_at"] = (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            )

            save_state(state)

            # Never let one unexpected exception
            # permanently kill continuous discovery.
            time.sleep(
                10
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
