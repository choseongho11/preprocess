import os
import logging
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# LLM 클라이언트 초기화
_client: Optional[OpenAI] = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        base_url = "http://115.137.55.154:90/v1"
        api_key = "sk-lm-vC1AeVpm:DI0vzMxJydOpbc3ELjmP"
        _client = OpenAI(base_url=base_url, api_key=api_key)
    return _client


def get_model() -> str:
    return "gemm4 e4b"


SYSTEM_PROMPT = """당신은 지방의회 회의록 요약 전문가입니다.
의원의 발언 내용을 핵심만 간결하게 1~3문장으로 요약하세요.
- 요약은 괄호 없이 순수 내용만 작성
- 주어(의원명) 생략하고 행위/주장 중심으로 작성
- 한국어로 작성
- 불필요한 인사말, 감사 표현 등은 제외
- [중요] 만약 발언 내용이 안건에 대한 의견이나 질의가 아니라, 단순한 '회의 진행 멘트'(예: 개의/산회/정회 선포, 의석 정돈, 안건 상정, 다음 발언자 지목 등)에 불과하다면 다른 말은 쓰지 말고 오직 "회의진행"이라고만 출력하세요."""


def summarize_speech(speaker: str, content: str) -> str:
    """
    의원 발언 내용을 LLM으로 요약
    """
    if not content.strip():
        return ""

    # 너무 짧은 발언은 그대로 반환
    if len(content) < 100:
        return content.strip()

    prompt = f"""다음은 {speaker}의 지방의회 회의 발언입니다. 핵심 내용을 1~3문장으로 요약하세요.

[발언 내용]
{content[:3000]}  

[요약]"""

    try:
        client = get_client()
        response = client.chat.completions.create(
            model=get_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        summary = response.choices[0].message.content.strip()
        logger.debug(f"요약 완료: {speaker} → {len(summary)}자")
        return summary

    except Exception as e:
        logger.error(f"LLM 요약 오류 ({speaker}): {e}")
        # 오류 시 첫 100자로 대체
        return content[:100].replace('\n', ' ').strip() + "..."


def test_connection() -> dict:
    """LLM 서버 연결 테스트"""
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": "안녕하세요. 연결 테스트입니다."}],
            max_tokens=50,
        )
        return {
            "status": "ok",
            "model": get_model(),
            "base_url": os.getenv("LLM_BASE_URL"),
            "response": response.choices[0].message.content[:50],
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "base_url": os.getenv("LLM_BASE_URL"),
            "model": get_model(),
        }
