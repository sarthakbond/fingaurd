"use strict";

// FinGuard in-page toast. Rendered inside a closed Shadow DOM so the host
// page's CSS can't bleed in, and every dynamic field is set via textContent —
// never innerHTML — so a scanned page can't smuggle markup into the notification.

(function () {
  const HOST_ID = "finguard-toast-host";

  function levelFromResult(data) {
    const isDeepfake = !!data.is_deepfake;
    const isScam = !!data.is_scam;
    const composite = typeof data.composite_risk_score === "number"
      ? data.composite_risk_score
      : (data.sebi_analysis && data.sebi_analysis.composite_risk_score) || 0;

    if (isDeepfake && isScam) return { level: "critical", label: "CRITICAL VIOLATION", color: "#e0576a" };
    if (isDeepfake) return { level: "warning", label: "DEEPFAKE FLAGGED", color: "#d9a441" };
    if (isScam) return { level: "warning", label: "SEBI VIOLATION FLAGGED", color: "#d9a441" };
    if (composite >= 0.35) return { level: "suspicious", label: "SUSPICIOUS CONTENT", color: "#d9a441" };
    return { level: "safe", label: "VERIFIED SAFE", color: "#22c58b" };
  }

  function buildShadow(host) {
    const root = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');
      :host { all: initial; }
      .toast {
        position: fixed; top: 24px; right: 24px; z-index: 2147483647;
        width: 320px; font-family: 'Inter', sans-serif; color: #eaf1ea;
        background: linear-gradient(180deg, #101c18, #0d1815);
        border: 1px solid rgba(201,162,39,0.22);
        border-left: 3px solid var(--accent, #22c58b);
        border-radius: 8px; padding: 14px 16px;
        box-shadow: 0 12px 32px rgba(0,0,0,0.55);
        transform: translateX(120%); opacity: 0;
        transition: transform .35s cubic-bezier(.22,.9,.32,1), opacity .35s ease;
        cursor: pointer;
      }
      .toast:hover {
        border-color: rgba(201,162,39,0.45);
        box-shadow: 0 16px 36px rgba(0,0,0,0.7);
      }
      .toast.in { transform: translateX(0); opacity: 1; }
      .row { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
      .label { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; letter-spacing: 0.06em; color: var(--accent, #22c58b); font-weight: 600; }
      .title { font-size: 13px; font-weight: 600; margin-top: 4px; color: #eaf1ea; }
      .meta { font-family: 'IBM Plex Mono', monospace; font-size: 10.5px; color: #93a99a; margin-top: 6px; }
      .action-hint { font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #e8c65a; margin-top: 8px; text-decoration: underline; text-underline-offset: 2px; }
      .close { background: none; border: none; color: #5e7568; cursor: pointer; font-size: 15px; line-height: 1; padding: 0; }
      .close:hover { color: #eaf1ea; }
      .bar-track { height: 3px; background: rgba(255,255,255,0.08); border-radius: 2px; margin-top: 10px; overflow: hidden; }
      .bar-fill { height: 100%; background: var(--accent, #22c58b); width: 100%; transform-origin: left; }
      .bar-fill.count { animation: fg-countdown 6s linear forwards; }
      @keyframes fg-countdown { from { transform: scaleX(1); } to { transform: scaleX(0); } }
      @media (prefers-reduced-motion: reduce) { .toast, .bar-fill.count { animation: none !important; transition: none !important; } }
    `;
    root.appendChild(style);
    return root;
  }

  function showToast(data, scannedText, apiUrl) {
    const existing = document.getElementById(HOST_ID);
    if (existing) existing.remove();

    const host = document.createElement("div");
    host.id = HOST_ID;
    document.documentElement.appendChild(host);
    const root = buildShadow(host);

    const { label, color } = levelFromResult(data);
    const composite = typeof data.composite_risk_score === "number"
      ? data.composite_risk_score
      : (data.sebi_analysis && data.sebi_analysis.composite_risk_score) || 0;
    
    const sebi = data.sebi_analysis || {};
    const quotes = [
      ...(sebi.specific_return_promises || []),
      ...(sebi.implied_returns || []),
      ...(sebi.urgency_scarcity_language || []),
      ...(sebi.paywall_push || []),
      ...(sebi.credential_misrepresentation || []),
      ...(sebi.flagged_statements || []),
      ...(data.flagged_statements || [])
    ].filter(Boolean);

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.style.setProperty("--accent", color);

    const row = document.createElement("div");
    row.className = "row";

    const left = document.createElement("div");
    const labelEl = document.createElement("div");
    labelEl.className = "label";
    labelEl.textContent = label;
    const titleEl = document.createElement("div");
    titleEl.className = "title";
    titleEl.textContent = data.verdict || "Forensic Scan Complete";
    left.appendChild(labelEl);
    left.appendChild(titleEl);

    const closeBtn = document.createElement("button");
    closeBtn.className = "close";
    closeBtn.setAttribute("aria-label", "Dismiss");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      dismiss();
    });

    row.appendChild(left);
    row.appendChild(closeBtn);

    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = quotes.length > 0
      ? `${quotes.length} regulatory violation flag${quotes.length === 1 ? "" : "s"} detected`
      : "Forensic analysis completed";

    const hintEl = document.createElement("div");
    hintEl.className = "action-hint";
    hintEl.textContent = "Click to open full report in dashboard ↗";

    const barTrack = document.createElement("div");
    barTrack.className = "bar-track";
    const barFill = document.createElement("div");
    barFill.className = "bar-fill count";
    barTrack.appendChild(barFill);

    toast.appendChild(row);
    toast.appendChild(metaEl);
    toast.appendChild(hintEl);
    toast.appendChild(barTrack);
    root.appendChild(toast);

    toast.addEventListener("click", (e) => {
      if (e.target.closest(".close")) return;
      const base = apiUrl || "http://127.0.0.1:8000";
      const targetUrl = scannedText ? `${base}/?scanText=${encodeURIComponent(scannedText)}` : base;
      window.open(targetUrl, "_blank");
    });

    requestAnimationFrame(() => toast.classList.add("in"));

    let dismissed = false;
    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      toast.classList.remove("in");
      setTimeout(() => host.remove(), 350);
    }
    const timer = setTimeout(dismiss, 7000);
    toast.addEventListener("mouseenter", () => { clearTimeout(timer); barFill.style.animationPlayState = "paused"; });
  }

  function showScanningToast(scanType) {
    const existing = document.getElementById(HOST_ID);
    if (existing) existing.remove();

    const host = document.createElement("div");
    host.id = HOST_ID;
    document.documentElement.appendChild(host);
    const root = buildShadow(host);

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.style.setProperty("--accent", "#22c58b");

    const labelEl = document.createElement("div");
    labelEl.className = "label";
    labelEl.textContent = "⚡ FINGUARD SCANNING";

    const titleEl = document.createElement("div");
    titleEl.className = "title";
    titleEl.textContent = `Running forensic AI pipeline on ${scanType || "content"}…`;

    toast.appendChild(labelEl);
    toast.appendChild(titleEl);
    root.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("in"));
  }

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message) => {
      if (message && message.type === "FINGUARD_SCANNING") {
        showScanningToast(message.scanType);
      } else if (message && message.type === "FINGUARD_RESULT") {
        const payload = message.data || message.result || message;
        showToast(payload, message.scannedText, message.apiUrl);
      } else if (message && message.type === "FINGUARD_ERROR") {
        showToast({ verdict: message.message || "Scan failed — check FinGuard server connection", is_scam: false, is_deepfake: false, composite_risk_score: 0 }, message.scannedText, message.apiUrl);
      }
    });
  }
})();
