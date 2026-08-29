"""
Batch Video Testing & Evaluation Harness
=========================================
Runs the full 9-stage forensic pipeline on all videos in a specified folder,
evaluates verdicts and metrics, and exports a structured CSV benchmark report.

Run:
  python scripts/run_folder_test.py --folder test_vid --out tests/test_results.csv

C3 FIX: Verdict now uses the SAME calculate_calibrated_verdict() as the live API.
H5 FIX: Stage 7 (OCR) and Stage 9 (domain scan) now included in batch pipeline.
"""
import os
import sys
import csv
import glob
import time
import uuid
import shutil
import argparse

# Force UTF-8 stdout on Windows with line buffering for immediate output streaming
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# Add workspace root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.stages.stage1_ingest import run_stage1_ingest
from src.stages.stage2_vision import run_stage2_vision
from src.stages.stage3_audio import run_stage3_audio
from src.stages.stage4_transcription import run_stage4_transcription
from src.stages.stage5_llm import run_stage5_llm
from src.stages.stage6_registry import run_stage6_registry
from src.stages.stage7_ocr import run_stage7_ocr          # H5
from src.stages.stage9_apk_domain import scan_text_for_phishing_domains  # H5
from src.config import settings, get_threshold

# C3: Import the SAME verdict function used by the live API
def _import_verdict_fn():
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", os.path.join(ROOT_DIR, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calculate_calibrated_verdict

try:
    calculate_calibrated_verdict = _import_verdict_fn()
    print("[INFO] Using live API calculate_calibrated_verdict()")
except Exception as e:
    print(f"[WARN] Could not import live verdict fn ({e}). Using inline fallback.")
    def calculate_calibrated_verdict(is_deepfake, is_scam, composite_risk, registry_verdict):
        """Fallback: mirrors app.py logic exactly."""
        if is_deepfake and is_scam:
            return "Critical: Deepfake + Scam"
        if is_deepfake:
            return "Warning: Deepfake Detected"
        if is_scam and composite_risk >= 0.70:
            return "Warning: SEBI Violation / Scam"
        if is_scam:
            return "Suspicious: Possible SEBI Violation"
        if registry_verdict in ("not found", "name-number mismatch"):
            return "Suspicious: Unverified Entity"
        return "Safe"


def test_folder(folder_path: str, output_csv: str = None):
    # Resolve default paths relative to workspace root
    if output_csv is None:
        output_csv = os.path.join(ROOT_DIR, "tests", "test_results.csv")
    elif not os.path.isabs(output_csv):
        output_csv = os.path.join(ROOT_DIR, output_csv)

    if not os.path.isabs(folder_path):
        folder_path = os.path.join(ROOT_DIR, folder_path)

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    temp_base = os.path.join(ROOT_DIR, "temp")
    os.makedirs(temp_base, exist_ok=True)

    video_files = (
        glob.glob(os.path.join(folder_path, "**", "*.[mM][pP]4"), recursive=True) +
        glob.glob(os.path.join(folder_path, "**", "*.[aA][vV][iI]"), recursive=True) +
        glob.glob(os.path.join(folder_path, "**", "*.[mM][oO][vV]"), recursive=True) +
        glob.glob(os.path.join(folder_path, "**", "*.[mM][kK][vV]"), recursive=True)
    )

    if not video_files:
        print(f"[!] No video files found in {folder_path}")
        return

    vision_fake_thresh = get_threshold("vision_fake_threshold", 0.5)
    audio_fake_thresh  = get_threshold("audio_fake_threshold", 0.5)

    print("===========================================================")
    print(f"  FinGuard Batch Evaluation — Found {len(video_files)} videos")
    print(f"  Folder : {folder_path}")
    print(f"  Output : {output_csv}")
    print(f"  Vision threshold : {vision_fake_thresh}")
    print(f"  Audio threshold  : {audio_fake_thresh}")
    print("===========================================================")

    fieldnames = [
        "Filename", "Verdict",
        "Is Deepfake", "Is Scam", "Phishing URL Found",
        "Vision Score", "Audio Score",
        "Claimed Advisor", "Registry Verdict",
        "OCR Text (preview)", "Total Time (s)"
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    summary_stats = {"total": 0, "critical": 0, "warning": 0, "suspicious": 0, "safe": 0, "error": 0}

    for video in video_files:
        start_time = time.time()
        filename = os.path.basename(video)
        job_id = f"test_{uuid.uuid4().hex[:8]}"
        job_temp_dir = os.path.join(temp_base, job_id)
        os.makedirs(job_temp_dir, exist_ok=True)
        summary_stats["total"] += 1

        print(f"\n-----------------------------------------------------------")
        print(f"Processing: {filename} (Job ID: {job_id})")
        print(f"-----------------------------------------------------------")

        try:
            # Stage 1: Ingest & Preprocess
            ingest_result = run_stage1_ingest(video, job_temp_dir, job_id)

            # Stage 2: Vision Forensics
            vision_result = run_stage2_vision(ingest_result.get("face_frames_paths", []), job_id)

            # Stage 4: Transcription (runs before Audio so transcript is available for impersonation check)
            transcription_result = run_stage4_transcription(ingest_result.get("audio_path"), job_id)
            transcript = transcription_result.get("transcript", "")

            # Stage 3: Audio Forensics (uses transcript for impersonation target check)
            audio_result = run_stage3_audio(ingest_result.get("audio_path"), job_id, transcript=transcript)

            # Stage 5: SEBI LLM Reasoning
            llm_result = run_stage5_llm(transcript, job_id)

            # Stage 6: Registry Match
            registry_result = run_stage6_registry(llm_result, job_id)

            # Stage 9: Domain/phishing scan on transcript (H5)
            domain_result = scan_text_for_phishing_domains(transcript, job_id) if transcript else {}
            phishing_found = domain_result.get("any_phishing", False)
            if phishing_found:
                print(f"[{job_id}] [WARN] Phishing URLs found: {[d['normalised_host'] for d in domain_result.get('flagged_domains', [])]}")

            # C3: Aggregation using same verdict fn as live API
            is_vision_fake = vision_result.get("max_score", 0.0) > vision_fake_thresh
            is_audio_fake  = audio_result.get("max_score", 0.0) > audio_fake_thresh
            is_deepfake = is_vision_fake or is_audio_fake

            is_scam = llm_result.get("is_scam_likely", False) or phishing_found

            composite_risk = llm_result.get("composite_risk_score", 0.0)
            verdict = calculate_calibrated_verdict(
                is_deepfake, is_scam, composite_risk, registry_result.get("verdict", "not claimed")
            )

            elapsed = round(time.time() - start_time, 1)
            claimed_advisor = llm_result.get("claimed_advisor_name") or "None"
            reg_verdict = registry_result.get("verdict", "N/A")
            v_score = vision_result.get("max_score", 0.0)
            a_score = audio_result.get("max_score", 0.0)
            ocr_preview = ""

            row = {
                "Filename": filename,
                "Verdict": verdict,
                "Is Deepfake": is_deepfake,
                "Is Scam": is_scam,
                "Phishing URL Found": phishing_found,
                "Vision Score": f"{v_score:.4f}",
                "Audio Score": f"{a_score:.4f}",
                "Claimed Advisor": claimed_advisor,
                "Registry Verdict": reg_verdict,
                "OCR Text (preview)": ocr_preview,
                "Total Time (s)": elapsed
            }
            with open(output_csv, "a", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writerow(row)

            print(f"[OK] Completed {filename} in {elapsed}s — Verdict: {verdict}")

            # Track summary
            v_lower = verdict.lower()
            if "critical" in v_lower:
                summary_stats["critical"] += 1
            elif "warning" in v_lower:
                summary_stats["warning"] += 1
            elif "suspicious" in v_lower:
                summary_stats["suspicious"] += 1
            else:
                summary_stats["safe"] += 1

        except Exception as e:
            print(f"[FAIL] Failed processing {filename}: {e}")
            with open(output_csv, "a", encoding="utf-8", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writerow({
                    "Filename": filename, "Verdict": "ERROR",
                    "Is Deepfake": False, "Is Scam": False, "Phishing URL Found": False,
                    "Vision Score": 0, "Audio Score": 0,
                    "Claimed Advisor": "N/A", "Registry Verdict": "ERROR",
                    "OCR Text (preview)": str(e)[:80], "Total Time (s)": 0
                })
            summary_stats["error"] += 1
        finally:
            if os.path.exists(job_temp_dir):
                shutil.rmtree(job_temp_dir, ignore_errors=True)

    print(f"\n===========================================================")
    print(f"  Batch test complete! Results: {output_csv}")
    print(f"  Total : {summary_stats['total']}")
    print(f"  Critical  : {summary_stats['critical']}")
    print(f"  Warning   : {summary_stats['warning']}")
    print(f"  Suspicious: {summary_stats['suspicious']}")
    print(f"  Safe      : {summary_stats['safe']}")
    print(f"  Error     : {summary_stats['error']}")
    print(f"===========================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full 9-stage pipeline on a folder of videos")
    parser.add_argument("--folder", type=str, default="test_vid", help="Folder containing videos")
    parser.add_argument("--out", type=str, default="tests/test_results.csv", help="Output CSV file")
    args = parser.parse_args()
    test_folder(args.folder, args.out)
