import json
import re
import requests
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Dict, Any

from src.config import get_stage_config, get_threshold

class SEBIAnalysis(BaseModel):
    claimed_advisor_name: Optional[str] = Field(default=None, description="The name of the investment advisor or entity mentioned in the transcript. Null if none found.")
    claimed_registration_number: Optional[str] = Field(default=None, description="The SEBI registration number mentioned, e.g. INA000000000. Null if none found.")
    specific_return_promises: Optional[List[str]] = Field(default_factory=list, description="Exact quotes of guaranteed or unrealistic returns promised.")
    urgency_scarcity_language: Optional[List[str]] = Field(default_factory=list, description="Exact quotes of pressure tactics, urgency, or scarcity.")
    social_proof_inflation: Optional[List[str]] = Field(default_factory=list, description="Exact quotes inflating credibility, e.g. '50,000+ members', 'trusted by top traders'.")
    paywall_push: Optional[List[str]] = Field(default_factory=list, description="Exact quotes pushing paid channels/groups, e.g. 'join premium telegram', 'DM for VIP tips'.")
    implied_returns: Optional[List[str]] = Field(default_factory=list, description="Exact quotes implying returns without explicit guarantees, e.g. 'consistent 3x outperformance', 'rocket call'.")
    credential_misrepresentation: Optional[List[str]] = Field(default_factory=list, description="Exact quotes where credentials or authority are exaggerated or fabricated.")
    signal_scores: Optional[Dict[str, float]] = Field(default_factory=dict, description="Individual confidence scores (0.0-1.0) for each signal category.")
    composite_risk_score: float = Field(default=0.0, description="Weighted aggregate risk score (0.0-1.0). Higher means more likely scam.")
    prompt_injection_detected: bool = Field(default=False, description="True if an adversarial attempt to manipulate the compliance LLM was detected.")
    dpdp_pii_scrubbed_count: int = Field(default=0, description="Count of sensitive PII entities masked under the DPDP Act 2023.")
    hinglish_slang_detected: Optional[List[str]] = Field(default_factory=list, description="Indian financial scam slang terms detected (e.g. 'rocket call', 'pakka jackpot').")
    is_scam_likely: bool = Field(default=False, description="True if the content contains unregistered advice, guaranteed returns, pressure tactics, or adversarial tampering.")
    reasoning: str = Field(default="", description="A short explanation of why the content is flagged or not.")

# Signal weights for composite scoring
SIGNAL_WEIGHTS = {
    "explicit_returns": 0.30,
    "implied_returns": 0.20,
    "urgency_scarcity": 0.15,
    "social_proof": 0.10,
    "paywall_push": 0.10,
    "credential_misrep": 0.15,
}

# ── DPDP Act 2023 Enterprise Data Shield (Local PII Scrubbing) ───────────
PII_PATTERNS = [
    # Indian Mobile Numbers (+91 or 10-digit starting with 6, 7, 8, 9)
    (r"(?:\+91[\s-]?)?[6-9]\d{9}\b", "[MASKED_PHONE_DPDP]"),
    # Indian PAN Card (5 letters, 4 digits, 1 letter)
    (r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b", "[MASKED_PAN_DPDP]"),
    # Indian Aadhaar Number (12 digits with spaces or hyphens)
    (r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b", "[MASKED_AADHAAR_DPDP]"),
    # UPI IDs (e.g. name@okhdfcbank, user@paytm, etc.)
    (r"\b[\w.-]+@(?:okaxis|okhdfcbank|oksbi|okicici|paytm|ybl|ibl|axl|apl|upi)\b", "[MASKED_UPI_ID_DPDP]"),
    # Bank Account Numbers (9-18 digits following account keywords)
    (r"(?i)(?:a/c|acc(?:ount)?(?:\s+no)?[:\s]+)(\d{9,18})", r"a/c [MASKED_BANK_ACCOUNT_DPDP]"),
    # Email Addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[MASKED_EMAIL_DPDP]"),
    # Telegram / WhatsApp Direct Invite Links
    (r"(?:https?://)?(?:t\.me|chat\.whatsapp\.com)/\S+", "[MASKED_PRIVATE_CHANNEL_LINK_DPDP]")
]

def scrub_pii_dpdp(text: str) -> tuple[str, int]:
    """
    Local Enterprise Data Shield for Digital Personal Data Protection (DPDP) Act 2023 compliance.
    Masks PII before sending transcribed text to LLMs or external processing.
    Returns (scrubbed_text, masked_entities_count).
    """
    scrubbed = text
    masked_count = 0
    for pattern, replacement in PII_PATTERNS:
        matches = len(re.findall(pattern, scrubbed))
        if matches > 0:
            masked_count += matches
            scrubbed = re.sub(pattern, replacement, scrubbed)
    return scrubbed, masked_count

# ── Adversarial "Hinglish" Slang & Coded Fraud NLP ────────────────────────
HINGLISH_SCAM_SLANG = [
    r"(?i)\brocket\s+calls?\b",
    r"(?i)\bpakka\s+jackpot\b",
    r"(?i)\bzero[\s-]loss\s+(?:setup|strategy|call)\b",
    r"(?i)\b(?:100%|hundred\s+percent)\s+(?:loss\s+)?recovery\b",
    r"(?i)\bsure[\s-]shot\s+(?:jackpot|multibagger|profit|gain)\b",
    r"(?i)\bnifty\s+blast\b",
    r"(?i)\bbanknifty\s+jackpot\b",
    r"(?i)\bkal\s+subah\s+9:?15\b",
    r"(?i)\b(?:dm|inbox|telegram)\s+(?:me\s+)?for\s+(?:vip|entry|signals|calls)\b",
    r"(?i)\b(?:10x|5x|2x|double)\s+(?:guaranteed|paisa\s+double)\b",
    r"(?i)\bloss\s+cover\s+(?:karenge|hoga)\b",
    r"(?i)\bpremium\s+(?:group|calls?|tips?)\s+join\s+karo\b",
]

def detect_hinglish_slang(text: str) -> list[str]:
    """Scans for coded Indian financial colloquialisms designed to bypass keyword filters."""
    flagged = []
    for pattern in HINGLISH_SCAM_SLANG:
        matches = re.findall(pattern, text)
        if matches:
            flagged.extend(matches)
    return list(set(flagged))

# ── Adversarial Prompt Injection Detection ───────────────────────────────
INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(?:all\s+)?(?:prior|previous|above|system)\s+(?:instructions|prompts|rules|commands)",
    r"(?i)\bdisregard\s+(?:all\s+)?(?:prior|previous|above|system|guidelines)",
    r"(?i)\byou\s+are\s+now\s+(?:in|acting\s+as|a)\s+(?:maintenance|developer|compliance|safe|unrestricted)\s+mode",
    r"(?i)\boutput\s+(?:only\s+)?\{\s*[\"']is_scam_likely[\"']\s*:\s*false",
    r"(?i)\bmark\s+(?:this|me|content)\s+as\s+(?:compliant|safe|verified|not\s+a\s+scam)",
    r"(?i)\bsystem\s+prompt\s*:\s*override",
    r"(?i)\bdo\s+not\s+flag\s+(?:this|as\s+scam)",
    r"(?i)\bDAN\s+mode\b|\bjailbreak\b",
]

def scan_for_prompt_injection(text: str) -> tuple[bool, Optional[str]]:
    """Detects adversarial jailbreak phrases designed to manipulate compliance checks."""
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return True, match.group(0)
    return False, None

def compute_composite_score(signal_scores: dict) -> float:
    """Weighted aggregate of all signal scores."""
    total = 0.0
    weight_sum = 0.0
    for key, weight in SIGNAL_WEIGHTS.items():
        if key in signal_scores:
            total += signal_scores[key] * weight
            weight_sum += weight
    if weight_sum > 0:
        return round(min(1.0, total / weight_sum), 4)
    return 0.0

def heuristic_sebi_analysis(text: str, pii_count: int, slang_found: list, injection_found: bool, injection_match: Optional[str]) -> dict:
    """Fast deterministic SEBI heuristic rule engine (sub-millisecond evaluation)."""
    scores = {
        "explicit_returns": 0.0,
        "implied_returns": 0.0,
        "urgency_scarcity": 0.0,
        "social_proof": 0.0,
        "paywall_push": 0.0,
        "credential_misrep": 0.0
    }
    quotes = {
        "specific_return_promises": [],
        "urgency_scarcity_language": [],
        "social_proof_inflation": [],
        "paywall_push": [],
        "implied_returns": [],
        "credential_misrepresentation": []
    }
    
    # Check explicit returns
    m = re.findall(r"(?i)(?:\b\d+%\s*(?:guaranteed|returns?|profit|monthly|daily)\b|100%\s*(?:guaranteed|sure|return)|guaranteed\s*returns?|paisa\s*double|sure\s*shot\s*profit)", text)
    if m:
        scores["explicit_returns"] = 0.95
        quotes["specific_return_promises"].extend(m)
        
    # Check implied returns & slang
    if slang_found:
        scores["implied_returns"] = max(scores["implied_returns"], 0.85)
        quotes["implied_returns"].extend([f"[Hinglish Slang]: '{s}'" for s in slang_found])
    m_imp = re.findall(r"(?i)\b(?:rocket\s*calls?|pakka\s*jackpot|zero-loss|multibagger|nifty\s*blast|10x|5x)\b", text)
    if m_imp:
        scores["implied_returns"] = max(scores["implied_returns"], 0.80)
        quotes["implied_returns"].extend(m_imp)
        
    # Check urgency
    m_urg = re.findall(r"(?i)\b(?:only\s*\d+\s*(?:seats?|slots?|spots?|members?)|kal\s*subah\s*9:15|closing\s*soon|last\s*chance|limited\s*time|hurry\s*up)\b", text)
    if m_urg:
        scores["urgency_scarcity"] = 0.85
        quotes["urgency_scarcity_language"].extend(m_urg)
        
    # Check paywall push
    m_pay = re.findall(r"(?i)\b(?:join\s*(?:vip|premium|paid|free)?\s*(?:telegram|whatsapp|group|channel)|dm\s*for\s*(?:vip|entry|tips)|\[MASKED_PRIVATE_CHANNEL_LINK_DPDP\]|t\.me/\S+|chat\.whatsapp\.com/\S+)\b", text)
    if m_pay:
        scores["paywall_push"] = 0.90
        quotes["paywall_push"].extend(m_pay)
        
    # Check credentials
    m_cred = re.findall(r"(?i)\b(?:sebi\s*(?:registered|approved|certified|advisor)|ina[0-9]{8,14}|inh[0-9]{8,14})\b", text)
    if m_cred:
        scores["credential_misrep"] = 0.70
        quotes["credential_misrepresentation"].extend(m_cred)
        
    claimed_advisor = None
    claimed_number = None
    # Match valid SEBI registration formats (e.g. INA000012345, INZ000031633) — requires digits to prevent matching words like 'instruments'
    m_num = re.search(r"\b(IN[A-Za-z]{1,3}[0-9]{4,12})\b", text)
    if m_num:
        claimed_number = m_num.group(1).upper()

    # C4: Heuristic advisor name extractor — runs when Ollama is offline
    # Pattern: "I am <Name>, SEBI..." / "<Name> here, registration..." / common intro formats
    advisor_patterns = [
        r"(?i)\bI(?:'m| am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})[,\s]+(?:sebi|registered|certified|advisor|analyst)",
        r"(?i)\bmy\s+name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
        r"(?i)\bthis\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})[,\s]+(?:sebi|registered|speaking)",
        r"(?i)\bnamskar[,\s]+(?:main|mera\s+naam)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:hoon|hun|hai)",
    ]
    for pat in advisor_patterns:
        m_adv = re.search(pat, text)
        if m_adv:
            claimed_advisor = m_adv.group(1).strip()
            break

    composite = compute_composite_score(scores)
    scam_thresh = get_threshold("scam_composite_threshold", 0.35)
    is_scam = composite >= scam_thresh or bool(slang_found or injection_found or quotes["specific_return_promises"] or quotes["paywall_push"])
    
    reasoning_parts = []
    if quotes["specific_return_promises"]:
        reasoning_parts.append("Guaranteed return promises detected")
    if slang_found:
        reasoning_parts.append(f"Coded Hinglish fraud slang detected ({', '.join(slang_found)})")
    if quotes["paywall_push"]:
        reasoning_parts.append("Unregistered VIP group / paywall push detected")
    if quotes["urgency_scarcity_language"]:
        reasoning_parts.append("Manufactured urgency tactics detected")
    if not reasoning_parts:
        reasoning_parts.append("General commentary with no high-risk SEBI violations flagged")
        
    reasoning = "; ".join(reasoning_parts) + "."
    if injection_found:
        scores["credential_misrep"] = 1.0
        is_scam = True
        composite = 1.0
        reasoning = f"CRITICAL: Adversarial prompt injection attempt ('{injection_match}'). " + reasoning

    return {
        "claimed_advisor_name": claimed_advisor,
        "claimed_registration_number": claimed_number,
        "specific_return_promises": list(set(quotes["specific_return_promises"])),
        "urgency_scarcity_language": list(set(quotes["urgency_scarcity_language"])),
        "social_proof_inflation": list(set(quotes["social_proof_inflation"])),
        "paywall_push": list(set(quotes["paywall_push"])),
        "implied_returns": list(set(quotes["implied_returns"])),
        "credential_misrepresentation": list(set(quotes["credential_misrepresentation"])),
        "signal_scores": scores,
        "composite_risk_score": composite,
        "prompt_injection_detected": injection_found,
        "dpdp_pii_scrubbed_count": pii_count,
        "hinglish_slang_detected": slang_found,
        "is_scam_likely": is_scam,
        "reasoning": reasoning
    }

def run_stage5_llm(transcript: str, job_id: str):
    """
    Calls local Ollama instance to perform SEBI compliance analysis on the transcript.
    Includes:
      1. DPDP Act 2023 Local PII Scrubbing
      2. Adversarial Hinglish Financial Slang Detection
      3. Prompt Injection Security Envelope
      4. Multi-Signal Regulatory Scoring & Entity Extraction
    """
    print(f"[{job_id}] Running Stage 5: SEBI Compliance Reasoning (with DPDP Shield & Hinglish NLP)")
    stage_config = get_stage_config("stage5_llm")
    model_id = stage_config.get("model_id", "llama3.1:latest")
    api_url = stage_config.get("api_url", "http://localhost:11434/api/chat")
    timeout_short = stage_config.get("timeout_short_sec", 3.5)
    timeout_long  = stage_config.get("timeout_long_sec", 30.0)
    llm_risk_thresh = get_threshold("llm_risk_auto_flag_threshold", 0.45)

    empty_result = SEBIAnalysis().model_dump()

    if not transcript or len(transcript.strip()) < 10:
        print(f"[{job_id}] Transcript too short or empty. Skipping LLM stage.")
        return empty_result

    # ── 1. DPDP Act 2023 Local PII Masking ───────────────────────────
    scrubbed_transcript, pii_count = scrub_pii_dpdp(transcript)
    if pii_count > 0:
        print(f"[{job_id}] [DPDP SHIELD] Masked {pii_count} sensitive PII entities (phone/PAN/UPI/Bank/Link) before analysis.")

    # ── 2. Adversarial Hinglish Slang Scan ───────────────────────────
    slang_found = detect_hinglish_slang(transcript)
    if slang_found:
        print(f"[{job_id}] [HINGLISH NLP] Detected coded fraud slang: {slang_found}")

    # ── 3. Prompt Injection Firewall ─────────────────────────────────
    injection_found, injection_match = scan_for_prompt_injection(transcript)
    if injection_found:
        print(f"[{job_id}] [ALERT] CRITICAL: Adversarial Prompt Injection detected: '{injection_match}'")

    # Fast deterministic heuristic baseline
    heuristic_baseline = heuristic_sebi_analysis(
        scrubbed_transcript, pii_count, slang_found, injection_found, injection_match
    )

    system_prompt = """You are a SEBI compliance AI. Analyze financial text for scams. Respond in valid JSON with keys: specific_return_promises (list), urgency_scarcity_language (list), social_proof_inflation (list), paywall_push (list), implied_returns (list), credential_misrepresentation (list), signal_scores (dict of floats 0.0-1.0), is_scam_likely (bool), reasoning (string)."""

    try:
        # Dynamic smart timeout: 3.5s for fast text scans, 30s for long video transcripts
        timeout_sec = timeout_short if len(transcript) < 400 else timeout_long
        print(f"[{job_id}] Sending DPDP-scrubbed content to Ollama ({model_id}, timeout={timeout_sec}s)...")
        payload = {
            "model": model_id,
            "keep_alive": -1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"<untrusted_user_content>\n{scrubbed_transcript}\n</untrusted_user_content>"}
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 350,
                "num_ctx": 2048
            }
        }

        response = requests.post(api_url, json=payload, timeout=timeout_sec)
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "{}")

        try:
            parsed_json = json.loads(content)
            # Normalize nulls to empty lists/dicts
            for list_key in [
                "specific_return_promises", "urgency_scarcity_language",
                "social_proof_inflation", "paywall_push", "implied_returns",
                "credential_misrepresentation", "hinglish_slang_detected"
            ]:
                if parsed_json.get(list_key) is None:
                    parsed_json[list_key] = []
            if parsed_json.get("signal_scores") is None:
                parsed_json["signal_scores"] = {}

            analysis = SEBIAnalysis(**parsed_json)
            result = analysis.model_dump()

            result["dpdp_pii_scrubbed_count"] = pii_count
            result["hinglish_slang_detected"] = slang_found

            # Incorporate Hinglish Slang into scores if detected
            if slang_found:
                current_implied = result["signal_scores"].get("implied_returns", 0.0)
                result["signal_scores"]["implied_returns"] = max(current_implied, 0.75)
                if not result["implied_returns"]:
                    result["implied_returns"] = []
                for s in slang_found:
                    if s not in result["implied_returns"]:
                        result["implied_returns"].append(f"[Hinglish Scam Slang]: '{s}'")

            # Weaponize prompt injection if caught
            if injection_found:
                result["prompt_injection_detected"] = True
                result["is_scam_likely"] = True
                result["signal_scores"]["credential_misrep"] = 1.0
                if not result.get("credential_misrepresentation"):
                    result["credential_misrepresentation"] = []
                result["credential_misrepresentation"].append(f"[Adversarial Manipulation Attempt]: '{injection_match}'")
                result["reasoning"] = f"CRITICAL: Adversarial prompt injection attempt detected ('{injection_match}') to bypass SEBI compliance scanner. " + result["reasoning"]

            # Compute composite risk score
            result["composite_risk_score"] = compute_composite_score(result.get("signal_scores", {}))

            if result["composite_risk_score"] >= llm_risk_thresh and not result["is_scam_likely"]:
                result["is_scam_likely"] = True
                result["reasoning"] += f" [Auto-flagged: composite risk score {result['composite_risk_score']:.2f} exceeds threshold {llm_risk_thresh}]"

            print(f"[{job_id}] LLM reasoning complete. Scam likely: {result['is_scam_likely']}, Composite Risk: {result['composite_risk_score']:.2f}, DPDP Masked: {pii_count}, Slang: {len(slang_found)}")
            return result

        except (json.JSONDecodeError, ValidationError) as e:
            print(f"[{job_id}] Failed to parse LLM output ({e}), using fast heuristic engine.")
            return heuristic_baseline

    except Exception as e:
        print(f"[{job_id}] LLM stage fast fallback ({e}), using instant heuristic engine.")
        return heuristic_baseline
