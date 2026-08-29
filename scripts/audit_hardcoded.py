"""Quick audit script to find hardcoded values in the FinGuard codebase."""
import os, re, sys

sys.stdout.reconfigure(encoding='utf-8')

SKIP_DIRS = {'.venv', '.git', '__pycache__', 'node_modules', 'dataset', 'test_vid', 'temp'}
SCAN_EXTS = {'.py', '.yaml'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATTERNS = [
    ('LOCALHOST/URL',        re.compile(r'(localhost|127\.0\.0\.1):\d+')),
    ('HARDCODED_PORT',       re.compile(r'(?:port|PORT)\s*=\s*(\d{4,5})')),
    ('HARDCODED_THRESHOLD',  re.compile(r'(?:>=|>|<=|<)\s*(0\.[0-9]+)')),
    ('MAGIC_FRAME_COUNT',    re.compile(r'\b(15|25|50)\b')),
    ('HARDCODED_MODEL_ID',   re.compile(r'["\']([A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+)["\']')),
    ('HARDCODED_PATH',       re.compile(r'["\'](?:static_data|temp|scripts)/[^"\']+["\']')),
    ('HARDCODED_API_URL',    re.compile(r'https?://[a-z0-9\-\.]+\.[a-z]{2,}/\S+')),
    ('HARDCODED_SCORE_MAGIC',re.compile(r'\b(0\.35|0\.65|0\.92|0\.5|35\.0|80|65)\b')),
    ('MAX_UPLOAD_BYTES',     re.compile(r'\b(100)\s*\*\s*1024\s*\*\s*1024\b')),
]

results = []

for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for fname in files:
        ext = os.path.splitext(fname)[1]
        if ext not in SCAN_EXTS:
            continue
        fpath = os.path.join(dirpath, fname)
        rel = os.path.relpath(fpath, ROOT)
        try:
            lines = open(fpath, encoding='utf-8', errors='ignore').readlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            for label, pat in PATTERNS:
                m = pat.search(stripped)
                if m:
                    results.append({
                        'label': label,
                        'file': rel,
                        'line': i,
                        'value': m.group(0),
                        'context': stripped[:120],
                    })

# Group by file
from collections import defaultdict
by_file = defaultdict(list)
for r in results:
    by_file[r['file']].append(r)

print(f"Found {len(results)} potential hardcoded values across {len(by_file)} files:\n")
for fpath, hits in sorted(by_file.items()):
    print(f"\n{'='*60}")
    print(f"  {fpath}")
    print(f"{'='*60}")
    for h in hits:
        print(f"  L{h['line']:>4}  [{h['label']}]  value={h['value']!r}")
        print(f"         > {h['context']}")
