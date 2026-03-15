"""
CANESENSE NIR - PLSR Model Training
Trains a Partial Least Squares Regression model on NIR spectral data
to predict sugarcane chemical parameters: TS, CP, ADF, IVOMD
"""

import pandas as pd
import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error
import joblib
import os
import json


def train_plsr_model(csv_path='nirscan_nano.csv'):
    print("=" * 60)
    print("  CANESENSE — PLSR NIR MODEL TRAINING")
    print("=" * 60)

    # ── Load dataset ──────────────────────────────────────────
    df = pd.read_csv(csv_path)
    print(f"\n[INFO] Dataset shape : {df.shape[0]} rows × {df.shape[1]} columns")

    # ── Identify spectral feature columns ─────────────────────
    spectral_cols = [c for c in df.columns if c.startswith('amplitude-')]
    target_cols   = ['TS', 'CP', 'ADF', 'IVOMD']

    print(f"[INFO] Spectral features : {len(spectral_cols)}")
    print(f"[INFO] Target parameters : {target_cols}")

    # ── Coerce targets to numeric, drop rows with NaN targets ─
    for col in target_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df_clean = df.dropna(subset=target_cols).reset_index(drop=True)
    print(f"[INFO] Clean samples     : {len(df_clean)}  "
          f"(dropped {len(df) - len(df_clean)} rows with missing targets)")

    # ── Build X and Y matrices ────────────────────────────────
    X = df_clean[spectral_cols].values.astype(float)
    Y = df_clean[target_cols].values.astype(float)

    # ── Standardise spectral features ─────────────────────────
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # ── Train PLSR ────────────────────────────────────────────
    n_components = min(10, X.shape[1], X.shape[0] - 1)
    plsr = PLSRegression(n_components=n_components, max_iter=1000)
    plsr.fit(X_scaled, Y)
    print(f"\n[TRAIN] PLSRegression  n_components={n_components}")

    # ── Evaluate on training set ──────────────────────────────
    Y_pred      = plsr.predict(X_scaled)
    r2_scores   = {}
    rmse_scores = {}

    print("\n[METRICS] Training performance:")
    for i, col in enumerate(target_cols):
        r2   = r2_score(Y[:, i], Y_pred[:, i])
        rmse = np.sqrt(mean_squared_error(Y[:, i], Y_pred[:, i]))
        r2_scores[col]   = round(float(r2),   4)
        rmse_scores[col] = round(float(rmse),  4)
        print(f"         {col:6s}  R²={r2:.4f}   RMSE={rmse:.4f}")

    # ── Persist model artefacts ───────────────────────────────
    os.makedirs('models', exist_ok=True)
    joblib.dump(plsr,         'models/plsr_model.pkl')
    joblib.dump(scaler,       'models/scaler.pkl')
    joblib.dump(spectral_cols,'models/feature_columns.pkl')

    # wavelength range label (strip 'amplitude-' prefix)
    wl_first = spectral_cols[0].replace('amplitude-', '')
    wl_last  = spectral_cols[-1].replace('amplitude-', '')

    metrics = {
        'model':           'PLSRegression',
        'n_components':    n_components,
        'n_samples_train': int(len(df_clean)),
        'n_features':      int(len(spectral_cols)),
        'target_params':   target_cols,
        'r2_scores':       r2_scores,
        'rmse_scores':     rmse_scores,
        'wavelength_range': f"{wl_first} – {wl_last} nm",
    }
    with open('models/metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    print("\n[SAVED] models/plsr_model.pkl")
    print("[SAVED] models/scaler.pkl")
    print("[SAVED] models/feature_columns.pkl")
    print("[SAVED] models/metrics.json")
    print("=" * 60)
    print("  Training complete!\n")

    return plsr, scaler, spectral_cols, metrics


if __name__ == '__main__':
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    train_plsr_model()
