"""
FinGuard — Financial Deepfake & Scam Detector
Main application entry point.
Serves the frontend and the async pipeline API.
Supports: Video scan (async), Text scan, Audio scan, Image scan (sync).
"""
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import shutil, os, uuid

from src.config import settings
from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry
from src.stages.stage7_ocr import run_stage7_ocr

app = FastAPI(title="FinGuard — Financial Deepfake & Scam Detector", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static", exist_ok=True)
os.makedirs("temp", exist_ok=True)

# Serve static assets (CSS, JS, images if any)
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory job store (swap for Redis in production)
jobs: dict = {}

# ── Frontend ────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# ── Video Pipeline (async background task) ──────────────────────────
def run_pipeline(job_id: str, file_path: str):
    try:
        print(f"\n[JOB {job_id}] Started processing: {file_path}")
        jobs[job_id]["status"] = "processing"

        # Stage 1
        jobs[job_id]["stage"] = "stage1_ingest"
        ingest = run_stage1_ingest(file_path, "temp", job_id)

        # Stage 2
        jobs[job_id]["stage"] = "stage2_vision"
        vision = run_stage2_vision(ingest.get("face_frames_paths", []), job_id)

        # Stage 3
        jobs[job_id]["stage"] = "stage3_audio"
        audio = run_stage3_audio(ingest.get("audio_path"), job_id)

        # Stage 4
        jobs[job_id]["stage"] = "stage4_transcription"
        tx = run_stage4_transcription(ingest.get("audio_path"), job_id)

        # Stage 5
        jobs[job_id]["stage"] = "stage5_llm"
        llm = run_stage5_llm(tx.get("transcript", ""), job_id)

        # Stage 6
        jobs[job_id]["stage"] = "stage6_registry"
        registry = run_stage6_registry(llm, job_id)

        # Stage 7 — Aggregation
        jobs[job_id]["stage"] = "stage7_aggregation"
        thresholds = settings.get("thresholds", {})
        vision_thresh = thresholds.get("vision_fake_threshold", 0.5)
        audio_thresh  = thresholds.get("audio_fake_threshold", 0.5)

        is_deepfake = (
            vision.get("max_score", 0.0) > vision_thresh or
            audio.get("max_score", 0.0) > audio_thresh
        )
        is_scam = llm.get("is_scam_likely", False)
        if registry.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
            is_scam = True

        if is_deepfake and is_scam:   verdict = "Critical: Deepfake + Scam"
        elif is_deepfake:             verdict = "Warning: Deepfake Detected"
        elif is_scam:                 verdict = "Warning: SEBI Violation / Scam"
        else:                         verdict = "Safe"

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "vision_score": vision.get("max_score", 0.0),
            "vision_temporal_variance": vision.get("temporal_variance", 0.0),
            "audio_score": audio.get("max_score", 0.0),
            "flagged_audio_segments": audio.get("flagged_segments", []),
            "transcript": tx.get("transcript", ""),
            "segments": tx.get("segments", []),      # timestamped segments for subtitle panel
            "sebi_analysis": llm,
            "registry_check": registry,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# ── Video scan (async) ──────────────────────────────────────────────
@app.post("/api/jobs")
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp4", ".avi", ".mov", ".mkv"]:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    job_id = str(uuid.uuid4())
    temp_path = f"temp/{job_id}{ext}"

    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "stage": "stage1_ingest",
        "filename": file.filename,
    }

    background_tasks.add_task(run_pipeline, job_id, temp_path)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


# ════════════════════════════════════════════════════════════════════
# NEW ENDPOINTS: Synchronous scan endpoints for text, audio, images
# ════════════════════════════════════════════════════════════════════

# ── Text Scan (sync) ────────────────────────────────────────────────
class TextScanRequest(BaseModel):
    text: str

@app.post("/api/scan/text")
async def scan_text(req: TextScanRequest):
    """
    Scan raw text for SEBI violations and scam patterns.
    Skips video/audio stages — goes straight to LLM + Registry.
    """
    if not req.text or len(req.text.strip()) < 5:
        raise HTTPException(status_code=400, detail="Text too short to analyze")

    job_id = f"text-{uuid.uuid4().hex[:8]}"
    print(f"\n[TEXT SCAN {job_id}] Analyzing {len(req.text)} chars...")

    # Stage 5: LLM multi-signal analysis
    llm = run_stage5_llm(req.text, job_id)

    # Stage 6: Registry cross-check
    registry = run_stage6_registry(llm, job_id)

    # Verdict
    is_scam = llm.get("is_scam_likely", False)
    if registry.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
        is_scam = True

    verdict = "Warning: SEBI Violation / Scam" if is_scam else "Safe"

    return {
        "scan_type": "text",
        "verdict": verdict,
        "is_scam": is_scam,
        "composite_risk_score": llm.get("composite_risk_score", 0.0),
        "sebi_analysis": llm,
        "registry_check": registry,
    }


# ── Audio Scan (sync) ──────────────────────────────────────────────
@app.post("/api/scan/audio")
async def scan_audio(file: UploadFile = File(...)):
    """
    Scan an audio file for deepfake voice + transcribe + SEBI analysis.
    Runs: Audio Deepfake → Transcription → LLM → Registry
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext}")

    job_id = f"audio-{uuid.uuid4().hex[:8]}"
    temp_path = f"temp/{job_id}{ext}"

    try:
        with open(temp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        print(f"\n[AUDIO SCAN {job_id}] Processing: {file.filename}")

        # Stage 3: Audio deepfake detection
        audio = run_stage3_audio(temp_path, job_id)

        # Stage 4: Transcription
        tx = run_stage4_transcription(temp_path, job_id)

        # Stage 5: LLM multi-signal analysis
        llm = run_stage5_llm(tx.get("transcript", ""), job_id)

        # Stage 6: Registry cross-check
        registry = run_stage6_registry(llm, job_id)

        # Verdict
        thresholds = settings.get("thresholds", {})
        audio_thresh = thresholds.get("audio_fake_threshold", 0.5)

        is_deepfake = audio.get("max_score", 0.0) > audio_thresh
        is_scam = llm.get("is_scam_likely", False)
        if registry.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
            is_scam = True

        if is_deepfake and is_scam:   verdict = "Critical: Deepfake + Scam"
        elif is_deepfake:             verdict = "Warning: Deepfake Detected"
        elif is_scam:                 verdict = "Warning: SEBI Violation / Scam"
        else:                         verdict = "Safe"

        return {
            "scan_type": "audio",
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "audio_score": audio.get("max_score", 0.0),
            "flagged_audio_segments": audio.get("flagged_segments", []),
            "transcript": tx.get("transcript", ""),
            "segments": tx.get("segments", []),
            "composite_risk_score": llm.get("composite_risk_score", 0.0),
            "sebi_analysis": llm,
            "registry_check": registry,
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ── Image Scan (sync) ──────────────────────────────────────────────
@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    """
    Scan an image for face deepfakes + extract text via OCR + SEBI analysis.
    Runs: Vision Deepfake (if faces) → OCR → LLM → Registry
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {ext}")

    job_id = f"img-{uuid.uuid4().hex[:8]}"
    temp_path = f"temp/{job_id}{ext}"

    try:
        with open(temp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)

        print(f"\n[IMAGE SCAN {job_id}] Processing: {file.filename}")

        # Stage 2: Vision deepfake detection (pass image as single frame)
        vision = run_stage2_vision([temp_path], job_id)

        # Stage 7 (OCR): Extract text from the image
        ocr = run_stage7_ocr(temp_path, job_id)
        extracted_text = ocr.get("extracted_text", "")

        # Stage 5: LLM multi-signal analysis on OCR-extracted text
        llm = run_stage5_llm(extracted_text, job_id) if extracted_text and len(extracted_text.strip()) >= 10 else {}

        # Stage 6: Registry cross-check
        registry = run_stage6_registry(llm, job_id) if llm else {"verdict": "not claimed", "matched_entity": None}

        # Verdict
        thresholds = settings.get("thresholds", {})
        vision_thresh = thresholds.get("vision_fake_threshold", 0.5)

        is_deepfake = vision.get("max_score", 0.0) > vision_thresh
        is_scam = llm.get("is_scam_likely", False) if llm else False
        if registry.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
            is_scam = True

        if is_deepfake and is_scam:   verdict = "Critical: Deepfake + Scam"
        elif is_deepfake:             verdict = "Warning: Deepfake Detected"
        elif is_scam:                 verdict = "Warning: SEBI Violation / Scam"
        else:                         verdict = "Safe"

        return {
            "scan_type": "image",
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "vision_score": vision.get("max_score", 0.0),
            "extracted_text": extracted_text,
            "ocr_confidence": ocr.get("avg_confidence", 0.0),
            "ocr_blocks": ocr.get("text_blocks", []),
            "composite_risk_score": llm.get("composite_risk_score", 0.0) if llm else 0.0,
            "sebi_analysis": llm if llm else {},
            "registry_check": registry,
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ── Health check (useful for extension connection test) ─────────────
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "3.0", "service": "FinGuard"}
