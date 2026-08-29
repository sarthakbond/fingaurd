"""
FinGuard — Financial Deepfake & Scam Detector
Main application entry point with security hardening, temp file isolation,
calibrated 3-tier verdicts, and SEBI SCORES complaint generation.
"""
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import shutil, os, uuid

from src.config import settings, get_threshold
from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry
from src.stages.stage7_ocr import run_stage7_ocr
from src.stages.stage8_report import generate_sebi_scores_complaint
from src.stages.stage9_apk_domain import run_stage9_apk_domain, scan_domain

_server_cfg = settings.get("server", {})
MAX_UPLOAD_SIZE = _server_cfg.get("max_upload_mb", 100) * 1024 * 1024

app = FastAPI(title="FinGuard — Financial Deepfake & Scam Detector", version="3.1")

# Configure CORS safely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows browser extension and localhost access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
os.makedirs("temp", exist_ok=True)

# Serve static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory job store
jobs: dict = {}

def validate_file_size(file: UploadFile):
    """Guards against oversized uploads causing memory/disk exhaustion."""
    if hasattr(file, "size") and file.size and file.size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed size ({MAX_UPLOAD_SIZE // (1024*1024)}MB)")

def calculate_calibrated_verdict(is_deepfake: bool, is_scam: bool, composite_risk: float, registry_verdict: str) -> str:
    """
    3-Tier regulatory calibration:
    - Critical: Deepfake + Scam
    - Warning: Deepfake or Hard Scam Violation / Fake Registry
    - Suspicious: Review Recommended (0.35 - 0.65 composite ambiguity band)
    - Safe: Clean content (<0.35 risk)
    """
    if is_deepfake and is_scam:
        return "Critical: Deepfake + Scam"
    elif is_deepfake:
        return "Warning: Deepfake Detected"
    elif is_scam or registry_verdict in ["not found", "name-number mismatch", "malformed number"]:
        return "Warning: SEBI Violation / Scam"
    elif composite_risk >= 0.35:
        return "Suspicious: Review Recommended"
    else:
        return "Safe"

def build_timeline_risk_track(audio_segments: list, text_segments: list, sebi_analysis: dict) -> list:
    """
    Merges audio chunk spoof scores and timestamped transcript red flags into
    a unified timeline for the interactive video/audio risk scrubber.
    """
    timeline = []
    
    # Add audio chunks
    for seg in audio_segments:
        timeline.append({
            "start": seg.get("start", 0.0),
            "end": seg.get("end", 0.0),
            "audio_score": seg.get("score", 0.0),
            "text_flag": None,
            "category": "audio_track"
        })
        
    # Mark text flags on timeline
    return_quotes = [q.lower() for q in sebi_analysis.get("specific_return_promises", [])]
    implied_quotes = [q.lower() for q in sebi_analysis.get("implied_returns", [])]
    urgency_quotes = [q.lower() for q in sebi_analysis.get("urgency_scarcity_language", [])]
    paywall_quotes = [q.lower() for q in sebi_analysis.get("paywall_push", [])]
    
    for t_seg in text_segments:
        txt = t_seg.get("text", "").lower()
        flag_type = None
        if any(q in txt or txt in q for q in return_quotes if q):
            flag_type = "explicit_return"
        elif any(q in txt or txt in q for q in implied_quotes if q):
            flag_type = "implied_return"
        elif any(q in txt or txt in q for q in urgency_quotes if q):
            flag_type = "urgency"
        elif any(q in txt or txt in q for q in paywall_quotes if q):
            flag_type = "paywall"
            
        if flag_type:
            timeline.append({
                "start": t_seg.get("start", 0.0),
                "end": t_seg.get("end", 0.0),
                "audio_score": 0.0,
                "text_flag": flag_type,
                "quote": t_seg.get("text", ""),
                "category": "speech_content"
            })
            
    timeline.sort(key=lambda x: x["start"])
    return timeline

# ── Frontend ────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# ── Video Pipeline (async background task with isolated cleanup) ─────
def run_pipeline(job_id: str, temp_job_dir: str, file_path: str):
    try:
        print(f"\n[JOB {job_id}] Started processing: {file_path}")
        jobs[job_id]["status"] = "processing"

        # Stage 1: Ingest
        jobs[job_id]["stage"] = "stage1_ingest"
        ingest = run_stage1_ingest(file_path, temp_job_dir, job_id)

        # Stage 2: Vision
        jobs[job_id]["stage"] = "stage2_vision"
        vision = run_stage2_vision(ingest.get("face_frames_paths", []), job_id)

        # Stage 4: Transcription
        jobs[job_id]["stage"] = "stage4_transcription"
        tx = run_stage4_transcription(ingest.get("audio_path"), job_id)

        # Stage 3: Audio (uses transcript for impersonation check)
        jobs[job_id]["stage"] = "stage3_audio"
        audio = run_stage3_audio(ingest.get("audio_path"), job_id, transcript=tx.get("transcript", ""))

        # Stage 5: LLM
        jobs[job_id]["stage"] = "stage5_llm"
        llm = run_stage5_llm(tx.get("transcript", ""), job_id)

        # Stage 6: Registry
        jobs[job_id]["stage"] = "stage6_registry"
        registry = run_stage6_registry(llm, job_id)

        # Stage 9: Phishing domain check on transcript
        jobs[job_id]["stage"] = "stage9_apk_domain"
        stage9 = run_stage9_apk_domain(job_id, ocr_text=tx.get("transcript", "")) if tx.get("transcript") else {}

        # Stage 8: Auto-generate SCORES legal evidence dossier
        jobs[job_id]["stage"] = "stage8_report"
        
        # Stage 7: Aggregation & Final Verdict
        jobs[job_id]["stage"] = "stage7_aggregation"
        vision_thresh = get_threshold("vision_fake_threshold", 0.5)
        audio_thresh  = get_threshold("audio_fake_threshold", 0.5)

        is_deepfake = (
            vision.get("max_score", 0.0) > vision_thresh or
            audio.get("max_score", 0.0) > audio_thresh
        )
        is_scam = llm.get("is_scam_likely", False)
        if stage9.get("any_threat_detected"):
            is_scam = True
        composite_risk = llm.get("composite_risk_score", 0.0)
        
        verdict = calculate_calibrated_verdict(
            is_deepfake, is_scam, composite_risk, registry.get("verdict", "not claimed")
        )

        timeline_track = build_timeline_risk_track(
            audio.get("all_segments", []), tx.get("segments", []), llm
        )

        result_payload = {
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "composite_risk_score": composite_risk,
            "vision_score": vision.get("max_score", 0.0),
            "vision_temporal_variance": vision.get("temporal_variance", 0.0),
            "mouth_motion_activity": vision.get("mouth_motion_activity", 0.0),
            "heatmap_base64": vision.get("heatmap_base64"),
            "audio_score": audio.get("max_score", 0.0),
            "flagged_audio_segments": audio.get("flagged_segments", []),
            "all_audio_segments": audio.get("all_segments", []),
            "impersonation_check": audio.get("impersonation_check", {}),
            "domain_scan": stage9.get("ocr_domain_result"),
            "transcript": tx.get("transcript", ""),
            "dpdp_pii_scrubbed_count": llm.get("dpdp_pii_scrubbed_count", 0),
            "hinglish_slang_detected": llm.get("hinglish_slang_detected", []),
            "segments": tx.get("segments", []),
            "timeline_track": timeline_track,
            "sebi_analysis": llm,
            "registry_check": registry,
            "input_quality": ingest.get("quality_assessment", {
                "rating": "Standard",
                "sharpness_score": 0.0,
                "resolution": "Unknown",
                "compression_flag": False
            }),
        }

        # Auto-generate SCORES legal complaint draft
        result_payload["scores_complaint"] = generate_sebi_scores_complaint(result_payload, "Video")

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result_payload

    except Exception as e:
        import traceback
        traceback.print_exc()
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
    finally:
        # Guaranteed PII & Temp disk purge
        if os.path.exists(temp_job_dir):
            shutil.rmtree(temp_job_dir, ignore_errors=True)
            print(f"[{job_id}] Purged temp directory: {temp_job_dir}")

# ── Video scan (async) ──────────────────────────────────────────────
@app.post("/api/jobs")
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    validate_file_size(file)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp4", ".avi", ".mov", ".mkv"]:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    job_id = str(uuid.uuid4())
    temp_job_dir = os.path.join("temp", job_id)
    os.makedirs(temp_job_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_job_dir, f"input{ext}")

    with open(temp_file_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "stage": "stage1_ingest",
        "filename": file.filename,
    }

    background_tasks.add_task(run_pipeline, job_id, temp_job_dir, temp_file_path)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/jobs/{job_id}/complaint", response_class=PlainTextResponse)
async def get_job_complaint(job_id: str):
    """Download the pre-formatted SEBI SCORES Complaint draft for a video job."""
    if job_id not in jobs or "result" not in jobs[job_id]:
        raise HTTPException(status_code=404, detail="Job result not found")
    complaint_text = jobs[job_id]["result"].get("scores_complaint")
    if not complaint_text:
        complaint_text = generate_sebi_scores_complaint(jobs[job_id]["result"], "Video")
    return complaint_text


# ════════════════════════════════════════════════════════════════════
# SYNCHRONOUS SCAN ENDPOINTS (Text, Audio, Image)
# ════════════════════════════════════════════════════════════════════

# ── Text Scan ───────────────────────────────────────────────────────
class TextScanRequest(BaseModel):
    text: str

@app.post("/api/scan/text")
async def scan_text(req: TextScanRequest):
    if not req.text or len(req.text.strip()) < 5:
        raise HTTPException(status_code=400, detail="Text too short to analyze")

    job_id = f"text-{uuid.uuid4().hex[:8]}"
    print(f"\n[TEXT SCAN {job_id}] Analyzing {len(req.text)} chars...")

    # Stage 9: Phishing domain check on text
    stage9 = run_stage9_apk_domain(job_id, ocr_text=req.text)

    # Stage 5: LLM
    llm = run_stage5_llm(req.text, job_id)
    # Stage 6: Registry
    registry = run_stage6_registry(llm, job_id)

    is_scam = llm.get("is_scam_likely", False)
    if stage9.get("any_threat_detected"):
        is_scam = True
    composite_risk = llm.get("composite_risk_score", 0.0)
    verdict = calculate_calibrated_verdict(False, is_scam, composite_risk, registry.get("verdict", "not claimed"))

    result = {
        "scan_type": "text",
        "verdict": verdict,
        "is_scam": is_scam,
        "composite_risk_score": composite_risk,
        "domain_scan": stage9.get("ocr_domain_result"),
        "sebi_analysis": llm,
        "registry_check": registry,
    }
    result["scores_complaint"] = generate_sebi_scores_complaint(result, "Text / Social Media Post")
    return result


# ── Audio Scan ──────────────────────────────────────────────────────
@app.post("/api/scan/audio")
async def scan_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    validate_file_size(file)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext}")

    job_id = f"audio-{uuid.uuid4().hex[:8]}"
    temp_job_dir = os.path.join("temp", job_id)
    os.makedirs(temp_job_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_job_dir, f"input{ext}")

    try:
        with open(temp_file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        print(f"\n[AUDIO SCAN {job_id}] Processing: {file.filename}")

        # Stage 4 Transcription first for context
        tx = run_stage4_transcription(temp_file_path, job_id)

        # Stage 3 Audio deepfake + Impersonation
        audio = run_stage3_audio(temp_file_path, job_id, transcript=tx.get("transcript", ""))

        # Stage 9 Phishing domain check on transcript
        stage9 = run_stage9_apk_domain(job_id, ocr_text=tx.get("transcript", "")) if tx.get("transcript") else {}

        # Stage 5 LLM
        llm = run_stage5_llm(tx.get("transcript", ""), job_id)

        # Stage 6 Registry
        registry = run_stage6_registry(llm, job_id)

        audio_thresh = get_threshold("audio_fake_threshold", 0.5)

        is_deepfake = audio.get("max_score", 0.0) > audio_thresh
        is_scam = llm.get("is_scam_likely", False)
        if stage9.get("any_threat_detected"):
            is_scam = True
        composite_risk = llm.get("composite_risk_score", 0.0)

        verdict = calculate_calibrated_verdict(
            is_deepfake, is_scam, composite_risk, registry.get("verdict", "not claimed")
        )

        timeline_track = build_timeline_risk_track(
            audio.get("all_segments", []), tx.get("segments", []), llm
        )

        result = {
            "scan_type": "audio",
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "composite_risk_score": composite_risk,
            "audio_score": audio.get("max_score", 0.0),
            "flagged_audio_segments": audio.get("flagged_segments", []),
            "all_audio_segments": audio.get("all_segments", []),
            "impersonation_check": audio.get("impersonation_check", {}),
            "domain_scan": stage9.get("ocr_domain_result"),
            "transcript": tx.get("transcript", ""),
            "segments": tx.get("segments", []),
            "timeline_track": timeline_track,
            "sebi_analysis": llm,
            "registry_check": registry,
        }
        result["scores_complaint"] = generate_sebi_scores_complaint(result, "Audio Broadcast / Podcast")
        return result
    finally:
        if os.path.exists(temp_job_dir):
            shutil.rmtree(temp_job_dir, ignore_errors=True)


# ── Image Scan ──────────────────────────────────────────────────────
@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    validate_file_size(file)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {ext}")

    job_id = f"img-{uuid.uuid4().hex[:8]}"
    temp_job_dir = os.path.join("temp", job_id)
    os.makedirs(temp_job_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_job_dir, f"input{ext}")

    try:
        with open(temp_file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        print(f"\n[IMAGE SCAN {job_id}] Processing: {file.filename}")

        # Stage 2: Vision deepfake (single frame + heatmap)
        vision = run_stage2_vision([temp_file_path], job_id)

        # Stage 7: OCR
        ocr = run_stage7_ocr(temp_file_path, job_id)
        extracted_text = ocr.get("extracted_text", "")

        # Stage 9: APK / Phishing domain check on any URLs found in the image
        stage9 = run_stage9_apk_domain(job_id, ocr_text=extracted_text) if extracted_text else {}

        # Stage 5: LLM on OCR
        llm = run_stage5_llm(extracted_text, job_id) if extracted_text and len(extracted_text.strip()) >= 10 else {}

        # Stage 6: Registry
        registry = run_stage6_registry(llm, job_id) if llm else {"verdict": "not claimed", "matched_entity": None}

        from src.config import get_threshold
        vision_thresh = get_threshold("vision_fake_threshold", 0.5)

        is_deepfake = vision.get("max_score", 0.0) > vision_thresh
        is_scam = llm.get("is_scam_likely", False) if llm else False
        # Elevate is_scam if Stage 9 found phishing domains
        if stage9.get("any_threat_detected"):
            is_scam = True
        composite_risk = llm.get("composite_risk_score", 0.0) if llm else 0.0

        verdict = calculate_calibrated_verdict(
            is_deepfake, is_scam, composite_risk, registry.get("verdict", "not claimed")
        )

        result = {
            "scan_type": "image",
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "composite_risk_score": composite_risk,
            "vision_score": vision.get("max_score", 0.0),
            "heatmap_base64": vision.get("heatmap_base64"),
            "extracted_text": extracted_text,
            "ocr_confidence": ocr.get("avg_confidence", 0.0),
            "ocr_blocks": ocr.get("text_blocks", []),
            "domain_scan": stage9.get("ocr_domain_result"),
            "sebi_analysis": llm if llm else {},
            "registry_check": registry,
        }
        result["scores_complaint"] = generate_sebi_scores_complaint(result, "Screenshot / Image Post")
        return result
    finally:
        if os.path.exists(temp_job_dir):
            shutil.rmtree(temp_job_dir, ignore_errors=True)


# ── APK Scan ──────────────────────────────────────────────────────────────────
@app.post("/api/scan/apk")
async def scan_apk(file: UploadFile = File(...)):
    """Stage 9: Inspects an uploaded .apk for fake broker impersonation and dangerous permissions."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    validate_file_size(file)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".apk":
        raise HTTPException(status_code=400, detail="Only .apk files are supported")

    job_id = f"apk-{uuid.uuid4().hex[:8]}"
    temp_job_dir = os.path.join("temp", job_id)
    os.makedirs(temp_job_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_job_dir, f"input.apk")

    try:
        with open(temp_file_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        print(f"\n[APK SCAN {job_id}] Processing: {file.filename}")
        result = run_stage9_apk_domain(job_id, apk_path=temp_file_path)
        result["scan_type"] = "apk"
        result["filename"] = file.filename
        # H2: Generate SEBI SCORES complaint from APK scan
        apk_r = result.get("apk_result") or {}
        complaint_data = {
            "scan_type": "APK",
            "verdict": "Suspicious APK" if apk_r.get("is_suspicious") else "Clean APK",
            "sebi_analysis": {
                "is_scam_likely": apk_r.get("is_suspicious", False),
                "reasoning": apk_r.get("reason", ""),
                "claimed_advisor_name": file.filename,
                "claimed_registration_number": None
            },
            "vision_score": 0.0,
            "audio_score": 0.0,
            "registry_check": {"verdict": "not checked"},
            "composite_risk_score": 1.0 if apk_r.get("is_suspicious") else 0.0
        }
        result["scores_complaint"] = generate_sebi_scores_complaint(complaint_data, "Fake Broker APK")
        return result
    finally:
        if os.path.exists(temp_job_dir):
            shutil.rmtree(temp_job_dir, ignore_errors=True)


# ── URL / Domain Scan ─────────────────────────────────────────────────────────
class UrlScanRequest(BaseModel):
    url: str

@app.post("/api/scan/url")
async def scan_url(req: UrlScanRequest):
    """Stage 9: Checks a URL or domain for typo-squatting / phishing against SEBI broker whitelist."""
    if not req.url or len(req.url.strip()) < 3:
        raise HTTPException(status_code=400, detail="URL too short")

    job_id = f"url-{uuid.uuid4().hex[:8]}"
    print(f"\n[URL SCAN {job_id}] Checking: {req.url}")

    result = run_stage9_apk_domain(job_id, url=req.url)
    result["scan_type"] = "url"
    # H2: Generate SEBI SCORES complaint from URL scan
    url_r = result.get("url_result") or {}
    complaint_data = {
        "scan_type": "URL",
        "verdict": "Phishing Domain" if url_r.get("is_phishing") else "Clean URL",
        "sebi_analysis": {
            "is_scam_likely": url_r.get("is_phishing", False),
            "reasoning": url_r.get("reason", ""),
            "claimed_advisor_name": req.url,
            "claimed_registration_number": None
        },
        "vision_score": 0.0,
        "audio_score": 0.0,
        "registry_check": {"verdict": "not checked"},
        "composite_risk_score": 1.0 if url_r.get("is_phishing") else 0.0
    }
    result["scores_complaint"] = generate_sebi_scores_complaint(complaint_data, "Phishing Domain / URL")
    return result


# ── Registry Status ───────────────────────────────────────────────────────────
@app.get("/api/registry/status")
async def registry_status():
    """Returns SEBI registry metadata: record count, last sync timestamp, breakdown by type."""
    import json as _json
    registry_path = os.path.join("static_data", "sebi_registry.json")
    sync_log_path = os.path.join("static_data", "sebi_sync_log.json")

    total_records = 0
    by_type: Dict[str, int] = {}
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = _json.load(f)
        total_records = len(registry)
        for entry in registry:
            t = entry.get("type", "Unknown")
            by_type[t] = by_type.get(t, 0) + 1

    sync_log: Dict[str, Any] = {}
    if os.path.exists(sync_log_path):
        with open(sync_log_path, "r", encoding="utf-8") as f:
            sync_log = _json.load(f)

    return {
        "total_records": total_records,
        "last_sync": sync_log.get("last_sync"),
        "last_sync_result": sync_log.get("last_sync_result"),
        "sync_count": sync_log.get("sync_count", 0),
        "registry_breakdown": by_type,
        "registry_path": registry_path
    }


# ── Admin: Trigger Registry Sync ─────────────────────────────────────────────
@app.post("/api/admin/sync-registry")
async def trigger_registry_sync(background_tasks: BackgroundTasks):
    """Triggers a background SEBI registry delta synchronization."""
    def _run_sync():
        import subprocess
        result = subprocess.run(
            [".venv/Scripts/python", "scripts/sync_sebi_registry.py"],
            capture_output=True, text=True, cwd=os.getcwd()
        )
        print(f"[SYNC] SEBI sync completed. Return code: {result.returncode}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"[SYNC STDERR] {result.stderr}")

    background_tasks.add_task(_run_sync)
    return {"status": "sync_queued", "message": "SEBI registry sync started in background"}


# ── Health check ────────────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "4.0", "stages": 9, "service": "FinGuard"}


@app.get("/{path:path}", response_class=HTMLResponse)
async def serve_ui_route(path: str):
    """Serve the SPA shell for client-side routes after API routes are matched."""
    if path.startswith("api/") or path.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not found")
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    host = _server_cfg.get("host", "0.0.0.0")
    port = int(_server_cfg.get("port", 8000))
    print(f"\n=============================================================")
    print(f"  FinGuard Forensic Platform Server")
    print(f"  Listening on http://localhost:{port} (or http://{host}:{port})")
    print(f"=============================================================\n")
    uvicorn.run("app:app", host=host, port=port, reload=False)

