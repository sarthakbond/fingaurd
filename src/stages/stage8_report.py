import datetime
from typing import Dict, Any

def generate_sebi_scores_complaint(data: Dict[str, Any], content_type: str = "Video") -> str:
    """
    Generates a structured, legally formatted complaint draft ready for submission
    to the SEBI Complaints Redress System (SCORES) portal / SEBI Enforcement Division.
    """
    now = datetime.datetime.now().strftime("%d-%B-%Y %H:%M:%S IST")
    sebi = data.get("sebi_analysis", {})
    registry = data.get("registry_check", {})
    
    claimed_name = sebi.get("claimed_advisor_name") or "Unspecified Entity / Finfluencer"
    claimed_reg = sebi.get("claimed_registration_number") or "None Disclosed"
    reg_verdict = registry.get("verdict", "not claimed").upper()
    
    is_deepfake = data.get("is_deepfake", False)
    vision_score = data.get("vision_score", 0.0)
    audio_score = data.get("audio_score", 0.0)
    risk_score = data.get("composite_risk_score", sebi.get("composite_risk_score", 0.0))
    verdict = data.get("verdict", "Suspicious Content")
    
    # Identify violated SEBI regulations
    violations = []
    return_quotes = sebi.get("specific_return_promises", [])
    implied_quotes = sebi.get("implied_returns", [])
    urgency_quotes = sebi.get("urgency_scarcity_language", [])
    paywall_quotes = sebi.get("paywall_push", [])
    cred_quotes = sebi.get("credential_misrepresentation", [])
    
    if return_quotes or implied_quotes:
        violations.append("• SEBI (Investment Advisers) Regulations, 2013 — Prohibition of guaranteed/assured return promises.")
    if reg_verdict in ["NOT FOUND", "NAME-NUMBER MISMATCH", "MALFORMED NUMBER"]:
        violations.append("• SEBI Act, 1992 Section 12(1) — Providing investment advice/research without valid SEBI registration.")
    if paywall_quotes:
        violations.append("• SEBI Master Circular on Social Media/Finfluencers — Unlawful monetization of unregistered financial advice via private channels.")
    if is_deepfake:
        violations.append("• SEBI (Prohibition of Fraudulent and Unfair Trade Practices) Regulations, 2003 (PFUTP) — Synthetically generated deepfake media used to deceive retail investors.")
    if not violations:
        violations.append("• Potential Deceptive Marketing & Misrepresentation under SEBI PFUTP Regulations.")

    # Format Evidence Section
    evidence_lines = []
    if return_quotes:
        evidence_lines.append(f"  [Guaranteed Return Claims]:\n" + "\n".join([f'    - "{q}"' for q in return_quotes]))
    if implied_quotes:
        evidence_lines.append(f"  [Implied Return Promises]:\n" + "\n".join([f'    - "{q}"' for q in implied_quotes]))
    if urgency_quotes:
        evidence_lines.append(f"  [Urgency & Pressure Tactics]:\n" + "\n".join([f'    - "{q}"' for q in urgency_quotes]))
    if paywall_quotes:
        evidence_lines.append(f"  [Unregistered Paid Channel Funnels]:\n" + "\n".join([f'    - "{q}"' for q in paywall_quotes]))
    if cred_quotes:
        evidence_lines.append(f"  [Credential Misrepresentation / Tampering]:\n" + "\n".join([f'    - "{q}"' for q in cred_quotes]))
        
    evidence_text = "\n\n".join(evidence_lines) if evidence_lines else "  No explicit verbal quotes extracted."

    complaint = f"""================================================================================
                    SECURITIES AND EXCHANGE BOARD OF INDIA (SEBI)
                 COMPLAINT LODGEMENT DRAFT — SCORES / MARKET SURVEILLANCE
================================================================================

DATE & TIME OF GENERATION : {now}
INVESTIGATION CASE ID    : FG-SCORES-{datetime.datetime.now().strftime("%Y%m%d")}-{data.get("scan_type", "AUDIT").upper()}
CLASSIFICATION VERDICT   : {verdict.upper()}
COMPOSITE FRAUD RISK     : {risk_score * 100:.1f}%

--------------------------------------------------------------------------------
1. RESPONDENT / SUSPECT DETAILS
--------------------------------------------------------------------------------
Name of Finfluencer / Entity : {claimed_name}
Claimed SEBI Reg. Number     : {claimed_reg}
SEBI Registry Status Check   : {reg_verdict}
Channel / Medium of Fraud    : Digital {content_type} (Social Media / Web Transmission)

--------------------------------------------------------------------------------
2. AI FORENSIC ANALYSIS SUMMARY
--------------------------------------------------------------------------------
• Visual Deepfake Probability : {vision_score * 100:.1f}% {"(SYNTHETIC FACE MANIPULATION DETECTED)" if vision_score > 0.5 else "(Within Normal Parameters)"}
• Audio Spoof Probability    : {audio_score * 100:.1f}% {"(SYNTHETIC VOICE CLONING DETECTED)" if audio_score > 0.5 else "(Within Normal Parameters)"}
• AI Forensic Analysis Notes  : {sebi.get("reasoning", "Evidence points to non-compliant financial advisory distribution.")}

--------------------------------------------------------------------------------
3. SPECIFIC SEBI REGULATION VIOLATIONS
--------------------------------------------------------------------------------
{chr(10).join(violations)}

--------------------------------------------------------------------------------
4. EXTRACTED FORENSIC EVIDENCE & VERBATIM TRANSCRIPT
--------------------------------------------------------------------------------
{evidence_text}

--------------------------------------------------------------------------------
5. RELIEF / REGULATORY ACTION SOUGHT
--------------------------------------------------------------------------------
1. Issue of directions under Section 11(1), 11(4) and 11B of the SEBI Act, 1992 restraining the respondent from accessing securities markets.
2. Immediate impounding and disgorgement of illicit advisory fees / subscription revenues collected through unauthorized payment funnels.
3. Referral to cyber crime units / MeitY for blocking synthetic media accounts and Telegram/WhatsApp distribution channels under the IT Act.

================================================================================
Report digitally signed by FinGuard Automated Forensic Engine v3.0
================================================================================
"""
    return complaint
