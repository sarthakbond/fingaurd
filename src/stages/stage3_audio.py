import os
import gc
import torch
import librosa
import numpy as np
from transformers import Wav2Vec2FeatureExtractor, AutoModelForAudioClassification

from src.config import get_device, get_stage_config, get_threshold, get_audio_config

# Prominent Indian market figures commonly targeted by voice cloning scammers
KNOWN_FINFLUENCER_NAMES = [
    "nithin kamath", "nikhil kamath", "ankur warikoo", "radhakishan damani",
    "jhunjhunwala", "akshat shrivastava", "rachana ranade", "pranjal kamra",
    "sunil singhania", "saurabh mukherjea", "vijay kedia", "porinju veliyath"
]

def check_finfluencer_impersonation(transcript: str, max_audio_fake_score: float) -> dict:
    """
    Checks if a high-profile financial personality is named in the transcript
    combined with an elevated synthetic audio score, indicating a voice clone impersonation scam.
    Threshold read from config: thresholds.impersonation_audio_threshold
    """
    impersonation_thresh = get_threshold("impersonation_audio_threshold", 0.45)
    if not transcript:
        return {"is_impersonation": False, "target": None}
        
    t_lower = transcript.lower()
    for name in KNOWN_FINFLUENCER_NAMES:
        if name in t_lower:
            if max_audio_fake_score > impersonation_thresh:
                return {
                    "is_impersonation": True,
                    "target": name.title(),
                    "warning": f"Potential AI Voice Clone Impersonation of '{name.title()}' (Voice Spoof Confidence: {max_audio_fake_score*100:.1f}%)"
                }
            else:
                return {
                    "is_impersonation": False,
                    "target": name.title(),
                    "warning": None
                }
    return {"is_impersonation": False, "target": None}

def run_stage3_audio(audio_path: str, job_id: str, transcript: str = ""):
    """
    Runs audio deepfake detection on the extracted audio with acoustic normalization.
    Processes audio in chunks to prevent VRAM overflow and isolate spliced segments.
    Returns:
        dict: {
            "avg_score": float,
            "max_score": float,
            "flagged_segments": list[dict], # Suspicious segments only (>0.5)
            "all_segments": list[dict],     # Full continuous timeline chunks for risk scrubber
            "impersonation_check": dict
        }
    """
    print(f"[{job_id}] Running Stage 3: Audio Deepfake Detection (Normalized with Timeline Heatmap)")
    stage_config = get_stage_config("stage3_audio")
    audio_cfg = get_audio_config()
    device = "cpu" if stage_config.get("use_cpu") else get_device()
    model_id = stage_config.get("model_id", "MelodyMachine/Deepfake-Audio-Detection-V2")
    segment_flag_thresh = get_threshold("audio_segment_flag_threshold", 0.45)
    consensus_weight = audio_cfg.get("consensus_top_weight", 0.65)
    consensus_min_chunks = audio_cfg.get("consensus_min_chunks", 2)
    chunk_duration = audio_cfg.get("chunk_duration_seconds", 5.0)
    
    result = {
        "avg_score": 0.0,
        "max_score": 0.0,
        "flagged_segments": [],
        "all_segments": [],
        "impersonation_check": {"is_impersonation": False, "target": None}
    }
    
    if not audio_path or not os.path.exists(audio_path):
        print(f"[{job_id}] No audio track provided. Skipping audio stage.")
        return result
        
    try:
        print(f"[{job_id}] Loading Audio Model: {model_id} on {device}...")
        processor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)
        model = AutoModelForAudioClassification.from_pretrained(
            model_id, torch_dtype=torch.float16 if device == "cuda" else torch.float32
        ).to(device)
        model.eval()
        
        # Load audio at 16kHz
        target_sr = 16000
        audio, sr = librosa.load(audio_path, sr=target_sr)
        
        # Acoustic Normalization (DC offset removal + Peak scaling)
        if len(audio) > 0 and np.max(np.abs(audio)) > 0:
            audio = audio - np.mean(audio)
            audio = audio / np.max(np.abs(audio))
        
        # Process in configurable chunk sizes (default 5s)
        chunk_samples = int(chunk_duration * target_sr)
        
        scores = []
        max_s = 0.0
        
        for i in range(0, len(audio), chunk_samples):
            chunk = audio[i:i+chunk_samples]
            if len(chunk) < target_sr:
                chunk = np.pad(chunk, (0, target_sr - len(chunk)), 'constant')
                
            proc_out = processor(chunk, sampling_rate=target_sr, return_tensors="pt", padding=True)
            model_dtype = next(model.parameters()).dtype
            inputs = {k: v.to(device).to(model_dtype) for k, v in proc_out.items()}
            
            with torch.no_grad():
                outputs = model(**inputs)
                del inputs
                logits = outputs.logits
                probs = torch.nn.functional.softmax(logits, dim=-1)
                
                fake_index = 1
                if model.config.id2label:
                    for k, v in model.config.id2label.items():
                        if "fake" in v.lower() or "spoof" in v.lower():
                            fake_index = k
                            break
                            
                fake_prob = probs[0, fake_index].item()
                scores.append(fake_prob)
                
                start_time = round(i / target_sr, 2)
                end_time = round((i + len(chunk)) / target_sr, 2)
                
                segment_info = {
                    "start": start_time,
                    "end": end_time,
                    "score": round(float(fake_prob), 4)
                }
                result["all_segments"].append(segment_info)
                
                if fake_prob > segment_flag_thresh:  # Flag individual suspicious segments
                    result["flagged_segments"].append(segment_info)
                    
                if fake_prob > max_s:
                    max_s = fake_prob
                    
        if scores:
            scores_sorted = sorted(scores, reverse=True)
            k = min(2, len(scores_sorted))
            top_k_mean = float(np.mean(scores_sorted[:k]))
            anti_weight = round(1.0 - consensus_weight, 4)
            consensus_audio = float(consensus_weight * top_k_mean + anti_weight * max_s) if len(scores) >= consensus_min_chunks else float(max_s)

            result["avg_score"] = float(np.mean(scores))
            result["max_score"] = consensus_audio
            result["raw_peak_score"] = float(max_s)
            
        result["impersonation_check"] = check_finfluencer_impersonation(transcript, result["max_score"])
        print(f"[{job_id}] Audio complete. Calibrated Score: {result['max_score']:.4f} (Peak: {max_s:.4f}), Chunks: {len(result['all_segments'])}, Impersonation: {result['impersonation_check']['is_impersonation']}")
        
    except Exception as e:
        print(f"[{job_id}] Audio stage failed: {e}")
    finally:
        if 'model' in locals():
            del model
        if 'processor' in locals():
            del processor
        if 'inputs' in locals():
            del inputs
        if 'outputs' in locals():
            del outputs
            
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    return result
