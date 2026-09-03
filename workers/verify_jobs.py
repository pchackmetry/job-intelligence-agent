from database.job_database import JobDatabase
from verification.job_verifier import JobVerifier


def main():
    print("=" * 70)
    print("JOB INTELLIGENCE AGENT")
    print("DATABASE VERIFICATION WORKER")
    print("=" * 70)

    db = JobDatabase()
    verifier = JobVerifier()

    jobs = db.get_pending_verification()

    print(f"Jobs pending verification: {len(jobs)}")
    print()

    verified = 0
    uncertain = 0
    rejected = 0

    for job in jobs:
        print("-" * 70)
        print(f"Company:  {job['company']}")
        print(f"Title:    {job['title']}")
        print(f"Location: {job['location']}")

        try:
            source_url = job["source_url"] or ""
            application_url = job["application_url"] or ""

            result = verifier.verify(
                company=job["company"] or "",
                title=job["title"] or "",
                location=job["location"] or "",
                description=job["description"] or "",
                source_url=source_url,
                official_url=source_url,
                application_url=application_url,
                requisition_id=job["requisition_id"] or "",
                source_ats=job["source"] or "",
                is_remote=job["is_remote"],
                work_mode=job["work_mode"] or "",
                is_fresher_friendly=job["is_fresher_friendly"],
            )

            print(f"Status:       {result.status}")
            print(f"Confidence:   {result.confidence}/100")
            print(f"Score:        {result.score}/100")
            print(f"Verified:     {result.verified}")
            print(f"ATS:          {result.ats}")
            print(f"Remote:       {result.remote_classification}")
            print(f"Official URL: {result.official_url}")
            print(f"Page accessible: {result.evidence.job_page_accessible}")
            print(f"Company match:   {result.evidence.company_match}")
            print(f"Title match:     {result.evidence.title_match}")
            print(f"Recognized ATS:  {result.evidence.recognized_ats}")
            print(f"Direct apply:    {result.evidence.application_url_direct}")
            print(f"India eligible:  {result.evidence.india_eligibility}")
            print(f"Reasons:         {' | '.join(result.evidence.reasons)}")

            db.set_verification_status(
                job["id"],
                result.status,
            )

            if result.status == "VERIFIED":
                verified += 1
            elif result.status == "UNCERTAIN":
                uncertain += 1
            else:
                rejected += 1

        except Exception as exc:
            print(f"❌ Verification error: {exc}")
            rejected += 1

    db.close()

    print()
    print("=" * 70)
    print("VERIFICATION RESULT")
    print("=" * 70)
    print(f"Jobs checked: {len(jobs)}")
    print(f"Verified:     {verified}")
    print(f"Uncertain:    {uncertain}")
    print(f"Rejected:     {rejected}")
    print("=" * 70)


if __name__ == "__main__":
    main()