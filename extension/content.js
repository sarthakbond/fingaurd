/**
 * FinGuard Chrome Extension — Content Script
 * Receives scan results from background worker and displays inline notifications.
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

function showToast(html, duration = 8000) {
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
  toast.innerHTML = html;
  container.appendChild(toast);

  // Add animation keyframes if not already present
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
    `;
    document.head.appendChild(style);
  }

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
    showToast(`
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:18px;height:18px;border:2px solid rgba(255,255,255,0.2);border-top-color:#3b82f6;border-radius:50%;animation:spin 0.8s linear infinite"></div>
        <span>FinGuard is scanning ${msg.scanType}...</span>
      </div>
      <style>@keyframes spin { to { transform: rotate(360deg); } }</style>
    `, 30000);
  }

  if (msg.type === 'FINGUARD_RESULT') {
    // Clear scanning toasts
    const container = getOrCreateContainer();
    container.innerHTML = '';

    const data = msg.data;
    const verdict = data.verdict || 'Unknown';
    const risk = ((data.composite_risk_score || 0) * 100).toFixed(0);

    let borderColor, bgColor, icon;
    if (verdict.includes('Critical')) { borderColor = '#f43f5e'; bgColor = 'rgba(244,63,94,0.1)'; icon = '🚨'; }
    else if (verdict.includes('Warning')) { borderColor = '#f59e0b'; bgColor = 'rgba(245,158,11,0.1)'; icon = '⚠️'; }
    else { borderColor = '#10b981'; bgColor = 'rgba(16,185,129,0.1)'; icon = '✅'; }

    const sebi = data.sebi_analysis || {};
    const flagCount = (sebi.specific_return_promises || []).length +
      (sebi.implied_returns || []).length +
      (sebi.urgency_scarcity_language || []).length +
      (sebi.social_proof_inflation || []).length +
      (sebi.paywall_push || []).length +
      (sebi.credential_misrepresentation || []).length;

    showToast(`
      <div style="border-left:3px solid ${borderColor};padding-left:12px">
        <div style="font-weight:700;font-size:14px;margin-bottom:4px">${icon} ${verdict}</div>
        <div style="color:#94a3b8;font-size:12px">Risk Score: <span style="color:${borderColor};font-weight:600">${risk}%</span></div>
        ${flagCount > 0 ? `<div style="color:#94a3b8;font-size:12px;margin-top:2px">${flagCount} red flag${flagCount > 1 ? 's' : ''} detected</div>` : ''}
        ${sebi.reasoning ? `<div style="color:#94a3b8;font-size:11px;margin-top:6px;border-top:1px solid rgba(255,255,255,0.06);padding-top:6px">${sebi.reasoning.substring(0, 150)}${sebi.reasoning.length > 150 ? '...' : ''}</div>` : ''}
        <div style="color:#64748b;font-size:10px;margin-top:6px">Click FinGuard extension for full report</div>
      </div>
    `, 12000);
  }

  if (msg.type === 'FINGUARD_ERROR') {
    const container = getOrCreateContainer();
    container.innerHTML = '';
    showToast(`
      <div style="border-left:3px solid #f43f5e;padding-left:12px">
        <div style="font-weight:600">❌ FinGuard Error</div>
        <div style="color:#94a3b8;font-size:12px;margin-top:4px">${msg.message}</div>
      </div>
    `, 6000);
  }
});
