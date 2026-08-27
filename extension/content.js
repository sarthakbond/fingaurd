/**
 * FinGuard Chrome Extension — Content Script
 * Receives scan results from background worker and safely displays inline notifications.
 * Uses safe DOM elements to prevent any script or markup injection.
 */

// ── Inject notification container ──────────────────────────────────
function getOrCreateContainer() {
  let container = document.getElementById('finguard-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'finguard-toast-container';
    container.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 2147483647;
      display: flex;
      flex-direction: column;
      gap: 10px;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      pointer-events: none;
    `;
    document.body.appendChild(container);
  }
  return container;
}

function ensureAnimationStyles() {
  if (!document.getElementById('finguard-styles')) {
    const style = document.createElement('style');
    style.id = 'finguard-styles';
    style.textContent = `
      @keyframes finguardSlideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes finguardSlideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
      }
      @keyframes finguardSpin {
        to { transform: rotate(360deg); }
      }
    `;
    document.head.appendChild(style);
  }
}

function showToastNode(elementNode, duration = 8000) {
  ensureAnimationStyles();
  const container = getOrCreateContainer();
  const toast = document.createElement('div');
  toast.style.cssText = `
    background: #0f1623;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 14px 18px;
    color: #f1f5f9;
    font-size: 13px;
    line-height: 1.5;
    max-width: 360px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    pointer-events: auto;
    animation: finguardSlideIn 0.3s ease;
    backdrop-filter: blur(12px);
  `;
  toast.appendChild(elementNode);
  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      toast.style.animation = 'finguardSlideOut 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  return toast;
}

// ── Message Listener ───────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'FINGUARD_SCANNING') {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:10px;';
    
    const spinner = document.createElement('div');
    spinner.style.cssText = 'width:18px;height:18px;border:2px solid rgba(255,255,255,0.2);border-top-color:#3b82f6;border-radius:50%;animation:finguardSpin 0.8s linear infinite;';
    
    const text = document.createElement('span');
    text.textContent = `FinGuard is scanning ${msg.scanType || 'content'}...`;
    
    wrap.appendChild(spinner);
    wrap.appendChild(text);
    showToastNode(wrap, 30000);
  }

  if (msg.type === 'FINGUARD_RESULT') {
    const container = getOrCreateContainer();
    container.innerHTML = '';

    const data = msg.data || {};
    const verdict = data.verdict || 'Unknown';
    const risk = ((data.composite_risk_score || 0) * 100).toFixed(0);

    let borderColor, icon;
    if (verdict.includes('Critical')) { borderColor = '#f43f5e'; icon = '🚨'; }
    else if (verdict.includes('Warning')) { borderColor = '#f59e0b'; icon = '⚠️'; }
    else { borderColor = '#10b981'; icon = '✅'; }

    const sebi = data.sebi_analysis || {};
    const flagCount = (sebi.specific_return_promises || []).length +
      (sebi.implied_returns || []).length +
      (sebi.urgency_scarcity_language || []).length +
      (sebi.social_proof_inflation || []).length +
      (sebi.paywall_push || []).length +
      (sebi.credential_misrepresentation || []).length;

    const wrap = document.createElement('div');
    wrap.style.borderLeft = `3px solid ${borderColor}`;
    wrap.style.paddingLeft = '12px';

    const titleEl = document.createElement('div');
    titleEl.style.cssText = 'font-weight:700;font-size:14px;margin-bottom:4px;';
    titleEl.textContent = `${icon} ${verdict}`;
    wrap.appendChild(titleEl);

    const riskEl = document.createElement('div');
    riskEl.style.cssText = 'color:#94a3b8;font-size:12px;';
    riskEl.textContent = 'Risk Score: ';
    const riskVal = document.createElement('span');
    riskVal.style.color = borderColor;
    riskVal.style.fontWeight = '600';
    riskVal.textContent = `${risk}%`;
    riskEl.appendChild(riskVal);
    wrap.appendChild(riskEl);

    if (flagCount > 0) {
      const flagEl = document.createElement('div');
      flagEl.style.cssText = 'color:#94a3b8;font-size:12px;margin-top:2px;';
      flagEl.textContent = `${flagCount} red flag${flagCount > 1 ? 's' : ''} detected`;
      wrap.appendChild(flagEl);
    }

    if (sebi.reasoning) {
      const reasonEl = document.createElement('div');
      reasonEl.style.cssText = 'color:#94a3b8;font-size:11px;margin-top:6px;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px;';
      const truncated = sebi.reasoning.length > 150 ? sebi.reasoning.substring(0, 150) + '...' : sebi.reasoning;
      reasonEl.textContent = truncated;
      wrap.appendChild(reasonEl);
    }

    const hintEl = document.createElement('div');
    hintEl.style.cssText = 'color:#64748b;font-size:10px;margin-top:6px;';
    hintEl.textContent = 'Click FinGuard extension for full report';
    wrap.appendChild(hintEl);

    showToastNode(wrap, 12000);
  }

  if (msg.type === 'FINGUARD_ERROR') {
    const container = getOrCreateContainer();
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.style.borderLeft = '3px solid #f43f5e';
    wrap.style.paddingLeft = '12px';

    const titleEl = document.createElement('div');
    titleEl.style.fontWeight = '600';
    titleEl.textContent = '❌ FinGuard Error';
    wrap.appendChild(titleEl);

    const msgEl = document.createElement('div');
    msgEl.style.cssText = 'color:#94a3b8;font-size:12px;margin-top:4px;';
    msgEl.textContent = msg.message || 'An error occurred during scan';
    wrap.appendChild(msgEl);

    showToastNode(wrap, 6000);
  }
});
