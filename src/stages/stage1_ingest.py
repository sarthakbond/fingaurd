import os
import gc
import torch
import cv2
import numpy as np
from moviepy import VideoFileClip
from facenet_pytorch import MTCNN
from PIL import Image

from src.config import get_device, get_stage_config

def run_stage1_ingest(video_path: str, temp_dir: str, job_id: str):
    """
    Extracts audio and uses adaptive scene-aware face sampling to catch micro-splices.
    Returns:
        dict: {
            "audio_path": str or None,
            "face_frames_paths": list[str]
        }
    """
    print(f"[{job_id}] Running Stage 1: Ingest & Preprocess (Adaptive Sampling)")
    stage_config = get_stage_config("stage1_ingest")
    device = get_device()
    
    result = {
        "audio_path": None,
        "face_frames_paths": []
    }
    
    # 1. Extract Audio
    try:
        audio_out = os.path.join(temp_dir, f"{job_id}_audio.wav")
        video = VideoFileClip(video_path)
        if video.audio is not None:
            video.audio.write_audiofile(audio_out, logger=None)
            result["audio_path"] = audio_out
            print(f"[{job_id}] Audio extracted.")
        else:
            print(f"[{job_id}] No audio track found in video.")
    except Exception as e:
        print(f"[{job_id}] Audio extraction failed: {e}")
    finally:
        if 'video' in locals():
            video.close()
            
    # 2. Adaptive Frame Extraction with Scene-Cut Awareness
    max_frames = stage_config.get("max_frames_to_extract", 25)
    print(f"[{job_id}] Extracting up to {max_frames} face frames on {device}...")
    
    try:
        mtcnn = MTCNN(keep_all=False, device=device)
        cap = cv2.VideoCapture(video_path)
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError("Could not read frame count from video.")
            
        # Target at least 1 frame every 1.5 seconds, capped by max_frames
        duration_sec = total_frames / fps
        target_frames = min(max_frames, max(15, int(duration_sec / 1.5)))
        base_interval = max(1, total_frames // target_frames)
        
        frame_count = 0
        extracted_count = 0
        prev_gray = None
        
        while cap.isOpened() and extracted_count < target_frames:
            ret, frame = cap.read()
            if not ret:
                break
                
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            is_scene_cut = False
            
            # Detect sudden shot/cut transitions (common in deepfake splices)
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                mean_diff = np.mean(diff)
                if mean_diff > 35.0: # Significant visual cut
                    is_scene_cut = True
                    
            prev_gray = gray
            
            # Sample if at periodic interval OR if a scene cut just occurred
            if (frame_count % base_interval == 0) or (is_scene_cut and extracted_count < target_frames):
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb_frame)
                
                # Detect face
                boxes, probs = mtcnn.detect(img)
                if boxes is not None and len(boxes) > 0:
                    box = boxes[0]
                    margin = 25
                    x1 = max(0, int(box[0]) - margin)
                    y1 = max(0, int(box[1]) - margin)
                    x2 = min(img.width, int(box[2]) + margin)
                    y2 = min(img.height, int(box[3]) + margin)
                    
                    if x2 > x1 and y2 > y1:
                        face_img = img.crop((x1, y1, x2, y2))
                        out_path = os.path.join(temp_dir, f"{job_id}_frame_{extracted_count}.jpg")
                        face_img.save(out_path)
                        result["face_frames_paths"].append(out_path)
                        extracted_count += 1
            
            frame_count += 1
            
        cap.release()
        print(f"[{job_id}] Extracted {extracted_count} face frames (Scene-aware across {duration_sec:.1f}s video).")
        
    except Exception as e:
        print(f"[{job_id}] Face extraction failed: {e}")
    finally:
        if 'mtcnn' in locals():
            del mtcnn
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    return result
