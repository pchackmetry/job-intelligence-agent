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

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        env=os.environ.copy(),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# DISCOVERY OUTPUT
# ============================================================

def find_discovery_file() -> Path:
    """
    Find the discovery JSON produced by the discovery engine.

    Preferred:
        data/discovery_queries.json

    Fallback:
        newest discovery*.json file.
    """

    if DISCOVERY_FILE.exists():
        return DISCOVERY_FILE

    candidates = sorted(
        DATA_DIR.glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    for path in candidates:

        if (
            "discovery" in path.name.lower()
            and path != SEARCH_RESULTS_FILE
        ):
            return path

    raise FileNotFoundError(
        "No discovery JSON file was produced."
    )


# ============================================================
# DISCOVERY VALIDATION
# ============================================================

def validate_discovery_file(
    path: Path,
) -> int:

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

    except Exception as exc:

        raise RuntimeError(
            f"Unable to read discovery file "
            f"{path}: {exc}"
        ) from exc

    if isinstance(data, dict):

        queries = data.get(
            "queries",
            [],
        )

    elif isinstance(data, list):

        queries = data

    else:

        queries = []

    if not isinstance(
        queries,
        list,
    ):
        queries = []

    if not queries:

        raise RuntimeError(
            f"Discovery file contains no queries: "
            f"{path}"
        )

    print(
        f"Discovery queries available: "
        f"{len(queries)}"
    )

    return len(queries)


# ============================================================
# SEARCH RESULT VALIDATION
# ============================================================

def validate_search_output(
    path: Path,
) -> int:

    if not path.exists():

        raise RuntimeError(
            f"Search collector did not create "
            f"{path}"
        )

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

    except Exception as exc:

        raise RuntimeError(
            f"Unable to read search result file: "
            f"{exc}"
        ) from exc

    if isinstance(data, dict):

        results = data.get(
            "results",
            [],
        )

    elif isinstance(data, list):

        results = data

    else:

        results = []

    if not isinstance(
        results,
        list,
    ):
        results = []

    print(
        f"Web search results collected: "
        f"{len(results)}"
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

    # ========================================================
    # 1. DISCOVERY / OSINT QUERY GENERATION
    # ========================================================

    run_step(
        "JOB DISCOVERY",
        [
            python,
            "sources/search/discovery_engine.py",
            "--output",
            str(DISCOVERY_FILE),
        ],
    )

    # ========================================================
    # 2. VALIDATE DISCOVERY
    # ========================================================

    discovery_path = find_discovery_file()

    query_count = validate_discovery_file(
        discovery_path
    )

    print(
        f"Using discovery file: "
        f"{discovery_path}"
    )

    # ========================================================
    # 3. ACTUAL WEB SEARCH
    # ========================================================

    # Keep the number bounded for GitHub Actions.
    #
    # The collector already:
    #   - searches public pages
    #   - parses Google results
    #   - detects blocking/interstitials
    #   - falls back safely when possible
    #
    # No CAPTCHA or anti-bot bypass is attempted.

    max_queries = min(
        query_count,
        50,
    )

    run_step(
        "WEB SEARCH COLLECTION",
        [
            python,
            "sources/search/search_collector.py",
            "--input",
            str(discovery_path),
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

    # ========================================================
    # 4. VALIDATE SEARCH RESULTS
    # ========================================================

    validate_search_output(
        SEARCH_RESULTS_FILE
    )

    # ========================================================
    # 5. ATS INGESTION
    # ========================================================

    run_step(
        "ATS INGESTION",
        [
            python,
            "workers/ingest_all_ats.py",
            "--max-companies",
            "10",
        ],
    )

    # ========================================================
    # 6. JOB MATCHING
    # ========================================================

    run_step(
        "JOB MATCHING",
        [
            python,
            "workers/match_jobs.py",
        ],
    )

    # ========================================================
    # 7. JOB VERIFICATION
    # ========================================================

    run_step(
        "JOB VERIFICATION",
        [
            python,
            "workers/verify_pending.py",
        ],
    )

    # ========================================================
    # 8. TELEGRAM ALERTS
    # ========================================================

    run_step(
        "TELEGRAM ALERTS",
        [
            python,
            "-m",
            "notifications.telegram.job_alerts",
        ],
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print()

    print("=" * 70)

    print(
        "✅ CLOUD JOB AGENT COMPLETE"
    )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
