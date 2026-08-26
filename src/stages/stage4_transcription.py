import os
import gc
import torch
from faster_whisper import WhisperModel

from src.config import get_device, get_stage_config

def run_stage4_transcription(audio_path: str, job_id: str):
    """
    Transcribes audio using faster-whisper.
    Returns:
        dict: {
            "transcript": str,
            "segments": list[dict] # {"start": float, "end": float, "text": str}
        }
    """
    print(f"[{job_id}] Running Stage 4: Transcription")
    stage_config = get_stage_config("stage4_transcription")
    device = "cpu" if stage_config.get("use_cpu") else get_device()
    model_size = stage_config.get("model_id", "medium").split("-")[-1]
    # Force CPU+int8 for faster-whisper: cublas64_12.dll is not available on
    # Windows unless the full CUDA Toolkit (not just PyTorch) is installed.
    # CPU int8 via CTranslate2 is still fast enough for this use case.
    whisper_device = "cpu"
    compute_type = "int8"
    
    result = {
        "transcript": "",
        "segments": []
    }
    
    if not audio_path or not os.path.exists(audio_path):
        print(f"[{job_id}] No audio track provided. Skipping transcription stage.")
        return result
        
    try:
        print(f"[{job_id}] Loading Whisper Model: {model_size} on {whisper_device} ({compute_type})...")
        model = WhisperModel(model_size, device=whisper_device, compute_type=compute_type)
            
        print(f"[{job_id}] Transcribing audio...")
        segments, info = model.transcribe(audio_path, beam_size=5)
        
        full_text = []
        for segment in segments:
            result["segments"].append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            })
            full_text.append(segment.text.strip())
            
        result["transcript"] = " ".join(full_text)
        print(f"[{job_id}] Transcription complete. Extracted {len(result['segments'])} segments.")
        
    except Exception as e:
        print(f"[{job_id}] Transcription stage failed: {e}")
    finally:
        # Crucial for VRAM budget: delete model and empty cache
        if 'model' in locals():
            del model
            
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    return result
