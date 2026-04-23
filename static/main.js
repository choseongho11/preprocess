/* ===========================
   회의록 전처리 시스템 - main.js
   =========================== */

const $ = (id) => document.getElementById(id);

// ── 상태 ──────────────────────────────────
let currentFile   = null;
let currentJobId  = null;
let pollTimer     = null;

// ── DOM 참조 ──────────────────────────────
const uploadZone      = $('uploadZone');
const fileInput       = $('fileInput');
const btnSelectFile   = $('btnSelectFile');
const btnRemoveFile   = $('btnRemoveFile');
const btnProcess      = $('btnProcess');
const btnDownload     = $('btnDownload');
const btnReset        = $('btnReset');
const btnErrorReset   = $('btnErrorReset');
const btnCopy         = $('btnCopy');
const btnSettings     = $('btnSettings');
const btnCloseSettings= $('btnCloseSettings');
const btnSaveSettings = $('btnSaveSettings');
const btnTestLlm      = $('btnTestLlm');

const uploadSection   = $('uploadSection');
const progressSection = $('progressSection');
const resultSection   = $('resultSection');
const errorCard       = $('errorCard');
const settingsPanel   = $('settingsPanel');

// ── 설정 패널 ────────────────────────────────
function openSettings() {
  // 현재 설정 불러오기
  fetch('/api/settings')
    .then(r => r.json())
    .then(data => {
      $('inputBaseUrl').value = data.base_url || '';
      $('inputModel').value   = data.model    || '';
    }).catch(() => {});
  settingsPanel.style.display = 'flex';
}
function closeSettings() {
  settingsPanel.style.display = 'none';
  $('testResult').style.display = 'none';
}

btnSettings.addEventListener('click', openSettings);
btnCloseSettings.addEventListener('click', closeSettings);
settingsPanel.addEventListener('click', (e) => {
  if (e.target === settingsPanel) closeSettings();
});

btnSaveSettings.addEventListener('click', () => {
  const payload = {
    base_url: $('inputBaseUrl').value.trim(),
    model:    $('inputModel').value.trim(),
    api_key:  $('inputApiKey').value.trim(),
  };
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(() => {
    closeSettings();
    showToast('설정이 저장되었습니다');
  });
});

btnTestLlm.addEventListener('click', () => {
  // 저장 먼저
  const payload = {
    base_url: $('inputBaseUrl').value.trim(),
    model:    $('inputModel').value.trim(),
    api_key:  $('inputApiKey').value.trim(),
  };
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(() =>
    fetch('/api/test-llm', { method: 'POST' })
  ).then(r => r.json()).then(data => {
    const el = $('testResult');
    el.style.display = 'block';
    if (data.status === 'ok') {
      el.className = 'test-result ok';
      el.textContent = `✅ 연결 성공 | 모델: ${data.model}\n응답: ${data.response}`;
    } else {
      el.className = 'test-result err';
      el.textContent = `❌ 연결 실패\n${data.error}`;
    }
  }).catch(e => {
    const el = $('testResult');
    el.style.display = 'block';
    el.className = 'test-result err';
    el.textContent = `❌ 요청 오류: ${e.message}`;
  });
});

// ── 파일 업로드 ──────────────────────────────
uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const files = e.dataTransfer.files;
  if (files.length > 0) handleFileSelect(files[0]);
});
uploadZone.addEventListener('click', () => fileInput.click());
btnSelectFile.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) handleFileSelect(fileInput.files[0]);
});

function handleFileSelect(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showError('PDF 파일만 업로드 가능합니다.');
    return;
  }
  currentFile = file;
  $('selectedFileName').textContent = file.name;
  $('selectedFileSize').textContent = formatBytes(file.size);
  $('selectedFile').style.display = 'flex';
  uploadZone.style.display = 'none';
  hideError();
}

btnRemoveFile.addEventListener('click', () => {
  currentFile = null;
  fileInput.value = '';
  $('selectedFile').style.display = 'none';
  uploadZone.style.display = '';
  hideError();
});

// ── 처리 시작 ─────────────────────────────────
btnProcess.addEventListener('click', startProcess);

async function startProcess() {
  if (!currentFile) return;

  // UI 전환
  uploadSection.style.display = 'none';
  progressSection.style.display = 'block';
  resultSection.style.display   = 'none';
  errorCard.style.display       = 'none';

  // 진행 초기화
  setProgress(0, '파싱 중...', '', '');

  // 업로드
  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok || data.error) {
      showProcessError(data.error || '업로드 실패');
      return;
    }
    currentJobId = data.job_id;
    startPolling();
  } catch (e) {
    showProcessError('서버 연결 오류: ' + e.message);
  }
}

// ── 진행 폴링 ─────────────────────────────────
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollStatus, 1500);
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollStatus() {
  if (!currentJobId) return;
  try {
    const res  = await fetch(`/api/status/${currentJobId}`);
    const data = await res.json();
    updateProgress(data);
    if (data.status === 'done' || data.status === 'error') stopPolling();
  } catch (e) {
    console.warn('폴링 오류:', e);
  }
}

function updateProgress(job) {
  const { status, total, done, current_speaker, result, error } = job;

  if (status === 'parsing') {
    setProgress(5, 'PDF 파싱 중...', 'PDF에서 텍스트를 추출하고 있습니다', '');
  } else if (status === 'summarizing') {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    setProgress(pct, '발언 요약 중...', `${current_speaker}`, `${done} / ${total} 건 완료`);
  } else if (status === 'formatting') {
    setProgress(98, '결과 포맷 생성 중...', '', '');
  } else if (status === 'done') {
    showResult(result);
  } else if (status === 'error') {
    showProcessError(error || '알 수 없는 오류');
  }
}

function setProgress(pct, label, speaker, count) {
  $('progressFill').style.width  = pct + '%';
  $('progressPct').textContent   = pct + '%';
  $('progressLabel').textContent = label;
  $('progressSpeaker').textContent = speaker;
  $('progressCount').textContent = count;
}

// ── 결과 표시 ─────────────────────────────────
function showResult(result) {
  progressSection.style.display = 'none';
  resultSection.style.display   = 'block';

  $('statRecords').textContent = result.record_count;
  $('statFile').textContent    = result.filename;

  // 미리보기 (구문 하이라이팅)
  $('previewContent').innerHTML = highlightRecord(result.text);

  // 다운로드
  btnDownload.onclick = () => {
    window.location.href = `/api/download/${encodeURIComponent(result.filename)}`;
  };
}

function showProcessError(msg) {
  progressSection.style.display = 'none';
  errorCard.style.display       = 'flex';
  $('errorMsg').textContent     = msg;
}

function hideError() {
  errorCard.style.display = 'none';
}

// ── 리셋 ──────────────────────────────────────
function resetAll() {
  stopPolling();
  currentFile  = null;
  currentJobId = null;
  fileInput.value = '';

  uploadSection.style.display   = 'block';
  progressSection.style.display = 'none';
  resultSection.style.display   = 'none';
  errorCard.style.display       = 'none';
  $('selectedFile').style.display = 'none';
  uploadZone.style.display = '';
}

btnReset.addEventListener('click', resetAll);
btnErrorReset.addEventListener('click', resetAll);

// ── 복사 ──────────────────────────────────────
btnCopy.addEventListener('click', () => {
  const text = $('previewContent').innerText;
  navigator.clipboard.writeText(text).then(() => {
    btnCopy.textContent = '✅ 복사됨';
    btnCopy.classList.add('copied');
    setTimeout(() => {
      btnCopy.textContent = '복사';
      btnCopy.classList.remove('copied');
    }, 2000);
  });
});

// ── 하이라이팅 ────────────────────────────────
function highlightRecord(text) {
  // HTML 이스케이프
  const esc = (s) => s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  return esc(text)
    .replace(/(=== RECORD (?:START|END) ===)/g,
      '<span class="hl-marker">$1</span>')
    .replace(/(\[META\]|\[SUMMARY\]|\[ORIGINAL\])/g,
      '<span class="hl-section">$1</span>')
    .replace(/^(회기|의원명|회의명|일자):/gm,
      '<span class="hl-key">$1</span>:');
}

// ── 유틸 ──────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024)       return bytes + ' B';
  if (bytes < 1048576)    return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function showToast(msg) {
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: '24px', left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(16,185,129,0.9)', color: '#fff',
    padding: '10px 22px', borderRadius: '999px',
    fontSize: '14px', fontWeight: '600',
    zIndex: '9999', backdropFilter: 'blur(8px)',
    animation: 'fadeIn 0.3s ease',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2500);
}

function showError(msg) {
  errorCard.style.display = 'flex';
  $('errorMsg').textContent = msg;
}
