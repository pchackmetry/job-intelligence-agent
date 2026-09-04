from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"

DISCOVERY_FILE = DATA_DIR / "discovery_queries.json"
SEARCH_RESULTS_FILE = DATA_DIR / "search_results.json"


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


def find_discovery_file() -> Path:
    """
    Locate the newest discovery JSON produced by
    discovery_engine.py.

    Preferred path:
        data/discovery_queries.json

    Fallback:
        newest JSON file in data/ whose filename
        contains 'discovery'.
    """

    if DISCOVERY_FILE.exists():
        return DISCOVERY_FILE

    candidates = sorted(
        DATA_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for path in candidates:
        if (
            "discovery" in path.name.lower()
            and path != SEARCH_RESULTS_FILE
        ):
            return path

    raise FileNotFoundError(
        "No discovery JSON was produced by "
        "discovery_engine.py."
    )


def validate_discovery_file(
    path: Path,
) -> int:
    """
    Validate that the discovery JSON contains
    search queries before search collection starts.
    """

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not read discovery file "
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

    if not isinstance(queries, list):
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


def main() -> None:
    python = sys.executable

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # 1. GENERATE DISCOVERY QUERIES
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
    # 2. LOCATE / VALIDATE DISCOVERY OUTPUT
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
    # 3. ACTUAL PUBLIC WEB SEARCH
    # ========================================================

    # Keep this bounded so GitHub Actions does not spend
    # excessive time or trigger search-engine blocking.
    #
    # The collector already handles Google blocking and
    # safely falls back to Bing where possible.

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
    # 4. ATS INGESTION
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
    # 5. JOB MATCHING
    # ========================================================

    run_step(
        "JOB MATCHING",
        [
            python,
            "workers/match_jobs.py",
        ],
    )

    # ========================================================
    # 6. JOB VERIFICATION
    # ========================================================

    run_step(
        "JOB VERIFICATION",
        [
            python,
            "workers/verify_pending.py",
        ],
    )

    # ========================================================
    # 7. TELEGRAM ALERTS
    # ========================================================

    run_step(
        "TELEGRAM ALERTS",
        [
            python,
            "-m",
            "notifications.telegram.job_alerts",
        ],
    )

    print()
    print("=" * 70)
    print("✅ CLOUD JOB AGENT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
