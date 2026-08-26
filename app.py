"""
FinGuard — Financial Deepfake & Scam Detector
Main application entry point.
Serves the frontend and the async pipeline API.
"""
from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid

from src.config import settings
from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry

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

# ── Pipeline background task ────────────────────────────────────────
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

# ── API endpoints ───────────────────────────────────────────────────
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
