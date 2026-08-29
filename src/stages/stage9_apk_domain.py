"""
Stage 9: APK Metadata Parser & Phishing Domain / Typo-Squatting Detector

Addresses Problem Statement #7's third detection vector:
  (a) Deepfake media        — covered by Stage 2 (vision)
  (b) Impersonation text    — covered by Stage 5 (LLM) + Stage 3 (audio)
  (c) Fake trading-app indicators — THIS STAGE

Two capabilities:
  1. APK scanner  : Inspects .apk package metadata for deceptive package names and
                    dangerous permissions using androguard.
  2. URL scanner  : Detects typo-squatting / phishing domains using Levenshtein
                    distance against a whitelist of SEBI-registered broker domains.
"""

import os
import re
import json
from typing import Optional

from src.config import get_stage_config, get_threshold, settings

# ── Whitelist helpers ────────────────────────────────────────────────────────

def _load_whitelist() -> list:
    stage_cfg = get_stage_config("stage9_apk_domain")
    whitelist_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        stage_cfg.get("apk_whitelist", "static_data/broker_apk_whitelist.json")
    )
    if not os.path.exists(whitelist_path):
        return []
    with open(whitelist_path, "r", encoding="utf-8") as f:
        return json.load(f)

def _get_canonical_packages(whitelist: list) -> list[tuple[str, str]]:
    """Returns [(package_name, broker_name), ...]"""
    result = []
    for entry in whitelist:
        for pkg in entry.get("package_names", []):
            result.append((pkg.lower(), entry["broker"]))
    return result

def _get_canonical_domains(whitelist: list) -> list[tuple[str, str]]:
    """Returns [(domain, broker_name), ...]"""
    result = []
    for entry in whitelist:
        for domain in entry.get("domains", []):
            result.append((domain.lower(), entry["broker"]))
    return result

# ── Levenshtein distance ─────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    """Standard dynamic programming edit-distance implementation."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = curr
    return prev[-1]

# ── URL extraction ────────────────────────────────────────────────────────────

_URL_RE = re.compile(
    r"(?:https?://|www\.)"          # scheme or www
    r"([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,})"  # host
    r"(?:/[^\s]*)?"                  # optional path
)

def extract_urls_from_text(text: str) -> list[str]:
    """Extracts all URLs / domains found in free text (OCR output, transcripts, etc.)."""
    return [m.group(1).lower() for m in _URL_RE.finditer(text)]

# ── Domain scanner ────────────────────────────────────────────────────────────

def scan_domain(url_or_domain: str, job_id: str = "manual") -> dict:
    """
    Checks a single URL or domain for typo-squatting against the SEBI broker whitelist.

    Returns:
        dict: {
            "input": str,
            "is_phishing": bool,
            "risk_level": "high" | "medium" | "low" | "clean",
            "matched_legitimate_domain": str or None,
            "legitimate_broker": str or None,
            "levenshtein_distance": int or None,
            "reason": str
        }
    """
    max_dist = get_threshold("apk_domain_levenshtein_max_dist", 3)
    whitelist = _load_whitelist()
    canonical_domains = _get_canonical_domains(whitelist)

    # Strip scheme / path — work on hostname only
    clean = url_or_domain.lower().strip()
    clean = re.sub(r"^https?://", "", clean)
    clean = re.sub(r"^www\.", "", clean)
    clean = clean.split("/")[0].strip()

    result = {
        "input": url_or_domain,
        "normalised_host": clean,
        "is_phishing": False,
        "risk_level": "clean",
        "matched_legitimate_domain": None,
        "legitimate_broker": None,
        "levenshtein_distance": None,
        "reason": "Domain not recognised as a broker typo-squatter."
    }

    # Exact match → legitimate
    for domain, broker in canonical_domains:
        if clean == domain:
            result["risk_level"] = "clean"
            result["matched_legitimate_domain"] = domain
            result["legitimate_broker"] = broker
            result["reason"] = f"Exact match: legitimate {broker} domain."
            print(f"[{job_id}] Domain '{clean}' → legitimate {broker}")
            return result

    # ── Pass 1: Brand keyword substring check ─────────────────────────
    # Scammers embed the real brand name inside a longer fake domain:
    # e.g., "groww-bonus-login.xyz" contains "groww"
    # Extract the "brand token" from each canonical domain and check if it
    # appears inside the suspicious hostname.
    clean_base = clean.rsplit(".", 1)[0] if "." in clean else clean   # strip TLD

    for domain, broker in canonical_domains:
        domain_base = domain.rsplit(".", 1)[0] if "." in domain else domain
        # Brand token = first word of domain base (before any dot or hyphen)
        brand_token = re.split(r"[-.]", domain_base)[0]
        if len(brand_token) >= 4 and brand_token in clean_base and clean != domain:
            # Contains the brand name but is NOT the real domain → phishing
            dist = _levenshtein(clean_base, domain_base)
            result["is_phishing"] = True
            result["risk_level"] = "high"
            result["matched_legitimate_domain"] = domain
            result["legitimate_broker"] = broker
            result["levenshtein_distance"] = dist
            result["reason"] = (
                f"PHISHING DETECTED: '{clean}' contains the brand keyword '{brand_token}' "
                f"from legitimate '{domain}' ({broker}) — classic impersonation pattern."
            )
            print(f"[{job_id}] ⚠ Brand-keyword phishing: '{clean}' contains '{brand_token}' ({broker})")
            return result

    # ── Pass 2: Levenshtein edit-distance on base hostname ────────────
    # Catches direct typo-squats like "zerodhaa.com" (one extra char)
    best_dist = 999
    best_domain = None
    best_broker = None

    for domain, broker in canonical_domains:
        domain_base = domain.rsplit(".", 1)[0] if "." in domain else domain
        dist = _levenshtein(clean_base, domain_base)
        if dist < best_dist:
            best_dist = dist
            best_domain = domain
            best_broker = broker

    result["levenshtein_distance"] = best_dist
    result["matched_legitimate_domain"] = best_domain
    result["legitimate_broker"] = best_broker

    if 0 < best_dist <= max_dist:
        result["is_phishing"] = True
        result["risk_level"] = "high" if best_dist == 1 else "medium"
        result["reason"] = (
            f"TYPO-SQUATTING DETECTED: '{clean}' is only {best_dist} character(s) "
            f"from legitimate '{best_domain}' ({best_broker}). "
            f"Probable phishing / impersonation domain."
        )
        print(f"[{job_id}] ⚠ Phishing domain detected: '{clean}' → '{best_domain}' (dist={best_dist})")
    else:
        result["risk_level"] = "low"
        result["reason"] = f"Domain not similar enough to any registered broker domain (best dist={best_dist})."

    return result


def scan_text_for_phishing_domains(text: str, job_id: str = "manual") -> dict:
    """
    Extracts all URLs from arbitrary text and scans each for typo-squatting.

    Returns:
        dict: {
            "urls_found": list[str],
            "flagged_domains": list[dict],
            "any_phishing": bool
        }
    """
    urls = extract_urls_from_text(text)
    flagged = []
    for url in urls:
        r = scan_domain(url, job_id)
        if r["is_phishing"]:
            flagged.append(r)

    return {
        "urls_found": urls,
        "flagged_domains": flagged,
        "any_phishing": len(flagged) > 0
    }


# ── APK scanner ───────────────────────────────────────────────────────────────

def scan_apk(apk_path: str, job_id: str = "manual") -> dict:
    """
    Inspects an Android APK for:
      - Deceptive package names (typo-squatting against known broker APKs)
      - Dangerous permission combinations indicative of financial fraud malware

    Returns:
        dict: {
            "package_name": str or None,
            "version_name": str or None,
            "app_name": str or None,
            "is_suspicious": bool,
            "risk_level": "high" | "medium" | "low" | "clean",
            "dangerous_permissions": list[str],
            "package_typosquat": dict or None,
            "permission_flags": list[str],
            "reason": str
        }
    """
    stage_cfg = get_stage_config("stage9_apk_domain")
    dangerous_perms = set(stage_cfg.get("dangerous_permissions", [
        "READ_SMS", "RECEIVE_SMS", "READ_CONTACTS",
        "BIND_ACCESSIBILITY_SERVICE", "PACKAGE_USAGE_STATS"
    ]))
    max_dist = get_threshold("apk_domain_levenshtein_max_dist", 3)
    whitelist = _load_whitelist()
    canonical_packages = _get_canonical_packages(whitelist)

    result = {
        "package_name": None,
        "version_name": None,
        "app_name": None,
        "is_suspicious": False,
        "risk_level": "clean",
        "dangerous_permissions": [],
        "package_typosquat": None,
        "permission_flags": [],
        "reason": "No issues detected."
    }

    if not os.path.exists(apk_path):
        result["reason"] = f"APK file not found: {apk_path}"
        return result

    try:
        from androguard.misc import AnalyzeAPK
        a, d, dx = AnalyzeAPK(apk_path)

        pkg = (a.get_package() or "").lower()
        version = a.get_androidversion_name() or "unknown"
        app_name = a.get_app_name() or "unknown"
        permissions = set(p.split(".")[-1].upper() for p in (a.get_permissions() or []))

        result["package_name"] = pkg
        result["version_name"] = version
        result["app_name"] = app_name

        print(f"[{job_id}] APK: package={pkg}, version={version}, app={app_name}")
        print(f"[{job_id}] Permissions declared: {len(permissions)}")

        # 1. Exact package match → legitimate
        for known_pkg, broker in canonical_packages:
            if pkg == known_pkg:
                result["risk_level"] = "clean"
                result["reason"] = f"Exact package match: legitimate {broker} app ({pkg})."
                return result

        # 2. Package name typo-squatting
        pkg_base = pkg.rsplit(".", 1)[-1] if "." in pkg else pkg
        best_dist = 999
        best_known = None
        best_broker = None

        for known_pkg, broker in canonical_packages:
            known_base = known_pkg.rsplit(".", 1)[-1] if "." in known_pkg else known_pkg
            dist = _levenshtein(pkg_base, known_base)
            if dist < best_dist:
                best_dist = dist
                best_known = known_pkg
                best_broker = broker

        if 0 < best_dist <= max_dist:
            result["package_typosquat"] = {
                "input_package": pkg,
                "closest_legitimate": best_known,
                "broker": best_broker,
                "levenshtein_distance": best_dist
            }
            result["is_suspicious"] = True
            result["risk_level"] = "high"
            print(f"[{job_id}] ⚠ Package typo-squat: '{pkg}' → '{best_known}' ({best_broker}) dist={best_dist}")

        # 3. Dangerous permissions check
        found_dangerous = list(permissions & dangerous_perms)
        result["dangerous_permissions"] = found_dangerous

        if found_dangerous:
            result["is_suspicious"] = True
            result["permission_flags"] = [
                f"DANGEROUS: android.permission.{p}" for p in found_dangerous
            ]
            if result["risk_level"] != "high":
                result["risk_level"] = "medium"
            print(f"[{job_id}] ⚠ Dangerous permissions found: {found_dangerous}")

        # Compose reason
        reasons = []
        if result["package_typosquat"]:
            reasons.append(
                f"Package name '{pkg}' is a suspected typo-squat of "
                f"'{best_known}' ({best_broker}) — edit distance {best_dist}."
            )
        if found_dangerous:
            reasons.append(
                f"Declares {len(found_dangerous)} dangerous permission(s): "
                f"{', '.join(found_dangerous)}."
            )
        result["reason"] = " | ".join(reasons) if reasons else "No significant issues detected."

    except ImportError:
        # androguard not installed — graceful fallback
        result["reason"] = (
            "androguard not installed. Install via: pip install androguard. "
            "APK analysis skipped."
        )
        print(f"[{job_id}] androguard not available — APK scan skipped.")
    except Exception as e:
        result["reason"] = f"APK analysis failed: {e}"
        print(f"[{job_id}] APK scan error: {e}")

    return result


# ── Stage entry-point ─────────────────────────────────────────────────────────

def run_stage9_apk_domain(
    job_id: str,
    apk_path: Optional[str] = None,
    url: Optional[str] = None,
    ocr_text: Optional[str] = None
) -> dict:
    """
    Unified Stage 9 entry-point. Accepts any combination of:
      - apk_path : path to an uploaded .apk file
      - url      : a single URL/domain string to check
      - ocr_text : free-form text (from Stage 7 OCR) to extract + scan URLs from

    Returns:
        dict: {
            "apk_result": dict or None,
            "url_result": dict or None,
            "ocr_domain_result": dict or None,
            "any_threat_detected": bool,
            "stage": "stage9_apk_domain"
        }
    """
    print(f"[{job_id}] Running Stage 9: APK & Phishing Domain Scanner")

    result = {
        "apk_result": None,
        "url_result": None,
        "ocr_domain_result": None,
        "any_threat_detected": False,
        "stage": "stage9_apk_domain"
    }

    if apk_path:
        result["apk_result"] = scan_apk(apk_path, job_id)
        if result["apk_result"].get("is_suspicious"):
            result["any_threat_detected"] = True

    if url:
        result["url_result"] = scan_domain(url, job_id)
        if result["url_result"].get("is_phishing"):
            result["any_threat_detected"] = True

    if ocr_text:
        result["ocr_domain_result"] = scan_text_for_phishing_domains(ocr_text, job_id)
        if result["ocr_domain_result"].get("any_phishing"):
            result["any_threat_detected"] = True

    print(
        f"[{job_id}] Stage 9 complete. Threats: {'YES' if result['any_threat_detected'] else 'none'}"
    )
    return result
