from pdf_parser import parse_speaker

lines = [
    "○김민수 의원 존경하는",
    "○홍성현 의원님과 함께",
    "○의장 홍성현 성원이 되었으므로",
    "○의회운영위원장 이철수 안녕하십니까?",
    "○도지사 김태흠 안녕하십니까",
]

for line in lines:
    print(f"[{line}] -> {parse_speaker(line)}")
