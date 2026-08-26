"""
Model Verification & Benchmark Script
======================================
Tests every model checkpoint in the pipeline:
  1. Confirms it exists on HuggingFace
  2. Downloads it
  3. Runs a real inference pass (dummy/real input)
  4. Reports VRAM usage before and after
  5. Runs VRAM cleanup and confirms memory is released

Run: python verify_all_models.py

Each model is tested in isolation so VRAM numbers are accurate.
"""
import gc
import sys
import time
import numpy as np
import torch
import yaml

print("=" * 60)
print("  Financial Deepfake Detector — Model Verification")
print("=" * 60)

# Load config so model IDs come from config, not hardcoding
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

pipeline = config.get("pipeline", {})
VISION_MODEL  = pipeline.get("stage2_vision", {}).get("model_id")
AUDIO_MODEL   = pipeline.get("stage3_audio", {}).get("model_id")
WHISPER_SIZE  = pipeline.get("stage4_transcription", {}).get("model_id", "medium").split("-")[-1]
LLM_MODEL     = config.get("pipeline", {}).get("stage5_llm", {}).get("model_id", "llama3.2:3b")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"\nHardware: {DEVICE.upper()}")
if DEVICE == "cuda":
    props = torch.cuda.get_device_properties(0)
    total_vram = props.total_memory / 1024**3
    print(f"GPU: {props.name} — {total_vram:.1f} GB VRAM")
print(f"\nModels to verify (from config.yaml):")
print(f"  Stage 2 Vision  : {VISION_MODEL}")
print(f"  Stage 3 Audio   : {AUDIO_MODEL}")
print(f"  Stage 4 Whisper : {WHISPER_SIZE}")
print(f"  Stage 5 LLM     : {LLM_MODEL} (via Ollama)")
print()

results = {}

def vram_used_gb():
    if DEVICE != "cuda":
        return 0.0
    return torch.cuda.memory_allocated() / 1024**3

def vram_free():
    if DEVICE == "cuda":
        gc.collect()
        torch.cuda.empty_cache()

def print_result(name, ok, msg, vram_delta=None, elapsed=None):
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"  [{status}] {name}")
    print(f"         {msg}")
    if vram_delta is not None:
        print(f"         VRAM used during inference: {vram_delta:.2f} GB")
    if elapsed is not None:
        print(f"         Time: {elapsed:.1f}s")
    results[name] = ok

# ─────────────────────────────────────────────────────────────
# Stage 2: Vision Model
# ─────────────────────────────────────────────────────────────
print("─" * 60)
print(f"[1/4] Stage 2 — Vision: {VISION_MODEL}")
print("─" * 60)

try:
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    from PIL import Image

    t0 = time.time()
    vram_before = vram_used_gb()

    print(f"  Downloading/loading processor...")
    processor = AutoImageProcessor.from_pretrained(VISION_MODEL)
    print(f"  Downloading/loading model weights...")
    model = AutoModelForImageClassification.from_pretrained(VISION_MODEL, torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32)
    model = model.to(DEVICE)
    model.eval()

    vram_after_load = vram_used_gb()
    print(f"  VRAM after load: {vram_after_load:.2f} GB")

    # Create a dummy 224x224 RGB image for inference
    dummy_img = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))
    inputs = processor(images=dummy_img, return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    # Print label mapping
    id2label = model.config.id2label if hasattr(model.config, "id2label") else {}
    print(f"  Labels: {dict(id2label)}")
    print(f"  Dummy inference probs: {probs[0].tolist()}")

    vram_peak = vram_used_gb()
    del model, processor, inputs, outputs
    vram_free()
    vram_after_free = vram_used_gb()

    elapsed = time.time() - t0
    print_result(
        VISION_MODEL, True,
        f"Loaded and ran inference. Labels: {dict(id2label)}",
        vram_delta=(vram_peak - vram_before),
        elapsed=elapsed
    )
    print(f"  VRAM after cleanup: {vram_after_free:.2f} GB")

except Exception as e:
    vram_free()
    print_result(VISION_MODEL, False, str(e))

print()

# ─────────────────────────────────────────────────────────────
# Stage 3: Audio Deepfake Model
# ─────────────────────────────────────────────────────────────
print("─" * 60)
print(f"[2/4] Stage 3 — Audio: {AUDIO_MODEL}")
print("─" * 60)

try:
    from transformers import Wav2Vec2FeatureExtractor, AutoModelForAudioClassification

    t0 = time.time()
    vram_before = vram_used_gb()

    print(f"  Downloading/loading feature extractor...")
    processor = Wav2Vec2FeatureExtractor.from_pretrained(AUDIO_MODEL)
    print(f"  Downloading/loading model weights...")
    model = AutoModelForAudioClassification.from_pretrained(AUDIO_MODEL, torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32)
    model = model.to(DEVICE)
    model.eval()

    vram_after_load = vram_used_gb()
    print(f"  VRAM after load: {vram_after_load:.2f} GB")

    # 1 second of dummy 16kHz audio
    dummy_audio = np.random.randn(16000).astype(np.float32)
    proc_out = processor(dummy_audio, sampling_rate=16000, return_tensors="pt", padding=True)
    model_dtype = next(model.parameters()).dtype
    inputs = {k: v.to(DEVICE).to(model_dtype) for k, v in proc_out.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    id2label = model.config.id2label if hasattr(model.config, "id2label") else {}
    print(f"  Labels: {dict(id2label)}")
    print(f"  Dummy inference probs: {probs[0].tolist()}")

    vram_peak = vram_used_gb()
    del model, processor, inputs, outputs, proc_out
    vram_free()
    vram_after_free = vram_used_gb()

    elapsed = time.time() - t0
    print_result(
        AUDIO_MODEL, True,
        f"Loaded and ran inference. Labels: {dict(id2label)}",
        vram_delta=(vram_peak - vram_before),
        elapsed=elapsed
    )
    print(f"  VRAM after cleanup: {vram_after_free:.2f} GB")

except Exception as e:
    vram_free()
    print_result(AUDIO_MODEL, False, str(e))

print()

# ─────────────────────────────────────────────────────────────
# Stage 4: Whisper (faster-whisper / CTranslate2)
# ─────────────────────────────────────────────────────────────
print("─" * 60)
print(f"[3/4] Stage 4 — Whisper ({WHISPER_SIZE}, CPU int8 via CTranslate2)")
print("─" * 60)

try:
    from faster_whisper import WhisperModel
    import io, wave, struct

    t0 = time.time()

    print(f"  Downloading/loading faster-whisper {WHISPER_SIZE}...")
    # Always CPU+int8 because cublas64_12.dll is not on Windows without full CUDA Toolkit
    model = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
    print(f"  Model loaded. Running dummy transcription (1s silence)...")

    # Write a 1-second silent WAV to a temp file
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))

    segments, info = model.transcribe(tmp_path, beam_size=1)
    text = " ".join([s.text for s in segments])
    os.unlink(tmp_path)

    del model
    gc.collect()

    elapsed = time.time() - t0
    print_result(
        f"faster-whisper-{WHISPER_SIZE}", True,
        f"Loaded and transcribed 1s silence. Output: '{text.strip() or '<empty>'}'",
        elapsed=elapsed
    )

except Exception as e:
    gc.collect()
    print_result(f"faster-whisper-{WHISPER_SIZE}", False, str(e))

print()

# ─────────────────────────────────────────────────────────────
# Stage 5: Ollama LLM
# ─────────────────────────────────────────────────────────────
print("─" * 60)
print(f"[4/4] Stage 5 — Ollama LLM: {LLM_MODEL}")
print("─" * 60)

try:
    import requests
    ollama_url = config.get("pipeline", {}).get("stage5_llm", {}).get("api_url", "http://localhost:11434/api/chat")

    t0 = time.time()
    print(f"  Pinging Ollama at {ollama_url}...")

    # First check if Ollama is running
    try:
        ping = requests.get("http://localhost:11434", timeout=3)
        print(f"  Ollama server is up (status {ping.status_code}).")
    except Exception:
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    # Check if the model is pulled
    models_resp = requests.get("http://localhost:11434/api/tags", timeout=5).json()
    available = [m["name"] for m in models_resp.get("models", [])]
    print(f"  Available models: {available}")

    model_base = LLM_MODEL.split(":")[0]
    found = any(model_base in m for m in available)

    if not found:
        print(f"  Model '{LLM_MODEL}' not found. Pulling now (this may take a while)...")
        pull_resp = requests.post("http://localhost:11434/api/pull",
                                  json={"name": LLM_MODEL, "stream": False}, timeout=300)
        print(f"  Pull status: {pull_resp.status_code}")

    # Run a quick test inference
    print(f"  Running test inference...")
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly: {\"ok\": true}"}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0}
    }
    resp = requests.post(ollama_url, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    print(f"  LLM response: {content.strip()}")

    elapsed = time.time() - t0
    print_result(LLM_MODEL, True, f"Ollama is running and {LLM_MODEL} responded.", elapsed=elapsed)

except Exception as e:
    print_result(LLM_MODEL, False, str(e))

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  SUMMARY")
print("=" * 60)
all_passed = True
for name, ok in results.items():
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"  [{status}] {name}")
    if not ok:
        all_passed = False

if all_passed:
    print("\n  All models verified! Run the test harness:")
    print("  python run_folder_test.py --folder test_vid --out test_results.csv")
else:
    print("\n  Some models failed. Fix the errors above before running the pipeline.")
    sys.exit(1)
