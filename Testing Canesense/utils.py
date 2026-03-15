"""
CANESENSE NIR — Utility helpers
JSON persistence layer for prediction results.
"""

import json
import os
from datetime import datetime

RESULTS_FILE = 'results.json'


# ── JSON persistence ──────────────────────────────────────────────────────────

def load_results() -> list:
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_results(results: list) -> None:
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2)


def append_batch(batch: dict) -> None:
    """Add a new farmer batch result to the JSON store."""
    results = load_results()
    # Replace existing batch with same farmer_id + same day
    today = datetime.now().strftime('%Y-%m-%d')
    results = [
        r for r in results
        if not (r.get('farmer_id') == batch.get('farmer_id')
                and r.get('timestamp', '').startswith(today))
    ]
    results.append(batch)
    save_results(results)


# ── Farmer lookup ─────────────────────────────────────────────────────────────

def get_all_farmers() -> list:
    results = load_results()
    farmers = []
    for r in results:
        farmers.append({
            'farmer_id':      r.get('farmer_id', '-'),
            'farmer_name':    r.get('farmer_name', 'Unknown'),
            'timestamp':      r.get('timestamp', ''),
            'samples_scanned': r.get('samples_scanned', 0),
            'average_TS':     r.get('average_TS', 0),
            'average_ADF':    r.get('average_ADF', 0),
            'average_CP':     r.get('average_CP', 0),
            'average_IVOMD':  r.get('average_IVOMD', 0),
            'predicted_pol':  r.get('predicted_pol', 0),
        })
    return farmers


def search_farmer(query: str) -> list:
    """Return farmer batches matching query against farmer_id or farmer_name."""
    results = load_results()
    q = query.strip().lower()
    if not q:
        return results
    return [
        r for r in results
        if q in r.get('farmer_id', '').lower()
        or q in r.get('farmer_name', '').lower()
    ]


# ── Batch summary helper ──────────────────────────────────────────────────────

def compute_batch_summary(samples: list) -> dict:
    if not samples:
        return {}

    def avg(key):
        vals = [s.get(key, 0) for s in samples]
        return round(sum(vals) / len(vals), 2) if vals else 0

    quality_counts = {'High': 0, 'Medium': 0, 'Low': 0}
    for s in samples:
        q = s.get('quality', 'Low')
        quality_counts[q] = quality_counts.get(q, 0) + 1

    return {
        'average_TS':      avg('TS'),
        'average_ADF':     avg('ADF'),
        'average_CP':      avg('CP'),
        'average_IVOMD':   avg('IVOMD'),
        'predicted_pol':   avg('Pol'),
        'samples_scanned': len(samples),
        'quality_counts':  quality_counts,
    }


# ── Timestamp helper ──────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now().isoformat()
