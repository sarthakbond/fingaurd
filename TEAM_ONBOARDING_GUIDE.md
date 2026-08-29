# 🛡️ FinGuard (FraudShield-SEBI Pro) — Complete Team Master Guide

> **For New Teammates**: This document explains **EVERYTHING** you need to know about FinGuard: what the project does, how the 9-stage pipeline works under the hood, how we handle files & privacy, why low-quality phone videos behave the way they do, how to run the project, and how to defend it to hackathon judges.

---

## 📌 1. Project Overview & Pitch

### What is FinGuard?
**FinGuard** is an **Air-Gapped, Local AI Forensic & Regulatory Intelligence Gateway** designed to detect **financial deepfakes** (synthetic face swaps, AI voice clones) and **SEBI compliance violations** (guaranteed return promises, unregistered investment advisory, coded stock manipulation) in videos, audio, screenshots, and text messages.

### The Big Problem We Solve:
1. **The Deepfake Crisis**: Scammers use AI tools (Face-swap, ElevenLabs voice cloning) to create deepfakes of high-profile financial leaders (e.g., Nithin Kamath, Mukesh Ambani, NSE CEO) giving fake stock recommendations.
2. **Unregistered Finfluencer Scams**: Unregistered creators promise *"40% monthly guaranteed returns"*, *"Pakka jackpot calls"*, and lure retail investors into unregulated paid Telegram/WhatsApp groups.
3. **SEBI's August 2024 Mandate**: SEBI issued a strict compliance circular barring all SEBI-registered brokers (Zerodha, Groww, Angel One) and mutual funds from associating with, paying, or advertising through unregistered financial influencers.

### Commercial Positioning:
We position FinGuard as a **B2B Enterprise RegTech SaaS** that stockbrokers and trading platforms use as an automated compliance firewall to continuously audit influencer content before paying affiliate marketing payouts.

---

## 🧠 2. The 9-Stage Forensic Pipeline (How It Works)

```
[Uploaded Video/Audio/Text/Image/APK/URL]
               │
               ▼
   [Stage 1: Adaptive Ingest]
   ├── Video -> 16kHz Mono Audio (MoviePy / librosa)
   └── Video -> Face Crops across Scene Cuts (MTCNN on CUDA)
               │
       ┌───────┴────────────────────────┬──────────────────────┐
       ▼                                ▼                      ▼
[Stage 2: Vision Forensics]   [Stage 3: Audio Spoof]   [Stage 4: Transcription]
 • Spatial: EfficientNet-B4    • Wav2Vec2 (MelodyMachine)• faster-whisper (int8/fp16)
 • Frequency: Xception + SRM   • 5s Chunks Analysis     • Multilingual (Hindi +
 • Viseme Mouth Motion Track   • Speaker Impersonation    English + Hinglish)
 • Early-Exit Optimizer        • Segment Scrubber
       └───────┬────────────────────────┴──────────────────────┘
               ▼
[Stage 5: DPDP Shield + SEBI Compliance LLM (LLaMA 3.1)]
 • DPDP Act 2023 Local PII Masker (Scrubs Phone, PAN, Aadhaar, UPI, Telegram links)
 • Adversarial Hinglish Scam Slang Engine ("rocket calls", "zero-loss", "jackpot")
 • 6-Factor Multi-Signal Regulatory Reasoner (Weights: 30%, 20%, 15%, 10%, 10%, 15%)
 • Heuristic Rule Fallback Engine (sub-millisecond instant execution)
               │
               ▼
[Stage 6: SEBI Intermediary Registry Cross-Check]
 • RapidFuzz Offline DB Match against SEBI Registered IA/RAs/Brokers
 • In-Memory TTL Cache (zero disk I/O latency on repeated lookups)
 • Verdicts: `verified` | `not found` | `name-number mismatch` | `malformed`
               │
               ▼
[Stage 7: OCR Text Extraction (EasyOCR)]
 • Multi-language (Hindi + English) text extraction from screenshots & certificates
 • Bounding box parsing with dynamic confidence thresholding
               │
               ▼
[Stage 8: SEBI SCORES Complaint Drafting Engine]
 • Formats formal legal complaints with evidentiary quotes and SEBI Act clauses
 • 1-Click Export to `.txt` ready for SEBI Market Surveillance / SCORES portal
               │
               ▼
[Stage 9: APK Metadata & Phishing Domain Scanner]
 • Androguard Android manifest inspection for high-risk permissions (SMS, Accessibility)
 • Two-pass brand-token & Levenshtein typo-squatting scanner against official broker whitelist
```

---

## 🔬 3. Deep-Dive: Each Stage Explained

### Stage 1: Ingestion & Adaptive Sampling (`src/stages/stage1_ingest.py`)
- Takes MP4, AVI, MOV, WAV, MP3, or images.
- Extracts clean mono audio at **16,000 Hz** (required by speech models).
- Uses **MTCNN (Multi-task Cascaded Convolutional Networks)** on GPU to detect faces.
- Employs **Scene-Cut Aware Frame Sampling** to capture dynamic facial changes across video cuts.

### Stage 2: Dual-Stream Vision Forensics (`src/stages/stage2_vision.py` & `src/model.py`)
- **Dual-Stream Hybrid Architecture**:
  1. **Spatial Stream (EfficientNet-B4)**: Looks at visible pixel-level abnormalities (unnatural skin textures, earlobe warping, inconsistent lighting).
  2. **Frequency Stream (Xception + SRM Filters)**: Uses **Steganalysis Rich Model (SRM)** high-pass filters to extract noise residuals, uncovering invisible GAN generation checkerboard fingerprints.
  3. **Cross-Modal Viseme Mouth-Motion Tracker**: Calculates optical flow and Sobel gradient variance around the lip/mouth region to detect voice-dubbing synchronization drift.
  4. **Early-Exit Inference Acceleration**: Halts frame evaluation early if 4 consecutive frames exceed 0.92 confidence, drastically reducing latency on obvious fakes.

### Stage 3: Audio Spoofing Detection (`src/stages/stage3_audio.py`)
- **Model**: `MelodyMachine/Deepfake-Audio-Detection-V2` (fine-tuned Wav2Vec2).
- Normalizes audio (DC offset removal + peak scaling).
- Breaks audio into **5-second sliding windows** to calculate timeline spoof probabilities.
- Runs an **Impersonation Target Classifier** (detects if synthetic voice claims to be Nithin Kamath, Mukesh Ambani, etc.).

### Stage 4: Multilingual Transcription (`src/stages/stage4_transcription.py`)
- **Engine**: `faster-whisper` (CTranslate2 int8/float16 quantized with CUDA acceleration).
- Generates millisecond-accurate timestamped segments (`[{start, end, text}]`).
- Transcribes code-mixed **Hindi, English, and Hinglish** audio with zero cloud API costs.
- Applies phonetic financial speech normalization (*"say bee"* → *"SEBI"*, spoken digit words to numeric strings).

### Stage 5: DPDP Act 2023 Shield & SEBI LLM (`src/stages/stage5_llm.py`)
- **🛡️ DPDP Act 2023 Data Shield**: Before sending any text to the LLM, local regex scrubbers mask Indian phone numbers (`+91`), PAN cards (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar, UPI IDs (`@okhdfcbank`, `@paytm`), bank account numbers, and private Telegram invite links.
- **🗣️ Adversarial Hinglish Scam Slang NLP**: Catches coded scam jargon: *"rocket calls"*, *"pakka jackpot"*, *"zero-loss setup"*, *"kal subah 9:15"*, *"paisa double"*, *"loss recovery"*.
- **🛡️ Anti-Prompt-Injection Security Envelope**: Detects adversarial jailbreaks and flags tampering as an immediate fraud indicator.

### Stage 6: SEBI Registry Cross-Check (`src/stages/stage6_registry.py`)
- Cross-checks claimed advisor name and registration numbers against SEBI database using token-sort RapidFuzz matching.
- Employs an in-memory TTL cache with file-mtime awareness for sub-2ms response times.

### Stage 7: OCR Text Extraction (`src/stages/stage7_ocr.py`)
- Uses EasyOCR (Hindi + English) on image uploads and video keyframes.
- Reads profit P&L screenshots, fake SEBI registration certificates, and WhatsApp tip forward images.

### Stage 8: SEBI SCORES Complaint Drafting (`src/stages/stage8_report.py`)
- Automatically compiles forensic findings into a standardized SEBI SCORES 2.0 formal complaint draft ready for copy-paste or download.

### Stage 9: APK Metadata & Phishing Domain Scanner (`src/stages/stage9_apk_domain.py`)
- **Android APK Parser**: Dissects `.apk` files using `androguard` to audit dangerous permissions (`READ_SMS`, `BIND_ACCESSIBILITY_SERVICE`) and detect typo-squatted package names.
- **Two-Pass Phishing Domain Detector**: Extracts and analyzes URLs against `broker_apk_whitelist.json` using brand-token substring matching and Levenshtein edit distance.
- **SEBI 6-Signal Multi-Factor Matrix**:
  1. `explicit_returns` (30% weight): "guaranteed 40% monthly"
  2. `implied_returns` (20% weight): "quit your 9-to-5 job"
  3. `urgency_scarcity` (15% weight): "only 10 seats left, act now"
  4. `social_proof` (10% weight): "10,000 members making crores"
  5. `paywall_push` (10% weight): "join my VIP private Telegram"
  6. `credential_misrep` (15% weight): "SEBI approved jackpot analyst"

### Stage 6: SEBI Registry Cross-Check (`src/stages/stage6_registry.py`)
- Evaluates claimed advisor names and registration numbers (`IN[A-Z0-9]{8,14}`) against `static_data/sebi_registry.json`.
- Uses **RapidFuzz `token_sort_ratio`** for typo-tolerant fuzzy matching (0ms local latency).

### Stage 7: OCR Screenshot Extractor (`src/stages/stage7_ocr.py`)
- Uses **EasyOCR** (Hindi + English) to extract text from fake P&L trading screenshots, forged SEBI certificates, and WhatsApp chat forwards.

### Stage 8: SEBI SCORES Complaint Generator (`src/stages/stage8_report.py`)
- Dynamically formats an official legal draft containing Case ID, respondent details, violated SEBI regulations (IA Regulations 2013, PFUTP 2003), evidentiary quotes, forensic confidence metrics, and statutory relief sought.

---

## 📱 4. Why Do Low-Quality Phone Videos Get Flagged? (Crucial Hackathon Defense)

### The Problem:
When you upload a low-quality video recorded on a smartphone or forwarded over WhatsApp, deepfake vision models sometimes give false positives (flagging real videos as fake).

### The 4 Technical Reasons:
1. **WhatsApp H.264 Compression (DCT Blocks)**: WhatsApp heavily compresses video into 8x8 Discrete Cosine Transform (DCT) pixel blocks. High-pass SRM filters misinterpret these sharp block boundaries as GAN generation artifacts.
2. **Camera Sensor Noise & High ISO**: Low-end phones in indoor/dim lighting produce high sensor noise (grainy footage) which triggers the frequency stream.
3. **Motion Blur & Low Shutter Speed**: When a phone moves, shutter blur makes face boundaries inconsistent across frames, mimicking face-swap edge blending.
4. **Compressed Audio Codecs (AAC/Opus)**: Phone microphones with room reverb and WhatsApp audio compression cut high-frequency phase harmonics, making natural voice look truncated to Wav2Vec2.

### How FinGuard Handles This (Our Solution):
- **Temporal Variance & Consensus**: We do not rely on a single noisy frame. We average across 15 adaptive frames.
- **Multi-Modal Triangulation**: A video is never classified as a full scam based on vision alone. If the speech content is 100% compliant and registry-verified, FinGuard suppresses false alarms.

---

## 💾 5. Saved Files & Storage Architecture (Data Privacy)

| Path / Folder | Description | Lifecycle & Privacy |
|---|---|---|
| `temp/<job_id>/input.mp4` | Temporary uploaded video/audio file. | **Auto-purged instantly**: Isolated in a unique UUID folder (`temp/<job_id>`) and destroyed in `finally: shutil.rmtree()` upon scan completion. |
| `temp/<job_id>/frame_X.jpg` | Extracted MTCNN face crops (up to 15 frames). | **Auto-purged instantly** as soon as the vision stage finishes. |
| `temp/<job_id>/audio.wav` | Extracted 16kHz mono audio track. | **Auto-purged instantly** after audio classification. |
| `static_data/sebi_registry.json` | Master offline database of SEBI registered entities. | **Permanent local asset** for 0ms offline fuzzy matching. |
| `tests/test_results.csv` | Benchmark evaluation metrics output. | **Test artifact** for reporting accuracy and VRAM metrics. |
| `app.py` -> `/api/jobs/<job_id>/complaint` | Plain-text SEBI SCORES Complaint Draft. | **On-demand export** streamed to the user with zero database persistence. |

---

## 📁 6. Repository File Map

```
fintech/
├── app.py                          # ⭐ Main FastAPI Server (Web Dashboard + All APIs)
├── config.yaml                     # ⚙️ Master Configuration (Thresholds, Model IDs, GPU)
├── requirements.txt                # 📦 Python Dependencies
├── README.md                       # 📖 Quick Start Guide
├── DOCUMENTATION.md                # 📚 Full Technical Deep-Dive
├── HACKATHON_GUIDE.md              # 🏆 Master Presentation & Judge Defense Guide
├── TEAM_ONBOARDING_GUIDE.md        # 📘 Complete Team Guide (This File)
│
├── src/                            # 🧠 Core Backend Engine
│   ├── config.py                   # Settings & YAML Loader
│   ├── model.py                    # PyTorch Hybrid Deepfake Architecture (SRM + EfficientNet)
│   ├── backup_api.py               # Sightengine Cloud Fallback
│   └── stages/                     # 🔬 8-Stage Modular Forensic Pipeline
│       ├── stage1_ingest.py        # Video Ingest, Adaptive Sampling, MTCNN Face Crop
│       ├── stage2_vision.py        # Dual-Stream Vision & Viseme Mouth Motion
│       ├── stage3_audio.py         # Wav2Vec2 Audio Spoof & Impersonation Detection
│       ├── stage4_transcription.py # faster-whisper int8 Speech-to-Text
│       ├── stage5_llm.py           # SEBI LLM + DPDP Act PII Masker + Hinglish NLP
│       ├── stage6_registry.py      # RapidFuzz SEBI Intermediary Registry Matching
│       ├── stage7_ocr.py           # EasyOCR Image Text Extraction
│       └── stage8_report.py        # SEBI SCORES Complaint Generator
│
├── static/index.html               # 🎨 Glassmorphic Dark-Mode Frontend Dashboard
├── static_data/sebi_registry.json  # 📊 Offline SEBI Intermediary Registry Database
├── extension/                      # 🧩 Chrome Extension (Manifest V3)
├── scripts/                        # 🛠️ Verification, Benchmark & Model Downloader Tools
│   ├── download_models.py          # Pre-download all models to local cache
│   ├── verify_all_models.py        # Benchmark VRAM & latency for all models
│   ├── run_folder_test.py          # Batch evaluate a folder of test videos
│   └── generate_sample.py          # Generate synthetic test video
├── test_vid/                       # 🎬 Demo Video Samples (scam_vid / noscam_vid)
├── dataset/                        # 📁 Reference Benchmark Datasets (DeepfakeTIMIT)
├── tests/                          # 🧪 Test Verification Suite & CSV Output
│   ├── test_verification.py        # 6-Point Automated System Verification Test
│   └── test_results.csv            # Batch Evaluation CSV
└── temp/                           # ⏳ Ephemeral Runtime Scratchpad (Auto-purged)
```

---

## ⚡ 7. Quick Start: How to Run & Test

### Step 1: Activate Virtual Environment
Open terminal in `c:\Users\sarth\Desktop\fintech`:
```powershell
.venv\Scripts\activate
```

### Step 2: Verify All Models & Dependencies
Run the automated 6-point verification test:
```powershell
python tests/test_verification.py
```
*(You should see `ALL SYSTEM CHECKS PASSED! SYSTEM READY FOR DEMO & JUDGING`)*

### Step 3: Start the FinGuard Application
```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
Open your browser and navigate to: **`http://127.0.0.1:8000`**

### Step 4: Run Batch Folder Test (Optional Benchmark)
```powershell
python scripts/run_folder_test.py --folder test_vid --out tests/test_results.csv
```

---

## 🎬 8. Live Demo Presentation Checklist (30-Second Flow)

1. **Text Scan Demo**:
   - Paste a sample scam message containing a phone number, UPI ID, and *"Kal subah 9:15 pe rocket calls aayenge, 100% pakka jackpot guarantee"*.
   - **Point out to judges**:
     - 🛡️ **`[DPDP Act 2023 Shield Active]`** badge showing PII was masked locally before LLM reasoning.
     - 🗣️ **Gold Hinglish Slang Chips** detecting *"rocket calls"*, *"pakka jackpot"*.
     - ⚖️ **SEBI SCORES Complaint Draft** generated in 1 click.
2. **Video Scan Demo**:
   - Click **`▶ Try demo scan`** on the Video tab or upload a video from `test_vid/scam_vid/`.
   - **Point out to judges**:
     - Real-time 7-stage visual pipeline stepper.
     - Spatial + Frequency SRM Saliency Energy Heatmap.
     - Timeline Risk Scrubber (click any bar to jump to the transcript).
     - RapidFuzz SEBI Intermediary Registry check (*"Registration number NOT FOUND"*).
     - 📥 **`[Download Report (.txt)]`** button for filing with SEBI SCORES.

---

## 🎯 9. Top 5 Judge Questions & Winning Answers

#### Q1: "Why run models locally instead of using OpenAI / cloud APIs?"
> **Answer**: *"Three critical reasons: **1) Data Privacy & DPDP Act 2023**: Financial videos and P&L screenshots contain sensitive PII that cannot leave the enterprise perimeter. **2) Zero Inference Cost**: A broker processing 100,000 affiliate videos/month would pay massive API bills. FinGuard runs with zero token costs on commodity GPUs (e.g. RTX 4050). **3) Air-Gapped Operation**: Our system works 100% offline with our local SEBI registry."*

#### Q2: "How do you detect AI voice clones if the video has high background noise?"
> **Answer**: *"We apply acoustic normalization (DC offset elimination and peak scaling) before passing 5-second chunks to our fine-tuned Wav2Vec2 classifier. We also evaluate cross-modal viseme mouth-motion tracking to detect desynchronization between spoken audio and lip movements."*

#### Q3: "What happens if a scammer uses coded slang to bypass keywords?"
> **Answer**: *"We built a dedicated Adversarial Hinglish Slang Engine trained on actual Indian market fraud jargon ('rocket calls', 'zero-loss setup', 'nifty blast', 'pakka jackpot'). Our 6-factor LLaMA 3.1 compliance matrix flags the composite intent even when the creator avoids explicit words."*

#### Q4: "How does the SEBI Registry lookup work without internet?"
> **Answer**: *"We maintain a local indexed database (`static_data/sebi_registry.json`) of SEBI-registered Investment Advisers and Research Analysts. We use RapidFuzz `token_sort_ratio` to execute sub-millisecond fuzzy matching against claimed advisor names and alphanumeric registration numbers (`INA...`)."*

#### Q5: "How does FinGuard comply with India's DPDP Act 2023?"
> **Answer**: *"We enforce a strict zero-retention ephemeral storage lifecycle. All temporary video frames and audio chunks are isolated in a UUID-scoped sandbox (`temp/<job_id>`) and automatically purged in a `finally:` block. All PII (PAN, Aadhaar, phone, UPI) is masked before LLM processing."*
