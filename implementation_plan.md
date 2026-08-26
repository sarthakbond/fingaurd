# Phase 1: SEBI-Compliant Deepfake Detection Pipeline

This plan outlines the architecture and implementation strategy for building a highly memory-efficient Deepfake Detection pipeline, tailored specifically for inference on an NVIDIA RTX 4050 (6GB VRAM) and ready for deployment to serve a browser extension.

## User Review Required

> [!IMPORTANT]
> **Payload Strategy for the Browser Extension**
> We need to decide how the extension will send videos to the backend. Sending full 50MB videos via `POST` will cause massive lag and timeouts.
> 
> **Option A (URL Passing)**: The extension sends just the video URL to the API (e.g., `{"url": "https://..."}`). The server downloads the video locally, processes it, and deletes it.
> **Option B (Frame Extraction)**: The extension uses JavaScript to extract 3-5 frames locally in the browser, and only sends those lightweight images to the API.
>
> **Which option do you prefer?** Option A is easier to build on the extension side, but Option B is much faster and cheaper for your backend bandwidth and GPU processing.

## Proposed Pipeline Architecture

1. **API & Ingestion**:
   - FastAPI server with `CORSMiddleware` enabled (to allow the Chrome extension to communicate with it).
   - Endpoints modified to support the chosen Payload Strategy (URL vs Frames).
2. **Vision Phase (Optimized)**:
   - Use `AdityaManojShinde/deepfake-detector` (a hybrid EfficientNet-B4 + Xception model).
   - This model is explicitly designed for deepfakes, uses transfer learning, and outputs a simple Sigmoid probability score (0 = fake, 1 = real).
   - Since it's a `.pth` state dict, we will define the `HybridDeepfakeDetector` PyTorch class using `timm` and load the weights.
3. **Memory Flush**: Aggressively clear VRAM between Vision and Audio phases.
4. **Audio Phase**:
   - Run the audio track through the Acoustic Model (Wav2Vec 2.0 fine-tuned for spoofing/deepfakes).
5. **Fusion**: Combine the Vision and Audio scores to produce a final "Deepfake Probability Score".

## Execution Steps

### 1. Update Models Script
- Modify `download_models.py` to download the `deepfake_detector_phase2.pth` file from Hugging Face using `huggingface_hub.hf_hub_download`.

### 2. Update Vision Inference
- Create a `model.py` to house the `HybridDeepfakeDetector` PyTorch class.
- Update `phase1_scanner.py` to:
  - Load the custom model architecture instead of the ViT model.
  - Preprocess the images appropriately for EfficientNet/Xception (using standard ImageNet normalization: mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]).
  - Process the Sigmoid output (`prob = model(tensor).item()`), mapping it back to a standard "fake score".

### 3. Update FastAPI App
- Add `CORSMiddleware` to `app.py`.
- Depending on your answer to the Open Question, add a new endpoint or modify the existing one to accept URLs or pre-extracted frames.

## Verification Plan

### Automated/Manual Verification
- Run `python download_models.py` to ensure the new `.pth` file is retrieved.
- Scan a dummy image/video using `python phase1_scanner.py --input sample.jpg` to verify the hybrid model loads and predicts without OOM errors.
- Test the FastAPI endpoints using `curl` or Postman to verify CORS is active and payloads are processed correctly.
