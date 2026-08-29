# ⚡ FinGuard — Complete Technical Documentation

> **AI-powered Financial Deepfake & Scam Detector with SEBI Compliance Analysis**

This document covers everything about FinGuard — what it does, how it works, the full tech stack, project structure, pipeline architecture, API reference, Chrome extension, and setup instructions. Read this top-to-bottom and you'll understand every moving piece.

---

## 📌 What is FinGuard?

FinGuard is a **local-first AI forensic tool** that analyzes financial content (videos, audio, images, text) to detect two things:

1. **Deepfakes** — Face-swapped videos, voice-cloned audio, AI-generated faces
2. **Financial Scams** — SEBI (Securities and Exchange Board of India) regulatory violations by finfluencers: fake advisors, guaranteed return promises, pump-and-dump schemes

It runs entirely on your laptop GPU (NVIDIA RTX 4050, 6GB VRAM) with **zero cloud dependency** for inference. All models run locally.

### Who is this for?
- Retail investors verifying if a stock tip video is legit
- Regulators scanning social media for SEBI violations
- Anyone receiving suspicious "investment advice" on WhatsApp/Telegram

---

## 🛠 Tech Stack

### Backend
| Component | Technology | Purpose |
|---|---|---|
| Web Framework | **FastAPI** | Async API server with background task support |
| ML Framework | **PyTorch** + **timm** | Vision model inference |
| Face Detection | **MTCNN** (facenet-pytorch) | Face extraction from video frames |
| Vision Deepfake | **EfficientNet-B4 + Xception SRM** (custom hybrid) | Spatial + frequency domain deepfake detection |
| Audio Deepfake | **Wav2Vec2** (MelodyMachine/Deepfake-Audio-Detection-V2) | Voice cloning / audio spoof detection |
| Transcription | **faster-whisper** (CTranslate2 int8) | Multilingual speech-to-text (Hindi+English) |
| LLM Reasoning | **LLaMA 3.1** via **Ollama** (local) | SEBI compliance analysis with structured JSON output |
| OCR | **EasyOCR** (Hindi + English) | Text extraction from scam screenshots |
| Registry Matching | **RapidFuzz** | Fuzzy matching against SEBI's registered intermediary database |
| Saliency Heatmaps | **OpenCV + SRM Filters** | Forensic noise residual heatmaps highlighting GAN artifacts |
| Complaint Generator | **Legal Formatting Engine** | Automated drafting for SEBI SCORES complaint lodgement |
| Video Processing | **MoviePy** + **OpenCV** | Frame extraction, audio separation |
| Audio Processing | **librosa** + **soundfile** | Audio loading, normalization, chunking |

### Frontend
| Component | Technology |
|---|---|
| UI | Single-page HTML + vanilla CSS + vanilla JS |
| Design | Dark theme, Inter font, glassmorphism, gradient accents |
| Interaction | Drag-and-drop uploads, tab navigation, polling for async jobs |

### Chrome Extension
| Component | Technology |
|---|---|
| Manifest | Manifest V3 |
| Communication | Chrome extension APIs (contextMenus, storage, messaging) |
| UI | Popup with settings, quick-scan, and results display |

### Infrastructure
| Component | Technology |
|---|---|
| Python | 3.10 or 3.11 |
| GPU | NVIDIA CUDA (RTX 4050 / any CUDA-compatible GPU) |
| LLM Server | Ollama (localhost:11434) |
| Deployment | Google Colab + ngrok (planned) |

---

## 📁 Project Structure

```
fintech/
├── app.py                          # FastAPI main application (all API endpoints & background jobs)
├── model.py                        # Root import shim for HybridDeepfakeDetector
├── config.yaml                     # All thresholds, model IDs, pipeline config (zero hardcoding)
├── requirements.txt                # Pinned Python dependencies
├── .env.example                    # Template for environment secrets
├── README.md                       # High-level overview & quick start
├── DOCUMENTATION.md                # Full technical architecture deep-dive
├── HACKATHON_GUIDE.md              # Master defense guide & judge Q&A cheat sheet
├── TEAM_ONBOARDING_GUIDE.md        # Complete developer & team onboarding guide
├── progress1.md                    # Comprehensive Architecture Blueprint & File Directory
│
├── src/
│   ├── config.py                   # Typed YAML config & environment loader
│   ├── model.py                    # HybridDeepfakeDetector PyTorch neural network
│   ├── backup_api.py               # Optional Sightengine cloud fallback adapter
│   └── stages/
│       ├── __init__.py
│       ├── stage1_ingest.py        # Video → frames + audio extraction + Laplacian quality index
│       ├── stage2_vision.py        # Face deepfake detection (Spatial + SRM Frequency + Visemes)
│       ├── stage3_audio.py         # Audio deepfake detection (Wav2Vec2 + Finfluencer check)
│       ├── stage4_transcription.py # Speech-to-text (faster-whisper + phonetic normalizer)
│       ├── stage5_llm.py           # SEBI compliance LLM (DPDP PET shield + Heuristic engine)
│       ├── stage6_registry.py      # SEBI registry fuzzy matching with in-memory TTL caching
│       ├── stage7_ocr.py           # OCR text extraction (EasyOCR Hindi + English)
│       ├── stage8_report.py        # Pre-filing SEBI SCORES 2.0 evidence dossier generator
│       └── stage9_apk_domain.py    # Rogue APK manifest inspector & phishing domain auditor
│
├── static/                         # Frontend Web Dashboard
│   ├── index.html                  # Modern glassmorphic SPA dashboard
│   ├── legacy-index.html           # Reference legacy UI
│   ├── css/
│   │   ├── app.css                 # Responsive layout & component styling
│   │   └── core.css                # Design system tokens, typography, and animations
│   ├── js/
│   │   ├── api.js                  # Frontend HTTP transport & job polling
│   │   ├── dom.js                  # DOM selectors and helper utilities
│   │   ├── main.js                 # App controller & media playback orchestrator
│   │   ├── model.js                # View model transformer & evidence builder
│   │   └── stages.js               # 9-stage pipeline metadata and progress steps
│   └── videos/                     # Demo & background video assets
│
├── static_data/
│   ├── sebi_registry.json          # Local SEBI registered intermediary database (Aug 2026 snapshot)
│   └── broker_apk_whitelist.json   # Legitimate broker app package names & official domains
│
├── extension/                      # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js               # Service worker (context menus + API calls)
│   ├── content.js                  # In-page toast notifications
│   ├── popup.html                  # Extension popup
│   ├── popup.css                   # Popup styling
│   ├── popup.js                    # Popup logic
│   └── icons/                      # Extension icons (16/48/128px)
│
├── scripts/                        # Developer, Benchmark & Operational Tooling
│   ├── self_test.py                # 13-point automated unit & integration regression suite
│   ├── e2e_system_test.py          # 7-point live end-to-end API stress test
│   ├── sync_sebi_registry.py       # Standalone SEBI master sync daemon & CLI
│   ├── run_folder_test.py          # Batch folder evaluation harness
│   ├── audit_hardcoded.py          # Static scan asserting zero hardcoded values
│   ├── download_models.py          # Pre-download all ML model weights
│   ├── generate_sample.py          # Synthetic verification media generator
│   └── verify_all_models.py        # Model verification & isolated VRAM benchmark
│
├── tests/                          # Evaluation outputs & verification
│   └── test_verification.py        # Model pipeline unit verification test
│
├── temp/                           # Ephemeral runtime scratchpad (auto-purged)
│   └── .gitkeep
├── dataset/                        # Reference benchmark datasets (DeepfakeTIMIT)
└── test_vid/                       # Evaluation video samples (scam_vid / noscam_vid)
```

---

## 🏗 Pipeline Architecture

### Video Scan (9-Stage Async Forensic Pipeline)

```
                        [ Uploaded Video (.mp4) ]
                                 │
                                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │ Stage 1: Ingest & Preprocessing                         │
   │  • MoviePy extracts audio track → temp WAV              │
   │  • OpenCV + MTCNN extracts face frames                   │
   │  • Adaptive scene-cut aware sampling (catches splices)   │
   │  • Input Quality Assessment (Laplacian blur variance)   │
   └──────────────────┬──────────────────┬───────────────────┘
                      │                  │
                      ▼                  ▼
   ┌──────────────────────┐  ┌───────────────────────────────────┐
   │ Stage 2: Vision      │  │ Stage 4: Transcription            │
   │  EfficientNet-B4     │  │  faster-whisper (medium, int8)    │
   │  + Xception SRM      │  │  Multilingual (Hindi+English)     │
   │  (spatial+frequency) │  │  Phonetic financial normalization │
   │  + mouth-motion act. │  │  Timestamped subtitle segments    │
   └──────────┬───────────┘  └─────────────────┬─────────────────┘
              │                                │
              │    ┌───────────────────────────┘
              │    │
              ▼    ▼
   ┌──────────────────────────────────────────┐
   │ Stage 3: Audio Deepfake Detection        │
   │  Wav2Vec2 fine-tuned spoof classifier    │
   │  5-second windowed chunks & timeline     │
   │  Finfluencer target impersonation alert  │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Stage 5: SEBI Compliance Reasoning       │
   │  LLaMA 3.1 via Ollama (Local-First)      │
   │  DPDP Act 2023 PII Masking Shield (PET)  │
   │  Hinglish Slang & Prompt Injection Guard │
   │  Deterministic Heuristic Fast Fallback   │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Stage 6: SEBI Registry Cross-Check       │
   │  Fuzzy match name / reg number against   │
   │  local SEBI snapshot (August 2026)       │
   │  TTL-cached with file-mtime awareness    │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Stage 7: On-Screen Text Extraction (OCR) │
   │  EasyOCR (English + Hindi recognition)   │
   │  Extracts on-screen claims & QR links    │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Stage 9: APK & Phishing Domain Forensics │
   │  Androguard manifest permission audit    │
   │  Levenshtein brand typosquatting scanner │
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Aggregation: Calibrated Decision Engine  │
   │  Fused multi-modal risk score (0–100%)   │
   │  → Safe / Suspicious / Warning / Critical│
   └──────────────────┬───────────────────────┘
                      ▼
   ┌──────────────────────────────────────────┐
   │ Stage 8: SEBI SCORES Evidence Dossier    │
   │  Automated pre-filing legal draft        │
   │  For compliance & regulatory review      │
   └──────────────────────────────────────────┘
```

### Text Scan
```
[ Raw Text ] → Stage 9 (Domain Scan) → Stage 5 (LLM / Heuristic) → Stage 6 (Registry) → Stage 8 (SCORES Dossier) → Verdict
```

### Audio Scan
```
[ Audio File ] → Stage 4 (Transcription) → Stage 3 (Acoustic Spoof) → Stage 5 (LLM) → Stage 6 (Registry) → Stage 8 (SCORES Dossier) → Verdict
```

### Image Scan
```
[ Image File ] → Stage 2 (Face Deepfake) + Stage 7 (OCR) → Stage 9 (Domain Scan) → Stage 5 (LLM) → Stage 6 (Registry) → Stage 8 (SCORES Dossier) → Verdict
```

### APK Scan
```
[ APK File ] → Stage 9 (Manifest Permissions + Broker Typosquatting) → Stage 8 (SCORES Dossier) → Verdict
```

### URL Scan
```
[ URL ] → Stage 9 (Levenshtein Brand Phishing + Punycode Check) → Stage 8 (SCORES Dossier) → Verdict
```

---

## 🧠 How Each Stage Works

### Stage 1: Ingest & Preprocessing
- **Audio extraction**: MoviePy rips the audio track to a 16kHz WAV file
- **Adaptive frame sampling**: Instead of naive uniform sampling, it detects **scene cuts** (sudden visual transitions) using frame differencing. This catches splice points where deepfakes are often stitched
- **Face detection**: MTCNN crops faces from selected frames with a 25px margin
- **Output**: List of face frame paths + audio WAV path

### Stage 2: Vision Deepfake Detection
- **Model**: Custom `HybridDeepfakeDetector` combining:
  - **EfficientNet-B4** (spatial domain — looks at pixel-level artifacts)
  - **Xception** with **SRM (Steganalysis Rich Model) filters** (frequency domain — detects noise patterns left by GAN generators)
- **How it works**: Each face frame is passed through both branches. The spatial branch sees the image normally. The SRM layer converts the image to grayscale, applies 3 high-pass forensic filters (detecting residual noise), and feeds that to Xception
- **Output**: Combined features → classifier → sigmoid probability (0=fake, 1=real). We invert this to get a "fake score"
- **Temporal variance**: If the fake score jumps wildly across sequential frames, that itself is suspicious

### Stage 3: Audio Deepfake Detection
- **Model**: Wav2Vec2 fine-tuned on deepfake audio (`MelodyMachine/Deepfake-Audio-Detection-V2`)
- **Chunking**: Audio is split into 5-second windows. Each chunk is scored independently
- **Normalization**: DC offset removal + peak scaling to prevent compression artifacts from triggering false positives
- **Output**: Per-chunk scores, max score, and flagged segments with timestamps

### Stage 4: Transcription
- **Model**: `faster-whisper` (CTranslate2-optimized Whisper medium, int8 quantized)
- **Why faster-whisper?** 4x faster than OpenAI's whisper, uses CTranslate2 for efficient inference
- **Phonetic normalization**: Custom regex pipeline converts spoken acronyms to standard form:
  - "say bee" / "saybi" → "SEBI"
  - "eye en ay" → "INA"
  - "zero one two three" after INA → "0123" (registration numbers)
  - Hindi digit words ("shunya", "ek", "do") also converted
- **Output**: Full transcript + timestamped segments (used for UI highlighting)

### Stage 5: SEBI Compliance LLM (Multi-Signal Scoring)
- **Model**: LLaMA 3.1 running locally via Ollama
- **System prompt**: Acts as a SEBI compliance officer. Analyzes text across 6 signal categories:

| Signal | Weight | What it catches |
|---|---|---|
| `explicit_returns` | 30% | "guaranteed 40% returns", "sure shot tips" |
| `implied_returns` | 20% | "consistent outperformance", "never had a losing month" |
| `urgency_scarcity` | 15% | "only 50 seats left", "last chance" |
| `social_proof` | 10% | "50,000+ members", "as seen on CNBC" |
| `paywall_push` | 10% | "join premium Telegram", "DM for VIP access" |
| `credential_misrep` | 15% | Fake SEBI claims, "government approved" |

- **Composite score**: Weighted average of individual signal scores. Multiple weak signals together (e.g. implied returns + social proof + paywall) trigger the flag even when no single signal is conclusive. This catches **sophisticated scammers** who avoid explicit violations
- **Output**: Structured JSON with exact flagged quotes, per-signal scores, composite risk score, and reasoning

### Stage 6: SEBI Registry Cross-Check
- **Database**: Local JSON file (`sebi_registry.json`) with SEBI-registered intermediaries (Zerodha, Groww, Angel One, etc.) including aliases
- **Matching logic**:
  1. If registration number is claimed → validate format (must match `IN[A-Z0-9]{8,14}`) → exact lookup in database
  2. If number found → fuzzy-match the claimed name against the registered entity (and aliases) using `token_sort_ratio`
  3. If only name claimed → fuzzy search across all entities and aliases (80% threshold)
- **Verdicts**: `verified` | `not found` | `name-number mismatch` | `malformed number` | `not claimed`

### Stage 7: OCR (Image scan only)
- **Model**: EasyOCR (English + Hindi)
- **Purpose**: Extract text from scam screenshots — fake profit P&L images, edited SEBI certificates, WhatsApp/Telegram forwards
- **Output**: Extracted text + per-block confidence scores + bounding boxes

---

## 🔌 API Reference

### Video Scan (Async)
```
POST /api/jobs
Content-Type: multipart/form-data
Body: file=<video.mp4>

Response: { "job_id": "uuid", "status": "queued" }
```
```
GET /api/jobs/{job_id}

Response: { "status": "processing|completed|failed", "stage": "...", "result": {...} }
```

### Text Scan (Sync)
```
POST /api/scan/text
Content-Type: application/json
Body: { "text": "I guarantee 40% returns..." }

Response: {
  "scan_type": "text",
  "verdict": "Warning: SEBI Violation / Scam",
  "is_scam": true,
  "composite_risk_score": 0.82,
  "sebi_analysis": { ... },   // Full multi-signal breakdown
  "registry_check": { ... }
}
```

### Audio Scan (Sync)
```
POST /api/scan/audio
Content-Type: multipart/form-data
Body: file=<audio.wav>

Response: {
  "scan_type": "audio",
  "verdict": "...",
  "is_deepfake": false,
  "audio_score": 0.12,
  "transcript": "...",
  "sebi_analysis": { ... },
  "registry_check": { ... }
}
```

### Image Scan (Sync)
```
POST /api/scan/image
Content-Type: multipart/form-data
Body: file=<screenshot.png>

Response: {
  "scan_type": "image",
  "verdict": "...",
  "is_deepfake": false,
  "vision_score": 0.05,
  "extracted_text": "...",      // OCR output
  "ocr_confidence": 0.87,
  "sebi_analysis": { ... },
  "registry_check": { ... }
}
```

### APK Scan (Sync)
```
POST /api/scan/apk
Content-Type: multipart/form-data
Body: file=<fake_broker.apk>

Response: {
  "scan_type": "apk",
  "apk_result": {
    "package_name": "com.zerodha.kite3.pro",
    "is_suspicious": true,
    "risk_level": "high",
    "dangerous_permissions": ["READ_SMS", "RECEIVE_SMS", "BIND_ACCESSIBILITY_SERVICE"],
    "package_typosquat": {
      "input_package": "com.zerodha.kite3.pro",
      "closest_legitimate": "com.zerodha.kite3",
      "broker": "Zerodha",
      "levenshtein_distance": 4
    },
    "reason": "Package name 'com.zerodha.kite3.pro' is a suspected typo-squat of 'com.zerodha.kite3' (Zerodha) | Declares dangerous SMS permissions."
  },
  "scores_complaint": "..."
}
```

### URL / Domain Phishing Scan (Sync)
```
POST /api/scan/url
Content-Type: application/json
Body: { "url": "https://groww-bonus-login.xyz/claim" }

Response: {
  "scan_type": "url",
  "url_result": {
    "input": "https://groww-bonus-login.xyz/claim",
    "normalised_host": "groww-bonus-login.xyz",
    "is_phishing": true,
    "risk_level": "high",
    "matched_legitimate_domain": "groww.in",
    "legitimate_broker": "Groww",
    "reason": "PHISHING DETECTED: 'groww-bonus-login.xyz' contains brand keyword 'groww' from legitimate 'groww.in' (Groww)."
  },
  "scores_complaint": "..."
}
```

### Registry Status & Delta Sync
```
GET /api/registry/status
Response: {
  "total_records": 24,
  "last_sync": "2026-08-29T17:15:00",
  "last_sync_result": "success",
  "registry_breakdown": { "Investment Adviser": 12, "Research Analyst": 10, "Stock Broker": 2 }
}

POST /api/admin/sync-registry
Response: { "status": "sync_queued", "message": "SEBI registry sync started in background" }
```

### Health Check
```
GET /api/health

Response: { "status": "ok", "version": "4.0", "stages": 9, "service": "FinGuard" }
```

---

## 🎨 Frontend

Single-page dark-themed dashboard (`static/index.html`) with 4 tabs:

| Tab | Input | What it does |
|---|---|---|
| 🎬 **Video** | File upload (drag-drop) | Full 7-stage async pipeline with live stage progress tracking |
| 📝 **Text** | Textarea | Instant LLM multi-signal analysis |
| 🎙 **Audio** | File upload | Audio deepfake + transcription + SEBI analysis |
| 🖼 **Image** | File upload (with preview) | Face deepfake + OCR + SEBI analysis |

**Results display includes:**
- Verdict banner (Safe 🟢 / Warning 🟡 / Critical 🔴)
- Composite risk meter (animated gradient bar)
- Signal grid (6 individual signal scores with color-coded bars)
- Flagged statements list with exact quotes
- Timestamped transcript with color-highlighted violations (video/audio)
- SEBI registry check result
- LLM reasoning explanation

---

## 🔌 Chrome Extension

### Loading the Extension
1. Open `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked** → select the `extension/` folder
4. The FinGuard shield icon appears in your toolbar

### Features
- **Right-click context menu**: Select any text on a page → right-click → "🔍 Scan with FinGuard". Same for images
- **Popup**: Click the extension icon → set API URL, paste text for quick scan, view last result
- **In-page toasts**: After scanning, a dark notification slides in from the right showing verdict, risk score, and flag count
- **Settings**: API URL is configurable (defaults to `http://localhost:8000`, switch to ngrok URL for cloud deployment)

### How it communicates
```
[Web Page] ←→ [Content Script] ←→ [Service Worker] ←→ [FinGuard API]
                 (content.js)        (background.js)    (localhost:8000)
```

---

## 🔧 VRAM Management

The biggest engineering challenge: fitting 4 heavy ML models into 6GB VRAM.

**Strategy: Sequential Load/Unload**
- Each stage loads its model, runs inference, then **aggressively flushes VRAM**:
  ```python
  del model
  gc.collect()
  torch.cuda.empty_cache()
  ```
- Models never coexist in memory — they run one at a time
- faster-whisper runs on CPU (int8 quantized) to avoid VRAM contention
- The LLM runs in Ollama (separate process with its own memory management)

---

## ⚙️ Configuration (`config.yaml`)

```yaml
hardware:
  device: "cuda"           # "cuda" or "cpu"
  force_cpu: false          # Override to force CPU for all stages

thresholds:
  vision_fake_threshold: 0.5   # Score above this = deepfake
  audio_fake_threshold: 0.5    # Score above this = deepfake
  sebi_risk_threshold: 0.7     # Composite risk above this = scam

pipeline:
  stage1_ingest:
    max_frames_to_extract: 25      # Max face frames to extract
    audio_sample_rate: 16000       # 16kHz for Wav2Vec2
  stage2_vision:
    model_id: "AdityaManojShinde/deepfake-detector"
  stage3_audio:
    model_id: "MelodyMachine/Deepfake-Audio-Detection-V2"
  stage4_transcription:
    model_id: "Systran/faster-whisper-medium"
    compute_type: "int8"
  stage5_llm:
    model_id: "llama3.1:latest"
    api_url: "http://localhost:11434/api/chat"
  stage6_registry:
    source: "static_data/sebi_registry.json"

backup_apis:
  enable_cloud_fallback: false     # Enable Sightengine as backup
```

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.10 or 3.11
- NVIDIA GPU with CUDA (or CPU fallback)
- [Ollama](https://ollama.ai) installed and running

### Step 1: Pull the LLM
```bash
ollama pull llama3.1:latest
```

### Step 2: Create virtual environment
```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux/macOS:
source .venv/bin/activate
```

### Step 3: Install dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Create `.env` file
```bash
# Copy the example
cp .env.example .env
# Edit and add your HF_TOKEN if needed
```

### Step 5: Run the app
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** in your browser.

### Step 6: Load Chrome Extension (optional)
1. Go to `chrome://extensions`
2. Enable Developer mode
3. Click "Load unpacked" → select `extension/` folder

---

## 🧪 Testing

### Quick text scan test (curl):
```bash
curl -X POST http://localhost:8000/api/scan/text ^
  -H "Content-Type: application/json" ^
  -d "{\"text\": \"I am SEBI registered advisor INA000012345. I guarantee 40%% monthly returns. Join my premium WhatsApp group now, only 50 seats left!\"}"
```

### Batch video test:
```bash
python run_folder_test.py --folder test_vid --out test_results.csv
```

---

## 📐 Verdict Logic

```
IF vision_score > 0.5 OR audio_score > 0.5:
    is_deepfake = True

IF llm says is_scam_likely = True:
    is_scam = True

IF registry verdict is "not found" / "mismatch" / "malformed":
    is_scam = True  (override)

FINAL VERDICT:
    deepfake + scam  →  "Critical: Deepfake + Scam"     🔴
    deepfake only    →  "Warning: Deepfake Detected"     🟡
    scam only        →  "Warning: SEBI Violation / Scam" 🟡
    neither          →  "Safe"                           🟢
```

---

## 🗺 Deployment Plan (Pending)

**Google Colab + ngrok** — For hackathon demo:
- Upload code to Colab (free T4 GPU, 16GB VRAM)
- Install deps + Ollama + pull LLaMA
- Start FastAPI + ngrok tunnel
- Judges get a public URL, Chrome extension points to ngrok URL
- Zero cost, production-grade demo

---

## 🤝 Contributing

1. All config is in `config.yaml` — no hardcoded values in source code
2. Each stage is isolated in its own file under `src/stages/`
3. New stages = new file + import in `app.py`
4. VRAM cleanup is mandatory in every stage's `finally` block
5. Frontend is a single self-contained HTML file (no build step)
