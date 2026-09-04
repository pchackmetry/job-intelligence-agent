from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

DISCOVERY_FILE = DATA_DIR / "discovery_queries.json"
SEARCH_RESULTS_FILE = DATA_DIR / "search_results.json"


# ============================================================
# STEP RUNNER
# ============================================================

def run_step(
    name: str,
    command: list[str],
) -> None:
    print()
    print("=" * 70)
    print(f"▶ {name}")
    print("=" * 70)

    print("Command:")
    print(" ".join(command))
    print()

    result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        check=False,
        env=os.environ.copy(),
        text=True,
    )

    print()

    print(
        f"{name} exit code: "
        f"{result.returncode}"
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# DISCOVERY FILE
# ============================================================

def validate_discovery_file(
    path: Path,
) -> int:
    if not path.exists():
        raise FileNotFoundError(
            f"Discovery file does not exist: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Discovery file is empty: {path}"
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        raise RuntimeError(
            f"Invalid discovery JSON: {exc}"
        ) from exc

    if isinstance(data, dict):
        queries = data.get(
            "queries",
            []
        )

    elif isinstance(data, list):
        queries = data

    else:
        queries = []

    if not isinstance(
        queries,
        list
    ):
        queries = []

    if not queries:
        raise RuntimeError(
            "Discovery file contains zero queries."
        )

    print(
        f"Discovery file: {path}"
    )

    print(
        f"Discovery queries: {len(queries)}"
    )

    return len(queries)


# ============================================================
# SEARCH OUTPUT
# ============================================================

def validate_search_output(
    path: Path,
) -> int:
    if not path.exists():
        raise RuntimeError(
            f"Search collector did not create: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Search output is empty: {path}"
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        raise RuntimeError(
            f"Invalid search-results JSON: {exc}"
        ) from exc

    if isinstance(data, dict):
        results = data.get(
            "results",
            []
        )
    elif isinstance(data, list):
        results = data
    else:
        results = []

    if not isinstance(
        results,
        list
    ):
        results = []

    print(
        f"Search results: {len(results)}"
    )

    return len(results)


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    python = sys.executable

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 1. JOB DISCOVERY
    # --------------------------------------------------------

    run_step(
        "JOB DISCOVERY",
        [
            python,
            "sources/search/discovery_engine.py",
            "--output",
            str(DISCOVERY_FILE),
        ],
    )

    # --------------------------------------------------------
    # 2. VALIDATE DISCOVERY
    # --------------------------------------------------------

    query_count = validate_discovery_file(
        DISCOVERY_FILE
    )

    # --------------------------------------------------------
    # 3. WEB SEARCH COLLECTION
    # --------------------------------------------------------

    max_queries = min(
        query_count,
        20,
    )

    print()
    print(
        f"Running {max_queries} public search queries."
    )

    run_step(
        "WEB SEARCH COLLECTION",
        [
            python,
            "sources/search/search_collector.py",
            "--input",
            str(DISCOVERY_FILE),
            "--output",
            str(SEARCH_RESULTS_FILE),
            "--max-queries",
            str(max_queries),
            "--max-results",
            "10",
            "--delay",
            "2",
            "--timeout",
            "20",
        ],
    )

    # --------------------------------------------------------
    # 4. VALIDATE SEARCH RESULTS
    # --------------------------------------------------------

    validate_search_output(
        SEARCH_RESULTS_FILE
    )

    # --------------------------------------------------------
    # 5. ATS INGESTION
    # --------------------------------------------------------

    run_step(
        "ATS INGESTION",
        [
            python,
            "workers/ingest_all_ats.py",
            "--max-companies",
            "10",
        ],
    )

    # --------------------------------------------------------
    # 6. JOB MATCHING
    # --------------------------------------------------------

    run_step(
        "JOB MATCHING",
        [
            python,
            "workers/match_jobs.py",
        ],
    )

    # --------------------------------------------------------
    # 7. JOB VERIFICATION
    # --------------------------------------------------------

    run_step(
        "JOB VERIFICATION",
        [
            python,
            "workers/verify_pending.py",
        ],
    )

    # --------------------------------------------------------
    # 8. TELEGRAM ALERTS
    # --------------------------------------------------------

    run_step(
        "TELEGRAM ALERTS",
        [
            python,
            "-m",
            "notifications.telegram.job_alerts",
        ],
    )

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("✅ CLOUD JOB AGENT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
