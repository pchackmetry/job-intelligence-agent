# --------------------------------------------------------
# 6. FRESHER SIGNAL
# --------------------------------------------------------

fresher_friendly = has_fresher_signal(
    title,
    experience_text,
    description,
)

# Do not reject a target-role job solely because the
# employer did not explicitly use "fresher", "junior",
# or "entry level".
#
# Explicit senior titles and explicit experience
# mismatches are already rejected earlier.

fresher_status = (
    "CONFIRMED"
    if fresher_friendly
    else "UNCONFIRMED"
)

# Fresher signal
if fresher_friendly:
    score += 20
else:
    score += 5


return {
    "matched": True,
    "category": category,
    "match_score": score,
    "india_eligible": True,
    "fresher_friendly": fresher_friendly,
    "fresher_status": fresher_status,
    "role": role["group"],
    "matched_role": role["role"],
    "reason": "TECHNICAL_FRESHER_MATCH",
}
