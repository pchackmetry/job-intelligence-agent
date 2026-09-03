from __future__ import annotations

import os
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_step(name: str, command: list[str]) -> None:
    print(f"\n{'=' * 70}")
    print(f"▶ {name}")
    print(f"{'=' * 70}")

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        env=os.environ.copy(),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code {result.returncode}"
        )


def main() -> None:
    python = sys.executable

    # 1. Discover jobs from public internet / OSINT sources
    run_step(
        "JOB DISCOVERY",
        [
            python,
            "sources/search/discovery_engine.py",
        ],
    )

    # 2. Discover additional jobs through ATS sources
    run_step(
        "ATS INGESTION",
        [
            python,
            "workers/ingest_all_ats.py",
            "--max-companies",
            "10",
        ],
    )

    # 3. Match jobs against configured target roles
    run_step(
        "JOB MATCHING",
        [
            python,
            "workers/match_jobs.py",
        ],
    )

    # 4. Verify candidate jobs and application URLs
    run_step(
        "JOB VERIFICATION",
        [
            python,
            "workers/verify_pending.py",
        ],
    )

    # 5. Send verified/high-quality jobs to Telegram
    run_step(
        "TELEGRAM ALERTS",
        [
            python,
            "-m",
            "notifications.telegram.job_alerts",
        ],
    )

    print(f"\n{'=' * 70}")
    print("✅ CLOUD JOB AGENT COMPLETE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
