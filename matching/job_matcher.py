from __future__ import annotations

import re


# ============================================================
# TARGET ROLE GROUPS
# ============================================================

ROLE_GROUPS = {
    # --------------------------------------------------------
    # CYBERSECURITY
    # --------------------------------------------------------

    "soc_security_operations": {
        "priority": 100,
        "roles": [
            "soc analyst",
            "soc analyst l1",
            "junior soc analyst",
            "security operations analyst",
            "junior security operations analyst",
            "security analyst",
            "junior security analyst",
            "cybersecurity analyst",
            "junior cybersecurity analyst",
            "cyber defense analyst",
            "junior cyber defense analyst",
            "security monitoring analyst",
            "cybersecurity monitoring analyst",
            "security operations center analyst",
            "security operations center l1 analyst",
            "incident monitoring analyst",
            "security incident analyst",
            "junior incident response analyst",
            "incident response analyst",
            "blue team analyst",
            "junior blue team analyst",
            "cyber defense operations analyst",
            "siem analyst",
            "junior siem analyst",
            "siem monitoring analyst",
            "siem support analyst",
            "security monitoring engineer",
            "security operations engineer",
            "cyber security operations analyst",
            "cyber security operations associate",
            "security operations associate",
            "cybersecurity operations associate",
            "threat monitoring analyst",
            "threat detection analyst",
            "detection analyst",
            "detection & response analyst",
            "cyber threat analyst",
            "threat intelligence analyst",
            "threat intelligence associate",
            "cyber defense associate",
            "security incident response associate",
        ],
    },

    "endpoint_security": {
        "priority": 90,
        "roles": [
            "endpoint security analyst",
            "endpoint security associate",
            "edr analyst",
            "edr support analyst",
            "endpoint detection & response analyst",
            "microsoft security analyst",
            "microsoft defender analyst",
            "security tool analyst",
            "security tools support analyst",
            "cybersecurity tool engineer",
            "security platform analyst",
        ],
    },

    "iam": {
        "priority": 88,
        "roles": [
            "iam analyst",
            "junior iam analyst",
            "iam support analyst",
            "identity & access management analyst",
            "identity analyst",
            "access management analyst",
            "access control analyst",
            "identity security analyst",
            "privileged access management analyst",
            "iam operations analyst",
            "identity governance analyst",
        ],
    },

    "vulnerability": {
        "priority": 88,
        "roles": [
            "vulnerability analyst",
            "junior vulnerability analyst",
            "vulnerability management analyst",
            "vulnerability management associate",
            "security assessment analyst",
            "security assessment associate",
            "vulnerability assessment analyst",
            "vulnerability management intern",
            "security testing analyst",
            "cyber risk assessment analyst",
        ],
    },

    "application_security": {
        "priority": 86,
        "roles": [
            "application security analyst",
            "junior application security analyst",
            "application security associate",
            "application security engineer",
            "product security analyst",
            "security testing analyst",
            "vapt analyst",
            "vapt engineer",
            "penetration testing intern",
            "cybersecurity testing intern",
            "offensive security intern",
            "application security intern",
        ],
    },

    "threat_intelligence": {
        "priority": 86,
        "roles": [
            "threat intelligence analyst",
            "junior threat intelligence analyst",
            "cyber threat intelligence analyst",
            "cyber threat intelligence associate",
            "threat research analyst",
            "threat research associate",
            "intelligence analyst",
            "cyber intelligence analyst",
            "osint analyst",
            "cyber research analyst",
            "threat intelligence intern",
            "cyber threat research intern",
        ],
    },

    "digital_forensics": {
        "priority": 82,
        "roles": [
            "digital forensics analyst",
            "digital forensics associate",
            "cyber forensics analyst",
            "computer forensics analyst",
            "digital investigation analyst",
            "cyber investigation analyst",
            "dfir analyst",
            "incident response & forensics analyst",
            "cyber forensics intern",
            "digital forensics intern",
        ],
    },

    "security_engineering": {
        "priority": 84,
        "roles": [
            "junior security engineer",
            "graduate security engineer",
            "security engineer entry level",
            "cybersecurity engineer",
            "junior cybersecurity engineer",
            "network security engineer",
            "junior network security engineer",
            "network security analyst",
            "junior network security analyst",
            "infrastructure security analyst",
            "cloud security analyst",
            "security infrastructure analyst",
            "security systems analyst",
        ],
    },

    "grc_risk_compliance": {
        "priority": 76,
        "roles": [
            "grc analyst",
            "junior grc analyst",
            "governance risk compliance analyst",
            "governance risk & compliance analyst",
            "risk & compliance analyst",
            "information security grc analyst",
            "cybersecurity grc analyst",
            "it risk analyst",
            "information security risk analyst",
            "security compliance analyst",
            "information security compliance analyst",
            "it compliance analyst",
            "security governance analyst",
            "third party risk analyst",
            "technology risk analyst",
            "cyber risk analyst",
            "privacy analyst",
            "compliance analyst",
            "risk analyst",
        ],
    },

    # --------------------------------------------------------
    # SOFTWARE
    # --------------------------------------------------------

    "software_development": {
        "priority": 82,
        "roles": [
            "software engineer",
            "junior software engineer",
            "software developer",
            "junior software developer",
            "software development engineer",
            "application developer",
            "junior application developer",
            "backend developer",
            "junior backend developer",
            "frontend developer",
            "junior frontend developer",
            "full stack developer",
            "junior full stack developer",
            "full stack engineer",
            "web developer",
            "python developer",
            "java developer",
            "javascript developer",
            "typescript developer",
            ".net developer",
            "c# developer",
            "php developer",
            "node.js developer",
            "react developer",
            "android developer",
            "ios developer",
        ],
    },

    # --------------------------------------------------------
    # QA / TESTING
    # --------------------------------------------------------

    "qa_testing": {
        "priority": 84,
        "roles": [
            "qa engineer",
            "junior qa engineer",
            "qa analyst",
            "qa tester",
            "software tester",
            "test engineer",
            "junior test engineer",
            "quality assurance engineer",
            "quality assurance analyst",
            "api tester",
            "api testing engineer",
            "manual tester",
            "automation tester",
            "qa automation engineer",
            "test automation engineer",
            "software engineer in test",
            "sdet",
        ],
    },

    # --------------------------------------------------------
    # DEVOPS / CLOUD / SRE
    # --------------------------------------------------------

    "devops_cloud_sre": {
        "priority": 82,
        "roles": [
            "devops engineer",
            "junior devops engineer",
            "devops intern",
            "cloud engineer",
            "junior cloud engineer",
            "cloud support engineer",
            "cloud support associate",
            "cloud operations engineer",
            "cloud administrator",
            "junior cloud administrator",
            "site reliability engineer",
            "junior site reliability engineer",
            "sre engineer",
            "platform engineer",
            "junior platform engineer",
            "infrastructure engineer",
            "junior infrastructure engineer",
        ],
    },

    # --------------------------------------------------------
    # NETWORKING
    # --------------------------------------------------------

    "networking": {
        "priority": 82,
        "roles": [
            "network engineer",
            "junior network engineer",
            "network administrator",
            "junior network administrator",
            "network support engineer",
            "network support analyst",
            "network operations engineer",
            "noc engineer",
            "noc analyst",
            "network technician",
            "network systems engineer",
        ],
    },

    # --------------------------------------------------------
    # IT SUPPORT
    # --------------------------------------------------------

    "it_support": {
        "priority": 84,
        "roles": [
            "it support engineer",
            "it support specialist",
            "it support analyst",
            "technical support engineer",
            "technical support specialist",
            "technical support analyst",
            "desktop support engineer",
            "desktop support technician",
            "desktop support analyst",
            "service desk analyst",
            "service desk engineer",
            "help desk analyst",
            "help desk technician",
            "it service desk",
            "system support engineer",
            "application support engineer",
            "l1 support engineer",
            "l1 technical support engineer",
        ],
    },

    # --------------------------------------------------------
    # SYSTEMS
    # --------------------------------------------------------

    "systems_linux_windows": {
        "priority": 80,
        "roles": [
            "systems administrator",
            "system administrator",
            "linux administrator",
            "linux support engineer",
            "windows administrator",
            "windows support engineer",
            "systems engineer",
            "junior systems engineer",
            "linux engineer",
            "windows engineer",
        ],
    },

    # --------------------------------------------------------
    # DATABASE / SQL
    # --------------------------------------------------------

    "database_sql": {
        "priority": 76,
        "roles": [
            "sql developer",
            "junior sql developer",
            "database developer",
            "junior database developer",
            "database administrator",
            "junior database administrator",
            "database analyst",
            "sql analyst",
            "database engineer",
            "junior database engineer",
        ],
    },

    # --------------------------------------------------------
    # DATA / BI
    # --------------------------------------------------------

    "data_analytics": {
        "priority": 72,
        "roles": [
            "data analyst",
            "junior data analyst",
            "data analytics analyst",
            "business intelligence analyst",
            "bi analyst",
            "reporting analyst",
            "data operations analyst",
            "data operations associate",
            "data analyst intern",
        ],
    },

    # --------------------------------------------------------
    # AI / ML
    # --------------------------------------------------------

    "ai_ml": {
        "priority": 70,
        "roles": [
            "machine learning engineer",
            "junior machine learning engineer",
            "ai engineer",
            "junior ai engineer",
            "artificial intelligence engineer",
            "data scientist",
            "junior data scientist",
            "ml engineer",
            "ai intern",
            "machine learning intern",
        ],
    },

    # --------------------------------------------------------
    # INTERNSHIPS / GRADUATE
    # --------------------------------------------------------

    "security_internships": {
        "priority": 96,
        "roles": [
            "cybersecurity intern",
            "cyber security intern",
            "soc intern",
            "soc analyst intern",
            "security operations intern",
            "cybersecurity analyst intern",
            "information security intern",
            "information security analyst intern",
            "security monitoring intern",
            "blue team intern",
            "cyber defense intern",
            "incident response intern",
            "digital forensics intern",
            "iam intern",
            "grc intern",
            "security engineering intern",
            "cybersecurity trainee",
            "security analyst trainee",
            "soc trainee",
            "cybersecurity graduate trainee",
            "graduate security analyst",
            "graduate cybersecurity analyst",
            "graduate soc analyst",
            "security operations trainee",
            "associate security analyst",
        ],
    },
}


# ============================================================
# NEGATIVE TITLE PATTERNS
# ============================================================

NEGATIVE_TITLE_PATTERNS = [
    r"\bsales\b",
    r"\bbusiness development\b",
    r"\baccount executive\b",
    r"\baccount manager\b",
    r"\bmarketing\b",
    r"\brecruiter\b",
    r"\brecruitment\b",
    r"\btalent acquisition\b",
    r"\bhuman resources\b",
    r"\bhr manager\b",
    r"\bfinance\b",
    r"\baccountant\b",
    r"\bpayroll\b",
    r"\bprocurement\b",
    r"\blegal\b",
    r"\bcustomer success\b",
    r"\bproduct manager\b",
    r"\bproject manager\b",
    r"\bprogram manager\b",
    r"\boperations manager\b",
]


# ============================================================
# HARD SENIOR / EXPERIENCED TITLE PATTERNS
# ============================================================

SENIOR_TITLE_PATTERNS = [
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\blead\b",
    r"\bprincipal\b",
    r"\bstaff\b",
    r"\bexpert\b",
    r"\barchitect\b",
    r"\bmanager\b",
    r"\bdirector\b",
    r"\bhead\b",
    r"\bchief\b",
    r"\bciso\b",
    r"\bvice president\b",
    r"\bvp\b",
    r"\bavp\b",
    r"\bmid[- ]level\b",
    r"\bmidlevel\b",
    r"\bexperienced\b",
    r"\blevel\s*[2-9]\b",
    r"\bl[2-9]\b",
    r"\bii\b",
    r"\biii\b",
    r"\biv\b",
    r"\bv\b",
    r"\b(?:engineer|developer|analyst|tester|scientist|administrator|specialist)\s*[2-9]\b",
]


# ============================================================
# INDIA LOCATIONS
# ============================================================

INDIA_LOCATIONS = [
    "india",
    "hyderabad",
    "bengaluru",
    "bangalore",
    "pune",
    "mumbai",
    "chennai",
    "delhi",
    "new delhi",
    "gurugram",
    "gurgaon",
    "noida",
    "kolkata",
    "kochi",
    "coimbatore",
    "ahmedabad",
    "jaipur",
    "indore",
    "bhubaneswar",
    "chandigarh",
    "trivandrum",
    "thiruvananthapuram",
    "mysore",
    "mysuru",
]


# ============================================================
# FOREIGN LOCATIONS
# ============================================================

FOREIGN_LOCATIONS = [
    "united states",
    "united states of america",
    "usa",
    "u.s.",
    "canada",
    "united kingdom",
    "uk",
    "england",
    "scotland",
    "ireland",
    "germany",
    "france",
    "spain",
    "italy",
    "netherlands",
    "sweden",
    "norway",
    "denmark",
    "finland",
    "poland",
    "romania",
    "portugal",
    "australia",
    "new zealand",
    "singapore",
    "malaysia",
    "philippines",
    "indonesia",
    "japan",
    "south korea",
    "colombia",
    "mexico",
    "brazil",
    "argentina",
    "chile",
    "taiwan",
    "hong kong",
    "israel",
    "switzerland",
    "belgium",
    "austria",
]


GLOBAL_REMOTE_PATTERNS = [
    "global",
    "worldwide",
    "anywhere",
    "work from anywhere",
    "remote - international",
    "remote international",
    "international remote",
]


# ============================================================
# FRESHER PATTERNS
# ============================================================

FRESHER_PATTERNS = [
    r"\b0\s*[-–]\s*[1-3]\s*years?\b",
    r"\bno experience\b",
    r"\bexperience not required\b",
    r"\bentry[- ]level\b",
    r"\bfresher\b",
    r"\brecent graduate\b",
    r"\bnew graduate\b",
    r"\bgraduate\b",
    r"\btrainee\b",
    r"\bjunior\b",
    r"\bapprentice\b",
    r"\bintern\b",
    r"\binternship\b",
]


# ============================================================
# EXPERIENCE REJECTION
# ============================================================

EXPERIENCE_REJECT_PATTERNS = [
    r"\b[1-9]\s*[-–]\s*[2-9]\s*years?\b",
    r"\b[2-9]\+\s*years?\b",
    r"\b10\+\s*years?\b",
    r"\b[2-9]\s*years?\b",
    r"\b10\s*years?\b",
]


# ============================================================
# HELPERS
# ============================================================

def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[/|]+", " ", text)
    text = re.sub(r"[^a-z0-9+#.\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_role(title: str):
    normalized_title = normalize(title)

    best_role = None
    best_priority = -1
    best_length = -1

    for group, data in ROLE_GROUPS.items():
        priority = int(data.get("priority", 70))

        for role in data.get("roles", []):
            role_normalized = normalize(role)

            if not role_normalized:
                continue

            if role_normalized in normalized_title:
                if (
                    priority > best_priority
                    or (
                        priority == best_priority
                        and len(role_normalized) > best_length
                    )
                ):
                    best_role = {
                        "group": group,
                        "role": role,
                        "priority": priority,
                    }

                    best_priority = priority
                    best_length = len(role_normalized)

    return best_role


def contains_pattern(
    text: str,
    patterns: list[str],
) -> bool:
    for pattern in patterns:
        if re.search(pattern, text):
            return True

    return False


def is_india_location(
    location: str,
) -> bool:
    location_lower = normalize(location)

    # Explicit foreign location always wins.
    for country in FOREIGN_LOCATIONS:
        if country in location_lower:
            return False

    # Generic global remote is not sufficient.
    for pattern in GLOBAL_REMOTE_PATTERNS:
        if pattern in location_lower:
            return False

    return any(
        city in location_lower
        for city in INDIA_LOCATIONS
    )


def has_fresher_signal(
    title: str,
    experience: str,
    description: str,
) -> bool:

    combined = " ".join(
        [
            normalize(title),
            normalize(experience),
            normalize(description),
        ]
    )

    return contains_pattern(
        combined,
        FRESHER_PATTERNS,
    )


def has_experience_mismatch(
    title: str,
    experience: str,
    description: str,
) -> bool:
    """
    Return True only when the posting clearly requires
    prior experience.
    """

    explicit = normalize(experience)

    # Structured experience field is strongest.
    if explicit:

        # Accept 0-1, 0-2 and 0-3 years.
        if re.search(
            r"\b0\s*[-–]\s*[1-3]\s*years?\b",
            explicit,
        ):
            return False

        # Accept explicit entry-level wording.
        if contains_pattern(
            explicit,
            [
                r"\bno experience\b",
                r"\bexperience not required\b",
                r"\bentry[- ]level\b",
                r"\bfresher\b",
                r"\brecent graduate\b",
                r"\bnew graduate\b",
                r"\bgraduate\b",
                r"\btrainee\b",
                r"\bjunior\b",
                r"\bapprentice\b",
                r"\bintern\b",
                r"\binternship\b",
            ],
        ):
            return False

        # Reject ranges starting above zero.
        if re.search(
            r"\b[1-9]\s*[-–]\s*[2-9]\s*years?\b",
            explicit,
        ):
            return True

        # Reject explicit 2+ through 10+ years.
        if re.search(
            r"\b(?:[2-9]|10)\+?\s*years?\b",
            explicit,
        ):
            return True

        # Reject remaining explicit numeric experience.
        if re.search(
            r"\b[1-9]\s*years?\b",
            explicit,
        ):
            return True

    # Description-level rejection only when it clearly
    # expresses a required experience threshold.
    combined = " ".join(
        [
            normalize(title),
            normalize(description),
        ]
    )

    required_experience_patterns = [
        r"\brequir(?:e|es|ed|ing)\b[^.]{0,80}\b"
        r"(?:at\s+least\s+)?[1-9]\s*\+?\s*years?\b",

        r"\bminimum\s+(?:of\s+)?[1-9]\s*\+?\s*years?\b",

        r"\b[1-9]\s*\+?\s*years?\s+"
        r"(?:of\s+)?(?:experience|work experience)\b",

        r"\b[1-9]\s*[-–]\s*[2-9]\s*years?\s+"
        r"(?:of\s+)?(?:experience|work experience)\b",

        r"\b10\s*\+?\s*years?\s+"
        r"(?:of\s+)?(?:experience|work experience)\b",

        r"\b[1-9]\s*\+?\s*years?\b[^.]{0,30}"
        r"\b(?:required|preferred|mandatory|minimum)\b",
    ]

    return contains_pattern(
        combined,
        required_experience_patterns,
    )


# ============================================================
# MAIN MATCH FUNCTION
# ============================================================

def match_job(
    title: str,
    description: str = "",
    location: str = "",
    experience_text: str = "",
):

    title = str(title or "")
    description = str(description or "")
    location = str(location or "")
    experience_text = str(
        experience_text or ""
    )

    title_lower = normalize(title)

    # --------------------------------------------------------
    # 1. EMPTY TITLE
    # --------------------------------------------------------

    if not title_lower:
        return {
            "matched": False,
            "category": "NONE",
            "match_score": 0,
            "india_eligible": False,
            "fresher_friendly": False,
            "reason": "NO_TITLE",
        }

    # --------------------------------------------------------
    # 2. SENIOR / LEVEL REJECTION
    # --------------------------------------------------------

    if contains_pattern(
        title_lower,
        SENIOR_TITLE_PATTERNS,
    ):
        return {
            "matched": False,
            "category": "REJECTED",
            "match_score": 0,
            "india_eligible": False,
            "fresher_friendly": False,
            "reason": "SENIOR_OR_EXPERIENCED_TITLE",
        }

    # --------------------------------------------------------
    # 3. NON-TECHNICAL REJECTION
    # --------------------------------------------------------

    if contains_pattern(
        title_lower,
        NEGATIVE_TITLE_PATTERNS,
    ):
        return {
            "matched": False,
            "category": "NONE",
            "match_score": 0,
            "india_eligible": False,
            "fresher_friendly": False,
            "reason": "NON_TECHNICAL_ROLE",
        }

    # --------------------------------------------------------
    # 4. INDIA LOCATION
    # --------------------------------------------------------

    india_eligible = is_india_location(
        location
    )

    if not india_eligible:
        return {
            "matched": False,
            "category": "OUTSIDE_INDIA",
            "match_score": 0,
            "india_eligible": False,
            "fresher_friendly": False,
            "reason": "NON_INDIA_LOCATION",
        }

    # --------------------------------------------------------
    # 5. EXPERIENCE REJECTION
    # --------------------------------------------------------

    if has_experience_mismatch(
        title,
        experience_text,
        description,
    ):
        return {
            "matched": False,
            "category": "EXPERIENCE_MISMATCH",
            "match_score": 0,
            "india_eligible": True,
            "fresher_friendly": False,
            "reason": (
                "EXPERIENCE_REQUIREMENT_NOT_FRESHER"
            ),
        }

    # --------------------------------------------------------
    # 6. FRESHER SIGNAL
    # --------------------------------------------------------

    fresher_friendly = has_fresher_signal(
        title,
        experience_text,
        description,
    )

    fresher_status = (
        "CONFIRMED"
        if fresher_friendly
        else "UNCONFIRMED"
    )

    # IMPORTANT:
    # Do not reject a target role just because the
    # employer omitted an explicit fresher keyword.
    #
    # Senior titles and explicit experience requirements
    # were already rejected above.

    # --------------------------------------------------------
    # 7. ROLE MATCH
    # --------------------------------------------------------

    role = find_role(title)

    if not role:
        return {
            "matched": False,
            "category": "NONE",
            "match_score": 0,
            "india_eligible": True,
            "fresher_friendly": fresher_friendly,
            "fresher_status": fresher_status,
            "reason": "ROLE_NOT_TARGETED",
        }

    # --------------------------------------------------------
    # 8. SCORE
    # --------------------------------------------------------

    # Initialize score BEFORE applying fresher bonus.
    score = 40

    # Fresher signal.
    if fresher_friendly:
        score += 20
    else:
        score += 5

    # Role priority.
    score += min(
        int(role["priority"] * 0.20),
        20,
    )

    location_lower = normalize(
        location
    )

    if "hyderabad" in location_lower:
        score += 8

    elif "india remote" in location_lower:
        score += 8

    else:
        score += 5

    # Internship / trainee bonus.
    if (
        "intern" in title_lower
        or "internship" in title_lower
        or "trainee" in title_lower
    ):
        score += 10

    score = min(
        score,
        98,
    )

    if score >= 90:
        category = "STRONG"

    elif score >= 75:
        category = "GOOD"

    else:
        category = "MAYBE"

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


# ============================================================
# TESTS
# ============================================================

if __name__ == "__main__":

    tests = [
        # GOOD MATCHES
        (
            "SOC Analyst L1",
            "Hyderabad, India",
            "0-1 years",
        ),
        (
            "Junior Cybersecurity Analyst",
            "Bengaluru, India",
            "0-2 years",
        ),
        (
            "Security Analyst",
            "Pune, India",
            "Fresher",
        ),
        (
            "GRC Analyst",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Junior Software Engineer",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Python Developer",
            "Bengaluru, India",
            "Fresher",
        ),
        (
            "API Testing Engineer",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Junior QA Engineer",
            "Pune, India",
            "0-1 years",
        ),
        (
            "Junior DevOps Engineer",
            "Bengaluru, India",
            "0-2 years",
        ),
        (
            "Cloud Support Engineer",
            "India Remote",
            "Entry Level",
        ),
        (
            "Junior Network Engineer",
            "Hyderabad, India",
            "0-1 years",
        ),
        (
            "IT Support Engineer",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Service Desk Analyst",
            "Bengaluru, India",
            "Fresher",
        ),
        (
            "Junior SQL Developer",
            "Pune, India",
            "0-2 years",
        ),
        (
            "Junior Data Analyst",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Junior Machine Learning Engineer",
            "Bengaluru, India",
            "0-2 years",
        ),
        (
            "Cybersecurity Intern",
            "Hyderabad, India",
            "Internship",
        ),

        # HARD REJECTS
        (
            "Senior Software Engineer",
            "Hyderabad, India",
            "5+ years",
        ),
        (
            "Software Engineer III",
            "Hyderabad, India",
            "3+ years",
        ),
        (
            "Software Developer II",
            "Pune, India",
            "2-4 years",
        ),
        (
            "Security Architect",
            "Bengaluru, India",
            "7+ years",
        ),
        (
            "Cybersecurity Manager",
            "India",
            "5+ years",
        ),
        (
            "Expert Network Engineer",
            "Pune, India",
            "8+ years",
        ),
        (
            "QA Engineer",
            "Pune, India",
            "1-2 years",
        ),
        (
            "Technical Recruiter",
            "Bengaluru, India",
            "0-2 years",
        ),
        (
            "Sales Development Representative",
            "Hyderabad, India",
            "0-2 years",
        ),
        (
            "Software Engineer",
            "United States",
            "0-2 years",
        ),
        (
            "Software Engineer",
            "Remote - Poland",
            "0-2 years",
        ),
        (
            "Software Engineer",
            "Global",
            "0-2 years",
        ),
        (
            "Software Engineer",
            "Worldwide",
            "0-2 years",
        ),
    ]

    print(
        "=" * 75
    )

    print(
        "TECHNICAL FRESHER MATCHER - HARD FILTER TEST"
    )

    print(
        "=" * 75
    )

    passed = 0
    failed = 0

    for title, location, experience in tests:

        result = match_job(
            title=title,
            location=location,
            experience_text=experience,
            description="",
        )

        score = result.get(
            "match_score",
            0,
        )

        category = result.get(
            "category",
            "NONE",
        )

        should_match = (
            title
            in {
                "SOC Analyst L1",
                "Junior Cybersecurity Analyst",
                "Security Analyst",
                "GRC Analyst",
                "Junior Software Engineer",
                "Python Developer",
                "API Testing Engineer",
                "Junior QA Engineer",
                "Junior DevOps Engineer",
                "Cloud Support Engineer",
                "Junior Network Engineer",
                "IT Support Engineer",
                "Service Desk Analyst",
                "Junior SQL Developer",
                "Junior Data Analyst",
                "Junior Machine Learning Engineer",
                "Cybersecurity Intern",
            }
        )

        actual_match = result.get(
            "matched",
            False,
        )

        if actual_match == should_match:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        print(
            f"[{status}] "
            f"{score:3}/100 | "
            f"{category:20} | "
            f"{title:38} | "
            f"{location}"
        )

    print(
        "=" * 75
    )

    print(
        f"TESTS PASSED : {passed}"
    )

    print(
        f"TESTS FAILED : {failed}"
    )

    print(
        "=" * 75
    )

    if failed == 0:
        print(
            "ALL MATCHER TESTS PASSED"
        )
    else:
        print(
            "SOME MATCHER TESTS FAILED"
        )
