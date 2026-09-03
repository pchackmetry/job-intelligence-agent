from __future__ import annotations

import subprocess
import sys


def run_step(name: str, command: list[str]) -> None:
    print(f"\n{'=' * 70}")
    print(f"▶ {name}")
    print(f"{'=' * 70}")

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"{name} failed with exit code {result.returncode}"
        )


def main() -> None:
    python = sys.executable

    run_step(
        "JOB DISCOVERY",
        [python, "sources/search/discovery_engine.py"],
    )

    run_step(
        "ATS INGESTION",
        [python, "workers/ingest_all_ats.py", "--max-companies", "10"],
    )

    run_step(
        "JOB MATCHING",
        [python, "workers/match_jobs.py"],
    )

    run_step(
        "JOB VERIFICATION",
        [python, "workers/verify_pending.py"],
    )

    run_step(
        "TELEGRAM ALERTS",
        [python, "notifications/telegram/job_alerts.py"],
    )

    print(f"\n{'=' * 70}")
    print("✅ CLOUD JOB AGENT COMPLETE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
