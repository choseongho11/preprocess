import os
import uuid
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

import pdf_parser as _parser
import summarizer
import formatter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

UPLOAD_FOLDER = Path("uploads")
OUTPUT_FOLDER = Path("output")
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

# 작업 상태 저장 (메모리, 단일 사용자용)
jobs: dict = {}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """현재 LLM 설정 조회"""
    return jsonify({
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        "model": os.getenv("LLM_MODEL", "llama3"),
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """LLM 설정 업데이트 (런타임)"""
    data = request.json or {}
    if "base_url" in data:
        os.environ["LLM_BASE_URL"] = data["base_url"]
        summarizer._client = None  # 클라이언트 재초기화
    if "model" in data:
        os.environ["LLM_MODEL"] = data["model"]
    if "api_key" in data:
        os.environ["LLM_API_KEY"] = data["api_key"]
        summarizer._client = None
    return jsonify({"status": "ok"})


@app.route("/api/test-llm", methods=["POST"])
def test_llm():
    """LLM 연결 테스트"""
    result = summarizer.test_connection()
    return jsonify(result)


@app.route("/api/upload", methods=["POST"])
def upload():
    """PDF 업로드 및 처리 시작"""
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "파일명이 없습니다"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "PDF 파일만 업로드 가능합니다"}), 400

    # 파일 저장
    job_id = str(uuid.uuid4())
    original_name = Path(secure_filename(file.filename)).stem
    pdf_path = UPLOAD_FOLDER / f"{job_id}.pdf"
    file.save(pdf_path)

    # 작업 초기화
    jobs[job_id] = {
        "status": "parsing",
        "filename": file.filename,
        "original_name": original_name,
        "total": 0,
        "done": 0,
        "current_speaker": "",
        "result": None,
        "error": None,
    }

    # 백그라운드 처리 (스레드)
    import threading
    thread = threading.Thread(target=process_job, args=(job_id, pdf_path, original_name))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


def process_job(job_id: str, pdf_path: Path, original_name: str):
    """PDF → 의원 발언 추출 → 요약 → 포맷 처리"""
    job = jobs[job_id]
    try:
        # 1. PDF 파싱
        logger.info(f"[{job_id}] PDF 파싱 시작: {pdf_path}")
        job["status"] = "parsing"
        speeches = _parser.parse_pdf(str(pdf_path))

        if not speeches:
            job["status"] = "error"
            job["error"] = "의원 발언을 찾을 수 없습니다. PDF 형식을 확인해주세요."
            return

        job["total"] = len(speeches)
        job["status"] = "summarizing"
        logger.info(f"[{job_id}] 의원 발언 {len(speeches)}건 추출 완료. 요약 시작.")

        # 2. 발언별 요약
        speeches_with_summaries = []
        for i, speech in enumerate(speeches):
            job["done"] = i
            job["current_speaker"] = speech.speaker
            logger.info(f"[{job_id}] 요약 중 ({i+1}/{len(speeches)}): {speech.speaker}")

            summary = summarizer.summarize_speech(speech.speaker, speech.content)
            
            # 단순 회의 진행 멘트 필터링
            if summary.strip() == "회의진행" or "회의진행" in summary.strip():
                logger.info(f"[{job_id}] 회의 진행 멘트 제외: {speech.speaker}")
                continue

            speeches_with_summaries.append((speech, summary))

        job["done"] = len(speeches)
        job["status"] = "formatting"

        # 3. 결과 포맷
        output_text = formatter.format_all_records(speeches_with_summaries)

        # 4. 파일 저장
        output_path = OUTPUT_FOLDER / f"{original_name}.txt"
        # 동일 파일명 중복 처리
        counter = 1
        while output_path.exists():
            output_path = OUTPUT_FOLDER / f"{original_name}_{counter}.txt"
            counter += 1

        output_path.write_text(output_text, encoding="utf-8")
        logger.info(f"[{job_id}] 완료: {output_path}")

        job["status"] = "done"
        job["result"] = {
            "text": output_text,
            "filename": output_path.name,
            "record_count": len(speeches),
        }

    except Exception as e:
        logger.error(f"[{job_id}] 처리 오류: {e}", exc_info=True)
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        pass
        # 업로드 파일 정리 (디버깅 위해 임시 주석 처리)
        # try:
        #     pdf_path.unlink(missing_ok=True)
        # except Exception:
        #     pass


@app.route("/api/status/<job_id>")
def job_status(job_id: str):
    """작업 상태 조회"""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다"}), 404
    return jsonify(job)


@app.route("/api/download/<filename>")
def download(filename: str):
    """결과 파일 다운로드"""
    safe_name = secure_filename(filename)
    file_path = OUTPUT_FOLDER / safe_name
    if not file_path.exists():
        return jsonify({"error": "파일을 찾을 수 없습니다"}), 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_name,
        mimetype="text/plain; charset=utf-8",
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
