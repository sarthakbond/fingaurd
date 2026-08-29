/**
 * FinGuard Chrome Extension — Background Service Worker
 * Handles context menus and API communication.
 */

const DEFAULT_API_URL = 'http://127.0.0.1:8000';

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
  const tabId = tab && tab.id;

  if (info.menuItemId === 'finguard-scan-text') {
    const selectedText = info.selectionText;
    if (!selectedText || selectedText.trim().length < 5) {
      notifyTab(tabId, { type: 'FINGUARD_ERROR', message: 'Selected text too short to analyze.' });
      return;
    }
    try {
      await notifyTab(tabId, { type: 'FINGUARD_SCANNING', scanType: 'text', apiUrl: apiUrl });
      const result = await scanText(apiUrl, selectedText);
      await notifyTab(tabId, {
        type: 'FINGUARD_RESULT',
        scanType: 'text',
        data: result,
        result: result,
        scannedText: selectedText,
        apiUrl: apiUrl
      });
      // Store last result for popup
      chrome.storage.local.set({ lastResult: result, lastScanType: 'text', lastScanTime: Date.now(), lastText: selectedText });
    } catch (err) {
      console.error('[FinGuard Background] Text scan error:', err);
      notifyTab(tabId, { type: 'FINGUARD_ERROR', message: err.message || 'Scan failed.', scannedText: selectedText, apiUrl: apiUrl });
    }
  }

  if (info.menuItemId === 'finguard-scan-image') {
    const imageUrl = info.srcUrl;
    if (!imageUrl) {
      notifyTab(tabId, { type: 'FINGUARD_ERROR', message: 'Could not get image URL.' });
      return;
    }
    try {
      await notifyTab(tabId, { type: 'FINGUARD_SCANNING', scanType: 'image' });
      const result = await scanImage(apiUrl, imageUrl);
      await notifyTab(tabId, { type: 'FINGUARD_RESULT', scanType: 'image', data: result, result: result });
      chrome.storage.local.set({ lastResult: result, lastScanType: 'image', lastScanTime: Date.now() });
    } catch (err) {
      console.error('[FinGuard Background] Image scan error:', err);
      notifyTab(tabId, { type: 'FINGUARD_ERROR', message: err.message || 'Image scan failed.' });
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
  let endpoint = apiUrl;
  if (!endpoint.endsWith('/')) {
    endpoint += '/api/scan/text';
  } else {
    endpoint += 'api/scan/text';
  }

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Scan failed: ${res.status}`);
  }
  return res.json();
}

async function scanImage(apiUrl, imageUrl) {
  const imgRes = await fetch(imageUrl);
  const blob = await imgRes.blob();

  const fd = new FormData();
  const ext = imageUrl.split('.').pop().split('?')[0] || 'jpg';
  fd.append('file', blob, `scan.${ext}`);

  let endpoint = apiUrl;
  if (!endpoint.endsWith('/')) {
    endpoint += '/api/scan/image';
  } else {
    endpoint += 'api/scan/image';
  }

  const res = await fetch(endpoint, {
    method: 'POST',
    body: fd
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Image scan failed: ${res.status}`);
  }
  return res.json();
}

async function checkHealth(apiUrl) {
  let endpoint = apiUrl;
  if (!endpoint.endsWith('/')) {
    endpoint += '/api/health';
  } else {
    endpoint += 'api/health';
  }
  const res = await fetch(endpoint, { method: 'GET' });
  if (!res.ok) throw new Error('Server unreachable');
  return res.json();
}

async function notifyTab(tabId, message) {
  if (!tabId) return;
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch (err) {
    // If content script is not yet present on the tab, dynamically inject it and retry
    try {
      if (chrome.scripting) {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ['content.js']
        });
        setTimeout(() => {
          chrome.tabs.sendMessage(tabId, message).catch(() => {});
        }, 150);
      }
    } catch (injectErr) {
      console.warn('[FinGuard] Could not inject content script:', injectErr);
    }
  }
}
