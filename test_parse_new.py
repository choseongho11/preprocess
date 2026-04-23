import re

EXCLUDED_TITLE_KEYWORDS = [
    "전문위원", "수석전문위원",
    "사무처장", "사무국장", "사무과장",
    "도지사", "부지사", "행정부지사", "정무부지사",
    "교육감", "부교육감",
    "원장", "소장", "청장",
]

NOISE_SPEAKER_PREFIXES = [
    "출석의원", "결석의원", "속기공무원",
    "보조출석", "참고인", "증인",
]

SPEAKER_PARSE_RE = re.compile(
    r'^[ \t]*[○◯]\s*'
    r'(?P<title>[가-힣]*(?:의장|위원장|전문위원|사무처장|사무국장|도지사|교육감|부지사|원장)\s+)?'
    r'(?P<name>[가-힣]{2,5})'
    r'(?P<suffix>\s*의원)?'
    r'\s*(?P<rest>.*)',
    re.DOTALL,
)

def parse_speaker(marker_line: str):
    m = SPEAKER_PARSE_RE.match(marker_line.strip())
    if not m:
        return None

    title  = (m.group("title") or "").strip()
    name   = (m.group("name")  or "").strip()
    suffix = (m.group("suffix") or "").strip()   # "의원" or ""
    rest   = (m.group("rest")   or "").strip()   # 발언 첫 부분

    full_raw = (title + name + suffix).strip()
    for prefix in NOISE_SPEAKER_PREFIXES:
        if full_raw.startswith(prefix) or name.startswith(prefix[:2]):
            return None

    for kw in EXCLUDED_TITLE_KEYWORDS:
        if kw in title or kw in suffix:
            if kw == "원장" and "위원장" in title:
                continue
            return None

    is_chairperson = any(t in title for t in ["의장", "위원장"])
    if not is_chairperson and "의원" not in suffix:
        return None

    if is_chairperson:
        speaker_name = f"{title} {name}".strip()
    else:
        speaker_name = f"{name} 의원"
        
    return speaker_name, rest

lines = [
    "○김민수 의원 존경하는",
    "○홍성현 의원님과 함께",
    "○의장 홍성현 성원이 되었으므로",
    "○의회운영위원장 이철수 안녕하십니까?",
    "○도지사 김태흠 안녕하십니까",
    "○원장 아무개 안녕하십니까",
]

for line in lines:
    print(f"[{line}] -> {parse_speaker(line)}")
