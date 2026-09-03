"""
India Location Intelligence Configuration
==========================================

Single source of truth for India job-location discovery.

Coverage:
- 28 States
- 8 Union Territories
- Major employment cities
- Common location aliases
- Remote / Pan-India search terms

Used by:
- Search discovery
- Job-board queries
- ATS discovery
- Location normalization
- Job matching
"""

# ============================================================
# 28 STATES
# ============================================================

INDIA_STATES = {
    "Andhra Pradesh": [
        "Visakhapatnam",
        "Vijayawada",
        "Tirupati",
        "Guntur",
        "Nellore",
        "Kurnool",
        "Rajahmundry",
        "Kakinada",
        "Anantapur",
        "Kadapa",
        "Amaravati",
    ],

    "Arunachal Pradesh": [
        "Itanagar",
        "Naharlagun",
        "Tawang",
        "Pasighat",
        "Ziro",
    ],

    "Assam": [
        "Guwahati",
        "Dibrugarh",
        "Silchar",
        "Jorhat",
        "Tezpur",
    ],

    "Bihar": [
        "Patna",
        "Gaya",
        "Muzaffarpur",
        "Bhagalpur",
        "Darbhanga",
        "Purnia",
    ],

    "Chhattisgarh": [
        "Raipur",
        "Bhilai",
        "Durg",
        "Bilaspur",
        "Korba",
        "Jagdalpur",
    ],

    "Goa": [
        "Panaji",
        "Vasco da Gama",
        "Margao",
        "Mapusa",
    ],

    "Gujarat": [
        "Ahmedabad",
        "Gandhinagar",
        "Surat",
        "Vadodara",
        "Rajkot",
        "Jamnagar",
        "Bhavnagar",
        "Anand",
        "Vapi",
    ],

    "Haryana": [
        "Gurugram",
        "Gurgaon",
        "Faridabad",
        "Panipat",
        "Ambala",
        "Hisar",
        "Rohtak",
        "Sonipat",
        "Karnal",
    ],

    "Himachal Pradesh": [
        "Shimla",
        "Dharamshala",
        "Manali",
        "Solan",
        "Baddi",
        "Mandi",
    ],

    "Jharkhand": [
        "Ranchi",
        "Jamshedpur",
        "Dhanbad",
        "Bokaro",
        "Deoghar",
    ],

    "Karnataka": [
        "Bengaluru",
        "Bangalore",
        "Mysuru",
        "Mangalore",
        "Mangaluru",
        "Hubballi",
        "Dharwad",
        "Belagavi",
        "Ballari",
        "Tumakuru",
        "Shivamogga",
    ],

    "Kerala": [
        "Thiruvananthapuram",
        "Trivandrum",
        "Kochi",
        "Cochin",
        "Kozhikode",
        "Calicut",
        "Thrissur",
        "Kollam",
        "Kannur",
        "Alappuzha",
    ],

    "Madhya Pradesh": [
        "Bhopal",
        "Indore",
        "Jabalpur",
        "Gwalior",
        "Ujjain",
        "Sagar",
        "Rewa",
        "Ratlam",
    ],

    "Maharashtra": [
        "Mumbai",
        "Navi Mumbai",
        "Pune",
        "Nagpur",
        "Nashik",
        "Aurangabad",
        "Chhatrapati Sambhajinagar",
        "Thane",
        "Kolhapur",
        "Solapur",
        "Amravati",
    ],

    "Manipur": [
        "Imphal",
        "Thoubal",
        "Churachandpur",
    ],

    "Meghalaya": [
        "Shillong",
        "Tura",
        "Jowai",
    ],

    "Mizoram": [
        "Aizawl",
        "Lunglei",
        "Champhai",
    ],

    "Nagaland": [
        "Kohima",
        "Dimapur",
        "Mokokchung",
    ],

    "Odisha": [
        "Bhubaneswar",
        "Cuttack",
        "Rourkela",
        "Berhampur",
        "Sambalpur",
        "Puri",
        "Balasore",
    ],

    "Punjab": [
        "Chandigarh",
        "Ludhiana",
        "Amritsar",
        "Jalandhar",
        "Patiala",
        "Mohali",
        "Bathinda",
    ],

    "Rajasthan": [
        "Jaipur",
        "Jodhpur",
        "Udaipur",
        "Kota",
        "Ajmer",
        "Bikaner",
        "Alwar",
        "Bhilwara",
    ],

    "Sikkim": [
        "Gangtok",
        "Namchi",
        "Gyalshing",
    ],

    "Tamil Nadu": [
        "Chennai",
        "Coimbatore",
        "Madurai",
        "Tiruchirappalli",
        "Trichy",
        "Salem",
        "Tiruppur",
        "Erode",
        "Vellore",
        "Thoothukudi",
        "Hosur",
    ],

    "Telangana": [
        "Hyderabad",
        "Secunderabad",
        "Warangal",
        "Hanamkonda",
        "Karimnagar",
        "Nizamabad",
        "Khammam",
        "Nalgonda",
        "Adilabad",
    ],

    "Tripura": [
        "Agartala",
        "Udaipur",
        "Dharmanagar",
    ],

    "Uttar Pradesh": [
        "Noida",
        "Greater Noida",
        "Lucknow",
        "Kanpur",
        "Agra",
        "Varanasi",
        "Prayagraj",
        "Ghaziabad",
        "Meerut",
        "Gorakhpur",
        "Bareilly",
        "Mathura",
    ],

    "Uttarakhand": [
        "Dehradun",
        "Haridwar",
        "Rishikesh",
        "Roorkee",
        "Haldwani",
        "Nainital",
    ],

    "West Bengal": [
        "Kolkata",
        "Howrah",
        "Siliguri",
        "Durgapur",
        "Asansol",
    ],
}


# ============================================================
# 8 UNION TERRITORIES
# ============================================================

INDIA_UTS = {
    "Andaman and Nicobar Islands": [
        "Port Blair",
        "Sri Vijaya Puram",
    ],

    "Chandigarh": [
        "Chandigarh",
    ],

    "Dadra and Nagar Haveli and Daman and Diu": [
        "Daman",
        "Diu",
        "Silvassa",
    ],

    "Delhi": [
        "New Delhi",
        "Delhi",
    ],

    "Jammu and Kashmir": [
        "Srinagar",
        "Jammu",
        "Anantnag",
        "Baramulla",
    ],

    "Ladakh": [
        "Leh",
        "Kargil",
    ],

    "Lakshadweep": [
        "Kavaratti",
        "Agatti",
    ],

    "Puducherry": [
        "Puducherry",
        "Pondicherry",
        "Karaikal",
        "Mahe",
        "Yanam",
    ],
}


# ============================================================
# COMMON LOCATION ALIASES
# ============================================================

LOCATION_ALIASES = {
    "Bangalore": "Bengaluru",
    "Bengaluru": "Bengaluru",

    "Bombay": "Mumbai",
    "Mumbai": "Mumbai",

    "Calcutta": "Kolkata",
    "Kolkata": "Kolkata",

    "Madras": "Chennai",
    "Chennai": "Chennai",

    "Cochin": "Kochi",
    "Kochi": "Kochi",

    "Trivandrum": "Thiruvananthapuram",
    "Thiruvananthapuram": "Thiruvananthapuram",

    "Calicut": "Kozhikode",
    "Kozhikode": "Kozhikode",

    "Gurgaon": "Gurugram",
    "Gurugram": "Gurugram",

    "Mangalore": "Mangaluru",
    "Mangaluru": "Mangaluru",

    "Mysore": "Mysuru",
    "Mysuru": "Mysuru",

    "Pondicherry": "Puducherry",
    "Puducherry": "Puducherry",

    "Trichy": "Tiruchirappalli",
    "Tiruchirappalli": "Tiruchirappalli",

    "Noida": "Noida",
    "New Delhi": "Delhi",
}


# ============================================================
# REMOTE / INDIA-WIDE SEARCH TERMS
# ============================================================

REMOTE_LOCATION_TERMS = [
    "Remote",
    "Remote - India",
    "Remote India",
    "Work From Home",
    "Work From Home - India",
    "WFH",
    "Anywhere in India",
    "Pan India",
    "India - Remote",
    "India Remote",
    "Remote Anywhere in India",
]


# ============================================================
# ALL INDIA SEARCH TERMS
# ============================================================

ALL_INDIA_TERMS = [
    "India",
    "India - All Locations",
    "Pan India",
    "Anywhere in India",
    "Remote India",
    "Remote - India",
    "Work From Home India",
]


# ============================================================
# BUILD MASTER LOCATION LIST
# ============================================================

ALL_STATES = list(INDIA_STATES.keys())

ALL_UTS = list(INDIA_UTS.keys())

ALL_INDIA_REGIONS = ALL_STATES + ALL_UTS


def get_all_cities():
    """Return all known cities across India."""
    cities = []

    for state_cities in INDIA_STATES.values():
        cities.extend(state_cities)

    for ut_cities in INDIA_UTS.values():
        cities.extend(ut_cities)

    return sorted(set(cities))


ALL_INDIA_CITIES = get_all_cities()


def get_search_locations():
    """
    Return every state, UT and known city that
    should be used for job discovery.
    """
    return sorted(
        set(
            ALL_INDIA_REGIONS
            + ALL_INDIA_CITIES
            + REMOTE_LOCATION_TERMS
            + ALL_INDIA_TERMS
        )
    )


SEARCH_LOCATIONS = get_search_locations()


# ============================================================
# LOCATION LOOKUP
# ============================================================

def normalize_location(location: str) -> str:
    """
    Normalize common Indian location aliases.
    """
    if not location:
        return ""

    cleaned = " ".join(location.strip().split())

    return LOCATION_ALIASES.get(cleaned, cleaned)


def find_state_for_city(city: str):
    """
    Find the state/UT containing a city.
    """
    normalized = normalize_location(city).lower()

    for state, cities in INDIA_STATES.items():
        if any(normalize_location(c).lower() == normalized for c in cities):
            return state

    for ut, cities in INDIA_UTS.items():
        if any(normalize_location(c).lower() == normalized for c in cities):
            return ut

    return None


def is_india_location(location: str) -> bool:
    """
    Determine whether text appears to represent
    an India-wide or Indian location.
    """
    if not location:
        return False

    value = location.lower()

    if "india" in value:
        return True

    for region in ALL_INDIA_REGIONS:
        if region.lower() in value:
            return True

    for city in ALL_INDIA_CITIES:
        if city.lower() in value:
            return True

    return False


# ============================================================
# DEBUG / INFORMATION
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("INDIA LOCATION CONFIGURATION")
    print("=" * 60)

    print(f"States: {len(ALL_STATES)}")
    print(f"Union Territories: {len(ALL_UTS)}")
    print(f"Regions: {len(ALL_INDIA_REGIONS)}")
    print(f"Known cities: {len(ALL_INDIA_CITIES)}")
    print(f"Search locations: {len(SEARCH_LOCATIONS)}")

    print("\nStates:")
    for state in ALL_STATES:
        print(f"  - {state}")

    print("\nUnion Territories:")
    for ut in ALL_UTS:
        print(f"  - {ut}")

    print("\nRemote / India-wide:")
    for term in REMOTE_LOCATION_TERMS:
        print(f"  - {term}")

    print("=" * 60)