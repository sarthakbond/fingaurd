from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import uuid
import os
import shutil
import asyncio

from src.config import settings
from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry

app = FastAPI(title="Financial Deepfake & Scam Detector", version="2.0")

# In-memory job store for MVP (use Redis/DB in prod)
jobs = {}

os.makedirs("temp", exist_ok=True)

async def process_video_pipeline(job_id: str, file_path: str):
    try:
        jobs[job_id]["status"] = "processing"
        
        # --- Stage 1: Ingest & Preprocess ---
        jobs[job_id]["stage"] = "stage1_ingest"
        ingest_result = run_stage1_ingest(file_path, "temp", job_id)
        
        # --- Stage 2: Vision ---
        jobs[job_id]["stage"] = "stage2_vision"
        vision_result = run_stage2_vision(ingest_result.get("face_frames_paths", []), job_id)
        
        jobs[job_id]["stage"] = "stage3_audio"
        audio_result = run_stage3_audio(ingest_result.get("audio_path"), job_id)
        
        jobs[job_id]["stage"] = "stage4_transcription"
        transcription_result = run_stage4_transcription(ingest_result.get("audio_path"), job_id)
        
        jobs[job_id]["stage"] = "stage5_llm"
        llm_result = run_stage5_llm(transcription_result.get("transcript", ""), job_id)
        
        jobs[job_id]["stage"] = "stage6_registry"
        registry_result = run_stage6_registry(llm_result, job_id)
        
        # --- Stage 7: Aggregation ---
        jobs[job_id]["stage"] = "stage7_aggregation"
        vision_fake_thresh = settings.get("thresholds", {}).get("vision_fake_threshold", 0.5)
        audio_fake_thresh = settings.get("thresholds", {}).get("audio_fake_threshold", 0.5)
        
        is_vision_fake = vision_result.get("max_score", 0.0) > vision_fake_thresh
        is_audio_fake = audio_result.get("max_score", 0.0) > audio_fake_thresh
        is_deepfake = is_vision_fake or is_audio_fake
        
        is_scam = llm_result.get("is_scam_likely", False)
        # If they claim to be registered but registry check fails, it's a huge red flag
        if registry_result.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
            is_scam = True
            
        verdict = "Safe"
        if is_deepfake and is_scam:
            verdict = "Critical: Deepfake + Scam"
        elif is_deepfake:
            verdict = "Warning: Deepfake Detected"
        elif is_scam:
            verdict = "Warning: SEBI Violation / Scam"
            
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = {
            "verdict": verdict,
            "is_deepfake": is_deepfake,
            "is_scam": is_scam,
            "vision_score": vision_result.get("max_score", 0.0),
            "vision_temporal_variance": vision_result.get("temporal_variance", 0.0),
            "audio_score": audio_result.get("max_score", 0.0),
            "flagged_audio_segments": audio_result.get("flagged_segments", []),
            "transcript": transcription_result.get("transcript", ""),
            "sebi_analysis": llm_result,
            "registry_check": registry_result
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/api/jobs")
async def create_scan_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
        
    job_id = str(uuid.uuid4())
    temp_path = f"temp/{job_id}_{file.filename}"
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "stage": "pending",
        "filename": file.filename
    }
    
    background_tasks.add_task(process_video_pipeline, job_id, temp_path)
    
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
