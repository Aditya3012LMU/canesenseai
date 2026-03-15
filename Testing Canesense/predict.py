"""
CANESENSE NIR — Prediction Pipeline
Loads the trained PLSR model and predicts TS, CP, ADF, IVOMD row-by-row
from an uploaded NIR CSV file, with a 2-second delay between samples.
"""

import pandas as pd
import numpy as np
import joblib
import time
import os


# ── Model loader (cached) ─────────────────────────────────────────────────────
_model_cache = {}

def load_model():
    if not _model_cache:
        _model_cache['plsr']   = joblib.load('models/plsr_model.pkl')
        _model_cache['scaler'] = joblib.load('models/scaler.pkl')
        _model_cache['cols']   = joblib.load('models/feature_columns.pkl')
    return _model_cache['plsr'], _model_cache['scaler'], _model_cache['cols']


# ── Chemistry helpers ─────────────────────────────────────────────────────────

def calculate_pol(ts: float, adf: float) -> float:
    """Predicted sucrose %: Pol = (TS × 0.85) − (ADF × 0.1)"""
    return round(float((ts * 0.85) - (adf * 0.1)), 3)


def assign_quality(ts: float) -> str:
    if ts > 15:
        return 'High'
    elif ts >= 12:
        return 'Medium'
    else:
        return 'Low'


# ── Single-sample prediction ──────────────────────────────────────────────────

def predict_sample(row: pd.Series, plsr, scaler, feature_cols: list) -> dict:
    """
    Align row's spectral features with training columns,
    run PLSR inference, compute Pol and quality grade.
    """
    # Align columns — use training column list, fill missing with col mean=0
    X = np.zeros((1, len(feature_cols)), dtype=float)
    for i, col in enumerate(feature_cols):
        if col in row.index:
            try:
                X[0, i] = float(row[col])
            except (ValueError, TypeError):
                X[0, i] = 0.0

    X_scaled = scaler.transform(X)
    Y_pred   = plsr.predict(X_scaled)[0]

    ts, cp, adf, ivomd = [float(v) for v in Y_pred]

    # Guard against extreme/negative predictions
    ts    = max(ts,    0.0)
    cp    = max(cp,    0.0)
    adf   = max(adf,   0.0)
    ivomd = max(ivomd, 0.0)

    pol     = calculate_pol(ts, adf)
    quality = assign_quality(ts)

    return {
        'sample_id': str(row.get('sample_id', 'N/A')),
        'TS':        round(ts,    2),
        'CP':        round(cp,    2),
        'ADF':       round(adf,   2),
        'IVOMD':     round(ivomd, 2),
        'Pol':       round(pol,   2),
        'quality':   quality,
    }


# ── Batch prediction generator ────────────────────────────────────────────────

def predict_batch(filepath: str, delay: float = 2.0):
    """
    Generator — yields one prediction dict per row, with `delay` seconds between.
    """
    plsr, scaler, feature_cols = load_model()

    df = pd.read_csv(filepath)
    # Keep only spectral + sample_id columns; ignore any target columns
    spectral_in_file = [c for c in df.columns if c.startswith('amplitude-')]
    keep_cols = ['sample_id'] + spectral_in_file if 'sample_id' in df.columns else spectral_in_file
    df = df[keep_cols]

    for idx, (_, row) in enumerate(df.iterrows()):
        result = predict_sample(row, plsr, scaler, feature_cols)
        result['row_index'] = idx
        yield result
        if idx < len(df) - 1:          # no sleep after the last sample
            time.sleep(delay)


# ── Batch summary helper ──────────────────────────────────────────────────────

def compute_summary(samples: list) -> dict:
    if not samples:
        return {}

    def avg(key):
        return round(sum(s[key] for s in samples) / len(samples), 2)

    return {
        'average_TS':    avg('TS'),
        'average_CP':    avg('CP'),
        'average_ADF':   avg('ADF'),
        'average_IVOMD': avg('IVOMD'),
        'predicted_pol': avg('Pol'),
        'samples_scanned': len(samples),
        'quality_counts': {
            'High':   sum(1 for s in samples if s['quality'] == 'High'),
            'Medium': sum(1 for s in samples if s['quality'] == 'Medium'),
            'Low':    sum(1 for s in samples if s['quality'] == 'Low'),
        }
    }
