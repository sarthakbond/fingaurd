"use strict";

const DEFAULT_API_URL = "http://localhost:8000";

const $ = (id) => document.getElementById(id);

const els = {
  statusDot: $("statusDot"), statusText: $("statusText"),
  settingsBtn: $("settingsBtn"), settingsPanel: $("settingsPanel"),
  apiUrlInput: $("apiUrlInput"), saveSettingsBtn: $("saveSettingsBtn"),
  quickText: $("quickText"), scanBtn: $("scanBtn"), demoBtn: $("demoBtn"),
  errorBox: $("errorBox"), resultCard: $("resultCard"),
  resultStamp: $("resultStamp"), resultTitle: $("resultTitle"), resultDesc: $("resultDesc"),
  resultMeterFill: $("resultMeterFill"), resultTopFlag: $("resultTopFlag"),
  openDashboardBtn: $("openDashboardBtn")
};

let apiUrl = DEFAULT_API_URL;

function getStorage(keys) {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(keys, resolve);
    } else {
      resolve({});
    }
  });
}
function setStorage(items) {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set(items, resolve);
    } else {
      resolve();
    }
  });
}

async function checkHealth() {
  els.statusDot.className = "status-dot";
  els.statusText.textContent = "Checking connection…";
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    const res = await fetch(apiUrl + "/api/health", { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) throw new Error("bad status");
    els.statusDot.className = "status-dot online";
    els.statusText.textContent = "Connected · " + apiUrl.replace(/^https?:\/\//, "");
  } catch (e) {
    els.statusDot.className = "status-dot offline";
    els.statusText.textContent = "Offline · " + apiUrl.replace(/^https?:\/\//, "") + " unreachable";
  }
}

function showError(msg) {
  els.errorBox.textContent = msg;
  els.errorBox.classList.add("show");
}
function clearError() {
  els.errorBox.classList.remove("show");
}

function renderMiniResult(data) {
  const isDeepfake = !!data.is_deepfake;
  const isScam = !!data.is_scam;
  const composite = typeof data.composite_risk_score === "number"
    ? data.composite_risk_score
    : (data.sebi_analysis && data.sebi_analysis.composite_risk_score) || 0;

  let level = "safe", word = "SAFE", title = "Clean";
  if (isDeepfake && isScam) { level = "critical"; word = "CRIT"; title = "Deepfake + SEBI violation"; }
  else if (isDeepfake) { level = "warning"; word = "FLAG"; title = "Deepfake detected"; }
  else if (isScam) { level = "warning"; word = "FLAG"; title = "SEBI violation likely"; }
  else if (composite >= 0.35) { level = "suspicious"; word = "SUSP"; title = "Review recommended"; }

  els.resultStamp.className = "mini-stamp " + level;
  els.resultStamp.textContent = word;
  els.resultTitle.textContent = data.verdict || title;
  els.resultDesc.textContent = "Composite fraud risk " + Math.round(composite * 100) + "%";
  els.resultMeterFill.style.width = Math.round(composite * 100) + "%";

  const sebi = data.sebi_analysis || {};
  const quotes = [
    ...(sebi.specific_return_promises || []),
    ...(sebi.implied_returns || []),
    ...(sebi.urgency_scarcity_language || []),
    ...(sebi.paywall_push || []),
    ...(sebi.credential_misrepresentation || []),
    ...(sebi.flagged_statements || []),
    ...(data.flagged_statements || [])
  ];

  if (quotes && quotes.length) {
    const firstQ = typeof quotes[0] === "string" ? quotes[0] : (quotes[0].text || quotes[0].quote || "");
    els.resultTopFlag.textContent = firstQ;
    els.resultTopFlag.style.display = "block";
  } else {
    els.resultTopFlag.style.display = "none";
  }

  els.resultCard.classList.add("show");
}

async function scanText(text) {
  const res = await fetch(apiUrl + "/api/scan/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || ("Server returned " + res.status));
  }
  return res.json();
}

const DEMO_RESULT = {
  verdict: "Warning: SEBI Violation / Scam",
  is_scam: true, is_deepfake: false, composite_risk_score: 0.82,
  sebi_analysis: {
    flagged_statements: ["I guarantee 40% monthly returns, only 50 seats left in my premium group!"]
  }
};

els.settingsBtn.addEventListener("click", () => {
  els.settingsPanel.classList.toggle("show");
});

els.saveSettingsBtn.addEventListener("click", async () => {
  const value = els.apiUrlInput.value.trim().replace(/\/+$/, "");
  apiUrl = value || DEFAULT_API_URL;
  await setStorage({ apiUrl });
  els.settingsPanel.classList.remove("show");
  checkHealth();
});

els.quickText.addEventListener("input", () => {
  els.scanBtn.disabled = els.quickText.value.trim().length === 0;
});

els.scanBtn.addEventListener("click", async () => {
  clearError();
  const text = els.quickText.value.trim();
  if (!text) return;
  const original = els.scanBtn.textContent;
  els.scanBtn.disabled = true; els.scanBtn.textContent = "Scanning…";
  try {
    const data = await scanText(text);
    renderMiniResult(data);
    await setStorage({ lastResult: data });
  } catch (e) {
    showError("Scan failed — backend unreachable. Try the Demo button, or check Settings.");
  } finally {
    els.scanBtn.disabled = false; els.scanBtn.textContent = original;
  }
});

els.demoBtn.addEventListener("click", () => {
  clearError();
  renderMiniResult(DEMO_RESULT);
});

els.openDashboardBtn.addEventListener("click", () => {
  if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
    chrome.tabs.create({ url: apiUrl });
  } else {
    window.open(apiUrl, "_blank", "noopener,noreferrer");
  }
});

(async function init() {
  const stored = await getStorage(["apiUrl", "lastResult"]);
  apiUrl = stored.apiUrl || DEFAULT_API_URL;
  els.apiUrlInput.value = apiUrl;
  if (stored.lastResult) renderMiniResult(stored.lastResult);
  checkHealth();
})();
