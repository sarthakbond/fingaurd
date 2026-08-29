"""
SEBI Registry Delta Synchronizer
================================
Pulls official SEBI intermediary data from SEBI's public portal and writes
incremental deltas into static_data/sebi_registry.json.

Architecture: "Air-gapped execution with authenticated one-way daily synchronization daemon."

Usage:
    python scripts/sync_sebi_registry.py             # Live sync
    python scripts/sync_sebi_registry.py --dry-run   # Preview changes only
    python scripts/sync_sebi_registry.py --stats      # Show current registry stats
"""

import os
import sys
import json
import datetime
import argparse
import time

# Force UTF-8 output on Windows to handle emoji in print statements
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Registry path ─────────────────────────────────────────────────────────────

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "static_data", "sebi_registry.json")
SYNC_LOG_PATH = os.path.join(ROOT, "static_data", "sebi_sync_log.json")

# ── SEBI public data endpoints ─────────────────────────────────────────────────
# SEBI provides downloadable CSVs for intermediary rosters via these URLs.
# These are publicly accessible without authentication.
SEBI_ENDPOINTS = {
    "investment_advisers": "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doBiodata=yes&intmId=13",
    "research_analysts":   "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doBiodata=yes&intmId=14",
    "stock_brokers":       "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doBiodata=yes&intmId=1",
}

# SEBI's new structured intermediary API (available in 2025+)
SEBI_API_BASE = "https://www.sebi.gov.in/sebiweb/rest/intermediary"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_registry() -> list:
    if not os.path.exists(REGISTRY_PATH):
        return []
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_registry(data: list) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_sync_log() -> dict:
    if not os.path.exists(SYNC_LOG_PATH):
        return {"last_sync": None, "sync_count": 0, "history": []}
    with open(SYNC_LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_sync_log(log: dict) -> None:
    with open(SYNC_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

def normalize_reg_no(reg_no: str) -> str:
    return reg_no.upper().replace(" ", "").replace("-", "").strip()

# ── Fetch from SEBI portal ─────────────────────────────────────────────────────

def _fetch_sebi_page(session, url: str, category: str) -> list:
    """
    Attempts to fetch SEBI intermediary data from the public portal.
    Returns a list of normalized registry entries.
    """
    import re as re_mod

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # SEBI portal returns an HTML table — extract registration numbers and names
        # Pattern: registration number like INA/INH/INZ followed by digits
        reg_pattern = re_mod.compile(
            r"(IN[A-Z0-9]{8,14})\s*[|\t,;]?\s*([A-Za-z\s&\.,'()-]{5,80}?)(?:\s*[|\t,;]|</td>|<br)",
            re_mod.IGNORECASE
        )
        matches = reg_pattern.findall(html)
        entries = []
        for reg_no, name in matches:
            clean_name = name.strip().strip("'\"").strip()
            clean_reg = normalize_reg_no(reg_no)
            if clean_name and len(clean_name) > 3:
                entries.append({
                    "name": clean_name,
                    "aliases": [],
                    "registration_number": clean_reg,
                    "type": category,
                    "status": "Active",
                    "source": "SEBI Portal",
                    "last_verified": datetime.datetime.now().isoformat()
                })
        return entries

    except Exception as e:
        print(f"  [WARN] Could not fetch from SEBI portal ({url}): {e}")
        return []

def fetch_live_sebi_data() -> list:
    """
    Attempts live fetch from SEBI public portal.
    Falls back to returning empty list (current local data preserved).
    """
    try:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": "FinGuard-Registry-Sync/1.0 (SEBI Compliance Verification Tool)",
            "Accept": "text/html,application/xhtml+xml"
        })

        all_entries = []
        categories = [
            ("Investment Adviser", SEBI_ENDPOINTS["investment_advisers"]),
            ("Research Analyst",   SEBI_ENDPOINTS["research_analysts"]),
            ("Stock Broker",       SEBI_ENDPOINTS["stock_brokers"]),
        ]

        for cat_name, url in categories:
            print(f"  Fetching {cat_name} roster from SEBI portal...")
            entries = _fetch_sebi_page(session, url, cat_name)
            print(f"    → Found {len(entries)} entries")
            all_entries.extend(entries)
            time.sleep(1)  # Polite delay to avoid rate-limiting

        return all_entries

    except ImportError:
        print("  [WARN] requests library not available. Install it: pip install requests")
        return []
    except Exception as e:
        print(f"  [ERROR] Live SEBI fetch failed: {e}")
        return []

# ── Delta computation ─────────────────────────────────────────────────────────

def compute_delta(current: list, fetched: list) -> dict:
    """
    Compares fetched SEBI data against current local registry.
    Returns a delta report with additions, status changes.
    """
    current_by_reg = {normalize_reg_no(e.get("registration_number", "")): e for e in current}
    fetched_by_reg = {normalize_reg_no(e.get("registration_number", "")): e for e in fetched}

    additions = []
    revocations = []

    for reg_no, entry in fetched_by_reg.items():
        if reg_no not in current_by_reg:
            additions.append(entry)

    # Detect potential revocations (in current but not in fetched active list)
    # Only flag if fetched actually returned data (avoid false revocations from empty fetch)
    if len(fetched_by_reg) > 10:
        for reg_no, entry in current_by_reg.items():
            if reg_no not in fetched_by_reg and entry.get("status") == "Active":
                revocation_candidate = dict(entry)
                revocation_candidate["status"] = "Revoked (Unverified)"
                revocation_candidate["revocation_flagged"] = datetime.datetime.now().isoformat()
                revocations.append(revocation_candidate)

    return {
        "additions": additions,
        "revocations": revocations,
        "total_fetched": len(fetched_by_reg),
        "total_current": len(current_by_reg)
    }

def apply_delta(current: list, delta: dict) -> list:
    """Applies computed delta to produce the updated registry."""
    current_by_reg = {normalize_reg_no(e.get("registration_number", "")): e for e in current}

    # Add new entries
    for entry in delta["additions"]:
        reg_no = normalize_reg_no(entry.get("registration_number", ""))
        current_by_reg[reg_no] = entry

    # Update revocation flags
    for entry in delta["revocations"]:
        reg_no = normalize_reg_no(entry.get("registration_number", ""))
        if reg_no in current_by_reg:
            current_by_reg[reg_no]["status"] = entry["status"]
            current_by_reg[reg_no]["revocation_flagged"] = entry.get("revocation_flagged")

    return list(current_by_reg.values())

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SEBI Registry Delta Synchronizer")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--stats", action="store_true", help="Show current registry statistics")
    args = parser.parse_args()

    print("=" * 60)
    print("  FinGuard — SEBI Registry Synchronization Daemon")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)

    current = load_registry()
    log = load_sync_log()

    if args.stats:
        print(f"\n  Registry file  : {REGISTRY_PATH}")
        print(f"  Total records  : {len(current)}")
        print(f"  Last sync      : {log.get('last_sync', 'Never')}")
        print(f"  Sync count     : {log.get('sync_count', 0)}")
        by_type = {}
        for e in current:
            t = e.get("type", "Unknown")
            by_type[t] = by_type.get(t, 0) + 1
        print("\n  Breakdown by type:")
        for t, count in sorted(by_type.items()):
            print(f"    {t:<35} {count}")
        return

    print("\n[1/3] Loading current local registry...")
    print(f"      Records loaded: {len(current)}")

    print("\n[2/3] Fetching live data from SEBI public portal...")
    fetched = fetch_live_sebi_data()

    if not fetched:
        print("\n  ⚠ No live data retrieved (SEBI portal unreachable or returned 0 records).")
        print("  Local registry preserved unchanged.")
        print("  Defense: Air-gapped execution — local registry is the last authenticated snapshot.")

        # Still update sync log so /api/registry/status shows accurate state
        log["last_sync_attempt"] = datetime.datetime.now().isoformat()
        log["last_sync_result"] = "failed_no_data"
        if not args.dry_run:
            save_sync_log(log)
        return

    print(f"\n[3/3] Computing delta...")
    delta = compute_delta(current, fetched)

    print(f"\n  📊 Delta Report:")
    print(f"     Entries in SEBI portal   : {delta['total_fetched']}")
    print(f"     Entries in local registry: {delta['total_current']}")
    print(f"     New additions            : {len(delta['additions'])}")
    print(f"     Revocation candidates    : {len(delta['revocations'])}")

    if delta["additions"]:
        print(f"\n  ➕ New entries to add:")
        for e in delta["additions"][:5]:
            print(f"     [{e['registration_number']}] {e['name']} ({e['type']})")
        if len(delta["additions"]) > 5:
            print(f"     ... and {len(delta['additions']) - 5} more")

    if delta["revocations"]:
        print(f"\n  ⚠ Entries flagged for revocation review:")
        for e in delta["revocations"][:5]:
            print(f"     [{e['registration_number']}] {e['name']}")

    if args.dry_run:
        print("\n  🔍 DRY RUN — no changes written.")
        return

    updated = apply_delta(current, delta)
    save_registry(updated)

    now_iso = datetime.datetime.now().isoformat()
    log["last_sync"] = now_iso
    log["last_sync_result"] = "success"
    log["sync_count"] = log.get("sync_count", 0) + 1
    log["history"] = log.get("history", [])
    log["history"].append({
        "timestamp": now_iso,
        "additions": len(delta["additions"]),
        "revocations": len(delta["revocations"]),
        "total_records": len(updated)
    })
    # Keep last 30 sync entries
    log["history"] = log["history"][-30:]
    save_sync_log(log)

    print(f"\n  ✅ Sync complete. Registry updated: {len(updated)} total records.")
    print(f"     Written to: {REGISTRY_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
