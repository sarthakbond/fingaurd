/**
 * FinGuard Chrome Extension — Background Service Worker
 * Handles context menus and API communication.
 */

const DEFAULT_API_URL = 'http://localhost:8000';

// ── Context Menu Setup ─────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  // Text selection context menu
  chrome.contextMenus.create({
    id: 'finguard-scan-text',
    title: '🔍 Scan selected text with FinGuard',
    contexts: ['selection']
  });

  // Image context menu
  chrome.contextMenus.create({
    id: 'finguard-scan-image',
    title: '🔍 Scan this image with FinGuard',
    contexts: ['image']
  });

  // Set default API URL
  chrome.storage.local.get('apiUrl', (data) => {
    if (!data.apiUrl) {
      chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
    }
  });
});

// ── Context Menu Click Handler ─────────────────────────────────────
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const apiUrl = await getApiUrl();

  if (info.menuItemId === 'finguard-scan-text') {
    const selectedText = info.selectionText;
    if (!selectedText || selectedText.trim().length < 5) {
      notifyTab(tab.id, { type: 'FINGUARD_ERROR', message: 'Selected text too short to analyze.' });
      return;
    }
    try {
      notifyTab(tab.id, { type: 'FINGUARD_SCANNING', scanType: 'text' });
      const result = await scanText(apiUrl, selectedText);
      notifyTab(tab.id, { type: 'FINGUARD_RESULT', scanType: 'text', data: result });
      // Store last result for popup
      chrome.storage.local.set({ lastResult: result, lastScanType: 'text', lastScanTime: Date.now() });
    } catch (err) {
      notifyTab(tab.id, { type: 'FINGUARD_ERROR', message: err.message });
    }
  }

  if (info.menuItemId === 'finguard-scan-image') {
    const imageUrl = info.srcUrl;
    if (!imageUrl) {
      notifyTab(tab.id, { type: 'FINGUARD_ERROR', message: 'Could not get image URL.' });
      return;
    }
    try {
      notifyTab(tab.id, { type: 'FINGUARD_SCANNING', scanType: 'image' });
      const result = await scanImage(apiUrl, imageUrl);
      notifyTab(tab.id, { type: 'FINGUARD_RESULT', scanType: 'image', data: result });
      chrome.storage.local.set({ lastResult: result, lastScanType: 'image', lastScanTime: Date.now() });
    } catch (err) {
      notifyTab(tab.id, { type: 'FINGUARD_ERROR', message: err.message });
    }
  }
});

// ── Message handler (from popup) ───────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SCAN_TEXT') {
    getApiUrl().then(apiUrl => {
      scanText(apiUrl, msg.text)
        .then(result => {
          chrome.storage.local.set({ lastResult: result, lastScanType: 'text', lastScanTime: Date.now() });
          sendResponse({ success: true, data: result });
        })
        .catch(err => sendResponse({ success: false, error: err.message }));
    });
    return true; // Keep channel open for async response
  }

  if (msg.type === 'CHECK_HEALTH') {
    getApiUrl().then(apiUrl => {
      checkHealth(apiUrl)
        .then(result => sendResponse({ success: true, data: result }))
        .catch(err => sendResponse({ success: false, error: err.message }));
    });
    return true;
  }
});

// ── API Functions ──────────────────────────────────────────────────
async function getApiUrl() {
  return new Promise(resolve => {
    chrome.storage.local.get('apiUrl', (data) => {
      resolve(data.apiUrl || DEFAULT_API_URL);
    });
  });
}

async function scanText(apiUrl, text) {
  const res = await fetch(`${apiUrl}/api/scan/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Scan failed');
  }
  return res.json();
}

async function scanImage(apiUrl, imageUrl) {
  // Download image as blob, then upload to our API
  const imgRes = await fetch(imageUrl);
  const blob = await imgRes.blob();

  const fd = new FormData();
  const ext = imageUrl.split('.').pop().split('?')[0] || 'jpg';
  fd.append('file', blob, `scan.${ext}`);

  const res = await fetch(`${apiUrl}/api/scan/image`, {
    method: 'POST',
    body: fd
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Image scan failed');
  }
  return res.json();
}

async function checkHealth(apiUrl) {
  const res = await fetch(`${apiUrl}/api/health`, { method: 'GET' });
  if (!res.ok) throw new Error('Server unreachable');
  return res.json();
}

function notifyTab(tabId, message) {
  chrome.tabs.sendMessage(tabId, message).catch(() => {
    // Content script might not be loaded yet
  });
}
