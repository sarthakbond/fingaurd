import os
import glob
import time
import uuid
import json

from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry
from src.config import settings

def test_folder(folder_path: str, output_csv: str = "test_results.csv"):
    video_files = glob.glob(os.path.join(folder_path, "**", "*.[mM][pP]4"), recursive=True) + \
                  glob.glob(os.path.join(folder_path, "**", "*.[aA][vV][iI]"), recursive=True) + \
                  glob.glob(os.path.join(folder_path, "**", "*.[mM][oO][vV]"), recursive=True)
                  
    if not video_files:
        print(f"No video files found in {folder_path}")
        return
        
    print(f"Found {len(video_files)} videos in {folder_path}. Starting batch test...")
    
    os.makedirs("temp", exist_ok=True)
    results = []
    
    vision_fake_thresh = settings.get("thresholds", {}).get("vision_fake_threshold", 0.5)
    audio_fake_thresh = settings.get("thresholds", {}).get("audio_fake_threshold", 0.5)
    
    # Simple CSV header
    with open(output_csv, "w", encoding="utf-8") as f:
        f.write("Filename,Verdict,Is Deepfake,Is Scam,Vision Score,Audio Score,Claimed Advisor,Registry Verdict,Total Time (s)\n")
        
    for video in video_files:
        start_time = time.time()
        filename = os.path.basename(video)
        job_id = f"test_{uuid.uuid4().hex[:8]}"
        print(f"\n==========================================")
        print(f"Processing: {filename} (Job ID: {job_id})")
        print(f"==========================================")
        
        try:
            # Stage 1
            ingest_result = run_stage1_ingest(video, "temp", job_id)
            
            # Stage 2
            vision_result = run_stage2_vision(ingest_result.get("face_frames_paths", []), job_id)
            
            # Stage 3
            audio_result = run_stage3_audio(ingest_result.get("audio_path"), job_id)
            
            # Stage 4
            transcription_result = run_stage4_transcription(ingest_result.get("audio_path"), job_id)
            
            # Stage 5
            llm_result = run_stage5_llm(transcription_result.get("transcript", ""), job_id)
            
            # Stage 6
            registry_result = run_stage6_registry(llm_result, job_id)
            
            # Stage 7 (Aggregation)
            is_vision_fake = vision_result.get("max_score", 0.0) > vision_fake_thresh
            is_audio_fake = audio_result.get("max_score", 0.0) > audio_fake_thresh
            is_deepfake = is_vision_fake or is_audio_fake
            
            is_scam = llm_result.get("is_scam_likely", False)
            if registry_result.get("verdict") in ["not found", "name-number mismatch", "malformed number"]:
                is_scam = True
                
            verdict = "Safe"
            if is_deepfake and is_scam:
                verdict = "Critical: Deepfake + Scam"
            elif is_deepfake:
                verdict = "Warning: Deepfake Detected"
            elif is_scam:
                verdict = "Warning: SEBI Violation / Scam"
                
            elapsed = time.time() - start_time
            
            claimed_advisor = llm_result.get("claimed_advisor_name") or "None"
            reg_verdict = registry_result.get("verdict", "N/A")
            v_score = vision_result.get("max_score", 0.0)
            a_score = audio_result.get("max_score", 0.0)
            
            # Write to CSV
            with open(output_csv, "a", encoding="utf-8") as f:
                f.write(f"{filename},{verdict},{is_deepfake},{is_scam},{v_score:.4f},{a_score:.4f},\"{claimed_advisor}\",{reg_verdict},{elapsed:.1f}\n")
                
            # Cleanup temp files for this job
            if ingest_result.get("audio_path") and os.path.exists(ingest_result.get("audio_path")):
                os.remove(ingest_result.get("audio_path"))
            for p in ingest_result.get("face_frames_paths", []):
                if os.path.exists(p):
                    os.remove(p)
                    
            print(f"Finished {filename} in {elapsed:.1f}s. Verdict: {verdict}")
            
        except Exception as e:
            print(f"Failed processing {filename}: {e}")
            with open(output_csv, "a", encoding="utf-8") as f:
                f.write(f"{filename},ERROR,False,False,0,0,N/A,ERROR,0\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run full pipeline on a folder of videos")
    parser.add_argument("--folder", type=str, default="test_vid", help="Folder containing videos")
    parser.add_argument("--out", type=str, default="test_results.csv", help="Output CSV file")
    
    args = parser.parse_args()
    test_folder(args.folder, args.out)
