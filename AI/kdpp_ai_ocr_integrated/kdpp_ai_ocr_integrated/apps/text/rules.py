# Material aliases combine the modular kyh structure with the broader feat mapping.
MATERIAL_ALIASES = {
    "면": [
        "cotton", "coton", "cot", "co", "baumwolle", "algodon", "algodón",
        "algod", "katoen", "pamuk", "bumbac", "bavlna", "cotone",
        "cottone", "cottonw", "puuvillaa", "puuvill", "puuvil",
        "pamut", "medvilne", "kokvilna", "kapas", "cons", "bawe",
        "хлопок", "棉", "코튼",
    ],
    "폴리에스터": [
        "polyester", "poliester", "polyestere", "polyestera", "polysstra",
        "polster", "polister", "polyesterpolyester", "poster", "vester",
        "polyeste", "poli", "폴리에스터", "полиэстер",
    ],
    "레이온": ["rayon", "레이온"],
    "나일론": [
        "nylon", "naylo", "nayl", "nylc", "najlon", "polyamide",
        "polyamid", "poliamide", "polyamidia", "poliamida", "ayamide",
        "yamide", "나일론", "폴리아미드",
    ],
    "울": [
        "wool", "laine", "lana", "wol", "wolle", "schurwolle",
        "urwolle", "virgin wool", "울",
    ],
    "아크릴": [
        "acrylic", "polyacryl", "polyacrylic", "polyacrylace", "acryl",
        "akryl", "acril", "akryylia", "acrylicer", "아크릴",
    ],
    "스판덱스": [
        "spandex", "elastane", "elastan", "elasthan", "elastaania",
        "elastaana", "elast", "lycra", "ukra", "lxra", "likha",
        "elastano", "스판덱스", "엘라스테인",
    ],
    "린넨": ["linen", "lin", "leinen", "lino", "린넨"],
    "비스코스": [
        "viscose", "viskose", "viscon", "viskon", "viskoz", "visko",
        "viscosa", "viscosal", "비스코스",
    ],
    "실크": ["silk", "soie", "seide", "seta", "실크"],
    "모달": ["modal", "모달"],
    "캐시미어": ["cashmere", "kaschmir", "kashmir", "cachemire", "캐시미어"],
    "폴리우레탄": ["polyurethane", "pu", "폴리우레탄"],
    "가죽": ["leather", "cuir", "leder", "piel", "가죽"],
    "라미": ["ramie", "라미"],
    "리오셀": ["lyocell", "tencel", "리오셀"],
    "다운": ["down", "don", "다운"],
    "깃털": ["feather", "깃털"],
    "야크": ["yak", "야크"],
    "모헤어": ["mohair", "모헤어"],
    "대나무": ["bamboo", "대나무"],
    "큐프라": ["cupro", "큐프라"],
}

OCR_CORRECTIONS = {
    "polyster": "polyester",
    "polyestcr": "polyester",
    "polyestet": "polyester",
    "cotlon": "cotton",
    "cotion": "cotton",
    "elastanc": "elastane",
    "elastan": "elastane",
    "viscoe": "viscose",
    "nyion": "nylon",
}

CARE_RULES = {
    "찬물 기계세탁 가능": ["machine wash cold", "wash cold", "cold wash"],
    "미온수 기계세탁 가능": ["machine wash warm", "wash warm"],
    "기계세탁 가능": ["machine wash", "lavable a la machine", "lavare in lavatrice"],
    "손세탁 가능": ["hand wash", "lavage a la main", "lavare a mano", "cold hand wash"],
    "물세탁 금지": ["do not wash"],
    "표백 금지": [
        "do not bleach", "ne pas utiliser de javel", "nicht bleichen",
        "ağartici kullanilmaz", "agartici kullanilmaz",
    ],
    "필요 시 비염소계 표백만 가능": [
        "only non-chlorine bleach when needed",
        "non-chlorine bleach when needed",
    ],
    "저온 건조 가능": ["tumble dry low"],
    "중온 건조 가능": ["tumble dry medium"],
    "고온 건조 가능": ["tumble dry high"],
    "건조기 사용 금지": ["do not tumble dry", "pas de sechage en tambour"],
    "건조기 사용 가능": ["tumble dry"],
    "걸어서 건조": ["line dry"],
    "평평하게 펴서 건조": ["lay flat to dry", "dry flat", "sechage a plat"],
    "저온 다림질 가능": ["cool iron", "iron low"],
    "중온 다림질 가능": ["warm iron", "medium iron"],
    "고온 다림질 가능": ["hot iron", "high iron"],
    "다림질 금지": ["do not iron", "ne pas repasser"],
    "드라이클리닝 전용": ["dry clean only"],
    "드라이클리닝 금지": ["do not dry clean"],
    "드라이클리닝 가능": ["dry clean"],
}

