/* ============================================================================
   Pipeline stage definitions.
   ----------------------------------------------------------------------------
   Every entry here corresponds to a stage that actually exists in the backend.
   The `key` values match the strings the service writes to `jobs[id]["stage"]`
   in app.py, and the order matches the real execution order in `run_pipeline`
   (note that transcription runs BEFORE audio spoof detection, because stage 3
   is given the transcript for its impersonation check).

   If a stage is added, renamed, or reordered in app.py, change it here — this
   is the only place the frontend encodes the shape of the pipeline.
   ========================================================================= */

/** Canonical stage catalogue, keyed by the backend's stage identifier. */
export const STAGE_CATALOGUE = {
  stage1_ingest: {
    label: 'Media secured',
    sub: 'Frames and audio extracted',
    status: 'SECURING MEDIA AND EXTRACTING FRAMES',
    weight: 3,
    topic: 'handling',
  },
  stage2_vision: {
    label: 'Visual deepfake forensics',
    sub: 'Facial manipulation scoring',
    status: 'SCANNING FACE REGIONS FOR MANIPULATION',
    weight: 4,
    topic: 'deepfake',
  },
  stage4_transcription: {
    label: 'Speech transcription',
    sub: 'Timestamped segments',
    status: 'TRANSCRIBING SPEECH WITH TIMESTAMPS',
    weight: 6,
    topic: 'speech',
  },
  stage3_audio: {
    label: 'Voice authenticity',
    sub: 'Windowed spoof detection',
    status: 'SCANNING AUDIO PATTERNS FOR SYNTHETIC SPEECH',
    weight: 4,
    topic: 'voice',
  },
  stage5_llm: {
    label: 'Financial scam patterns',
    sub: 'Six weighted signals',
    status: 'ANALYSING FINANCIAL CLAIMS AND PRESSURE TACTICS',
    weight: 5,
    topic: 'scam',
  },
  stage6_registry: {
    label: 'SEBI registry verification',
    sub: 'Name and registration match',
    status: 'VERIFYING DETECTED ENTITIES AGAINST THE REGISTRY',
    weight: 2,
    topic: 'sebi',
  },
  stage7_ocr: {
    label: 'On-screen text extraction',
    sub: 'OCR over the image',
    status: 'READING ON-SCREEN TEXT',
    weight: 4,
    topic: 'speech',
  },
  stage8_report: {
    label: 'Evidence dossier compilation',
    sub: 'SEBI SCORES pre-filing draft',
    status: 'COMPILING LEGAL EVIDENCE DOSSIER',
    weight: 2,
    topic: 'report',
  },
  stage9_apk_domain: {
    label: 'APK & domain forensics',
    sub: 'Phishing & fake broker checks',
    status: 'SCANNING DOMAINS AND PERMISSIONS',
    weight: 3,
    topic: 'domain',
  },
  stage7_aggregation: {
    label: 'Forensic verdict synthesis',
    sub: 'Calibrated risk assessment',
    status: 'GENERATING FINAL RISK ASSESSMENT',
    weight: 2,
    topic: 'verdict',
  },
};

/**
 * Which stages each scan mode actually runs, in execution order.
 * Derived by reading app.py: run_pipeline (video), scan_audio, scan_image,
 * scan_text, scan_apk, scan_url.
 */
export const STAGE_PLAN = {
  video: [
    'stage1_ingest',
    'stage2_vision',
    'stage4_transcription',
    'stage3_audio',
    'stage5_llm',
    'stage6_registry',
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
  audio: [
    'stage4_transcription',
    'stage3_audio',
    'stage5_llm',
    'stage6_registry',
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
  image: [
    'stage2_vision',
    'stage7_ocr',
    'stage5_llm',
    'stage6_registry',
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
  text: [
    'stage5_llm',
    'stage6_registry',
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
  apk: [
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
  url: [
    'stage9_apk_domain',
    'stage8_report',
    'stage7_aggregation',
  ],
};

/** Resolve a mode into a list of {key, label, sub, status, weight, topic}. */
export function planFor(mode) {
  return (STAGE_PLAN[mode] || STAGE_PLAN.video).map((key) => ({
    key,
    ...STAGE_CATALOGUE[key],
  }));
}

/**
 * The nine pipeline stages as presented on the landing page.
 */
export const TECHNOLOGY_STAGES = [
  {
    n: '01',
    title: 'Ingest and preprocessing',
    body: 'The upload is written to an isolated per-job directory. Audio is demuxed and resampled, and frames are sampled adaptively around scene cuts. Detected face regions are cropped for the visual stage, and input quality is assessed via Laplacian variance.',
    out: 'face crops · normalised audio · quality assessment',
  },
  {
    n: '02',
    title: 'Visual forensics',
    body: 'Each face crop is scored for manipulation using dual RGB spatial + 3-filter SRM high-pass frequency residual forensics, paired with mouth-motion activity to catch static photo puppet animations.',
    out: 'peak score · temporal variance · SRM heatmap',
  },
  {
    n: '03',
    title: 'Audio deepfake detection',
    body: 'Audio is level-normalised and cut into 5-second windows, each scored by Wav2Vec2 for acoustic spoof detection, paired with named-entity recognition to identify targeted finfluencer voice clones.',
    out: 'windowed spoof scores · finfluencer check',
  },
  {
    n: '04',
    title: 'Speech transcription',
    body: 'Timestamped transcription tuned for Hindi-English code-switched financial speech, with a phonetic cleaner that repairs spoken registration numbers into standardized SEBI formats.',
    out: 'transcript · per-segment timestamps',
  },
  {
    n: '05',
    title: 'SEBI compliance reasoning & DPDP shield',
    body: 'PII (Aadhaar, PAN, phone numbers) is redacted first under DPDP principles. A locally-hosted LLM extracts exact quotes across six scored regulatory signals and flags adversarial prompt injections.',
    out: 'quoted claims · 6 regulatory signal scores · composite risk',
  },
  {
    n: '06',
    title: 'Registry cross-check',
    body: 'Claimed registration numbers are verified against the local SEBI snapshot (Aug 2026). Names and aliases are fuzzy-matched to separate verified entities from unregistered impostors.',
    out: 'verdict · matched entity · snapshot date',
  },
  {
    n: '07',
    title: 'On-screen OCR extraction',
    body: 'EasyOCR scans frames and screenshots for on-screen registration numbers, QR codes, WhatsApp group links, and promotional claims in English and Hindi.',
    out: 'extracted visual text · confidence scores',
  },
  {
    n: '08',
    title: 'SCORES evidence dossier generation',
    body: 'Assembles full forensic findings into a structured, pre-filing SEBI SCORES 2.0 evidence dossier for compliance officer review and expedited portal lodgement.',
    out: 'formal pre-filing draft · regulatory citations',
  },
  {
    n: '09',
    title: 'APK & phishing domain scanner',
    body: 'Decompiles APK manifests to detect dangerous permission abuse and brand typosquatting, while the domain engine audits URLs against legitimate broker whitelists using Levenshtein distance.',
    out: 'flagged permissions · phishing threats · broker cert check',
  },
];
