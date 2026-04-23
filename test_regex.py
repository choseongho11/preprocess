import re

text = """○김민수 의원 존경하는 충남 도민 여
○홍성현 의원님과 함께
○의장 홍성현 성원이 되었으므로 제
○의회운영위원장 이철수 안녕하십니까?
"""

SPEAKER_PARSE_RE = re.compile(
    r'^[○◯]\s*'
    r'(?P<title>[가-힣]+(?:의장|위원장|전문위원|사무처장|사무국장|도지사|교육감|부지사|원장)\s+)?'
    r'(?P<name>[가-힣]{2,5})'
    r'(?P<suffix>\s*의원)?'
    r'\s*(?P<rest>.*)',
    re.DOTALL,
)

for line in text.split("\n"):
    if not line: continue
    print(f"[{line}]")
    m = SPEAKER_PARSE_RE.match(line)
    if m:
        print("  MATCH:", m.groupdict())
    else:
        print("  NO MATCH")
