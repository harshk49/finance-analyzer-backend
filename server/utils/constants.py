"""Constants — category mappings, rules, and configuration values."""

# Spending categories with associated keywords (for rule-based categorization)
CATEGORY_RULES: dict[str, list[str]] = {
    "Food & Dining": [
        "swiggy", "zomato", "uber eats", "dominos", "pizza", "mcdonalds",
        "kfc", "burger", "restaurant", "cafe", "coffee", "starbucks",
        "food", "dining", "meal", "lunch", "dinner", "breakfast",
        "biryani", "dosa", "chai", "bakery", "ice cream", "dessert",
        "haldiram", "barbeque", "eat", "kitchen", "dhaba",
    ],
    "Groceries": [
        "bigbasket", "blinkit", "zepto", "dmart", "grocery", "supermarket",
        "reliance fresh", "more", "star bazaar", "nature basket",
        "vegetables", "fruits", "milk", "provisions", "kirana",
        "jiomart", "amazon fresh", "dunzo", "instamart",
    ],
    "Transport": [
        "uber", "ola", "rapido", "metro", "bus", "train", "irctc",
        "petrol", "diesel", "fuel", "parking", "toll", "fastag",
        "redbus", "makemytrip", "cab", "auto", "rickshaw", "lyft",
        "gas station", "shell", "hp petrol", "indian oil",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa",
        "shopping", "mall", "store", "retail", "purchase", "buy",
        "snapdeal", "tatacliq", "firstcry", "bewakoof", "zara",
        "h&m", "uniqlo", "decathlon",
    ],
    "Entertainment": [
        "netflix", "hotstar", "prime video", "spotify", "youtube",
        "movie", "cinema", "pvr", "inox", "theatre", "gaming",
        "steam", "playstation", "xbox", "concert", "event",
        "disney", "zee5", "sonyliv", "jiocinema", "bookmyshow",
    ],
    "Bills & Utilities": [
        "electricity", "water", "gas bill", "broadband", "internet",
        "wifi", "jio", "airtel", "vi", "bsnl", "phone bill",
        "recharge", "postpaid", "prepaid", "dth", "tata sky",
        "municipal", "maintenance", "society",
    ],
    "Rent & Housing": [
        "rent", "housing", "apartment", "flat", "lease", "landlord",
        "property", "maintenance", "broker", "pg", "hostel",
    ],
    "Health & Medical": [
        "hospital", "clinic", "doctor", "medical", "pharmacy",
        "medicine", "apollo", "1mg", "netmeds", "pharmeasy",
        "diagnostic", "lab", "health", "dental", "eye", "therapy",
        "gym", "fitness", "cult", "yoga",
    ],
    "Education": [
        "school", "college", "university", "course", "udemy",
        "coursera", "education", "tuition", "coaching", "books",
        "exam", "unacademy", "byjus", "vedantu",
    ],
    "Insurance": [
        "insurance", "lic", "premium", "policy", "health insurance",
        "life insurance", "motor insurance", "term plan",
    ],
    "Investment": [
        "mutual fund", "sip", "stock", "share", "demat", "zerodha",
        "groww", "upstox", "angel", "fd", "fixed deposit", "ppf",
        "nps", "gold", "investment", "trading",
    ],
    "EMI & Loans": [
        "emi", "loan", "installment", "repayment", "principal",
        "interest", "credit card", "personal loan", "home loan",
        "car loan", "education loan",
    ],
    "Transfer": [
        "transfer", "neft", "rtgs", "imps", "upi", "sent to",
        "paid to", "fund transfer", "self transfer",
    ],
    "ATM & Cash": [
        "atm", "cash withdrawal", "cash deposit", "cash",
    ],
    "Subscriptions": [
        "subscription", "membership", "annual", "monthly plan",
        "premium plan", "pro plan",
    ],
    "Travel": [
        "flight", "hotel", "booking", "airbnb", "oyo", "goibibo",
        "cleartrip", "yatra", "visa", "passport", "travel",
        "indigo", "airindia", "spicejet", "vistara",
    ],
    "Personal Care": [
        "salon", "spa", "grooming", "haircut", "beauty",
        "cosmetics", "skincare", "parlour",
    ],
    "Gifts & Donations": [
        "gift", "donation", "charity", "tip", "fund raiser",
    ],
}

# Icons for categories
CATEGORY_ICONS: dict[str, str] = {
    "Food & Dining": "🍔",
    "Groceries": "🛒",
    "Transport": "🚗",
    "Shopping": "🛍️",
    "Entertainment": "🎬",
    "Bills & Utilities": "💡",
    "Rent & Housing": "🏠",
    "Health & Medical": "🏥",
    "Education": "📚",
    "Insurance": "🛡️",
    "Investment": "📈",
    "EMI & Loans": "🏦",
    "Transfer": "💸",
    "ATM & Cash": "🏧",
    "Subscriptions": "📦",
    "Travel": "✈️",
    "Personal Care": "💇",
    "Gifts & Donations": "🎁",
    "Uncategorized": "❓",
    "Salary": "💰",
    "Refund": "🔄",
    "Interest": "💵",
}

# ── UPI / Payment Noise Patterns ────────────────────────────────────
# Each tuple: (regex_pattern, replacement_string)
# Applied sequentially by MerchantCleaner._remove_upi_noise()
UPI_PATTERNS: list[tuple[str, str]] = [
    # Full UPI message format:  UPI-<MERCHANT>-<REF>-<IFSC>-<ACC>
    (r"(?i)upi[-/][^-/]+[-/][\w]{8,}[-/][A-Z]{4}0\w{6}[-/][\w]+", ""),
    # UPI ref numbers
    (r"(?i)upi\s*ref\s*(?:no|number|#)?\s*:?\s*\d+", ""),
    # Generic ref / UTR numbers
    (r"(?i)(?:ref|utr|rrn|txn)\s*(?:no|number|id|#)?\s*:?\s*[\w]{6,}", ""),
    # MMID / IFSC codes
    (r"\b[A-Z]{4}0[A-Z0-9]{6}\b", ""),
    # Cheque / instrument numbers
    (r"(?i)(?:chq|cheque|chk|instr)\s*(?:no)?\s*:?\s*\d{4,}", ""),
    # UPI handles:  name@okaxis, name@ybl, name@paytm
    (r"[a-zA-Z0-9._]+@[a-zA-Z]{2,15}", ""),
    # Google Pay / PhonePe specific noise
    (r"(?i)google\s*pay\s*[-/]?\s*\d+", "Google Pay"),
    (r"(?i)phonepe\s*[-/]?\s*\d+", "PhonePe"),
    # Long digit sequences (≥ 8 digits — refs, acc nos)
    (r"\b\d{8,}\b", ""),
    # P2P / P2M markers
    (r"(?i)\b(?:p2p|p2m)\b", ""),
    # Common filler words in UPI descriptions
    (r"(?i)\b(?:via|through|by)\s+(?:upi|neft|imps|rtgs)\b", ""),
]

# ── Merchant Keyword Dictionary ─────────────────────────────────────
# Maps lowercase substrings → canonical display names.
# Used by MerchantCleaner._match_known_merchant() for fast O(n) lookup.
MERCHANT_KEYWORDS: dict[str, str] = {
    # Food & Dining
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "uber eats": "Uber Eats",
    "dominos": "Domino's",
    "domino's": "Domino's",
    "mcdonalds": "McDonald's",
    "mcdonald": "McDonald's",
    "kfc": "KFC",
    "burger king": "Burger King",
    "starbucks": "Starbucks",
    "pizza hut": "Pizza Hut",
    "subway": "Subway",
    "haldiram": "Haldiram's",
    "barbeque nation": "Barbeque Nation",
    "box8": "Box8",
    "faasos": "Faasos",
    "behrouz": "Behrouz Biryani",
    "chaayos": "Chaayos",
    "wow momo": "WOW Momo",
    # Groceries
    "bigbasket": "BigBasket",
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "dmart": "DMart",
    "jiomart": "JioMart",
    "amazon fresh": "Amazon Fresh",
    "dunzo": "Dunzo",
    "instamart": "Swiggy Instamart",
    "nature basket": "Nature's Basket",
    "reliance fresh": "Reliance Fresh",
    "more supermarket": "More Supermarket",
    "star bazaar": "Star Bazaar",
    "spencers": "Spencer's",
    # Transport
    "uber": "Uber",
    "ola": "Ola",
    "rapido": "Rapido",
    "irctc": "IRCTC",
    "makemytrip": "MakeMyTrip",
    "redbus": "RedBus",
    "fastag": "FASTag",
    "indian oil": "Indian Oil",
    "hp petrol": "HP Petrol",
    "bharat petroleum": "BPCL",
    "shell": "Shell",
    # Shopping
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "myntra": "Myntra",
    "meesho": "Meesho",
    "ajio": "AJIO",
    "nykaa": "Nykaa",
    "tatacliq": "Tata CLiQ",
    "snapdeal": "Snapdeal",
    "firstcry": "FirstCry",
    "bewakoof": "Bewakoof",
    "zara": "Zara",
    "h&m": "H&M",
    "uniqlo": "Uniqlo",
    "decathlon": "Decathlon",
    "croma": "Croma",
    "reliance digital": "Reliance Digital",
    "vijay sales": "Vijay Sales",
    # Entertainment
    "netflix": "Netflix",
    "hotstar": "Hotstar",
    "spotify": "Spotify",
    "youtube": "YouTube",
    "prime video": "Prime Video",
    "disney": "Disney+ Hotstar",
    "zee5": "ZEE5",
    "sonyliv": "SonyLIV",
    "jiocinema": "JioCinema",
    "bookmyshow": "BookMyShow",
    "steam": "Steam",
    "pvr": "PVR",
    "inox": "INOX",
    # Bills & Utilities
    "jio": "Jio",
    "airtel": "Airtel",
    "bsnl": "BSNL",
    "tata sky": "Tata Play",
    "tata play": "Tata Play",
    # Health
    "apollo": "Apollo",
    "1mg": "1mg",
    "netmeds": "Netmeds",
    "pharmeasy": "PharmEasy",
    "cult.fit": "Cult.fit",
    "cultfit": "Cult.fit",
    # Payments / Fintech
    "phonepe": "PhonePe",
    "paytm": "Paytm",
    "gpay": "Google Pay",
    "google pay": "Google Pay",
    "cred": "CRED",
    "mobikwik": "MobiKwik",
    "freecharge": "FreeCharge",
    "razorpay": "Razorpay",
    # Investment
    "groww": "Groww",
    "zerodha": "Zerodha",
    "upstox": "Upstox",
    "angel one": "Angel One",
    "kuvera": "Kuvera",
    "coin": "Coin by Zerodha",
    # Travel
    "goibibo": "Goibibo",
    "cleartrip": "Cleartrip",
    "yatra": "Yatra",
    "oyo": "OYO",
    "airbnb": "Airbnb",
    "indigo": "IndiGo",
    "air india": "Air India",
    "spicejet": "SpiceJet",
    "vistara": "Vistara",
    # Education
    "udemy": "Udemy",
    "coursera": "Coursera",
    "unacademy": "Unacademy",
    "byju": "BYJU'S",
    "vedantu": "Vedantu",
    "skillshare": "Skillshare",
    # Insurance
    "lic": "LIC",
    "policybazaar": "PolicyBazaar",
    "acko": "Acko",
    "digit insurance": "Digit Insurance",
}

# ── Date format patterns ────────────────────────────────────────────
# Tried in order by CSVParser._parse_date() and DataCleaner._normalize_date()
DATE_FORMATS = [
    # dd/mm/yyyy variants (most common in India)
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    # yyyy-mm-dd (ISO)
    "%Y-%m-%d",
    # mm/dd/yyyy (US)
    "%m/%d/%Y",
    # Short year
    "%d/%m/%y",
    "%d-%m-%y",
    "%d.%m.%y",
    # yyyy/mm/dd
    "%Y/%m/%d",
    # Named months
    "%d %b %Y",       # 15 Mar 2024
    "%d %B %Y",       # 15 March 2024
    "%b %d, %Y",      # Mar 15, 2024
    "%B %d, %Y",      # March 15, 2024
    "%d-%b-%Y",       # 15-Mar-2024
    "%d-%b-%y",       # 15-Mar-24
    "%d/%b/%Y",       # 15/Mar/2024
    "%d %b, %Y",      # 15 Mar, 2024
    # Datetime variants (truncated to date by parsers)
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
]

# ── Column name aliases for auto-detection ──────────────────────────
COLUMN_ALIASES = {
    "date": [
        "date", "transaction date", "txn date", "value date",
        "posting date", "trans date", "dt", "tran date",
    ],
    "description": [
        "description", "narration", "particular", "details",
        "transaction details", "remarks", "memo", "narrative", "desc",
        "transaction description", "txn description",
    ],
    "amount": [
        "amount", "transaction amount", "txn amount", "amt", "value",
        "txn amt",
    ],
    "debit": [
        "debit", "debit amount", "debit amt", "withdrawal",
        "dr", "dr.", "debit(inr)", "withdrawal amt",
    ],
    "credit": [
        "credit", "credit amount", "credit amt", "deposit",
        "cr", "cr.", "credit(inr)", "deposit amt",
    ],
    "balance": [
        "balance", "closing balance", "available balance",
        "running balance", "bal", "closing bal",
    ],
    "type": [
        "type", "transaction type", "txn type", "dr/cr", "cr/dr",
    ],
    "reference": [
        "reference", "ref", "ref no", "reference no",
        "cheque no", "chq no", "utr", "utr no",
    ],
}

# Spending personality types
SPENDING_PERSONALITIES = {
    "saver": {
        "type": "The Disciplined Saver",
        "description": "You consistently save more than you spend. Your financial habits are strong and sustainable.",
        "icon": "🏆",
        "strengths": ["High savings rate", "Controlled spending", "Financial discipline"],
        "risks": ["May under-invest in experiences", "Could miss growth opportunities"],
    },
    "balanced": {
        "type": "The Balanced Spender",
        "description": "You maintain a healthy balance between spending and saving. Room for optimization exists.",
        "icon": "⚖️",
        "strengths": ["Good balance", "Flexible", "Adaptable"],
        "risks": ["Can slip into overspending", "May lack emergency fund"],
    },
    "impulse": {
        "type": "The Impulse Buyer",
        "description": "You tend to make frequent small purchases that add up. Awareness is your greatest tool.",
        "icon": "⚡",
        "strengths": ["Enjoys life", "Takes opportunities"],
        "risks": ["Micro-spending leaks", "Subscription overload", "Low savings"],
    },
    "feast_famine": {
        "type": "The Feast & Famine Spender",
        "description": "Your spending fluctuates wildly between high and low periods. Consistency would help.",
        "icon": "🎢",
        "strengths": ["Can be frugal when motivated"],
        "risks": ["Unpredictable cash flow", "Hard to budget", "Stress spending"],
    },
    "lifestyle_inflator": {
        "type": "The Lifestyle Inflator",
        "description": "Your spending grows proportionally with income. Be mindful of lifestyle creep.",
        "icon": "📊",
        "strengths": ["Growing income", "Enjoys achievements"],
        "risks": ["Lifestyle creep", "Savings don't grow with income"],
    },
}
