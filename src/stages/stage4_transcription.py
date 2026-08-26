import os
import gc
import re
import torch
from faster_whisper import WhisperModel

from src.config import get_device, get_stage_config

def normalize_phonetic_financial_speech(text: str) -> str:
    """
    Normalizes spoken acronyms and Indian financial phonetic variations:
    - 'eye n a' -> 'INA'
    - 'i.n.a.' -> 'INA'
    - 'say bee' / 'saybi' -> 'SEBI'
    - 'r.i.a.' -> 'RIA'
    - Spoken registration numbers: 'INA zero zero...' -> 'INA00...'
    """
    if not text:
        return ""
        
    cleaned = text
    
    # 1. Acronym standardizations (case-insensitive)
    acronym_patterns = [
        (r"\b(?:eye|ay|i)[\s\.\-]+(?:en|n)[\s\.\-]+(?:ay|a)\b", "INA"),
        (r"\b(?:eye|ay|i)[\s\.\-]+(?:en|n)[\s\.\-]+(?:aitch|h)\b", "INH"),
        (r"\b(?:eye|ay|i)[\s\.\-]+(?:en|n)[\s\.\-]+(?:zed|zee|z)\b", "INZ"),
        (r"\b(?:s|es)[\s\.\-]+(?:e|ee)[\s\.\-]+(?:b|bee)[\s\.\-]+(?:i|eye)\b", "SEBI"),
        (r"\b(?:say\s*bee|saybi|sebee)\b", "SEBI"),
        (r"\b(?:r|ar)[\s\.\-]+(?:i|eye)[\s\.\-]+(?:a|ay)\b", "RIA"),
        (r"\b(?:r|ar)[\s\.\-]+(?:a|ay)\b", "RA"),
    ]
    
    for pat, repl in acronym_patterns:
        cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)
        
    # 2. Spoken digit words following INA/INH/INZ
    digit_words = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "shunya": "0", "ek": "1", "do": "2", "teen": "3", "chaar": "4",
        "paanch": "5", "chhe": "6", "saat": "7", "aath": "8", "nau": "9"
    }
    
    def replace_spoken_digits(match):
        prefix = match.group(1) # INA, INH, INZ
        rest = match.group(2)
        tokens = rest.strip().split()
        converted = []
        for t in tokens:
            t_clean = t.lower().strip(".,-")
            if t_clean in digit_words:
                converted.append(digit_words[t_clean])
            elif t_clean.isdigit():
                converted.append(t_clean)
            else:
                converted.append(t)
        return prefix + "".join(converted)

    cleaned = re.sub(r"\b(INA|INH|INZ)\s+([a-zA-Z0-9\s]+?)(?=\s+(?:and|is|was|registered|hai|ka|number)|$)", replace_spoken_digits, cleaned, flags=re.IGNORECASE)
    
    return cleaned

def run_stage4_transcription(audio_path: str, job_id: str):
    """
    Transcribes audio using faster-whisper with phonetic financial normalization.
    Returns:
        dict: {
            "transcript": str,
            "segments": list[dict] # {"start": float, "end": float, "text": str}
        }
    """
    print(f"[{job_id}] Running Stage 4: Transcription")
    stage_config = get_stage_config("stage4_transcription")
    model_size = stage_config.get("model_id", "medium").split("-")[-1]
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
            
        print(f"[{job_id}] Transcribing audio with multilingual beam search...")
        segments, info = model.transcribe(audio_path, beam_size=5)
        
        full_text = []
        for segment in segments:
            clean_text = normalize_phonetic_financial_speech(segment.text.strip())
            result["segments"].append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": clean_text
            })
            full_text.append(clean_text)
            
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
