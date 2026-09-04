# --------------------------------------------------------
# 6. FRESHER SIGNAL
# --------------------------------------------------------

fresher_friendly = has_fresher_signal(
    title,
    experience_text,
    description,
)

if not fresher_friendly:
    return {
        "matched": False,
        "category": "EXPERIENCE_MISMATCH",
        "match_score": 0,
        "india_eligible": True,
        "fresher_friendly": False,
        "reason": "NO_FRESHER_SIGNAL",
    }
