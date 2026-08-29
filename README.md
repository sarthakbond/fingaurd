# ⚡ FinGuard — Financial Deepfake & Scam Detector (Enterprise RegTech)

An offline-first, local AI forensic pipeline that analyzes financial content (videos, audio, images, text) to detect:
1. **Deepfake Visual & Voice Manipulation** (Face-swap, reenactment, synthetic voice cloning, viseme lip-sync anomalies)
2. **SEBI Regulatory Violations** (Guaranteed-return promises, unregistered-advisor impersonation, pressure tactics, Hinglish scam slang)
3. **DPDP Act 2023 Compliance** (Local automated PII masking for enterprise privacy)

---

## 🌟 Key Features

- **100% Offline & Local**: Runs on a laptop GPU (RTX 4050 6GB VRAM budget) with sequential VRAM offloading (`torch.cuda.empty_cache()`).
- **Dual-Branch Visual Forensics**: EfficientNet-B4 + Xception SRM noise residuals (`AdityaManojShinde/deepfake-detector`) detecting spatial and frequency synthesis artifacts.
- **Audio Spoofing Detection**: Wav2Vec2 audio classification (`MelodyMachine/Deepfake-Audio-Detection-V2`) with 5-second windowed segment scoring.
- **Cross-Modal Viseme Motion**: Optical flow tracking on mouth regions to expose audio-visual dubbing desync.
- **Multilingual Transcription**: `faster-whisper` (medium, CTranslate2 int8/float16) optimized for Hindi-English code-switched financial speech.
- **DPDP Act 2023 Shield**: Local regex-based PII masking (phones, PAN, Aadhaar, UPI, bank accounts) before LLM analysis.
- **Adversarial Hinglish Slang Detection**: Built-in detection for Indian financial colloquialisms (*"rocket calls"*, *"pakka jackpot"*, *"zero-loss setup"*).
- **SEBI Registry Cross-Check**: Local fuzzy-matching against SEBI's registered intermediary database (`rapidfuzz`) with in-memory TTL caching and daily sync daemon.
- **OCR Screenshot Extraction**: EasyOCR multi-lingual text extraction for P&L screenshots, fake certificates, and social forwards.
- **APK Metadata & Typo-Squatting Scanner**: Androguard manifest inspection for dangerous permissions + Levenshtein / brand-token phishing domain detection.
- **SEBI SCORES Complaint Generator**: Automated formal legal complaint drafting ready for SEBI portal lodgement.
- **Interactive UI & Chrome Extension**: Dark-themed dashboard with live stage tracking and Manifest V3 browser extension.

---

## 🏗️ 9-Stage Pipeline Architecture

```
                       [ Uploaded Video / Audio / Image / Text / APK / URL ]
                                                │
                                                ▼
  ┌───────────────────────────────────────────────────────────────────────────────────────────┐
  │ Stage 1: Ingest & Preprocessing (MoviePy + MTCNN Adaptive Scene-Cut Sampling)            │
  └─────────────────────────────┬─────────────────────────────────────────────────────────────┘
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
                        │ (faster-whisper multilingual) │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 5: SEBI Compliance LLM  │
                        │ (Ollama llama3.1 + DPDP PII)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 6: SEBI Registry Check  │
                        │ (Local database fuzzy match)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 7: OCR Text Extraction  │
                        │ (EasyOCR Hindi+English blocks)│
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 8: SEBI SCORES Report   │
                        │ (Auto-generated Legal Draft)  │
                        └───────────────┬───────────────┘
                                        ▼
                        ┌───────────────────────────────┐
                        │ Stage 9: APK & Domain Scanner │
                        │ (Androguard + Typo-squatting) │
                        └───────────────────────────────┘
```

---

## 📁 Clean Repository Structure

```
fintech/
├── app.py                          # ⭐ Main application entry point (FastAPI server v4.0 + UI + 9-Stage Pipeline)
├── config.yaml                     # ⚙️ Master configuration (zero hardcoded thresholds, model IDs, hardware)
├── requirements.txt                # 📦 Python package dependencies (including androguard, python-Levenshtein)
├── .env.example                    # 🔑 Environment variables template
├── README.md                       # 📖 Project Overview
├── DOCUMENTATION.md                # 📚 Complete Technical Architecture Deep-Dive
├── HACKATHON_GUIDE.md              # 🏆 Cheat Sheet: File-by-File breakdown & Judge Defense
├── TEAM_ONBOARDING_GUIDE.md        # 👥 Team Onboarding & Technical Deep Dive
│
├── src/                            # 🧠 Core Application Package
│   ├── config.py                   # Configuration and environment loader
│   ├── model.py                    # PyTorch HybridDeepfakeDetector (EfficientNet-B4 + SRM)
│   ├── backup_api.py               # Cloud fallback integration (Sightengine)
│   └── stages/                     # 🔬 8-Stage Modular Forensic Pipeline
│
├── static/                         # 🎨 Frontend Web Dashboard (HTML + CSS + JS)
├── static_data/                    # 📊 Reference Datasets (sebi_registry.json)
├── extension/                      # 🧩 Browser Extension (Manifest V3)
├── scripts/                        # 🛠️ Tooling & Benchmark Scripts
├── test_vid/                       # 🎬 Benchmark / Demo Test Videos
├── dataset/                        # 📁 Reference Benchmark Datasets
├── tests/                          # 🧪 Benchmark Output CSVs
└── temp/                           # ⏳ Runtime Scratchpad (Auto-purged per job)
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

## 🧪 Developer & Benchmark Tooling (`scripts/`)

- **Verify & Benchmark Models**:
  ```bash
  python scripts/verify_all_models.py
  ```
- **Pre-download Checkpoints**:
  ```bash
  python scripts/download_models.py
  ```
- **Batch Scan Video Folder**:
  ```bash
  python scripts/run_folder_test.py --folder test_vid --out tests/test_results.csv
  ```
- **Generate Synthetic Verification Video**:
  ```bash
  python scripts/generate_sample.py
  ```

---

## ⚙️ Configuration (`config.yaml`)

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
  enable_cloud_fallback: false
```
