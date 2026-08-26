import os
import gc
import torch
import cv2
from moviepy import VideoFileClip
from facenet_pytorch import MTCNN
from PIL import Image

from src.config import get_device, get_stage_config

def run_stage1_ingest(video_path: str, temp_dir: str, job_id: str):
    """
    Extracts audio to a wav file and extracts face frames from the video.
    Returns:
        dict: {
            "audio_path": str or None,
            "face_frames_paths": list[str]
        }
    """
    print(f"[{job_id}] Running Stage 1: Ingest & Preprocess")
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
            # Note: We can resample in moviepy, but doing it in librosa later is safer.
            # Just extract to standard wav for now.
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
            
    # 2. Extract Frames & Detect Faces
    max_frames = stage_config.get("max_frames_to_extract", 15)
    print(f"[{job_id}] Extracting up to {max_frames} face frames on {device}...")
    
    try:
        mtcnn = MTCNN(keep_all=False, device=device)
        cap = cv2.VideoCapture(video_path)
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError("Could not read frame count from video.")
            
        # We want to sample `max_frames` evenly across the video
        frame_interval = max(1, total_frames // max_frames)
        
        frame_count = 0
        extracted_count = 0
        
        while cap.isOpened() and extracted_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_count % frame_interval == 0:
                # Convert BGR to RGB for MTCNN
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb_frame)
                
                # Detect face
                boxes, probs = mtcnn.detect(img)
                if boxes is not None and len(boxes) > 0:
                    # Just take the first/most confident face
                    box = boxes[0]
                    # Expand box slightly for context
                    margin = 30
                    x1 = max(0, int(box[0]) - margin)
                    y1 = max(0, int(box[1]) - margin)
                    x2 = min(img.width, int(box[2]) + margin)
                    y2 = min(img.height, int(box[3]) + margin)
                    
                    face_img = img.crop((x1, y1, x2, y2))
                    out_path = os.path.join(temp_dir, f"{job_id}_frame_{extracted_count}.jpg")
                    face_img.save(out_path)
                    result["face_frames_paths"].append(out_path)
                    extracted_count += 1
            
            frame_count += 1
            
        cap.release()
        print(f"[{job_id}] Extracted {extracted_count} face frames.")
        
    except Exception as e:
        print(f"[{job_id}] Face extraction failed: {e}")
    finally:
        # Clear MTCNN from VRAM
        if 'mtcnn' in locals():
            del mtcnn
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    return result
