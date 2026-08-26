import argparse
import os
import gc
import cv2
import torch
import torchaudio
from facenet_pytorch import MTCNN
from torchvision import transforms
from transformers import (
    AutoFeatureExtractor, 
    AutoModelForAudioClassification
)
from PIL import Image
from model import HybridDeepfakeDetector
import librosa
import numpy as np

def print_vram(stage_name):
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / (1024 ** 3)
        reserved = torch.cuda.memory_reserved() / (1024 ** 3)
        print(f"[VRAM] {stage_name}: Allocated: {allocated:.2f} GB | Reserved: {reserved:.2f} GB")
    else:
        print(f"[VRAM] {stage_name}: CUDA not available.")

def extract_audio_from_video(video_path, audio_out_path):
    from moviepy import VideoFileClip
    print(f"Extracting audio from {video_path}...")
    try:
        video = VideoFileClip(video_path)
        if video.audio is not None:
            video.audio.write_audiofile(audio_out_path, logger=None)
            video.close()
            return True
        else:
            print("No audio track found in video.")
            video.close()
            return False
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False

def _process_single_frame(frame, mtcnn, transform, vision_model, device):
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(frame_rgb)
    
    boxes, probs = mtcnn.detect(pil_img)
    
    if boxes is not None and len(boxes) > 0:
        max_score = 0
        for box in boxes:
            x1, y1, x2, y2 = [int(b) for b in box]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(pil_img.width, x2), min(pil_img.height, y2)
            
            if x2 <= x1 or y2 <= y1:
                continue
                
            face_crop = pil_img.crop((x1, y1, x2, y2))
            
            inputs = transform(face_crop).unsqueeze(0).to(device)
            with torch.no_grad():
                prob_real = vision_model(inputs).item()
                # Model outputs 1 for real, 0 for fake. Fake probability is 1 - prob_real
                score = 1.0 - prob_real
                
                if score > max_score:
                    max_score = score
        return max_score if max_score > 0 else None
    return None

def vision_phase(file_path, is_image=False):
    print("\n--- Starting Vision Phase ---")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # 1. Initialize Face Detector (MTCNN)
    print("Loading MTCNN...")
    mtcnn = MTCNN(keep_all=False, select_largest=True, device=device)
    print_vram("After loading MTCNN")
    
    # 2. Initialize Vision Model
    print("Loading Hybrid Vision Model (EfficientNet-B4 + Xception)...")
    vision_model = HybridDeepfakeDetector()
    try:
        # Load the downloaded weights from cache or local path
        from huggingface_hub import hf_hub_download
        weights_path = hf_hub_download(repo_id="AdityaManojShinde/deepfake-detector", filename="deepfake_detector_phase2.pth")
        vision_model.load_state_dict(torch.load(weights_path, map_location=device))
    except Exception as e:
        print(f"Failed to load weights. Did you run download_models.py? Error: {e}")
        
    vision_model = vision_model.to(device)
    vision_model.eval()
    
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    print_vram("After loading Vision Model")
    
    # 3. Process Video Frames (1 FPS) or Image
    fake_scores = []
    
    if is_image:
        print("Extracting and scoring face from image...")
        frame = cv2.imread(file_path)
        if frame is not None:
            score = _process_single_frame(frame, mtcnn, transform, vision_model, device)
            if score is not None:
                fake_scores.append(score)
        else:
            print("Failed to open image.")
    else:
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0 or not cap.isOpened():
            print("Failed to open video.")
            return None
        
        frame_interval = 1 # EVERY SINGLE FRAME
        frame_count = 0
        
        print("Extracting and scoring EVERY frame (Max Accuracy)...")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_count % frame_interval == 0:
                score = _process_single_frame(frame, mtcnn, transform, vision_model, device)
                if score is not None:
                    fake_scores.append(score)
                        
            frame_count += 1
    
        cap.release()
    
    # Use the MAXIMUM score across all frames. 
    # If even one frame clearly shows a deepfake artifact, the video is a deepfake.
    avg_fake_score = np.max(fake_scores) if fake_scores else None
    if avg_fake_score is not None:
        print(f"Vision Phase Average Fake Score: {avg_fake_score:.4f}")
    else:
        print("No faces detected in video.")

    # 4. EXPLICIT VRAM FLUSH
    print("Flushing VRAM...")
    del mtcnn
    del vision_model
    del transform
    if 'inputs' in locals(): del inputs
    if 'outputs' in locals(): del outputs
    
    gc.collect()
    torch.cuda.empty_cache()
    print_vram("After Vision Flush")
    
    return avg_fake_score

def vision_phase_frames(frame_paths):
    print("\n--- Starting Vision Phase (Frames) ---")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    print("Loading MTCNN...")
    mtcnn = MTCNN(keep_all=False, select_largest=True, device=device)
    
    print("Loading Hybrid Vision Model (EfficientNet-B4 + Xception)...")
    vision_model = HybridDeepfakeDetector()
    try:
        from huggingface_hub import hf_hub_download
        weights_path = hf_hub_download(repo_id="AdityaManojShinde/deepfake-detector", filename="deepfake_detector_phase2.pth")
        vision_model.load_state_dict(torch.load(weights_path, map_location=device))
    except Exception as e:
        print(f"Failed to load weights: {e}")
        
    vision_model = vision_model.to(device)
    vision_model.eval()
    
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    fake_scores = []
    for file_path in frame_paths:
        frame = cv2.imread(file_path)
        if frame is not None:
            score = _process_single_frame(frame, mtcnn, transform, vision_model, device)
            if score is not None:
                fake_scores.append(score)
    
    avg_fake_score = np.max(fake_scores) if fake_scores else None
    
    del mtcnn
    del vision_model
    del transform
    gc.collect()
    torch.cuda.empty_cache()
    
    return avg_fake_score


def audio_phase(audio_path):
    print("\n--- Starting Audio Phase ---")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print_vram("Before Audio Load")
    
    # Initialize Audio Model
    audio_model_name = "MelodyMachine/Deepfake-Audio-Detection-V2"
    print(f"Loading Audio Model ({audio_model_name})...")
    
    try:
        feature_extractor = AutoFeatureExtractor.from_pretrained(audio_model_name)
        audio_model = AutoModelForAudioClassification.from_pretrained(audio_model_name).to(device)
        audio_model.eval()
        print_vram("After loading Audio Model")
        
        # Load and resample audio
        target_sr = feature_extractor.sampling_rate
        speech_array, sr = librosa.load(audio_path, sr=target_sr)
        
        # Chunk audio to prevent dilution of deepfake artifacts (3-second chunks)
        chunk_size = target_sr * 3
        chunks = [speech_array[i:i+chunk_size] for i in range(0, len(speech_array), chunk_size)]
        
        max_audio_score = 0
        for chunk in chunks:
            if len(chunk) < target_sr: # Skip very short tail chunks
                continue
                
            inputs = feature_extractor(chunk, sampling_rate=target_sr, return_tensors="pt").to(device)
            
            # Inference
            with torch.no_grad():
                outputs = audio_model(**inputs)
                logits = outputs.logits
                probs_softmax = torch.nn.functional.softmax(logits, dim=-1)
                
                id2label = audio_model.config.id2label
                fake_id = next((k for k, v in id2label.items() if 'fake' in v.lower() or 'spoof' in v.lower()), 0)
                     
                score = probs_softmax[0][fake_id].item()
                if score > max_audio_score:
                    max_audio_score = score
                    
        audio_fake_score = max_audio_score if max_audio_score > 0 else None
            
        print(f"Audio Phase Max Fake Score: {audio_fake_score:.4f}")
        
    except Exception as e:
        print(f"Audio phase failed: {e}")
        audio_fake_score = None

    # EXPLICIT VRAM FLUSH
    print("Flushing VRAM...")
    if 'audio_model' in locals(): del audio_model
    if 'feature_extractor' in locals(): del feature_extractor
    if 'inputs' in locals(): del inputs
    if 'outputs' in locals(): del outputs
    gc.collect()
    torch.cuda.empty_cache()
    print_vram("After Audio Flush")
    
    return audio_fake_score

def main():
    parser = argparse.ArgumentParser(description="Phase 1 Deepfake Detection Scanner")
    parser.add_argument("--input", type=str, required=True, help="Path to input video (.mp4, .avi, .mov) or image (.jpg, .png)")
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"File not found: {args.input}")
        return
        
    print(f"=== Starting Deepfake Scan for {args.input} ===")
    print_vram("Initial State")
    is_image = args.input.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))
    
    has_audio = False
    if not is_image:
        audio_temp_path = "temp_audio.wav"
        has_audio = extract_audio_from_video(args.input, audio_temp_path)
    
    vision_score = vision_phase(args.input, is_image)
    
    audio_score = None
    if has_audio:
        audio_score = audio_phase(audio_temp_path)
        if os.path.exists(audio_temp_path):
             os.remove(audio_temp_path)
             
    print("\n=== FINAL RESULTS ===")
    if vision_score is not None:
        print(f"Vision Fake Probability: {vision_score:.2%}")
    if audio_score is not None:
        print(f"Audio Fake Probability:  {audio_score:.2%}")
        
    if vision_score is not None and audio_score is not None:
        combined_score = max(vision_score, audio_score)
        print(f"Combined Deepfake Score: {combined_score:.2%} (Max of modalities)")
    elif vision_score is not None:
        print(f"Combined Deepfake Score: {vision_score:.2%} (Vision only)")
    elif audio_score is not None:
        print(f"Combined Deepfake Score: {audio_score:.2%} (Audio only)")
    else:
        print("Scan failed to produce a score.")

if __name__ == "__main__":
    main()
