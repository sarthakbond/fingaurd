# ⚡ FinGuard — Financial Deepfake & Scam Detector

An offline-first, local AI forensic pipeline that analyzes uploaded videos/audio to detect:
1. **Deepfake Visual & Voice Manipulation** (Face-swap, reenactment, synthetic voice cloning)
2. **SEBI Regulatory Violations** (Guaranteed-return claims, unregistered-advisor impersonation, urgency/pressure tactics)

---

## 🌟 Key Features

- **100% Offline & Local**: Runs on a laptop GPU (RTX 4050 6GB VRAM budget) with sequential VRAM offloading (`torch.cuda.empty_cache()`).
- **Dual-Branch Visual Forensics**: EfficientNet-B4 + Xception SRM noise residuals (`AdityaManojShinde/deepfake-detector`) to detect face-swaps without false positives on camera compression.
- **Audio Spoofing Detection**: Wav2Vec2 audio classification (`MelodyMachine/Deepfake-Audio-Detection-V2`) with 5-second windowed segment scoring.
- **Multilingual Transcription**: `faster-whisper` (medium, CTranslate2 int8) optimized for Hindi-English code-switched financial speech.
- **Local LLM Compliance Reasoning**: Local LLaMA 3.1 via Ollama extracting structured fraud entities (promised returns, pressure tactics, claimed advisor identity).
- **SEBI Registry Cross-Check**: Local fuzzy-matching against SEBI's registered intermediary database (`rapidfuzz`) to catch fake or unregistered entities.
- **Interactive UI**: Dark-themed dashboard with live stage tracking, time-synced transcript highlighting, and violation breakdowns.
- **Cloud Backup Ready**: Config-driven optional fallback for cloud APIs (Sightengine) during hackathons without code changes.

---

## 🏗️ 7-Stage Pipeline Architecture

```
                       [ Uploaded Video ]
                                │
                                ▼
  ┌───────────────────────────────────────────────────────────┐
  │ Stage 1: Ingest & Preprocessing (MoviePy + MTCNN)         │
  └─────────────────────────────┬─────────────────────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│ Stage 2: Vision Forensics     │       │ Stage 3: Audio Spoof Detector │
│ (Spatial + Frequency Residual)│       │ (Wav2Vec2 5s windowed chunks) │
└───────────────┬───────────────┘       └───────────────┬───────────────┘
                │                                       │
                └───────────────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 4: Speech Transcription │
                        │ (faster-whisper medium int8)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 5: SEBI Compliance LLM  │
                        │ (Ollama llama3.1 structured)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 6: SEBI Registry Check  │
                        │ (Local database fuzzy match)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 7: Synthesis & Verdict  │
                        │ (Safe / Scam / Deepfake / Both│
                        └───────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10 or 3.11
- NVIDIA GPU with CUDA support (or CPU fallback)
- [Ollama](https://ollama.ai) installed and running

### 2. Pull the Local LLM
```bash
ollama pull llama3.1:latest
```

### 3. Install Dependencies
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run the Application
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🧪 Running Folder Batch Tests

To evaluate a folder of test videos and dump the results to CSV:

```bash
python run_folder_test.py --folder test_vid --out test_results.csv
```

---

## ⚙️ Configuration (`config.yaml`)

All thresholds, model checkpoints, and fallback switches are fully config-driven without touching source code:

```yaml
hardware:
  device: "cuda"
  force_cpu: false

thresholds:
  vision_fake_threshold: 0.5
  audio_fake_threshold: 0.5
  sebi_risk_threshold: 0.7

pipeline:
  stage1_ingest:
    max_frames_to_extract: 15
    audio_sample_rate: 16000
  stage2_vision:
    model_id: "AdityaManojShinde/deepfake-detector"
  stage3_audio:
    model_id: "MelodyMachine/Deepfake-Audio-Detection-V2"
  stage4_transcription:
    model_id: "Systran/faster-whisper-medium"
  stage5_llm:
    model_id: "llama3.1:latest"
  stage6_registry:
    source: "static_data/sebi_registry.json"

backup_apis:
  enable_cloud_fallback: false # Toggle to true if cloud API backup is needed
```
