# Phase 2: SEBI Compliance & Scam Detection

This plan outlines the architecture for transcribing video/audio content and analyzing it against SEBI (Securities and Exchange Board of India) guidelines to flag finfluencer scams, unregistered investment advice, and pump-and-dump schemes.

## User Review Required

> [!WARNING]
> **LLM Hosting Strategy (6GB VRAM Constraint)**
> We are already pushing your RTX 4050 (6GB) to its limits with the Vision and Audio Deepfake models. We now need a **Transcription model (Whisper)** and a **Reasoning model (LLM)** to read the text and apply SEBI rules.
> 
> We must decide how to run the Reasoning LLM:
> 
> * **Option A (Cloud API - Highly Recommended)**: We use a cloud API like **Groq** (free and blazing fast), **OpenAI**, or **Gemini**. This uses **0 VRAM** on your local machine, allowing Whisper to run easily, and provides vastly superior logic for interpreting complex SEBI guidelines.
> * **Option B (Local LLM via Ollama)**: We download a heavily compressed "tiny" LLM (like `Phi-3-Mini` 4-bit) to run locally. This will consume ~2.5GB VRAM, run slower, and might struggle with complex legal reasoning compared to a larger model.
> 
> **Which option do you prefer?** (If Option A, do you have an API key we can use, or should we use a free-tier provider like Groq/Google?)

## Proposed Architecture

1. **Transcription Phase (Whisper)**:
   - We will use OpenAI's `whisper` library (specifically the `base` or `tiny` model).
   - During the audio processing phase, we will transcribe the `temp.wav` file into a text string.
   - We will immediately clear Whisper from VRAM using our existing `torch.cuda.empty_cache()` flush system.

2. **SEBI System Prompting**:
   - We will create a strict persona prompt: *"You are a SEBI Regulatory Auditor..."*
   - We will embed the core SEBI rules into the prompt:
     - No specific security recommendations without RIA (Registered Investment Advisor) status.
     - No promises of "assured" or "guaranteed" returns.
     - Prohibition of pump-and-dump language.
   
3. **LLM Analysis Phase**:
   - The transcript is sent to the LLM (either Local or Cloud) along with the SEBI system prompt.
   - We will force the LLM to output a clean JSON response:
     ```json
     {
       "sebi_violation": true,
       "reasoning": "The speaker guarantees a 40% return on XYZ stock within one month, violating SEBI rules on assured returns.",
       "risk_score": 0.95
     }
     ```

4. **API Integration**:
   - We will update the `app.py` endpoints to include the `sebi_compliance` results in the final JSON response, alongside the `vision_score` and `audio_score`.

## Execution Steps
1. Wait for your decision on the LLM hosting strategy.
2. Install `openai-whisper` and the required LLM SDK (e.g., `groq`, `openai`, or `ollama`).
3. Create `phase2_sebi.py` to house the transcription and LLM logic.
4. Integrate `phase2_sebi.py` into `app.py`'s scanning endpoints.

## Verification
- We will test the system by submitting a video/audio clip of a fake "get rich quick" stock scheme to ensure the LLM correctly flags it as a SEBI violation.
