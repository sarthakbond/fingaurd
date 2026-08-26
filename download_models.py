"""
Pre-download all models required by the pipeline.
Run this once before running the test harness.
"""
import sys
import yaml

print("=== Model Pre-Downloader ===")
print("Loading config...")
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

pipeline = config.get("pipeline", {})

vision_model = pipeline.get("stage2_vision", {}).get("model_id")
audio_model  = pipeline.get("stage3_audio", {}).get("model_id")
whisper_model = pipeline.get("stage4_transcription", {}).get("model_id", "medium")
# Extract just the size part from "Systran/faster-whisper-medium" -> "medium"
whisper_size = whisper_model.split("-")[-1] if "/" in whisper_model else whisper_model

print(f"\nModels to download:")
print(f"  Stage 2 Vision  : {vision_model}")
print(f"  Stage 3 Audio   : {audio_model}")
print(f"  Stage 4 Whisper : {whisper_size} (faster-whisper)")
print()

# --- Stage 2: Vision Model ---
print(f"[1/3] Downloading Vision model: {vision_model}")
try:
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    AutoImageProcessor.from_pretrained(vision_model)
    AutoModelForImageClassification.from_pretrained(vision_model)
    print(f"  ✓ Vision model downloaded successfully.\n")
except Exception as e:
    print(f"  ✗ FAILED: {e}\n")

# --- Stage 3: Audio Model ---
print(f"[2/3] Downloading Audio model: {audio_model}")
try:
    from transformers import AutoProcessor, AutoModelForAudioClassification
    AutoProcessor.from_pretrained(audio_model)
    AutoModelForAudioClassification.from_pretrained(audio_model)
    print(f"  ✓ Audio model downloaded successfully.\n")
except Exception as e:
    print(f"  ✗ FAILED: {e}\n")

# --- Stage 4: Whisper Model ---
print(f"[3/3] Downloading Whisper model: {whisper_size}")
try:
    from faster_whisper import WhisperModel
    WhisperModel(whisper_size, device="cpu", compute_type="int8")
    print(f"  ✓ Whisper model downloaded successfully.\n")
except Exception as e:
    print(f"  ✗ FAILED: {e}\n")

print("=== Done! All models are cached locally. Run the test harness now. ===")
