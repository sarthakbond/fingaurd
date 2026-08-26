import os
import requests
from src.config import settings, is_cloud_fallback_enabled

def check_sightengine_deepfake(image_path: str):
    """
    Backup cloud API integration with Sightengine for deepfake detection.
    Only triggers if 'backup_apis.enable_cloud_fallback' is true in config.yaml.
    Returns:
        dict or None: {
            "score": float, # 0.0 - 1.0 fake probability
            "is_fake": bool,
            "provider": "sightengine"
        }
    """
    if not is_cloud_fallback_enabled():
        return None
        
    api_user = os.getenv("SIGHTENGINE_API_USER")
    api_secret = os.getenv("SIGHTENGINE_API_SECRET")
    
    if not api_user or not api_secret:
        print("[BACKUP API] Sightengine credentials missing in .env. Skipping cloud fallback.")
        return None
        
    if not os.path.exists(image_path):
        return None
        
    try:
        models = settings.get("backup_apis", {}).get("sightengine", {}).get("models", "deepfake,genai")
        params = {
            "models": models,
            "api_user": api_user.strip(),
            "api_secret": api_secret.strip()
        }
        
        with open(image_path, "rb") as img_file:
            files = {"media": img_file}
            response = requests.post(
                "https://api.sightengine.com/1.0/check.json",
                files=files,
                data=params,
                timeout=10
            )
            
        if response.status_code == 200:
            data = response.json()
            # Parse deepfake/genai probability
            fake_score = 0.0
            if "type" in data and "deepfake" in data["type"]:
                fake_score = max(fake_score, data["type"]["deepfake"])
            if "type" in data and "ai_generated" in data["type"]:
                fake_score = max(fake_score, data["type"]["ai_generated"])
                
            return {
                "score": float(fake_score),
                "is_fake": fake_score > 0.5,
                "provider": "sightengine",
                "raw": data
            }
        else:
            print(f"[BACKUP API] Sightengine returned {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[BACKUP API] Sightengine query failed: {e}")
        return None
