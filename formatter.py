from typing import List, Tuple
from pdf_parser import Speech

ORIGINAL_MAX_LEN = 200  # 원문 앞 N자만 포함


def format_record(speech: Speech, summary: str) -> str:
    """단일 발언을 RECORD 형식으로 변환"""
    # 원문: 앞 200자 + "...>" 처리
    original_trimmed = speech.content.replace('\n', ' ').strip()
    if len(original_trimmed) > ORIGINAL_MAX_LEN:
        original_display = f"<{original_trimmed[:ORIGINAL_MAX_LEN]}...>"
    else:
        original_display = f"<{original_trimmed}>"

    record = (
        "=== RECORD START ===\n"
        "[META]\n"
        f"회기: {speech.session}\n"
        f"의원명: {speech.speaker}\n"
        f"회의명: {speech.meeting_name}\n"
        f"일자: {speech.date}\n"
        "\n"
        "[SUMMARY]\n"
        f"({summary})\n"
        "\n"
        "[ORIGINAL]\n"
        f"{original_display}\n"
        "=== RECORD END ==="
    )
    return record


def format_all_records(speeches_with_summaries: List[Tuple[Speech, str]]) -> str:
    """전체 발언 목록을 연결된 텍스트로 변환"""
    records = []
    for speech, summary in speeches_with_summaries:
        records.append(format_record(speech, summary))
    return "\n\n".join(records)
