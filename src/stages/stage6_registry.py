import os
import json
import re
from rapidfuzz import process, fuzz

from src.config import get_stage_config

def run_stage6_registry(sebi_analysis: dict, job_id: str):
    """
    Cross-checks the claimed advisor name and registration number against the local SEBI registry.
    Supports exact registration matching, alias matching, and fuzzy name matching.
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
        # Valid SEBI IA/RA/Broker starts with INA/INH/INZ followed by alphanumeric
        clean_reg_no = claimed_reg_no.upper().replace(" ", "").replace("-", "").strip()
        if not re.match(r"^IN[A-Z0-9]{8,14}$", clean_reg_no):
            result["verdict"] = "malformed number"
            print(f"[{job_id}] Verdict: Malformed registration number format: {claimed_reg_no}")
            return result
        claimed_reg_no = clean_reg_no
            
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
        matched_entity = next((item for item in registry if item.get("registration_number", "").upper() == claimed_reg_no), None)
        
        if matched_entity:
            # Number exists, check if name or any alias matches (fuzzy)
            if claimed_name:
                possible_names = [matched_entity.get("name", "")] + matched_entity.get("aliases", [])
                best_score = max(
                    [fuzz.token_sort_ratio(claimed_name.lower(), p.lower()) for p in possible_names if p],
                    default=0
                )
                if best_score > 65:
                    result["verdict"] = "verified"
                    result["matched_entity"] = matched_entity
                    print(f"[{job_id}] Verdict: Verified (Match score: {best_score})")
                else:
                    result["verdict"] = "name-number mismatch"
                    print(f"[{job_id}] Verdict: Name-Number Mismatch. Registered to {matched_entity.get('name')}, claimed {claimed_name}.")
            else:
                result["verdict"] = "verified"
                result["matched_entity"] = matched_entity
                print(f"[{job_id}] Verdict: Verified (Number only).")
            return result
        else:
            result["verdict"] = "not found"
            print(f"[{job_id}] Verdict: Registration number {claimed_reg_no} not found in registry.")
            return result
            
    # Check by Name or Aliases (fuzzy search)
    if claimed_name:
        candidates = []
        for item in registry:
            if item.get("name"):
                candidates.append((item["name"], item))
            for alias in item.get("aliases", []):
                candidates.append((alias, item))
                
        if not candidates:
            result["verdict"] = "not found"
            return result
            
        candidate_strings = [c[0] for c in candidates]
        best_match = process.extractOne(claimed_name, candidate_strings, scorer=fuzz.token_sort_ratio)
        
        if best_match and best_match[1] >= 80: # 80% threshold for aliases & full names
            matched_tuple = next((c for c in candidates if c[0] == best_match[0]), None)
            matched_entity = matched_tuple[1] if matched_tuple else None
            result["verdict"] = "verified"
            result["matched_entity"] = matched_entity
            print(f"[{job_id}] Verdict: Verified by Name/Alias '{best_match[0]}' (Score: {best_match[1]}). Entity: {matched_entity.get('name')}")
        else:
            result["verdict"] = "not found"
            print(f"[{job_id}] Verdict: Name '{claimed_name}' not found in registry. Best match was '{best_match[0] if best_match else 'None'}' ({best_match[1] if best_match else 0}%).")
            
    return result
