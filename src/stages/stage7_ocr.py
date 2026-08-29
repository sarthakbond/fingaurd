import gc
import torch
from PIL import Image
import numpy as np

from src.config import get_device, get_threshold

def run_stage7_ocr(image_path: str, job_id: str):
    """
    Extracts text from an image using EasyOCR (Hindi + English).
    Designed for scam screenshots: fake profit P&Ls, edited SEBI certificates,
    WhatsApp forwards, and Telegram channel screenshots.
    Returns:
        dict: {
            "extracted_text": str,
            "avg_confidence": float,
            "text_blocks": list[dict]  # {"text": str, "confidence": float, "bbox": list}
        }
    """
    print(f"[{job_id}] Running Stage 7: OCR Text Extraction (EasyOCR)")
    
    result = {
        "extracted_text": "",
        "avg_confidence": 0.0,
        "text_blocks": []
    }
    
    if not image_path:
        print(f"[{job_id}] No image path provided. Skipping OCR stage.")
        return result
    
    reader = None
    try:
        import easyocr
        
        device = get_device()
        use_gpu = device == "cuda" and torch.cuda.is_available()
        
        print(f"[{job_id}] Loading EasyOCR reader (en+hi) on {'GPU' if use_gpu else 'CPU'}...")
        reader = easyocr.Reader(['en', 'hi'], gpu=use_gpu, verbose=False)
        
        print(f"[{job_id}] Extracting text from image...")
        ocr_results = reader.readtext(image_path, detail=1, paragraph=False)
        
        all_texts = []
        confidences = []
        
        ocr_min_conf = get_threshold("ocr_min_confidence", 0.15)
        for (bbox, text, conf) in ocr_results:
            if conf < ocr_min_conf:  # Skip very low confidence noise (from config)
                continue
            text_clean = text.strip()
            if not text_clean:
                continue
                
            all_texts.append(text_clean)
            confidences.append(conf)
            result["text_blocks"].append({
                "text": text_clean,
                "confidence": round(float(conf), 3),
                "bbox": [[int(p) for p in point] for point in bbox]
            })
        
        result["extracted_text"] = " ".join(all_texts)
        result["avg_confidence"] = round(float(np.mean(confidences)), 3) if confidences else 0.0
        
        print(f"[{job_id}] OCR complete. Extracted {len(all_texts)} text blocks, avg confidence: {result['avg_confidence']:.3f}")
        
    except ImportError:
        print(f"[{job_id}] easyocr not installed. Run: pip install easyocr")
    except Exception as e:
        print(f"[{job_id}] OCR stage failed: {e}")
    finally:
        if reader is not None:
            del reader
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    return result
