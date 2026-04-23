"""
pdf_parser.py  ─  충청남도의회 회의록 PDF 파서 (두 컬럼 지원)

PDF 구조
  - 2단(좌·우) 컬럼 레이아웃
  - 발화자 마커: ○직책 이름  or  ○이름 의원
  - 포함 대상: "의원"이 붙고 "의장·위원장·부의장" 직책이 없는 발화자만
"""

import re
import pdfplumber
from dataclasses import dataclass
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────
# 상수 / 패턴
# ───────────────────────────────────────────

# 제외 직책 키워드 (이 단어가 발화자명에 있으면 제외)
EXCLUDED_TITLE_KEYWORDS = [
    "전문위원", "수석전문위원",
    "사무처장", "사무국장", "사무과장",
    "도지사", "부지사", "행정부지사", "정무부지사",
    "교육감", "부교육감",
    "원장", "소장", "청장",
]

# 노이즈 발화자 시작 키워드 (이런 이름으로 시작하면 블록 전체 제외)
NOISE_SPEAKER_PREFIXES = [
    "출석의원", "결석의원", "속기공무원",
    "보조출석", "참고인", "증인",
]

# 의원 suffix 패턴 (발화자 이름 끝에 "의원" 있어야 포함)
MEMBER_SUFFIX = re.compile(r'의원\s*$')

# ○ 마커 + 발화자명 파싱 패턴
# 그룹: title(선택 직책), name(한글 이름 2-5자), suffix(선택 "의원")
SPEAKER_PARSE_RE = re.compile(
    r'^[ \t]*[○◯]\s*'
    r'(?P<title>[가-힣]*(?:의장|위원장|전문위원|사무처장|사무국장|도지사|교육감|부지사|원장)\s+)?'
    r'(?P<name>[가-힣]{2,5})'
    r'(?P<suffix>\s*의원)?'
    r'\s*(?P<rest>.*)',
    re.DOTALL,
)

# 날짜 / 회기 / 회의명 추출
DATE_RE    = re.compile(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일')
SESSION_RE = re.compile(r'제\s*(\d+)\s*회')
# 회의명: 헤더 줄에서 추출
MEETING_RE = re.compile(
    r'(제\d+회\s*충청남도의회\s*(?:임시회|정례회)[^\n]{0,30})',
)


# ───────────────────────────────────────────
# 데이터 클래스
# ───────────────────────────────────────────

@dataclass
class Speech:
    speaker:      str   # 예: "신영호 의원"
    content:      str   # 발언 전체 원문
    session:      str   # 예: "제364회"
    meeting_name: str   # 예: "제364회 충청남도의회 임시회 제1차 본회의"
    date:         str   # 예: "2026-02-19"


# ───────────────────────────────────────────
# PDF 텍스트 추출 (두 컬럼 처리)
# ───────────────────────────────────────────

def extract_page_text_two_column(page) -> str:
    """
    두 컬럼 레이아웃 페이지에서 텍스트 추출.
    왼쪽 컬럼 → 오른쪽 컬럼 순서로 이어붙임.
    """
    w = page.width
    # 마진 고려: 좌 10% ~ 50%, 우 50% ~ 90%
    left_bbox  = (w * 0.02, 0, w * 0.50, page.height)
    right_bbox = (w * 0.50, 0, w * 0.98, page.height)

    left_text  = (page.within_bbox(left_bbox).extract_text()  or "").strip()
    right_text = (page.within_bbox(right_bbox).extract_text() or "").strip()

    return left_text + "\n" + right_text


def extract_full_text(filepath: str) -> str:
    """전체 PDF를 두 컬럼 방식으로 텍스트 추출"""
    pages_text = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            try:
                text = extract_page_text_two_column(page)
            except Exception:
                text = page.extract_text() or ""
            pages_text.append(text)
    return "\n".join(pages_text)


# ───────────────────────────────────────────
# 메타데이터 추출
# ───────────────────────────────────────────

def extract_metadata(text: str) -> dict:
    meta = {"session": "", "meeting_name": "", "date": ""}

    # 회기
    m = SESSION_RE.search(text[:600])
    if m:
        meta["session"] = f"제{m.group(1)}회"

    # 날짜
    m = DATE_RE.search(text[:600])
    if m:
        y, mo, d = m.groups()
        meta["date"] = f"{y}-{int(mo):02d}-{int(d):02d}"

    # 회의명: 첫 번째 ○ 마커 이전 텍스트에서 추출
    header = text[:text.find("○")] if "○" in text else text[:800]
    # "의록" "회의" "위원회" 등이 포함된 줄 찾기
    for line in header.split("\n"):
        line = line.strip()
        if re.search(r'제\d+회', line) and re.search(r'회의|위원회|본회의', line):
            meta["meeting_name"] = re.sub(r'\s+', ' ', line).strip()
            break

    # 회의명 못 찾으면 문서 제목 형태로
    if not meta["meeting_name"]:
        m = MEETING_RE.search(header)
        if m:
            meta["meeting_name"] = m.group(1).strip()

    return meta


# ───────────────────────────────────────────
# 발화자 파싱 / 필터링
# ───────────────────────────────────────────

def parse_speaker(marker_line: str) -> Optional[Tuple[str, str]]:
    """
    ○ 마커 줄에서 (발화자명, 발언 첫 내용) 추출.
    의장·위원장 등은 None 반환(제외).
    """
    m = SPEAKER_PARSE_RE.match(marker_line.strip())
    if not m:
        return None

    title  = (m.group("title") or "").strip()
    name   = (m.group("name")  or "").strip()
    suffix = (m.group("suffix") or "").strip()   # "의원" or ""
    rest   = (m.group("rest")   or "").strip()   # 발언 첫 부분

    # 노이즈 발화자 제외 (출석의원, 속기공무원 등)
    full_raw = (title + name + suffix).strip()
    for prefix in NOISE_SPEAKER_PREFIXES:
        if full_raw.startswith(prefix) or name.startswith(prefix[:2]):
            return None

    # 제외 직책 키워드 검사
    for kw in EXCLUDED_TITLE_KEYWORDS:
        if kw in title or kw in suffix:
            # "위원장"은 "원장"을 포함하므로 예외 처리
            if kw == "원장" and "위원장" in title:
                continue
            return None

    # "의원" suffix 없으면 제외. 단, 직책이 의장/위원장 등인 경우는 허용
    is_chairperson = any(t in title for t in ["의장", "위원장"])
    if not is_chairperson and "의원" not in suffix:
        return None

    if is_chairperson:
        # 직책이 의장/위원장이더라도 최종 전처리에서는 "이름 의원"으로 통일
        speaker_name = f"{name} 의원"
    else:
        speaker_name = f"{name} 의원"

    return speaker_name, rest


def is_noise_block(content: str) -> bool:
    """
    출석의원 목록, 속기공무원 목록 등 노이즈 블록 감지.
    """
    stripped = content.strip()
    # 너무 짧은 블록
    if len(stripped) < 30:
        return True
    
    # 직책+이름 목록 패턴
    if re.search(r'감사위원장|자치경찰위원장|청년정책관|속기공무원|투자통상', stripped[:100]):
        return True
        
    return False


# ───────────────────────────────────────────
# 발화 블록 분리
# ───────────────────────────────────────────

def split_speeches(full_text: str) -> List[Tuple[str, str]]:
    """
    전체 텍스트를 ○ 마커 기준으로 분리.
    반환: [(speaker_name, content), ...]  — 의원 발언만
    """
    # ○ 마커 위치 목록
    positions: List[Tuple[int, int]] = []   # (start, end_of_marker_line)
    for m in re.finditer(r'(?m)^[ \t]*[○◯][^\n]+', full_text):
        positions.append((m.start(), m.end()))

    results: List[Tuple[str, str]] = []

    for i, (start, end_marker) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)

        marker_line = full_text[start:end_marker]
        body        = full_text[end_marker:next_start].strip()

        parsed = parse_speaker(marker_line)
        if parsed is None:
            continue

        speaker_name, first_content = parsed
        content = (first_content + "\n" + body).strip()

        if is_noise_block(content):
            logger.debug(f"노이즈 블록 제외: {speaker_name}")
            continue

        results.append((speaker_name, content))
        logger.debug(f"포함: {speaker_name} ({len(content)}자)")

    return results


# ───────────────────────────────────────────
# 메인 진입점
# ───────────────────────────────────────────

def parse_pdf(filepath: str) -> List[Speech]:
    """PDF 파일에서 의원 발언 목록을 추출하여 반환"""
    logger.info(f"PDF 파싱 시작: {filepath}")

    full_text = extract_full_text(filepath)
    with open("debug_extracted_text.txt", "w", encoding="utf-8") as f:
        f.write(full_text)
    
    if not full_text.strip():
        raise ValueError("PDF에서 텍스트를 추출할 수 없습니다.")

    meta    = extract_metadata(full_text)
    logger.info(f"메타데이터: {meta}")

    blocks  = split_speeches(full_text)
    logger.info(f"의원 발언 {len(blocks)}건 추출")

    speeches = [
        Speech(
            speaker      = speaker,
            content      = content,
            session      = meta["session"],
            meeting_name = meta["meeting_name"],
            date         = meta["date"],
        )
        for speaker, content in blocks
    ]
    return speeches
