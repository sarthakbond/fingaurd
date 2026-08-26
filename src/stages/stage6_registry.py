import os
import json
import re
from rapidfuzz import process, fuzz

from src.config import get_stage_config

def run_stage6_registry(sebi_analysis: dict, job_id: str):
    """
    Cross-checks the claimed advisor name and registration number against the local SEBI registry.
    Returns:
        dict: {
            "verdict": "verified" | "not found" | "malformed number" | "name-number mismatch" | "not claimed",
            "matched_entity": dict or None
        }
    """
    print(f"[{job_id}] Running Stage 6: SEBI Registrant Cross-check")
    stage_config = get_stage_config("stage6_registry")
    source_file = os.path.join(os.path.dirname(__file__), "..", "..", stage_config.get("source", "static_data/sebi_registry.json"))
    
    result = {
        "verdict": "not claimed",
        "matched_entity": None
    }
    
    claimed_name = sebi_analysis.get("claimed_advisor_name")
    claimed_reg_no = sebi_analysis.get("claimed_registration_number")
    
    if not claimed_name and not claimed_reg_no:
        print(f"[{job_id}] No advisor claims made. Skipping registry check.")
        return result
        
    print(f"[{job_id}] Checking claim - Name: {claimed_name}, Reg No: {claimed_reg_no}")
    
    if claimed_reg_no:
        # Valid SEBI IA number starts with INA followed by 9 digits (usually)
        # We use a broad regex just to check format sanity
        if not re.match(r"^IN[A-Z0-9]{8,12}$", claimed_reg_no.upper().strip()):
            result["verdict"] = "malformed number"
            print(f"[{job_id}] Verdict: Malformed registration number.")
            return result
            
    # Load Registry
    if not os.path.exists(source_file):
        print(f"[{job_id}] Warning: Registry file not found at {source_file}. Cannot verify.")
        result["verdict"] = "not found"
        return result
        
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except Exception as e:
        print(f"[{job_id}] Failed to load registry: {e}")
        return result
        
    # Check by Registration Number (Strongest check)
    if claimed_reg_no:
        clean_reg_no = claimed_reg_no.upper().strip()
        matched_entity = next((item for item in registry if item.get("registration_number", "").upper() == clean_reg_no), None)
        
        if matched_entity:
            # Number exists, check if name matches (fuzzy)
            if claimed_name:
                score = fuzz.token_sort_ratio(claimed_name.lower(), matched_entity.get("name", "").lower())
                if score > 70:
                    result["verdict"] = "verified"
                    result["matched_entity"] = matched_entity
                    print(f"[{job_id}] Verdict: Verified (Match score: {score})")
                else:
                    result["verdict"] = "name-number mismatch"
                    print(f"[{job_id}] Verdict: Name-Number Mismatch. Registered to {matched_entity.get('name')}, claimed {claimed_name}.")
            else:
                # Number exists and no name claimed to contradict it
                result["verdict"] = "verified"
                result["matched_entity"] = matched_entity
                print(f"[{job_id}] Verdict: Verified (Number only).")
            return result
        else:
            # Number not in registry
            result["verdict"] = "not found"
            print(f"[{job_id}] Verdict: Registration number not found in registry.")
            return result
            
    # Check by Name only (fuzzy search)
    if claimed_name:
        names = [item.get("name") for item in registry if item.get("name")]
        if not names:
            result["verdict"] = "not found"
            return result
            
        best_match = process.extractOne(claimed_name, names, scorer=fuzz.token_sort_ratio)
        if best_match and best_match[1] > 85: # High threshold for name-only matches
            matched_entity = next((item for item in registry if item.get("name") == best_match[0]), None)
            result["verdict"] = "verified"
            result["matched_entity"] = matched_entity
            print(f"[{job_id}] Verdict: Verified by Name (Score: {best_match[1]}).")
        else:
            result["verdict"] = "not found"
            print(f"[{job_id}] Verdict: Name not found in registry. Best match was {best_match[0] if best_match else 'None'} ({best_match[1] if best_match else 0}).")
            
    return result
