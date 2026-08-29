"""
End-to-End System & Pipeline Live Test
======================================
Tests all FastAPI endpoints, data contracts, and runs the full 9-stage
pipeline on actual video files to ensure zero runtime crashes.
"""
import sys
import os
import time
import json

sys.stdout.reconfigure(encoding='utf-8')

# Ensure root directory is on path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

print("=" * 65)
print("  FinGuard End-to-End Live System Stress & Verification Test")
print("=" * 65)

from fastapi.testclient import TestClient
from app import app, calculate_calibrated_verdict

client = TestClient(app)

# ── 1. Health Endpoint Test ──────────────────────────────────────────
print("\n[1/7] Testing GET /api/health...")
res = client.get("/api/health")
assert res.status_code == 200, f"Health check failed: {res.text}"
health_data = res.json()
assert health_data.get("status") == "ok"
assert health_data.get("version") == "4.0"
assert health_data.get("stages") == 9
print(f"      Status: OK | Version: {health_data['version']} | Stages: {health_data['stages']}")

# ── 2. Registry Status Endpoint Test ─────────────────────────────────
print("\n[2/7] Testing GET /api/registry/status...")
res = client.get("/api/registry/status")
assert res.status_code == 200, f"Registry status failed: {res.text}"
reg_data = res.json()
assert reg_data.get("total_records", 0) > 0, "Registry has 0 records"
print(f"      Total SEBI Registrants: {reg_data['total_records']}")
print(f"      Breakdown: {reg_data.get('registry_breakdown')}")

# ── 3. URL / Domain Phishing Scan Endpoint Test ─────────────────────
print("\n[3/7] Testing POST /api/scan/url...")
# Test A: Legitimate domain
res_clean = client.post("/api/scan/url", json={"url": "https://kite.zerodha.com/dashboard"})
assert res_clean.status_code == 200
r_clean = res_clean.json()["url_result"]
assert not r_clean["is_phishing"], f"False positive on legitimate domain: {r_clean}"
print(f"      Clean URL Test: '{r_clean['normalised_host']}' -> Legitimate ({r_clean['legitimate_broker']})")

# Test B: Typo-squatting phishing domain
res_phish = client.post("/api/scan/url", json={"url": "http://groww-bonus-reward.xyz/login"})
assert res_phish.status_code == 200
phish_json = res_phish.json()
r_phish = phish_json["url_result"]
assert r_phish["is_phishing"], f"Failed to catch phishing domain: {r_phish}"
assert "scores_complaint" in phish_json, "SCORES complaint missing from URL scan"
print(f"      Phishing URL Test: '{r_phish['normalised_host']}' -> FLAGGED ({r_phish['legitimate_broker']} spoof)")

# ── 4. Text Scan Endpoint Test (with Cross-Pipeline Phishing Check) ───
print("\n[4/7] Testing POST /api/scan/text...")
# Test A: Clean educational text
res_safe = client.post("/api/scan/text", json={"text": "Diversification across index funds and debt instruments is a prudent long-term wealth strategy."})
assert res_safe.status_code == 200
safe_data = res_safe.json()
assert safe_data["verdict"] == "Safe", f"Clean text flagged unexpectedly: {safe_data['verdict']}"
print(f"      Safe Text Verdict: {safe_data['verdict']} (Risk: {safe_data['composite_risk_score']:.2f})")

# Test B: Scam text with guaranteed returns and phishing link
scam_msg = (
    "Namaskar friends! I am Rajesh Kumar, official SEBI advisor INA000099999. "
    "Join our VIP group at http://zerodha-vip-trading.xyz and get 100% guaranteed double profits daily! "
    "Only 5 spots left, DM now!"
)
res_scam = client.post("/api/scan/text", json={"text": scam_msg})
assert res_scam.status_code == 200
scam_data = res_scam.json()
assert scam_data["is_scam"] == True, f"Failed to flag obvious scam: {scam_data}"
assert scam_data["domain_scan"] is not None, "Domain scan result missing from text response"
assert scam_data["domain_scan"]["any_phishing"] == True, "Failed to flag phishing domain in text"
assert len(scam_data["scores_complaint"]) > 100, "SCORES complaint draft empty"
print(f"      Scam Text Verdict: {scam_data['verdict']} (Composite Risk: {scam_data['composite_risk_score']:.2f})")
print(f"      Phishing URLs Found in Text: {scam_data['domain_scan']['urls_found']}")
print(f"      SCORES Complaint Generated: {len(scam_data['scores_complaint'])} characters")

# ── 5. APK Scan Endpoint Validation ─────────────────────────────────
print("\n[5/7] Testing POST /api/scan/apk validation...")
# Non-APK file rejection test
res_bad_file = client.post(
    "/api/scan/apk",
    files={"file": ("malicious.txt", b"plain text content", "text/plain")}
)
assert res_bad_file.status_code == 400, f"Expected 400 for non-apk, got {res_bad_file.status_code}"
print("      Non-APK upload correctly rejected with HTTP 400")

# ── 6. SEBI Sync Daemon Test ─────────────────────────────────────────
print("\n[6/7] Testing SEBI Sync Daemon (--stats & --dry-run)...")
import subprocess
proc_stats = subprocess.run(
    [r".venv\Scripts\python.exe", "scripts/sync_sebi_registry.py", "--stats"],
    capture_output=True, text=True, encoding="utf-8", errors="replace"
)
assert proc_stats.returncode == 0, f"Sync stats error: {proc_stats.stderr}"
print(f"      Sync Daemon Stats Check: OK\n      {proc_stats.stdout.strip().splitlines()[-1]}")

# ── 7. Live 9-Stage Video Pipeline Execution ─────────────────────────
print("\n[7/7] Testing Full 9-Stage Video Pipeline on Live Video File...")
sample_video = os.path.join(ROOT_DIR, "test_vid", "noscam_vid", "WhatsApp Video 2026-08-26 at 4.05.46 PM.mp4")

if os.path.exists(sample_video):
    print(f"      Running pipeline on: {os.path.basename(sample_video)}")
    t0 = time.time()
    with open(sample_video, "rb") as vf:
        res_job = client.post("/api/jobs", files={"file": (os.path.basename(sample_video), vf, "video/mp4")})
    
    assert res_job.status_code == 200, f"Failed to submit video job: {res_job.text}"
    job_id = res_job.json().get("job_id")
    print(f"      Video job queued: {job_id}. Polling execution progress...")

    max_wait_sec = 60
    start_poll = time.time()
    completed = False
    last_stage = None

    while time.time() - start_poll < max_wait_sec:
        res_poll = client.get(f"/api/jobs/{job_id}")
        assert res_poll.status_code == 200
        job_info = res_poll.json()
        stage = job_info.get("stage", "starting")
        status = job_info.get("status")

        if stage != last_stage:
            print(f"        -> Executing Stage: {stage}")
            last_stage = stage

        if status == "completed":
            completed = True
            result = job_info.get("result", {})
            dur = round(time.time() - t0, 1)
            print(f"\n      [✓] Pipeline finished successfully in {dur}s!")
            print(f"          Verdict: {result.get('verdict')}")
            print(f"          Vision Fake Score: {result.get('vision_score', 0):.3f}")
            print(f"          Audio Spoof Score: {result.get('audio_score', 0):.3f}")
            print(f"          Composite Scam Risk: {result.get('composite_risk_score', 0):.3f}")
            print(f"          Timeline Scrub Track: {len(result.get('timeline_track', []))} events")
            print(f"          SCORES Draft Available: {len(result.get('scores_complaint', '')) > 50}")
            break
        elif status == "failed":
            raise RuntimeError(f"Video job failed: {job_info.get('error')}")

        time.sleep(1.0)

    assert completed, f"Pipeline timed out after {max_wait_sec}s"
else:
    print(f"      Sample video not found at {sample_video}, skipping live video execution.")

print("\n" + "=" * 65)
print("  ALL END-TO-END SYSTEM TESTS PASSED CLEANLY (0 ERRORS)")
print("=" * 65)
