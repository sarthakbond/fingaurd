/* ============================================================================
   Adapter — raw backend payload → view model.
   ----------------------------------------------------------------------------
   Presentation code reads only what this module returns, so a change in the
   backend's response shape is a change to this one file.

   Every field read here exists in the payloads assembled by app.py. Where a
   scan type does not produce a signal (there is no visual score in an audio
   scan) the category is marked unavailable rather than filled with a zero,
   because a zero would read as "clean" when it means "not examined".
   ========================================================================= */

import { fmtClock } from './dom.js';

/* ── Verdict → risk tier ─────────────────────────────────────────────────── */

const TIERS = {
  critical: { key: 'critical', label: 'Critical risk', rank: 4 },
  high:     { key: 'high',     label: 'High risk',     rank: 3 },
  moderate: { key: 'moderate', label: 'Moderate risk', rank: 2 },
  low:      { key: 'low',      label: 'Low risk',      rank: 1 },
  unknown:  { key: 'unknown',  label: 'Inconclusive',  rank: 0 },
};

/** app.py's calculate_calibrated_verdict emits exactly four prefixes. */
export function tierFromVerdict(verdict) {
  const v = String(verdict || '').toLowerCase();
  if (v.startsWith('critical')) return TIERS.critical;
  if (v.startsWith('warning')) return TIERS.high;
  if (v.startsWith('suspicious')) return TIERS.moderate;
  if (v.startsWith('safe')) return TIERS.low;
  return TIERS.unknown;
}

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const arr = (v) => (Array.isArray(v) ? v.filter(Boolean) : []);

/** Detector scores: 0.5 is the configured threshold in config.yaml. */
function detectorTier(score) {
  if (score === null) return 'unknown';
  if (score >= 0.5) return 'high';
  if (score >= 0.3) return 'moderate';
  return 'low';
}

/** Composite scam score: 0.45 is the backend's auto-flag threshold. */
function scamTier(score, isScam) {
  if (score === null) return 'unknown';
  if (isScam || score >= 0.45) return 'high';
  if (score >= 0.3) return 'moderate';
  return 'low';
}

const REGISTRY_READING = {
  'verified':             { tier: 'low',      label: 'Verified',              text: 'The claimed identity matches a registered entry in the registry.' },
  'not claimed':          { tier: 'unknown',  label: 'No claim made',         text: 'No advisor name or registration number was claimed, so there was nothing to verify. Absence of a claim is not the same as being registered.' },
  'not found':            { tier: 'high',     label: 'Not in registry',       text: 'The claimed identity does not appear in the registry. Advertising investment advice without registration is itself a violation.' },
  'malformed number':     { tier: 'high',     label: 'Malformed number',      text: 'The registration number does not match the format SEBI issues, so it cannot be a valid registration.' },
  'name-number mismatch': { tier: 'critical', label: 'Registered elsewhere',  text: 'The registration number is real but belongs to a different entity. Borrowing a genuine number is a deliberate misrepresentation, not a clerical slip.' },
};

/* ── Scam signal labels (keys come from SIGNAL_WEIGHTS in stage5_llm.py) ─── */

export const SIGNAL_LABELS = {
  explicit_returns:  'Guaranteed returns',
  implied_returns:   'Implied returns',
  urgency_scarcity:  'Urgency and scarcity',
  social_proof:      'Inflated social proof',
  paywall_push:      'Paywall push',
  credential_misrep: 'Credential misrepresentation',
};

/* ── Quoted-claim groups (fields come from the SEBIAnalysis model) ───────── */

const CLAIM_GROUPS = [
  {
    field: 'specific_return_promises', kind: 'Guaranteed return', tier: 'high', flag: 'explicit_return',
    why: 'A promised or assured return is the clearest marker of unregistered investment advice. No registered adviser may guarantee a market outcome.',
  },
  {
    field: 'implied_returns', kind: 'Implied return', tier: 'moderate', flag: 'implied_return',
    why: 'A return implied without being promised outright sets the same expectation while leaving room to deny it later.',
  },
  {
    field: 'urgency_scarcity_language', kind: 'Urgency', tier: 'moderate', flag: 'urgency',
    why: 'Deadlines and limited spots exist to stop you verifying. Legitimate advice survives a delay.',
  },
  {
    field: 'social_proof_inflation', kind: 'Social proof', tier: 'moderate', flag: null,
    why: 'Member counts and testimonials are cheap to fabricate and are used to substitute for a track record.',
  },
  {
    field: 'paywall_push', kind: 'Paywall push', tier: 'moderate', flag: 'paywall',
    why: 'Charging for advice is what registration governs. A push to a paid channel is where an unregistered operator takes payment.',
  },
  {
    field: 'credential_misrepresentation', kind: 'Credentials', tier: 'high', flag: null,
    why: 'An overstated or invented credential is intended to borrow authority the speaker has not earned.',
  },
];

/* ── Timestamp resolution ────────────────────────────────────────────────── */

/**
 * The backend already timestamps flagged quotes in `timeline_track`. Prefer
 * that; fall back to a substring search across transcript segments.
 */
function buildQuoteClock(raw) {
  const index = new Map();
  for (const entry of arr(raw.timeline_track)) {
    if (entry.quote) index.set(String(entry.quote).trim().toLowerCase(), entry.start);
  }
  const segments = arr(raw.segments);
  return (quote) => {
    const key = String(quote || '').trim().toLowerCase();
    if (!key) return null;
    if (index.has(key)) return index.get(key);
    const hit = segments.find((s) => {
      const text = String(s.text || '').toLowerCase();
      return text.includes(key) || (key.length > 12 && key.includes(text) && text.length > 6);
    });
    return hit ? hit.start : null;
  };
}

/* ── Main adapter ────────────────────────────────────────────────────────── */

/**
 * @param {object} raw    the payload from any of the four scan endpoints
 * @param {object} meta   {mode, filename, jobId, size, startedAt}
 */
export function toViewModel(raw, meta = {}) {
  const sebi = raw.sebi_analysis || {};
  const registry = raw.registry_check || {};
  const impersonation = raw.impersonation_check || {};
  const tier = tierFromVerdict(raw.verdict);
  const clockFor = buildQuoteClock(raw);

  const visionScore = num(raw.vision_score);
  const audioScore = num(raw.audio_score);
  const scamScore = num(raw.composite_risk_score);
  const flaggedAudio = arr(raw.flagged_audio_segments);
  const audioSegments = arr(raw.all_audio_segments);
  const isScam = Boolean(raw.is_scam);

  /* Peak signal: the strongest single detector reading. This mirrors how the
     backend actually escalates — any one detector crossing its threshold
     raises the verdict — so the headline number is the loudest signal, not an
     average that would bury it. */
  const signalInputs = [
    { key: 'Visual', value: visionScore },
    { key: 'Voice', value: audioScore },
    { key: 'Scam composite', value: scamScore },
  ].filter((s) => s.value !== null);
  const peakSignal = signalInputs.length ? Math.max(...signalInputs.map((s) => s.value)) : null;

  /* ── Categories ───────────────────────────────────────────────────────── */
  const categories = [];

  // 1 · Visual authenticity
  if (visionScore === null) {
    categories.push({
      id: 'visual', name: 'Visual authenticity', score: null, tier: 'unknown',
      status: 'Not examined', stage: 'Stage 02 · vision',
      text: 'This scan type carries no video frames, so the visual detector did not run.',
      count: 0, detail: [],
    });
  } else {
    const noFaces = visionScore === 0 && !raw.heatmap_base64;
    categories.push({
      id: 'visual',
      name: 'Visual authenticity',
      score: visionScore,
      tier: noFaces ? 'unknown' : detectorTier(visionScore),
      status: noFaces ? 'No face scored' : (visionScore >= 0.5 ? 'Manipulation indicated' : 'No manipulation indicated'),
      stage: 'Stage 02 · vision',
      text: noFaces
        ? 'No face region was scored. Either no face was detected in the sampled frames, or nothing registered above zero.'
        : visionScore >= 0.5
          ? 'Face regions scored above the manipulation threshold. Inspect the noise-residual heatmap before drawing a conclusion.'
          : 'Sampled face regions scored below the manipulation threshold.',
      count: raw.heatmap_base64 ? 1 : 0,
      detail: [
        ['Peak frame score', visionScore === null ? '—' : `${(visionScore * 100).toFixed(1)}%`],
        ['Threshold', '50.0%'],
        num(raw.vision_temporal_variance) !== null
          ? ['Temporal variance', raw.vision_temporal_variance.toFixed(4)] : null,
        raw.backup_provider ? ['Scored by', raw.backup_provider] : null,
      ].filter(Boolean),
    });
  }

  // 2 · Voice authenticity
  if (audioScore === null) {
    categories.push({
      id: 'voice', name: 'Voice authenticity', score: null, tier: 'unknown',
      status: 'Not examined', stage: 'Stage 03 · audio',
      text: 'This scan type carries no audio track, so the voice detector did not run.',
      count: 0, detail: [],
    });
  } else {
    const noAudio = audioSegments.length === 0;
    categories.push({
      id: 'voice',
      name: 'Voice authenticity',
      score: audioScore,
      tier: noAudio ? 'unknown' : detectorTier(audioScore),
      status: noAudio ? 'No audio scored' : (audioScore >= 0.5 ? 'Synthetic speech indicated' : 'No synthesis indicated'),
      stage: 'Stage 03 · audio',
      text: noAudio
        ? 'No audio windows were scored. The track may be silent or absent.'
        : audioScore >= 0.5
          ? `${flaggedAudio.length} of ${audioSegments.length} audio windows scored above the spoof threshold.`
          : `All ${audioSegments.length} audio windows scored below the spoof threshold.`,
      count: flaggedAudio.length,
      detail: [
        ['Peak window score', `${(audioScore * 100).toFixed(1)}%`],
        ['Threshold', '50.0%'],
        ['Windows scored', String(audioSegments.length)],
        ['Windows flagged', String(flaggedAudio.length)],
        impersonation.target ? ['Name matched', impersonation.target] : null,
      ].filter(Boolean),
    });
  }

  // 3 · Financial scam risk
  const signalScores = sebi.signal_scores && typeof sebi.signal_scores === 'object' ? sebi.signal_scores : {};
  const quotedCount = CLAIM_GROUPS.reduce((n, g) => n + arr(sebi[g.field]).length, 0);
  categories.push({
    id: 'scam',
    name: 'Financial scam risk',
    score: scamScore,
    tier: scamTier(scamScore, isScam),
    status: sebi.prompt_injection_detected ? 'Tampering detected'
      : isScam ? 'Scam indicators present'
      : scamScore === null ? 'Not examined'
      : 'No scam pattern flagged',
    stage: 'Stage 05 · compliance',
    text: sebi.prompt_injection_detected
      ? 'The content tried to instruct the compliance model to mark itself safe. That attempt is itself treated as evidence of fraud.'
      : quotedCount > 0
        ? `${quotedCount} quoted claim${quotedCount === 1 ? '' : 's'} matched one or more of the six weighted scam signals.`
        : scamScore === null
          ? 'No transcript or text reached the compliance stage.'
          : 'No quoted claim matched a scam signal.',
    count: quotedCount,
    detail: Object.entries(SIGNAL_LABELS)
      .filter(([key]) => key in signalScores)
      .map(([key, label]) => [label, `${Math.round((signalScores[key] || 0) * 100)}%`]),
  });

  // 4 · SEBI / entity verification
  const registryVerdict = String(registry.verdict || 'not claimed');
  const reading = REGISTRY_READING[registryVerdict] || { tier: 'unknown', label: registryVerdict, text: 'The registry check returned an unrecognised state.' };
  const matched = registry.matched_entity || null;
  categories.push({
    id: 'sebi',
    name: 'SEBI verification',
    score: null,
    tier: reading.tier,
    status: reading.label,
    stage: 'Stage 06 · registry',
    text: reading.text,
    count: matched ? 1 : 0,
    detail: [
      sebi.claimed_advisor_name ? ['Claimed name', sebi.claimed_advisor_name] : null,
      sebi.claimed_registration_number ? ['Claimed number', sebi.claimed_registration_number] : null,
      matched?.name ? ['Registered to', matched.name] : null,
      matched?.registration_number ? ['Registry number', matched.registration_number] : null,
      matched?.category || matched?.type ? ['Category', matched.category || matched.type] : null,
      ['Outcome', registryVerdict],
    ].filter(Boolean),
  });

  /* ── Evidence ─────────────────────────────────────────────────────────── */
  const evidence = [];
  let seq = 0;
  const push = (item) => { seq += 1; evidence.push({ id: `E${String(seq).padStart(2, '0')}`, ...item }); };

  const quality = raw.input_quality || {};
  if (quality.rating && quality.rating !== 'Unknown') {
    push({
      kind: 'Input Quality', tier: quality.compression_flag ? 'moderate' : 'low', stage: 'Stage 01 · ingest',
      title: `Media Quality: ${quality.rating}`,
      body: `Video input assessed at ${quality.resolution || 'standard resolution'} with Laplacian sharpness index of ${quality.sharpness_score || 0}. ${quality.compression_flag ? 'Heavy compression artifacts detected; calibrated ensemble thresholds applied to maintain forensic sensitivity.' : 'Image clarity is sufficient for high-confidence forensic extraction.'}`,
      quote: null, at: null,
      kv: [
        ['Resolution', quality.resolution || 'N/A'],
        ['Sharpness Score', String(quality.sharpness_score || 0)],
        ['Quality Rating', quality.rating],
      ],
    });
  }

  if (sebi.prompt_injection_detected) {
    push({
      kind: 'Tampering', tier: 'critical', stage: 'Stage 05 · compliance',
      title: 'Attempt to manipulate the compliance scanner',
      body: 'The submitted content contained instructions aimed at the analysis model — telling it to ignore its rules or to report the content as safe. Legitimate media has no reason to address the scanner. FinGuard treats the attempt as a direct fraud indicator and escalates on it.',
      quote: arr(sebi.credential_misrepresentation).find((q) => /adversarial|injection/i.test(q)) || null,
      at: null,
    });
  }

  if (visionScore !== null && visionScore >= 0.5) {
    push({
      kind: 'Visual', tier: visionScore >= 0.75 ? 'critical' : 'high', stage: 'Stage 02 · vision',
      title: `Face regions scored ${(visionScore * 100).toFixed(1)}% for manipulation`,
      body: `The peak-scoring frame exceeded the 50% manipulation threshold.${num(raw.vision_temporal_variance) !== null ? ` Score variance across sampled frames was ${raw.vision_temporal_variance.toFixed(4)} — high variance suggests the manipulation is not present throughout the clip.` : ''} The noise-residual heatmap below shows which regions drove the score.`,
      quote: null, at: null,
    });
  }

  if (impersonation.is_impersonation && impersonation.warning) {
    push({
      kind: 'Impersonation', tier: 'critical', stage: 'Stage 03 · audio',
      title: `Possible voice clone of ${impersonation.target || 'a known name'}`,
      body: `${impersonation.warning} A recognised finance personality is named in the speech while the voice itself scores as synthetic — the combination is the signature of a cloned-voice endorsement.`,
      quote: null, at: null,
    });
  }

  for (const seg of flaggedAudio) {
    push({
      kind: 'Voice', tier: (seg.score ?? 0) >= 0.75 ? 'high' : 'moderate', stage: 'Stage 03 · audio',
      title: `Audio window scored ${Math.round((seg.score ?? 0) * 100)}% synthetic`,
      body: `The window from ${fmtClock(seg.start)} to ${fmtClock(seg.end)} scored above the spoof threshold. Isolated windows can indicate a spliced insert rather than a wholly synthetic track — play the segment and listen for a change in room tone.`,
      quote: null, at: num(seg.start),
    });
  }

  for (const group of CLAIM_GROUPS) {
    for (const quote of arr(sebi[group.field])) {
      push({
        kind: group.kind, tier: group.tier, stage: 'Stage 05 · compliance',
        title: group.kind === 'Credentials' ? 'Credential claim flagged' : `${group.kind} language quoted`,
        body: group.why, quote, at: clockFor(quote),
      });
    }
  }

  if (reading.tier !== 'low' && reading.tier !== 'unknown') {
    push({
      kind: 'Registry', tier: reading.tier, stage: 'Stage 06 · registry',
      title: reading.label,
      body: reading.text,
      quote: null, at: null,
      kv: categories.find((c) => c.id === 'sebi').detail,
    });
  }

  // Stage 9: Phishing domain findings
  const domScan = raw.domain_scan || {};
  if (domScan.is_phishing || (domScan.flagged_domains && domScan.flagged_domains.length)) {
    push({
      kind: 'Phishing Domain', tier: 'critical', stage: 'Stage 09 · domain',
      title: `Suspicious domain: ${domScan.domain || (domScan.flagged_domains || [])[0]}`,
      body: `Phishing domain threat detected. ${domScan.reason || 'Domain impersonates a registered stockbroker platform.'}`,
      quote: null, at: null,
      kv: [
        ['Target Brand', domScan.closest_match || 'N/A'],
        ['Risk Reason', domScan.reason || 'Impersonation'],
      ],
    });
  }

  // Stage 9: APK findings
  const apkScan = raw.apk_analysis || {};
  if (apkScan.suspicious || (apkScan.dangerous_permissions && apkScan.dangerous_permissions.length)) {
    push({
      kind: 'APK Forensics', tier: 'critical', stage: 'Stage 09 · apk',
      title: `Rogue APK Threat: ${apkScan.package_name || 'Suspicious App'}`,
      body: `APK package failed security checks. Flagged for dangerous permissions: ${(apkScan.dangerous_permissions || []).join(', ')}.`,
      quote: null, at: null,
      kv: [
        ['Package Name', apkScan.package_name || 'N/A'],
        ['Dangerous Permissions', String((apkScan.dangerous_permissions || []).length)],
        ['Whitelisted Broker', apkScan.is_official_broker ? 'Yes' : 'No'],
      ],
    });
  }

  evidence.sort((a, b) => (TIERS[b.tier]?.rank ?? 0) - (TIERS[a.tier]?.rank ?? 0));

  /* ── Transcript, flagged against the backend's own timeline ───────────── */
  const flagByStart = new Map();
  for (const entry of arr(raw.timeline_track)) {
    if (entry.text_flag) flagByStart.set(Number(entry.start).toFixed(2), entry.text_flag);
  }
  const FLAG_LABEL = {
    explicit_return: 'Guaranteed return',
    implied_return: 'Implied return',
    urgency: 'Urgency',
    paywall: 'Paywall push',
  };
  const FLAG_TIER = {
    explicit_return: 'critical',
    implied_return: 'high',
    urgency: 'moderate',
    paywall: 'moderate',
  };
  const transcript = arr(raw.segments).map((s) => {
    const flag = flagByStart.get(Number(s.start).toFixed(2)) || null;
    return {
      start: num(s.start) ?? 0,
      end: num(s.end) ?? 0,
      text: String(s.text || ''),
      flag,
      flagLabel: flag ? FLAG_LABEL[flag] || flag : null,
      flagTier: flag ? FLAG_TIER[flag] || 'moderate' : null,
    };
  });

  /* ── Summary line ─────────────────────────────────────────────────────── */
  const reasoning = String(sebi.reasoning || '').trim();
  const summary = reasoning || fallbackSummary(tier, categories);

  const duration = audioSegments.length
    ? Math.max(...audioSegments.map((s) => num(s.end) ?? 0))
    : transcript.length
      ? Math.max(...transcript.map((s) => s.end))
      : null;

  return {
    mode: meta.mode || raw.scan_type || 'video',
    jobId: meta.jobId || null,
    filename: meta.filename || null,
    startedAt: meta.startedAt || new Date(),

    verdict: String(raw.verdict || 'Inconclusive'),
    tier,
    peakSignal,
    signalInputs,
    summary,
    isDeepfake: Boolean(raw.is_deepfake),
    isScam,
    injectionDetected: Boolean(sebi.prompt_injection_detected),

    categories,
    evidence,
    transcript,
    transcriptText: String(raw.transcript || ''),
    timeline: arr(raw.timeline_track),
    audioSegments,
    duration,

    heatmap: raw.heatmap_base64 || null,
    extractedText: raw.extracted_text || null,
    ocrConfidence: num(raw.ocr_confidence),
    complaint: raw.scores_complaint || null,

    raw,
  };
}

function fallbackSummary(tier, categories) {
  const flagged = categories.filter((c) => c.tier === 'high' || c.tier === 'critical');
  if (!flagged.length) {
    return tier.key === 'low'
      ? 'No stage returned a signal above its threshold. Treat this as the absence of detected manipulation, not a guarantee of authenticity.'
      : 'No single stage crossed its threshold, but the combined signals were high enough to warrant review.';
  }
  const names = flagged.map((c) => c.name.toLowerCase());
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
  return `Escalated on ${list}. Read the evidence below before acting on this media.`;
}
