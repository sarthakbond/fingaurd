import os
import gc
import torch
from PIL import Image
from torchvision import transforms
import numpy as np

from src.config import get_device, get_stage_config

def run_stage2_vision(face_frames_paths: list, job_id: str):
    """
    Runs the vision deepfake detection model on the extracted face frames.
    Uses HybridDeepfakeDetector (EfficientNet-B4 + Xception SRM) by default.
    Returns:
        dict: {
            "avg_score": float,
            "max_score": float,
            "peak_frame": str or None,
            "temporal_variance": float
        }
    """
    print(f"[{job_id}] Running Stage 2: Vision Deepfake Detection")
    stage_config = get_stage_config("stage2_vision")
    device = "cpu" if stage_config.get("use_cpu") else get_device()
    model_id = stage_config.get("model_id", "AdityaManojShinde/deepfake-detector")
    
    result = {
        "avg_score": 0.0,
        "max_score": 0.0,
        "peak_frame": None,
        "temporal_variance": 0.0
    }
    
    if not face_frames_paths:
        print(f"[{job_id}] No face frames provided. Skipping vision stage.")
        return result
        
    try:
        print(f"[{job_id}] Loading Vision Model: {model_id} on {device}...")
        
        if "AdityaManojShinde" in model_id:
            from model import HybridDeepfakeDetector
            from huggingface_hub import hf_hub_download
            
            model = HybridDeepfakeDetector()
            weights_path = hf_hub_download(repo_id="AdityaManojShinde/deepfake-detector", filename="deepfake_detector_phase2.pth")
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
        
        print(f"[{job_id}] Processing {len(face_frames_paths)} frames sequentially...")
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
                
        if scores:
            result["avg_score"] = float(np.mean(scores))
            result["max_score"] = float(max_s)
            result["peak_frame"] = best_frame
            result["temporal_variance"] = float(np.var(scores))
            
        print(f"[{job_id}] Vision complete. Max Fake Score: {max_s:.4f}, Avg: {result['avg_score']:.4f}")
        
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
