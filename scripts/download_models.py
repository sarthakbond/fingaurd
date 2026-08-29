"""
Pre-download all models required by the pipeline into local cache.
Run: python scripts/download_models.py
"""
import os
import sys
import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add workspace root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

config_path = os.path.join(ROOT_DIR, "config.yaml")

print("=== Model Pre-Downloader ===")
print(f"Loading config from: {config_path}")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

pipeline = config.get("pipeline", {})

vision_model = pipeline.get("stage2_vision", {}).get("model_id")
audio_model  = pipeline.get("stage3_audio", {}).get("model_id")
whisper_model = pipeline.get("stage4_transcription", {}).get("model_id", "medium")
whisper_size = whisper_model.split("-")[-1] if "/" in whisper_model else whisper_model

print(f"\nModels to download:")
print(f"  Stage 2 Vision  : {vision_model}")
print(f"  Stage 3 Audio   : {audio_model}")
print(f"  Stage 4 Whisper : {whisper_size} (faster-whisper)")
print()

# --- Stage 2: Vision Model ---
print(f"[1/3] Downloading Vision model: {vision_model}")
try:
    if "AdityaManojShinde" in (vision_model or ""):
        from huggingface_hub import hf_hub_download
        weights_path = hf_hub_download(repo_id="AdityaManojShinde/deepfake-detector", filename="deepfake_detector_phase2.pth")
        print(f"  [OK] Vision weights downloaded to: {weights_path}\n")
    else:
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        AutoImageProcessor.from_pretrained(vision_model)
        AutoModelForImageClassification.from_pretrained(vision_model)
        print(f"  [OK] Vision model downloaded successfully.\n")
except Exception as e:
    print(f"  [FAIL] FAILED: {e}\n")

# --- Stage 3: Audio Model ---
print(f"[2/3] Downloading Audio model: {audio_model}")
try:
    from transformers import Wav2Vec2FeatureExtractor, AutoModelForAudioClassification
    Wav2Vec2FeatureExtractor.from_pretrained(audio_model)
    AutoModelForAudioClassification.from_pretrained(audio_model)
    print(f"  [OK] Audio model downloaded successfully.\n")
except Exception as e:
    print(f"  [FAIL] FAILED: {e}\n")

# --- Stage 4: Whisper Model ---
print(f"[3/3] Downloading Whisper model: {whisper_size}")
try:
    from faster_whisper import WhisperModel
    WhisperModel(whisper_size, device="cpu", compute_type="int8")
    print(f"  [OK] Whisper model downloaded successfully.\n")
except Exception as e:
    print(f"  [FAIL] FAILED: {e}\n")

print("=== Done! All models are cached locally. Run the test harness now. ===")
