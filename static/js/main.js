import { $, $$, clear, el, esc, fmtBytes, fmtClock, fmtScore, fmtStamp, fitCanvas, reducedMotion, whileVisible } from './dom.js';
import { LIMITS, complaintUrl, health, startRun, validateFile, validateText } from './api.js';
import { planFor, TECHNOLOGY_STAGES } from './stages.js';
import { toViewModel } from './model.js';

const state = {
  route: ['/', '/analyze', '/analysis', '/results'].includes(window.location.pathname) ? window.location.pathname : '/',
  mode: 'video',
  file: null,
  previewUrl: null,
  text: '',
  run: null,
  startedAt: null,
  jobId: null,
  viewModel: null,
};

const icons = {
  check: '<path d="m5 12 4 4L19 6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  upload: '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 15v4h16v-4"/>',
  shield: '<path d="M12 2.5 4.5 5.6v5.9c0 4.7 3.1 8.6 7.5 10 4.4-1.4 7.5-5.3 7.5-10V5.6Z"/><path d="m8.6 12.1 3.4 3.3 3.4-5.6"/>',
};
const svg = (body, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

function showRoute(route) {
  state.route = route;
  history.pushState({}, '', route);
  $('#view-landing').hidden = route !== '/';
  $('#view-analyze').hidden = route !== '/analyze';
  $('#view-analysis').hidden = route !== '/analysis';
  $('#view-results').hidden = route !== '/results';
  $('.fg-footer').hidden = route === '/analysis';
  if (route === '/') window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' });
  if (route === '/analyze') renderWork();
  if (route === '/results' && state.viewModel) renderResults(state.viewModel);
  closeMenu();
}

function closeMenu() {
  const nav = $('#nav');
  nav.dataset.open = 'false';
  $('#nav-toggle')?.setAttribute('aria-expanded', 'false');
}

function goAnchor(id) {
  if (state.route !== '/') {
    showRoute('/');
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth' }));
  } else document.getElementById(id)?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth' });
  closeMenu();
}

function bindNavigation() {
  document.addEventListener('click', (event) => {
    const route = event.target.closest('[data-route]')?.dataset.route;
    const anchor = event.target.closest('[data-anchor]')?.dataset.anchor;
    if (route) showRoute(route);
    else if (anchor) goAnchor(anchor);
  });
  window.addEventListener('popstate', () => showRoute(window.location.pathname === '/analyze' ? '/analyze' : '/'));
  window.addEventListener('scroll', () => { $('#nav').dataset.scrolled = window.scrollY > 8 ? 'true' : 'false'; }, { passive: true });
  $('#nav-toggle')?.addEventListener('click', () => {
    const open = $('#nav').dataset.open !== 'true';
    $('#nav').dataset.open = open ? 'true' : 'false';
    $('#nav-toggle').setAttribute('aria-expanded', String(open));
  });
}

function initIntro() {
  const intro = $('#intro');
  const video = $('#intro-video');
  if (!intro || sessionStorage.getItem('fingaurdIntroSeen') === 'true') return;
  const desktop = '/static/videos/fingaurd-intro-desktop.mp4';
  const mobile = '/static/videos/fingaurd-intro-mobile.mp4';
  const source = window.matchMedia('(max-width: 768px)').matches ? mobile : desktop;
  let finished = false;
  const leave = () => {
    if (finished) return;
    finished = true;
    sessionStorage.setItem('fingaurdIntroSeen', 'true');
    video.pause();
    intro.dataset.handoff = 'true';
    setTimeout(() => { intro.dataset.leaving = 'true'; document.body.dataset.locked = 'false'; }, reducedMotion() ? 0 : 250);
    setTimeout(() => { intro.hidden = true; }, reducedMotion() ? 10 : 900);
  };
  video.src = source;
  intro.hidden = false;
  document.body.dataset.locked = 'true';
  $('#intro-skip').addEventListener('click', leave);
  video.addEventListener('timeupdate', () => { $('#intro-rule').style.width = `${video.duration ? video.currentTime / video.duration * 100 : 0}%`; });
  video.addEventListener('ended', leave);
  video.addEventListener('error', leave, { once: true });
  video.play().catch(leave);
}

function setHealth() {
  health().then((data) => {
    $('#health').dataset.state = 'online';
    $('#health-text').textContent = data.status === 'ok' ? 'Service online' : 'Service ready';
  }).catch(() => {
    $('#health').dataset.state = 'offline';
    $('#health-text').textContent = 'Service offline';
  });
}

function renderWork() {
  const slot = $('#work-slot');
  const plan = planFor(state.mode);
  $('#rail-title').textContent = state.mode === 'text' ? 'What this run will do' : 'What this scan will do';
  $('#rail-list').innerHTML = plan.map((stage, index) => `<li class="fg-rail__item"><span class="fg-rail__idx">${String(index + 1).padStart(2, '0')}</span><p><b>${esc(stage.label)}</b><br>${esc(stage.sub)}</p></li>`).join('');
  $$('.fg-mode').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.mode === state.mode)));
  if (state.mode === 'text') {
    slot.innerHTML = `<div class="fg-panel"><div class="fg-panel__body"><label class="fg-sr" for="scan-text">Text to analyse</label><textarea class="fg-textarea" id="scan-text" placeholder="Paste a financial message, claim, or social post..."></textarea><div class="fg-count"><span>Compliance reasoning input</span><span id="text-count">0 characters</span></div><div class="fg-file__actions" style="margin-top:1rem"><button class="fg-btn fg-file__go" id="text-start" type="button">Analyse text ${svg(icons.arrow, 'fg-btn__arrow')}</button></div></div></div>`;
    const textarea = $('#scan-text');
    textarea.value = state.text;
    textarea.addEventListener('input', () => { state.text = textarea.value; $('#text-count').textContent = `${state.text.length} characters`; });
    $('#text-start').addEventListener('click', () => { const check = validateText(state.text); if (!check.ok) return showError(check.message); startAnalysis(); });
    return;
  }
  if (state.mode === 'url') {
    slot.innerHTML = `<div class="fg-panel"><div class="fg-panel__body"><label class="fg-sr" for="scan-url">URL to audit</label><textarea class="fg-textarea" id="scan-url" style="min-height:70px;height:70px;padding:0.75rem 1rem;resize:none;" placeholder="https://groww-bonus-reward.xyz/login"></textarea><div class="fg-count"><span>Phishing & domain typosquatting check</span><span id="url-count">0 characters</span></div><div class="fg-file__actions" style="margin-top:1rem"><button class="fg-btn fg-file__go" id="url-start" type="button">Audit URL ${svg(icons.arrow, 'fg-btn__arrow')}</button></div></div></div>`;
    const urlInput = $('#scan-url');
    urlInput.value = state.urlText || '';
    urlInput.addEventListener('input', () => { state.urlText = urlInput.value; $('#url-count').textContent = `${state.urlText.length} characters`; });
    $('#url-start').addEventListener('click', () => {
      const val = (state.urlText || '').trim();
      if (!val || (!val.startsWith('http://') && !val.startsWith('https://') && !val.includes('.'))) {
        return showError('Enter a valid URL to audit (e.g. https://kite.zerodha.com).');
      }
      clearError();
      startAnalysis();
    });
    return;
  }
  const accept = (LIMITS[state.mode] || []).join(',');
  const dropDesc = state.mode === 'apk' ? 'Drop an Android .apk package file here, or browse your device.' : `Drop a ${state.mode} file here, or browse your device.`;
  slot.innerHTML = `<label class="fg-drop" id="drop" for="file-input"><input class="fg-drop__input" id="file-input" type="file" accept="${accept}"><span class="fg-drop__inner"><span class="fg-drop__mark">${svg(icons.upload)}</span><strong class="fg-drop__title">Upload ${state.mode === 'apk' ? 'APK package' : 'media'} for analysis</strong><span class="fg-drop__text">${dropDesc}</span><span class="fg-drop__formats">${(LIMITS[state.mode] || []).map((item) => `<span class="fg-drop__format">${item.slice(1)}</span>`).join('')}</span><span class="fg-drop__limit">Maximum 100 MB</span></span></label>`;
  const input = $('#file-input');
  const drop = $('#drop');
  input.addEventListener('change', () => chooseFile(input.files[0]));
  ['dragenter', 'dragover'].forEach((type) => drop.addEventListener(type, (event) => { event.preventDefault(); drop.dataset.dragging = 'true'; }));
  ['dragleave', 'drop'].forEach((type) => drop.addEventListener(type, (event) => { event.preventDefault(); drop.dataset.dragging = 'false'; }));
  drop.addEventListener('drop', (event) => chooseFile(event.dataTransfer.files[0]));
  if (state.file) renderFile();
}

function chooseFile(file) {
  const check = validateFile(state.mode, file);
  if (!check.ok) return showError(check.message);
  clearError();
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.file = file;
  state.previewUrl = file.type.startsWith('video/') || file.type.startsWith('audio/') || file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
  renderFile();
}

function renderFile() {
  if (!state.file) return;
  const media = state.mode === 'video'
    ? `<video src="${state.previewUrl}" controls muted></video>`
    : state.mode === 'audio'
      ? `<audio src="${state.previewUrl}" controls></audio>`
      : state.mode === 'image'
        ? `<img src="${state.previewUrl}" alt="Selected image preview">`
        : `<div class="fg-media__empty" style="padding:2rem 1rem;font-weight:600;">Android APK Package: ${esc(state.file.name)}</div>`;
  $('#work-slot').innerHTML = `<div class="fg-file"><div class="fg-file__preview">${media}</div><div class="fg-file__meta"><div class="fg-file__cell"><span class="fg-file__key">File</span><span class="fg-file__val" title="${esc(state.file.name)}">${esc(state.file.name)}</span></div><div class="fg-file__cell"><span class="fg-file__key">Type</span><span class="fg-file__val">${state.mode.toUpperCase()}</span></div><div class="fg-file__cell"><span class="fg-file__key">Size</span><span class="fg-file__val">${fmtBytes(state.file.size)}</span></div></div><div class="fg-file__actions"><button class="fg-btn fg-btn--ghost" id="remove-file" type="button">Remove</button><button class="fg-btn fg-file__go" id="start-file" type="button">Start analysis ${svg(icons.arrow, 'fg-btn__arrow')}</button></div></div>`;
  $('#remove-file').addEventListener('click', () => { state.file = null; renderWork(); });
  $('#start-file').addEventListener('click', startAnalysis);
}

function showError(message) { const node = $('#work-error'); node.hidden = false; node.className = 'fg-notice'; node.innerHTML = `${svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v5m0 3h.01">')}<span>${esc(message)}</span>`; }
function clearError() { const node = $('#work-error'); node.hidden = true; node.textContent = ''; }

function startAnalysis() {
  if (state.run) state.run.cancel();
  state.startedAt = new Date();
  state.jobId = null;
  state.viewModel = null;
  showRoute('/analysis');
  const payload = state.mode === 'text' ? state.text : state.mode === 'url' ? state.urlText : state.file;
  const plan = planFor(state.mode);
  const displayName = state.mode === 'text' ? 'Pasted text' : state.mode === 'url' ? state.urlText : state.file.name;
  setupAnalysis(plan, displayName);
  state.run = startRun(state.mode, payload, {
    onJob: (jobId) => { state.jobId = jobId; },
    onStage: (index, status) => updateStage(index, status, plan),
    onProgress: (fraction) => updateProgress(fraction),
    onStatus: (text) => { $('#core-status').textContent = text; $('#prog-label').textContent = text; },
    onDone: (raw) => finishAnalysis(raw),
    onError: (error) => failAnalysis(error),
  });
}

function setupAnalysis(plan, filename) {
  $('#analysis').dataset.done = 'false';
  $('#core-file').textContent = filename;
  $('#pipe-list').innerHTML = plan.map((stage) => `<li class="fg-stage" data-state="waiting"><span class="fg-stage__marker">${svg('')}</span><span><span class="fg-stage__label">${esc(stage.label)}</span><span class="fg-stage__sub">${esc(stage.sub)}</span></span></li>`).join('');
  $('#pipe-count').textContent = `0 / ${plan.length}`;
  $('#pipe-note').textContent = state.mode === 'video' ? 'Live stage state from the analysis service.' : 'Stage timing is estimated while the synchronous scan runs.';
  $('#prog-fill').style.width = '0%'; $('#prog-pct').textContent = '0%'; $('#prog-label').textContent = 'Preparing analysis'; $('#core-status').textContent = 'Preparing analysis';
  setupTipRotation(plan);
  animateCore($('#core-canvas'), 'core');
}

function updateStage(index, status, plan) {
  const items = $$('.fg-stage');
  if (!items[index]) return;
  items[index].dataset.state = status === 'failed' ? 'failed' : status;
  items[index].querySelector('.fg-stage__marker').innerHTML = status === 'done' ? svg(icons.check) : status === 'active' ? '<span class="fg-stage__dot"></span>' : svg('');
  const done = items.filter((item) => item.dataset.state === 'done').length;
  $('#pipe-count').textContent = `${done} / ${plan.length}`;
}

function updateProgress(fraction) {
  const percent = Math.round(fraction * 100);
  $('#prog-fill').style.width = `${percent}%`; $('#prog-pct').textContent = `${percent}%`; $('#core-pct').innerHTML = `${percent}<sup>%</sup>`;
  $('#prog-track').setAttribute('aria-valuenow', String(percent));
}

function setupTipRotation(plan) {
  const tips = [
    ['Pro tip', 'Pause before you act. Scammers often create urgency to stop you verifying the claim.', 'low'],
    ['Fraud alert', 'Guaranteed returns and limited-time offers deserve independent verification.', 'moderate'],
    ['Deepfake awareness', 'A realistic face or voice does not guarantee that the identity is authentic.', 'high'],
    ['What we are checking', `The pipeline is currently checking ${plan[0]?.sub.toLowerCase() || 'the submitted media'}.`, 'low'],
  ];
  let index = 0;
  const paint = () => { const tip = $('#tip'); tip.dataset.swap = 'true'; setTimeout(() => { const item = tips[index % tips.length]; $('#tip-kind').textContent = item[0]; $('#tip-title').textContent = item[0] === 'What we are checking' ? 'Pipeline signal' : item[0]; $('#tip-text').textContent = item[1]; tip.dataset.tier = item[2]; $('#tip-dots').innerHTML = tips.map((_, i) => `<span class="fg-tip__dot" data-on="${i === index % tips.length}"></span>`).join(''); tip.dataset.swap = 'false'; index += 1; }, reducedMotion() ? 0 : 260); };
  paint();
  clearInterval(state.tipTimer); state.tipTimer = setInterval(paint, 6000);
}

function finishAnalysis(raw) {
  clearInterval(state.tipTimer);
  updateProgress(1);
  $('#analysis').dataset.done = 'true';
  $('#core-status').textContent = 'Analysis complete';
  setTimeout(() => {
    try {
      state.viewModel = toViewModel(raw, {
        mode: state.mode,
        filename: state.mode === 'text' ? 'Pasted text' : state.file?.name,
        jobId: state.jobId,
        size: state.file?.size,
        startedAt: state.startedAt,
      });
      showRoute('/results');
    } catch (err) {
      console.error('Error rendering results view model:', err);
      showRoute('/results');
    }
  }, reducedMotion() ? 0 : 500);
}

function failAnalysis(error) { clearInterval(state.tipTimer); $('#core-status').textContent = 'Analysis could not finish'; showRoute('/analyze'); showError(error?.message || 'The analysis service could not finish this run.'); }

function tierStyle(tier) { return tier === 'critical' ? 'crit' : tier === 'high' ? 'risk' : tier === 'moderate' ? 'warn' : tier === 'low' ? 'safe' : 'flat'; }
function renderResults(vm) {
  const score = vm.peakSignal === null ? null : fmtScore(vm.peakSignal);
  const modeLabel = vm.mode === 'text' ? 'Text scan' : `${vm.mode} scan`;
  $('#results').innerHTML = `<div class="fg-band-head"><p class="fg-eyebrow">Forensic report · ${esc(modeLabel)}</p><h2 class="fg-h2">Analysis result</h2></div><section class="fg-verdict" data-tier="${vm.tier.key}"><div class="fg-verdict__grid"><div class="fg-verdict__copy"><p class="fg-eyebrow fg-eyebrow--plain">Overall risk level</p><h3 class="fg-verdict__tier">${esc(vm.tier.label)}</h3><span class="fg-verdict__code">${esc(vm.verdict)}</span><p class="fg-verdict__summary">${esc(vm.summary)}</p><div class="fg-verdict__stamps"><span class="fg-verdict__stamp">File <b>${esc(vm.filename || 'Pasted text')}</b></span><span class="fg-verdict__stamp">Analysed <b>${fmtStamp(vm.startedAt)}</b></span></div></div><div class="fg-verdict__gauge"><canvas id="verdict-gauge"></canvas><div class="fg-verdict__gauge-read"><span class="fg-verdict__score">${score ?? '—'}<small>%</small></span><span class="fg-verdict__score-label">Peak signal</span></div></div></div><div class="fg-verdict__actions"><button class="fg-btn" data-route="/analyze">Analyse another ${svg(icons.arrow, 'fg-btn__arrow')}</button>${vm.complaint ? `<a class="fg-btn fg-btn--ghost" href="${complaintUrl(vm.jobId)}" download>Download complaint draft</a>` : ''}</div></section><section><div class="fg-band-head"><p class="fg-eyebrow">Signal breakdown</p><h2 class="fg-h2">What the pipeline found</h2></div><div class="fg-breakdown">${vm.categories.map(renderCategory).join('')}</div></section><section><div class="fg-band-head"><p class="fg-eyebrow">Evidence</p><h2 class="fg-h2">Read the findings in context.</h2></div><div class="fg-disclose" id="evidence-list">${vm.evidence.length ? vm.evidence.map(renderEvidence).join('') : `<div class="fg-blank"><span class="fg-blank__mark">${svg(icons.shield)}</span><h3>No evidence items were raised</h3><p>No detector returned a finding that requires an evidence item. Review the category scores and transcript before deciding.</p></div>`}</div></section>${renderForensics(vm)}<div class="fg-results__end"><button class="fg-btn fg-btn--ghost" data-route="/analyze">Start a new analysis</button></div>`;
  drawGauge($('#verdict-gauge'), vm.peakSignal, vm.tier.key);
  bindDisclosure(); bindTranscript(vm); bindMedia(vm);
}

function renderCategory(category) {
  const value = category.score === null ? 0 : Math.round(category.score * 100);
  return `<article class="fg-cat" data-tier="${category.tier}"><div class="fg-cat__top"><h3 class="fg-cat__name">${esc(category.name)}</h3><div class="fg-cat__score"><b>${category.score === null ? '—' : `${value}%`}</b><span>${esc(category.status)}</span></div><div class="fg-cat__bar"><i style="width:${value}%"></i></div></div><p class="fg-cat__text">${esc(category.text)}</p><div class="fg-cat__foot"><span>${category.count} evidence item${category.count === 1 ? '' : 's'}</span>${category.detail.length ? `<button class="fg-btn fg-btn--text fg-cat__more" type="button" data-detail="${esc(category.id)}">Details ${svg(icons.chevron)}</button>` : ''}</div></article>`;
}

function renderEvidence(item) {
  return `<div class="fg-disclose__row" data-tier="${item.tier}"><button class="fg-disclose__btn" type="button" aria-expanded="false"><span class="fg-disclose__kind">${esc(item.kind)}</span><span class="fg-disclose__title">${esc(item.title)}</span><span class="fg-disclose__at">${item.at === null ? '—' : fmtClock(item.at)}</span>${svg(icons.chevron, 'fg-disclose__chev')}</button><div class="fg-disclose__body" hidden><p>${esc(item.body)}</p>${item.quote ? `<blockquote class="fg-quote">${esc(item.quote)}</blockquote>` : ''}${item.kv ? `<dl class="fg-kv">${item.kv.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>` : ''}</div></div>`;
}

function bindDisclosure() { $$('.fg-disclose__btn').forEach((button) => button.addEventListener('click', () => { const body = button.nextElementSibling; const open = button.getAttribute('aria-expanded') === 'true'; button.setAttribute('aria-expanded', String(!open)); body.hidden = open; })); }

function renderForensics(vm) {
  const mediaSource = state.file && state.previewUrl ? (state.mode === 'video' ? `<video src="${state.previewUrl}" controls></video>` : state.mode === 'audio' ? `<audio src="${state.previewUrl}" controls></audio>` : `<img src="${state.previewUrl}" alt="Analysed image">`) : '<div class="fg-media__empty">Media preview is available in this browser session only.</div>';
  const media = vm.mode === 'text' ? '' : `<section class="fg-panel"><div class="fg-panel__head"><h3>Submitted media</h3></div><div class="fg-media__stage">${mediaSource}</div></section>`;
  const transcript = vm.transcript.length ? vm.transcript.map((line, index) => `<button class="fg-line" data-start="${line.start}" data-line="${index}" ${line.flag ? `data-flag="${line.flag}"` : ''}><span class="fg-line__at">${fmtClock(line.start)}</span><span class="fg-line__text">${esc(line.text)}${line.flagLabel ? `<span class="fg-line__mark" data-tier="${line.flagTier}">${esc(line.flagLabel)}</span>` : ''}</span></button>`).join('') : `<div class="fg-blank"><h3>No timestamped transcript</h3><p>This scan did not return timestamped speech segments.</p></div>`;
  return `<section><div class="fg-band-head"><p class="fg-eyebrow">Media evidence</p><h2 class="fg-h2">Inspect the timeline and transcript.</h2></div><div class="fg-forensics">${media}<section class="fg-panel"><div class="fg-panel__head"><h3>Interactive transcript</h3></div><div class="fg-transcript" id="transcript">${transcript}</div></section></div></section>`;
}

function bindTranscript(vm) { $$('.fg-line').forEach((line) => line.addEventListener('click', () => { $$('.fg-line').forEach((item) => item.dataset.playing = 'false'); line.dataset.playing = 'true'; })); }
function bindMedia() { /* Media URLs are intentionally not returned by the backend after its purge. */ }

function animateCore(canvas, kind) {
  if (!canvas) return;
  const stop = whileVisible(canvas, (time) => { const { ctx, w, h } = fitCanvas(canvas); const cx = w / 2; const cy = h / 2; const radius = Math.min(w, h) * 0.32; ctx.clearRect(0, 0, w, h); ctx.strokeStyle = 'rgba(11,107,79,.14)'; ctx.lineWidth = 1; for (let i = 0; i < 3; i += 1) { ctx.beginPath(); ctx.arc(cx, cy, radius + i * 30 + Math.sin(time / 1800 + i) * 3, 0, Math.PI * 2); ctx.stroke(); } ctx.strokeStyle = 'rgba(11,107,79,.5)'; ctx.beginPath(); ctx.moveTo(cx, cy - radius); ctx.lineTo(cx + radius * .72, cy - radius * .2); ctx.lineTo(cx + radius * .45, cy + radius); ctx.lineTo(cx - radius * .45, cy + radius); ctx.lineTo(cx - radius * .72, cy - radius * .2); ctx.closePath(); ctx.stroke(); ctx.fillStyle = 'rgba(11,107,79,.05)'; ctx.fill(); if (!reducedMotion()) { ctx.fillStyle = '#0B6B4F'; const angle = time / (kind === 'core' ? 1900 : 2400); ctx.beginPath(); ctx.arc(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, 3, 0, Math.PI * 2); ctx.fill(); } });
  canvas.dataset.stop = stop;
}

function drawGauge(canvas, value, tier) {
  if (!canvas) return;
  const { ctx, w, h } = fitCanvas(canvas); const cx = w / 2; const cy = h / 2; const r = Math.min(w, h) * .38; const colors = { low: '#0B6B4F', moderate: '#A8730B', high: '#B33A2B', critical: '#8A1F14', unknown: '#A3ADA8' }; ctx.clearRect(0, 0, w, h); ctx.lineWidth = 9; ctx.strokeStyle = '#E4E9E6'; ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI * .75, Math.PI * .75); ctx.stroke(); if (value !== null) { ctx.strokeStyle = colors[tier] || colors.unknown; ctx.beginPath(); ctx.arc(cx, cy, r, -Math.PI * .75, -Math.PI * .75 + Math.PI * 1.5 * value); ctx.stroke(); } }

function renderTechnology() { $('#tech-stages').innerHTML = TECHNOLOGY_STAGES.map((stage) => `<li class="fg-disclose__row"><button class="fg-disclose__btn" type="button" aria-expanded="false"><span class="fg-disclose__kind">${stage.n}</span><span class="fg-disclose__title">${esc(stage.title)}</span><span class="fg-disclose__at">${esc(stage.out)}</span>${svg(icons.chevron, 'fg-disclose__chev')}</button><div class="fg-disclose__body" hidden><p>${esc(stage.body)}</p></div></li>`).join(''); bindDisclosure(); }

bindNavigation();
renderTechnology();
$$('.fg-mode').forEach((button) => button.addEventListener('click', () => { state.mode = button.dataset.mode; state.file = null; state.text = ''; clearError(); renderWork(); }));
showRoute(state.route);
setHealth();
initIntro();
animateCore($('#hero-canvas'), 'hero');
animateCore($('#cta-canvas'), 'cta');