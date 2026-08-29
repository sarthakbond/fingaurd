"""
Model Verification & Benchmark Script
======================================
Tests every model checkpoint in the pipeline:
  1. Confirms it exists on HuggingFace / Local Ollama
  2. Downloads & loads it
  3. Runs a real inference pass (dummy/synthetic input)
  4. Reports VRAM usage before and after
  5. Runs VRAM cleanup and confirms memory is released

Run: python scripts/verify_all_models.py
"""
import os
import gc
import sys
import time
import numpy as np
import torch
import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add workspace root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

config_path = os.path.join(ROOT_DIR, "config.yaml")

print("=" * 60)
print("  FinGuard — Model Verification & Hardware Benchmark")
print("=" * 60)

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

pipeline = config.get("pipeline", {})
VISION_MODEL  = pipeline.get("stage2_vision", {}).get("model_id")
AUDIO_MODEL   = pipeline.get("stage3_audio", {}).get("model_id")
WHISPER_SIZE  = pipeline.get("stage4_transcription", {}).get("model_id", "medium").split("-")[-1]
LLM_MODEL     = pipeline.get("stage5_llm", {}).get("model_id", "llama3.1:latest")

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
    status = "[PASS]" if ok else "[FAIL]"
    print(f"  {status} {name}")
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
    from PIL import Image
    from torchvision import transforms

    t0 = time.time()
    vram_before = vram_used_gb()

    if "AdityaManojShinde" in (VISION_MODEL or ""):
        from src.model import HybridDeepfakeDetector
        from huggingface_hub import hf_hub_download

        print(f"  Loading Hybrid (EfficientNet-B4 + Xception SRM)...")
        model = HybridDeepfakeDetector()
        weights_path = hf_hub_download(repo_id="AdityaManojShinde/deepfake-detector", filename="deepfake_detector_phase2.pth")
        model.load_state_dict(torch.load(weights_path, map_location=DEVICE))
        model = model.to(DEVICE)
        model.eval()

        vram_after_load = vram_used_gb()
        print(f"  VRAM after load: {vram_after_load:.2f} GB")

        dummy_img = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))
        tf = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        inp = tf(dummy_img).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            prob = model(inp).item()
        print(f"  Dummy inference probability: {prob:.4f}")
        del model, inp
    else:
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        processor = AutoImageProcessor.from_pretrained(VISION_MODEL)
        model = AutoModelForImageClassification.from_pretrained(VISION_MODEL, torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32)
        model = model.to(DEVICE)
        model.eval()

        vram_after_load = vram_used_gb()
        print(f"  VRAM after load: {vram_after_load:.2f} GB")

        dummy_img = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))
        inputs = processor(images=dummy_img, return_tensors="pt")
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        print(f"  Dummy inference probs: {probs[0].tolist()}")
        del model, processor, inputs, outputs

    vram_peak = vram_used_gb()
    vram_free()
    vram_after_free = vram_used_gb()

    elapsed = time.time() - t0
    print_result(
        VISION_MODEL, True,
        f"Loaded and ran inference successfully.",
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
    import wave, struct, tempfile

    t0 = time.time()

    print(f"  Downloading/loading faster-whisper {WHISPER_SIZE}...")
    model = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")
    print(f"  Model loaded. Running dummy transcription (1s silence)...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))

    segments, info = model.transcribe(tmp_path, beam_size=1)
    text = " ".join([s.text for s in segments])
    if os.path.exists(tmp_path):
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
    ollama_url = pipeline.get("stage5_llm", {}).get("api_url", "http://localhost:11434/api/chat")
    base_url = ollama_url.replace("/api/chat", "").replace("/api/generate", "")

    t0 = time.time()
    print(f"  Pinging Ollama at {base_url}...")

    try:
        r = requests.get(f"{base_url}/api/tags", timeout=3)
        if r.status_code == 200:
            installed = [m["name"] for m in r.json().get("models", [])]
            print(f"  Ollama is running. Installed models: {installed}")
            has_model = any(LLM_MODEL in m for m in installed)
            if not has_model:
                print(f"  WARNING: {LLM_MODEL} not in installed models! Run: ollama pull {LLM_MODEL}")
        else:
            print(f"  Ollama ping returned HTTP {r.status_code}")
    except Exception as e:
        print(f"  Cannot connect to Ollama ({e}). Is it running?")

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a SEBI compliance auditor."},
            {"role": "user", "content": "Is promising guaranteed 100% daily profit a SEBI violation? Answer in 1 short sentence."}
        ],
        "stream": False
    }

    r2 = requests.post(ollama_url, json=payload, timeout=20)
    if r2.status_code == 200:
        reply = r2.json().get("message", {}).get("content", "")
        elapsed = time.time() - t0
        print_result(
            f"Ollama ({LLM_MODEL})", True,
            f"Response received ({len(reply)} chars): '{reply.strip()[:100]}...'",
            elapsed=elapsed
        )
    else:
        print_result(f"Ollama ({LLM_MODEL})", False, f"HTTP {r2.status_code}: {r2.text}")

except Exception as e:
    print_result(f"Ollama ({LLM_MODEL})", False, str(e))

print()
print("=" * 60)
print("  Summary:")
for k, v in results.items():
    print(f"  {'[PASS]' if v else '[FAIL]'} {k}")
print("=" * 60)
