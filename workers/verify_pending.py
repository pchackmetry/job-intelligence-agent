import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.job_database import JobDatabase
from verification.job_verifier import JobVerifier


def get_value(row, *names, default=""):
    for name in names:
        try:
            value = row[name]
            if value is not None and str(value).strip():
                return value
        except (KeyError, IndexError):
            pass
    return default


def main():
    print("=" * 70)
    print("BULK JOB VERIFICATION - DIAGNOSTIC")
    print("=" * 70)

    db = JobDatabase()
    jobs = db.get_pending_verification(limit=100)

    print(f"Pending active jobs: {len(jobs)}")

    verifier = JobVerifier()

    for index, job in enumerate(jobs, 1):

        company = str(get_value(job, "company", default="")).strip()
        title = str(get_value(job, "title", "job_title", default="")).strip()
        location = str(get_value(job, "location", default="")).strip()
        description = str(get_value(job, "description", default="")).strip()

        source_url = str(get_value(
            job,
            "source_url",
            "sourceUrl",
            "source",
            "url",
            default=""
        )).strip()

        application_url = str(get_value(
            job,
            "application_url",
            "applicationUrl",
            "apply_url",
            "applyUrl",
            default=""
        )).strip()

        official_url = str(get_value(
            job,
            "official_url",
            "officialUrl",
            "company_url",
            "companyUrl",
            default=""
        )).strip()

        if not official_url:
            official_url = application_url

        requisition_id = str(get_value(
            job,
            "requisition_id",
            "requisitionId",
            "job_id",
            "jobId",
            default=""
        )).strip()

        fingerprint = str(get_value(
            job,
            "fingerprint",
            default=""
        )).strip()

        print()
        print("-" * 70)
        print(f"[{index}/{len(jobs)}] {company} — {title}")

        try:
            result = verifier.verify(
                company=company,
                title=title,
                location=location,
                description=description,
                source_url=source_url,
                official_url=official_url,
                application_url=application_url,
                requisition_id=requisition_id,
            )

            print(f"STATUS       : {result.status}")
            print(f"SCORE        : {result.score}/100")
            print(f"CONFIDENCE   : {result.confidence}/100")
            print(f"ATS          : {result.ats or 'None'}")
            print(f"REMOTE       : {result.remote_classification}")

            e = result.evidence

            print()
            print("EVIDENCE")
            print(f"  Third-party source : {e.source_is_third_party}")
            print(f"  Recognized ATS     : {e.recognized_ats}")
            print(f"  Career path        : {e.official_career_path}")
            print(f"  Page accessible    : {e.job_page_accessible}")
            print(f"  Company match      : {e.company_match}")
            print(f"  Title match        : {e.title_match}")
            print(f"  Location match     : {e.location_match}")
            print(f"  Remote match       : {e.remote_match}")
            print(f"  Direct application : {e.application_url_direct}")
            print(f"  Third-party apply  : {e.application_url_third_party}")

            print()
            print("REASONS")
            for reason in e.reasons:
                print(f"  - {reason}")

            # Only update DB after seeing a legitimate VERIFIED result.
            if result.status == "VERIFIED":
                db.set_verification_status(
                    fingerprint,
                    "VERIFIED",
                    reason="Verification passed",
                    checked_url=official_url or application_url or source_url,
                )

                print()
                print("DB STATUS    : VERIFIED")

            else:
                print()
                print("DB STATUS    : PENDING")

        except Exception as exc:
            print(f"ERROR        : {type(exc).__name__}: {exc}")

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
