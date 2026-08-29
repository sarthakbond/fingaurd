/* ============================================================================
   Transport layer — the only module that talks to the backend.
   ----------------------------------------------------------------------------
   Endpoints, verbatim from app.py:

     POST /api/jobs                  multipart `file`  → {job_id, status}
     GET  /api/jobs/{job_id}                           → {status, stage, result?}
     GET  /api/jobs/{job_id}/complaint                 → text/plain
     POST /api/scan/audio            multipart `file`  → full result (synchronous)
     POST /api/scan/image            multipart `file`  → full result (synchronous)
     POST /api/scan/text             json {text}       → full result (synchronous)
     GET  /api/health                                  → {status, version, service}

   Nothing else exists. If you need a capability that isn't here, add it to the
   backend first.
   ========================================================================= */

import { ext } from './dom.js';
import { planFor } from './stages.js';

/* Mirrors MAX_UPLOAD_SIZE and the extension allowlists in app.py exactly. */
export const LIMITS = {
  maxBytes: 100 * 1024 * 1024,
  video: ['.mp4', '.avi', '.mov', '.mkv'],
  audio: ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'],
  image: ['.jpg', '.jpeg', '.png', '.webp', '.bmp'],
  apk: ['.apk'],
  minTextChars: 5,
};

/** True when the service reports live progress per stage. Only video does. */
export const hasLiveStages = (mode) => mode === 'video';

class ServiceError extends Error {
  constructor(message, status) { super(message); this.name = 'ServiceError'; this.status = status; }
}

async function readError(response) {
  let detail = '';
  try {
    const body = await response.json();
    detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
  } catch { detail = await response.text().catch(() => ''); }
  return new ServiceError(detail || `Request failed (${response.status})`, response.status);
}

async function asJson(response) {
  if (!response.ok) throw await readError(response);
  return response.json();
}

/* ── Endpoints ───────────────────────────────────────────────────────────── */

export async function health() {
  const res = await fetch('/api/health', { cache: 'no-store' });
  return asJson(res);
}

async function postFile(path, file, signal) {
  const form = new FormData();
  form.append('file', file, file.name);
  return asJson(await fetch(path, { method: 'POST', body: form, signal }));
}

export const createVideoJob = (file, signal) => postFile('/api/jobs', file, signal);
export const scanAudio      = (file, signal) => postFile('/api/scan/audio', file, signal);
export const scanImage      = (file, signal) => postFile('/api/scan/image', file, signal);
export const scanApk        = (file, signal) => postFile('/api/scan/apk', file, signal);

export async function scanText(text, signal) {
  return asJson(await fetch('/api/scan/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal,
  }));
}

export async function scanUrl(url, signal) {
  return asJson(await fetch('/api/scan/url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal,
  }));
}

export async function getJob(jobId, signal) {
  return asJson(await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store', signal }));
}

/** Video jobs expose the complaint draft as a downloadable plain-text route. */
export const complaintUrl = (jobId) => `/api/jobs/${encodeURIComponent(jobId)}/complaint`;

/* ── Client-side validation ──────────────────────────────────────────────── */

export function validateFile(mode, file) {
  const allowed = LIMITS[mode];
  if (!allowed) return { ok: false, message: `No upload for ${mode}.` };
  if (!file) return { ok: false, message: 'Choose a file to analyse.' };

  const e = ext(file.name);
  if (!allowed.includes(e)) {
    return {
      ok: false,
      message: `${e || 'That file'} isn't a supported ${mode} format. Use ${allowed.join(', ')}.`,
    };
  }
  if (file.size > LIMITS.maxBytes) {
    return {
      ok: false,
      message: `That file is ${(file.size / 1048576).toFixed(0)} MB. The analysis service accepts up to 100 MB.`,
    };
  }
  if (file.size === 0) return { ok: false, message: 'That file is empty.' };
  return { ok: true };
}

export function validateText(text) {
  const trimmed = (text || '').trim();
  if (trimmed.length < LIMITS.minTextChars) {
    return { ok: false, message: `Paste at least ${LIMITS.minTextChars} characters to analyse.` };
  }
  return { ok: true };
}

/* ══════════════════════════════════════════════════════════════════════════
   Run orchestration
   --------------------------------------------------------------------------
   One interface over two very different backend behaviours:

     video  — asynchronous. A job id is returned immediately and
              GET /api/jobs/{id} reports the stage currently executing. Stage
              transitions here are REAL.

     audio, image, text — synchronous. The request returns once, at the end,
              with no intermediate signal. Stage timing is therefore ESTIMATED,
              and the UI says so. If these endpoints ever gain a job id and a
              status route, delete `estimatedSource` and route them through
              `pollingSource` instead — nothing else needs to change.
   ═══════════════════════════════════════════════════════════════════════ */

/** Cumulative weight boundaries, normalised to 0..1. */
function boundaries(plan) {
  const total = plan.reduce((sum, s) => sum + s.weight, 0) || 1;
  let acc = 0;
  return plan.map((s) => { acc += s.weight; return acc / total; });
}

/**
 * Approaches `cap` without ever reaching it. Used for progress inside a stage
 * of unknown duration — it keeps moving, and it never lies about being nearly
 * finished.
 */
const approach = (elapsedMs, tauMs, cap) => cap * (1 - Math.exp(-elapsedMs / tauMs));

/**
 * @param {'video'|'audio'|'image'|'text'} mode
 * @param {File|string} payload         file, or the text to scan
 * @param {object} handlers  {onStage, onProgress, onStatus, onDone, onError}
 * @returns {{cancel: () => void}}
 */
export function startRun(mode, payload, handlers) {
  const plan = planFor(mode);
  const bounds = boundaries(plan);
  const controller = new AbortController();
  let stopped = false;

  const emit = {
    stage: (index, state) => handlers.onStage?.(index, state),
    progress: (fraction) => handlers.onProgress?.(Math.max(0, Math.min(1, fraction))),
    status: (text) => handlers.onStatus?.(text),
  };

  const finish = (raw) => { if (!stopped) { stopped = true; handlers.onDone?.(raw); } };
  const fail = (error) => {
    if (stopped) return;
    stopped = true;
    if (error?.name === 'AbortError') return;
    handlers.onError?.(error);
  };

  /* ── Real stage feed (video) ───────────────────────────────────────────── */
  async function pollingSource() {
    const { job_id: jobId } = await createVideoJob(payload, controller.signal);
    handlers.onJob?.(jobId);

    let index = 0;
    let stageEnteredAt = performance.now();
    emit.stage(0, 'active');
    emit.status(plan[0].status);

    const tick = async () => {
      if (stopped) return;
      let job;
      try {
        job = await getJob(jobId, controller.signal);
      } catch (error) {
        // A single dropped poll shouldn't end the run; keep trying.
        if (error?.status === 404) return fail(error);
        if (error?.name === 'AbortError') return;
        setTimeout(tick, 2500);
        return;
      }

      const reported = plan.findIndex((s) => s.key === job.stage);
      if (reported > index) {
        for (let i = index; i < reported; i += 1) emit.stage(i, 'done');
        index = reported;
        stageEnteredAt = performance.now();
        emit.stage(index, 'active');
        emit.status(plan[index].status);
      }

      // Progress: settled stage boundaries, plus a decaying creep inside the
      // stage now running. Never crosses into the next stage's territory.
      const floor = index === 0 ? 0 : bounds[index - 1];
      const ceiling = bounds[index];
      const gap = ceiling - floor;
      emit.progress(floor + approach(performance.now() - stageEnteredAt, 14000, gap * 0.88));

      if (job.status === 'completed' && job.result) {
        plan.forEach((_, i) => emit.stage(i, 'done'));
        emit.progress(1);
        return finish(job.result);
      }
      if (job.status === 'failed') {
        emit.stage(index, 'failed');
        return fail(new ServiceError(job.error || 'The analysis service could not finish this job.', 500));
      }
      setTimeout(tick, 1400);
    };

    setTimeout(tick, 700);
  }

  /* ── Estimated stage feed (synchronous endpoints) ──────────────────────── */
  function estimatedSource(request) {
    const startedAt = performance.now();
    const totalWeight = plan.reduce((sum, s) => sum + s.weight, 0);
    const tau = Math.max(12000, totalWeight * 2400);
    const cap = 0.93;
    let index = -1;

    const advance = () => {
      if (stopped) return;
      const fraction = approach(performance.now() - startedAt, tau, cap);
      emit.progress(fraction);

      let next = bounds.findIndex((b) => fraction < b);
      if (next === -1) next = plan.length - 1;
      if (next > index) {
        for (let i = Math.max(index, 0); i < next; i += 1) emit.stage(i, 'done');
        index = next;
        emit.stage(index, 'active');
        emit.status(plan[index].status);
      }
      timer = setTimeout(advance, 420);
    };

    let timer = setTimeout(advance, 60);
    index = 0;
    emit.stage(0, 'active');
    emit.status(plan[0].status);

    request(controller.signal)
      .then((result) => {
        clearTimeout(timer);
        plan.forEach((_, i) => emit.stage(i, 'done'));
        emit.progress(1);
        finish(result);
      })
      .catch((error) => { clearTimeout(timer); fail(error); });
  }

  const run = {
    video: pollingSource,
    audio: () => estimatedSource((signal) => scanAudio(payload, signal)),
    image: () => estimatedSource((signal) => scanImage(payload, signal)),
    text:  () => estimatedSource((signal) => scanText(payload, signal)),
    apk:   () => estimatedSource((signal) => scanApk(payload, signal)),
    url:   () => estimatedSource((signal) => scanUrl(payload, signal)),
  }[mode];

  Promise.resolve().then(run).catch(fail);

  return {
    cancel() {
      if (stopped) return;
      stopped = true;
      controller.abort();
    },
  };
}
