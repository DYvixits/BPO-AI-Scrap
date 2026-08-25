"""Curated keyword tables the heuristic parser matches against. These lists
are intentionally modest, not exhaustive — extending them (a new country, a
new industry) is a one-line addition here, never a code change to the
parser itself. Values are lowercase surface forms matched against a
lowercased query.
"""

# Canonical name -> surface forms (name + common demonym/adjective forms).
GEOGRAPHY: dict[str, list[str]] = {
    "Cameroon": ["cameroon", "cameroonian", "cameroun"],
    "Nigeria": ["nigeria", "nigerian"],
    "Kenya": ["kenya", "kenyan"],
    "Ghana": ["ghana", "ghanaian"],
    "South Africa": ["south africa", "south african"],
    "Senegal": ["senegal", "senegalese"],
    "Ivory Coast": ["ivory coast", "côte d'ivoire", "cote d'ivoire", "ivorian"],
    "Egypt": ["egypt", "egyptian"],
    "Morocco": ["morocco", "moroccan"],
    "Tunisia": ["tunisia", "tunisian"],
    "Ethiopia": ["ethiopia", "ethiopian"],
    "Rwanda": ["rwanda", "rwandan"],
    "Uganda": ["uganda", "ugandan"],
    "Tanzania": ["tanzania", "tanzanian"],
    "Algeria": ["algeria", "algerian"],
    "DR Congo": ["dr congo", "democratic republic of congo", "congolese"],
    "United States": ["united states", "usa", "u.s.", "u.s.a", "american"],
    "United Kingdom": ["united kingdom", "uk", "u.k.", "british"],
    "France": ["france", "french"],
    "Germany": ["germany", "german"],
    "India": ["india", "indian"],
    "China": ["china", "chinese"],
    "Brazil": ["brazil", "brazilian"],
    "Canada": ["canada", "canadian"],
    "United Arab Emirates": ["united arab emirates", "uae", "emirati"],
}

INDUSTRY: dict[str, list[str]] = {
    "fintech": ["fintech", "financial technology"],
    "banking": ["bank", "banking", "banks"],
    "healthcare": ["healthcare", "health care", "medical"],
    "logistics": ["logistics", "supply chain"],
    "agritech": ["agritech", "agtech", "agriculture technology"],
    "e-commerce": ["e-commerce", "ecommerce", "online retail"],
    "cybersecurity": ["cybersecurity", "cyber security", "infosec"],
    "telecom": ["telecom", "telecommunications"],
    "energy": ["energy", "renewable energy", "oil and gas"],
    "real estate": ["real estate", "property"],
    "manufacturing": ["manufacturing", "industrial"],
    "insurance": ["insurance", "insurtech"],
    "education": ["education", "edtech"],
    "saas": ["saas", "software as a service"],
    "retail": ["retail"],
    "hospitality": ["hospitality", "hotel", "tourism"],
    "transportation": ["transportation", "transport", "mobility"],
}

# Canonical signal -> (surface forms, polarity). Polarity isn't scored yet
# (that's Phase 7's Commercial Signal Engine / Phase 8's Intent Engine) —
# recorded now so those phases have a documented starting vocabulary.
SIGNALS: dict[str, tuple[list[str], str]] = {
    "hiring": (["hiring", "recruiting", "recruitment", "job openings"], "positive"),
    "expansion": (["expansion", "expanding", "new office", "new branch"], "positive"),
    "funding": (
        ["funding", "raised", "investment", "series a", "series b", "seed round"],
        "positive",
    ),
    "acquisition": (["acquisition", "acquired", "merger"], "positive"),
    "leadership_change": (
        ["new ceo", "new cto", "new cfo", "leadership change", "executive change"],
        "positive",
    ),
    "product_launch": (["product launch", "launching", "launched a new"], "positive"),
    "digital_transformation": (
        ["digital transformation", "cloud migration", "modernization"],
        "positive",
    ),
    "layoffs": (["layoffs", "layoff", "downsizing"], "negative"),
    "closure": (["closure", "closing down", "shut down", "bankruptcy", "bankrupt"], "negative"),
}

# Canonical attribute -> surface forms.
ATTRIBUTES: dict[str, list[str]] = {
    "revenue": ["revenue", "turnover"],
    "employees": ["employees", "headcount", "staff size"],
    "funding": ["funding", "investment"],
    "founded_year": ["founded", "founding", "established"],
    "ceo": ["ceo", "chief executive"],
    "website": ["website"],
    "founders": ["founders", "founder"],
    "investors": ["investors", "investor"],
}

PERSON_ENTITY_KEYWORDS = [
    "decision maker",
    "decision makers",
    "executive",
    "executives",
    "contact",
    "contacts",
    "ceo",
    "cto",
    "cfo",
    "ciso",
    "founder",
    "founders",
]

FRESHNESS_KEYWORDS = [
    "recent",
    "recently",
    "latest",
    "current",
    "currently",
    "new",
    "this year",
    "this quarter",
]
