/* ============================================================================
   Small DOM + formatting helpers. No framework, no dependencies.
   ========================================================================= */

export const $  = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/** Build an element from a tag, an attribute bag, and children. */
export function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

/* ── Formatting ──────────────────────────────────────────────────────────── */

export function fmtBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const n = bytes / 1024 ** i;
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`;
}

/** Seconds → m:ss, the form used everywhere a media clock appears. */
export function fmtClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** 0..1 → integer percentage string. Returns '—' for absent scores. */
export function fmtScore(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return String(Math.round(value * 100));
}

export function fmtStamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function ext(filename) {
  const m = /\.[^.]+$/.exec(filename || '');
  return m ? m[0].toLowerCase() : '';
}

/* ── Environment ─────────────────────────────────────────────────────────── */

export const reducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Device-pixel-ratio aware canvas sizing. Returns CSS-pixel dimensions. */
export function fitCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width));
  const h = Math.max(1, Math.round(rect.height));
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

/** Runs a rAF loop only while the element is on screen. Returns a stop fn. */
export function whileVisible(element, frame) {
  let raf = 0;
  let live = false;
  const tick = (t) => { frame(t); if (live) raf = requestAnimationFrame(tick); };
  const io = new IntersectionObserver((entries) => {
    const visible = entries.some((e) => e.isIntersecting);
    if (visible && !live) { live = true; raf = requestAnimationFrame(tick); }
    else if (!visible && live) { live = false; cancelAnimationFrame(raf); }
  }, { threshold: 0.01 });
  io.observe(element);
  return () => { live = false; cancelAnimationFrame(raf); io.disconnect(); };
}
