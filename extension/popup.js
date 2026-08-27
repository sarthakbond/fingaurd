/**
 * FinGuard Chrome Extension — Popup Logic
 */

const SIGNAL_LABELS = {
  'explicit_returns': '💰 Explicit Returns',
  'implied_returns': '📈 Implied Returns',
  'urgency_scarcity': '⏰ Urgency',
  'social_proof': '👥 Social Proof',
  'paywall_push': '🔒 Paywall',
  'credential_misrep': '🎭 Credentials'
};

// ── Init ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Load saved API URL
  chrome.storage.local.get('apiUrl', (data) => {
    document.getElementById('api-url-input').value = data.apiUrl || 'http://localhost:8000';
  });

  // Check server health
  checkConnection();

  // Load last result if exists
  chrome.storage.local.get(['lastResult', 'lastScanType', 'lastScanTime'], (data) => {
    if (data.lastResult && data.lastScanTime) {
      const ago = Math.floor((Date.now() - data.lastScanTime) / 60000);
      const timeStr = ago < 1 ? 'just now' : `${ago}m ago`;
      document.getElementById('last-scan-info').textContent = `Last scan: ${data.lastScanType} · ${timeStr}`;
      renderResult(data.lastResult);
    }
  });
});

// ── Settings ───────────────────────────────────────────────────────
function saveApiUrl() {
  const url = document.getElementById('api-url-input').value.trim().replace(/\/$/, '');
  if (!url) return;
  chrome.storage.local.set({ apiUrl: url }, () => {
    checkConnection();
  });
}

async function checkConnection() {
  const dot = document.getElementById('status-dot');
  dot.className = 'status-dot';
  dot.title = 'Checking...';

  chrome.runtime.sendMessage({ type: 'CHECK_HEALTH' }, (res) => {
    if (chrome.runtime.lastError || !res || !res.success) {
      dot.className = 'status-dot offline';
      dot.title = 'Server offline';
    } else {
      dot.className = 'status-dot online';
      dot.title = `Connected — v${res.data.version}`;
    }
  });
}

// ── Quick Scan ─────────────────────────────────────────────────────
function quickScan() {
  const text = document.getElementById('quick-text').value.trim();
  if (!text || text.length < 5) return;

  const btn = document.getElementById('quick-scan-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Scanning...';

  chrome.runtime.sendMessage({ type: 'SCAN_TEXT', text }, (res) => {
    btn.disabled = false;
    btn.textContent = '🔍 Scan Text';

    if (chrome.runtime.lastError || !res || !res.success) {
      alert('Scan failed: ' + (res?.error || 'Connection error'));
      return;
    }

    renderResult(res.data);
    document.getElementById('last-scan-info').textContent = 'Last scan: text · just now';
  });
}

// ── Render Result ──────────────────────────────────────────────────
function renderResult(data) {
  const section = document.getElementById('result-section');
  section.style.display = 'block';

  // Banner
  const banner = document.getElementById('result-banner');
  const verdict = data.verdict || 'Unknown';
  document.getElementById('result-verdict').textContent = verdict;

  const risk = ((data.composite_risk_score || 0) * 100).toFixed(0);
  document.getElementById('result-risk').textContent = `Composite Risk: ${risk}%`;

  if (verdict.includes('Critical')) banner.className = 'result-banner danger';
  else if (verdict.includes('Warning')) banner.className = 'result-banner warning';
  else banner.className = 'result-banner safe';

  // Signal bars
  const sebi = data.sebi_analysis || {};
  const scores = sebi.signal_scores || {};
  const signalsContainer = document.getElementById('signals-compact');
  signalsContainer.innerHTML = '';

  for (const [key, label] of Object.entries(SIGNAL_LABELS)) {
    const score = scores[key] || 0;
    const pct = (score * 100).toFixed(0);
    const color = score >= 0.7 ? '#f43f5e' : score >= 0.4 ? '#f59e0b' : '#10b981';

    signalsContainer.innerHTML += `
      <div class="sig-row">
        <span class="sig-name">${label}</span>
        <div class="sig-bar-bg"><div class="sig-bar-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="sig-pct" style="color:${color}">${pct}%</span>
      </div>`;
  }

  // Flags
  const allFlags = [
    ...(sebi.specific_return_promises || []).map(q => ({ type: 'return', quote: q, label: 'Return Claim' })),
    ...(sebi.implied_returns || []).map(q => ({ type: 'implied', quote: q, label: 'Implied Return' })),
    ...(sebi.urgency_scarcity_language || []).map(q => ({ type: 'urgency', quote: q, label: 'Urgency' })),
    ...(sebi.social_proof_inflation || []).map(q => ({ type: 'social', quote: q, label: 'Social Proof' })),
    ...(sebi.paywall_push || []).map(q => ({ type: 'paywall', quote: q, label: 'Paywall' })),
    ...(sebi.credential_misrepresentation || []).map(q => ({ type: 'credential', quote: q, label: 'Credential' })),
  ];

  const flagsSection = document.getElementById('flags-compact');
  const flagsList = document.getElementById('flags-list');
  if (allFlags.length) {
    flagsSection.style.display = 'block';
    flagsList.innerHTML = allFlags.map(f => `
      <div class="flag-compact type-${f.type}">
        <div class="flag-quote">"${f.quote}"</div>
        <div class="flag-label">${f.label}</div>
      </div>
    `).join('');
  } else {
    flagsSection.style.display = 'none';
  }

  // Reasoning
  const reasoningSection = document.getElementById('reasoning-compact');
  if (sebi.reasoning) {
    reasoningSection.style.display = 'block';
    document.getElementById('reasoning-text').textContent = sebi.reasoning;
  } else {
    reasoningSection.style.display = 'none';
  }
}
