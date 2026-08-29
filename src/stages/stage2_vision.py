import os
import gc
import io
import base64
import torch
import cv2
from PIL import Image
from torchvision import transforms
import numpy as np

from src.config import get_device, get_stage_config, get_vision_config

def estimate_mouth_region_motion(frame_paths: list) -> float:
    """
    Estimates optical motion and edge variance in the mouth region (viseme area).
    Synthetic lip-sync / reenactment overlays (Wav2Lip, DeepFaceLive) often show
    localized boundary blending jitter or unnatural stillness compared to full-face dynamics.
    """
    if len(frame_paths) < 2:
        return 0.0
    mouth_diffs = []
    prev_mouth = None
    for p in frame_paths:
        if not os.path.exists(p):
            continue
        img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        h, w = img.shape
        # Lower third center is the mouth region (y: 60%-95%, x: 25%-75%)
        mouth = img[int(h * 0.60):int(h * 0.95), int(w * 0.25):int(w * 0.75)]
        mouth = cv2.resize(mouth, (64, 48))
        if prev_mouth is not None:
            diff = float(np.mean(cv2.absdiff(mouth, prev_mouth)))
            mouth_diffs.append(diff)
        prev_mouth = mouth
    if not mouth_diffs:
        return 0.0
    return float(np.mean(mouth_diffs))

def generate_srm_heatmap_base64(image_path: str, model) -> str:
    """
    Generates a color-mapped forensic noise residual heatmap for explainability.
    Highlights facial regions with high-frequency GAN synthesis artifacts.
    Returns a data URI string (data:image/jpeg;base64,...).
    """
    try:
        orig_img = cv2.imread(image_path)
        if orig_img is None:
            return ""

        orig_h, orig_w = orig_img.shape[:2]

        # Pass through SRM layer in model
        rgb_img = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
        tensor_img = transforms.ToTensor()(Image.fromarray(rgb_img)).unsqueeze(0)

        device = next(model.parameters()).device
        tensor_img = tensor_img.to(device)

        with torch.no_grad():
            srm_out = model.srm(tensor_img).squeeze(0).cpu().numpy()

        # Calculate residual energy map across the 3 SRM filters
        residual_energy = np.mean(np.abs(srm_out), axis=0)
        norm_map = cv2.normalize(residual_energy, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        norm_map = cv2.resize(norm_map, (orig_w, orig_h))

        # Apply Jet colormap (Blue=Natural texture, Red=Anomalous high-frequency synthesis noise)
        heatmap = cv2.applyColorMap(norm_map, cv2.COLORMAP_JET)

        # Blend with original image
        blended = cv2.addWeighted(orig_img, 0.6, heatmap, 0.4, 0)

        # Encode to base64 JPEG
        _, buffer = cv2.imencode('.jpg', blended, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        b64_str = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_str}"
    except Exception as e:
        print(f"[EXPLAINABILITY] Failed to generate heatmap: {e}")
        return ""

def run_stage2_vision(face_frames_paths: list, job_id: str):
    """
    Runs the vision deepfake detection model on the extracted face frames.
    Uses HybridDeepfakeDetector (EfficientNet-B4 + Xception SRM) and cross-modal mouth activity tracking.
    Returns:
        dict: {
            "avg_score": float,
            "max_score": float,
            "peak_frame": str or None,
            "temporal_variance": float,
            "mouth_motion_activity": float,
            "heatmap_base64": str or None
        }
    """
    print(f"[{job_id}] Running Stage 2: Vision Deepfake Detection (with Spatial+Frequency SRM Forensics)")
    stage_config = get_stage_config("stage2_vision")
    vision_cfg = get_vision_config()
    device = "cpu" if stage_config.get("use_cpu") else get_device()
    model_id = stage_config.get("model_id", "AdityaManojShinde/deepfake-detector")
    model_weights_file = stage_config.get("model_weights_file", "deepfake_detector_phase2.pth")
    early_exit_frames = vision_cfg.get("early_exit_frame_count", 4)
    early_exit_score = vision_cfg.get("early_exit_score", 0.92)
    consensus_weight = vision_cfg.get("consensus_top_weight", 0.65)
    consensus_min_frames = vision_cfg.get("consensus_min_frames", 3)

    result = {
        "avg_score": 0.0,
        "max_score": 0.0,
        "peak_frame": None,
        "temporal_variance": 0.0,
        "mouth_motion_activity": 0.0,
        "heatmap_base64": None
    }

    if not face_frames_paths:
        print(f"[{job_id}] No face frames provided. Skipping vision stage.")
        return result

    try:
        # Cross-modal mouth motion dynamics (Viseme analysis)
        result["mouth_motion_activity"] = estimate_mouth_region_motion(face_frames_paths)

        print(f"[{job_id}] Loading Vision Model: {model_id} on {device}...")

        if "AdityaManojShinde" in model_id:
            try:
                from src.model import HybridDeepfakeDetector
            except ImportError:
                from model import HybridDeepfakeDetector
            from huggingface_hub import hf_hub_download

            model = HybridDeepfakeDetector()
            weights_path = hf_hub_download(repo_id=model_id, filename=model_weights_file)
            model.load_state_dict(torch.load(weights_path, map_location=device))
            model = model.to(device)
            model.eval()

            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])

            is_hybrid = True
        else:
            from transformers import AutoImageProcessor, AutoModelForImageClassification
            processor = AutoImageProcessor.from_pretrained(model_id)
            model = AutoModelForImageClassification.from_pretrained(model_id).to(device)
            model.eval()
            is_hybrid = False

        scores = []
        best_frame = None
        max_s = -1.0
        early_exit_triggered = False

        print(f"[{job_id}] Processing {len(face_frames_paths)} frames (early-exit at {early_exit_frames} consecutive frames >{early_exit_score:.2f})...")
        consecutive_high = 0
        for frame_path in face_frames_paths:
            if not os.path.exists(frame_path):
                continue

            img = Image.open(frame_path).convert("RGB")

            if is_hybrid:
                inputs = transform(img).unsqueeze(0).to(device)
                with torch.no_grad():
                    prob_real = model(inputs).item()
                    # Model outputs 1 for real, 0 for fake
                    fake_prob = max(0.0, min(1.0, 1.0 - prob_real))
            else:
                inputs = processor(images=img, return_tensors="pt").to(device)
                with torch.no_grad():
                    outputs = model(**inputs)
                    probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                    fake_index = 1
                    if model.config.id2label:
                        for k, v in model.config.id2label.items():
                            if "fake" in v.lower() or "spoof" in v.lower():
                                fake_index = k
                                break
                    fake_prob = probs[0, fake_index].item()

            scores.append(fake_prob)

            if fake_prob > max_s:
                max_s = fake_prob
                best_frame = frame_path

            # Early-exit: N consecutive high-confidence frames → no need to process more
            if fake_prob > early_exit_score:
                consecutive_high += 1
                if consecutive_high >= early_exit_frames:
                    print(f"[{job_id}] Early-exit triggered after {len(scores)} frames (score {fake_prob:.3f} > {early_exit_score}).")
                    early_exit_triggered = True
                    break
            else:
                consecutive_high = 0

        if scores:
            scores_sorted = sorted(scores, reverse=True)
            k = min(3, len(scores_sorted))
            top_k_mean = float(np.mean(scores_sorted[:k]))
            anti_weight = round(1.0 - consensus_weight, 4)
            # Temporal consensus smoothing; bypassed on early-exit (use raw peak instead)
            if early_exit_triggered:
                consensus_score = float(max_s)
            else:
                consensus_score = float(consensus_weight * top_k_mean + anti_weight * max_s) if len(scores) >= consensus_min_frames else float(max_s)

            result["avg_score"] = float(np.mean(scores))
            result["max_score"] = consensus_score
            result["raw_peak_score"] = float(max_s)
            result["peak_frame"] = best_frame
            result["temporal_variance"] = float(np.var(scores))

            # Generate Explainability Saliency Heatmap for the most suspicious frame
            if is_hybrid and best_frame and os.path.exists(best_frame):
                result["heatmap_base64"] = generate_srm_heatmap_base64(best_frame, model)

        print(f"[{job_id}] Vision complete. Calibrated Score: {result['max_score']:.4f} (Peak: {max_s:.4f}), Avg: {result['avg_score']:.4f}, Mouth Motion: {result['mouth_motion_activity']:.2f}")

    except Exception as e:
        print(f"[{job_id}] Vision stage failed locally: {e}")
        # Try cloud fallback if enabled in config.yaml
        try:
            from src.backup_api import check_sightengine_deepfake
            if face_frames_paths:
                cloud_res = check_sightengine_deepfake(face_frames_paths[0])
                if cloud_res:
                    print(f"[{job_id}] Cloud fallback succeeded (Sightengine): {cloud_res['score']:.4f}")
                    result["max_score"] = cloud_res["score"]
                    result["avg_score"] = cloud_res["score"]
                    result["peak_frame"] = face_frames_paths[0]
                    result["backup_provider"] = "sightengine"
        except Exception as cloud_err:
            print(f"[{job_id}] Cloud fallback failed: {cloud_err}")
    finally:
        # Crucial for VRAM budget: delete model and empty cache
        if 'model' in locals():
            del model
        if 'processor' in locals():
            del processor
        if 'inputs' in locals():
            del inputs
        if 'outputs' in locals():
            del outputs

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    return result
