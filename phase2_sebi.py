import torch
import librosa
from transformers import WhisperProcessor, WhisperForConditionalGeneration
import ollama
import json
import gc

def transcribe_audio(audio_path):
    print("\n--- Starting SEBI Transcription Phase ---")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("Loading Whisper Model (openai/whisper-tiny)...")
    
    processor = WhisperProcessor.from_pretrained("openai/whisper-tiny")
    model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-tiny").to(device)
    
    # Load and resample audio to 16kHz
    try:
        speech_array, sr = librosa.load(audio_path, sr=16000)
    except Exception as e:
        print(f"Failed to load audio for transcription: {e}")
        return ""
        
    print("Transcribing audio...")
    inputs = processor(speech_array, sampling_rate=16000, return_tensors="pt").input_features.to(device)
    
    with torch.no_grad():
        predicted_ids = model.generate(inputs)
        
    transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
    print(f"Transcription complete. ({len(transcription)} chars)")
    
    # FLUSH VRAM
    del model
    del processor
    if 'inputs' in locals(): del inputs
    if 'predicted_ids' in locals(): del predicted_ids
    gc.collect()
    torch.cuda.empty_cache()
    
    return transcription

def analyze_sebi_compliance(transcript):
    if not transcript or len(transcript.strip()) < 10:
        return {
            "sebi_violation": False,
            "reasoning": "Transcript too short or empty.",
            "risk_score": 0.0
        }
        
    print("\n--- Starting SEBI LLM Analysis (Ollama) ---")
    system_prompt = """You are a strict Securities and Exchange Board of India (SEBI) Regulatory Compliance Auditor. Your task is to analyze financial influencer transcripts and flag any violations of SEBI regulations.

You must rigorously check for the following violations:
- Guaranteed Returns: Any promise of assured profits, risk-free income, or 100% accuracy.
- Unregistered Advice: Providing specific stock buy/sell calls or portfolio management without explicitly stating a valid SEBI Investment Advisor (IA) or Research Analyst (RA) registration number.
- Market Manipulation: Promoting pump-and-dump schemes, creating sudden hype around micro-cap stocks, or urging immediate, panic buying.
- Prohibited Superlatives: Using terms like "best", "No 1", or "top adviser" to build false authority.
- Misleading Testimonials: Showcasing specific monetary gains from clients or selectively reporting only winning trades.
- Gamification: Promoting trading leagues or competitions that offer prize money or gifts.

Analyze the transcript. You must output ONLY a valid JSON object matching this schema, with no other text or markdown:
{
    "sebi_violation": boolean,
    "reasoning": "A short, 1-2 sentence explanation of why it violates or complies with SEBI rules.",
    "risk_score": float (0.0 to 1.0, where 1.0 is a blatant scam/violation)
}"""

    try:
        response = ollama.chat(model='phi3', messages=[
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': f"Transcript:\n{transcript}"
            }
        ], format='json')
        
        result = json.loads(response['message']['content'])
        print("SEBI Analysis Complete.")
        return result
    except Exception as e:
        print(f"LLM Analysis failed: {e}")
        return {
            "sebi_violation": False,
            "reasoning": "Error analyzing transcript.",
            "risk_score": 0.0
        }
