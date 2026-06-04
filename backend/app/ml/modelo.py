"""
Modelo Random Forest para predicción de desabastecimiento.
Entrena con features del CUM y guarda el modelo en data/modelo_rf.pkl.
"""
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    classification_report, roc_auc_score, average_precision_score
)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.utils.class_weight import compute_class_weight

from app.ml.features import FEATURE_COLS, construir_features

MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "modelo_rf.pkl"

UMBRALES_RIESGO = [0.0, 0.25, 0.50, 0.75, 1.01]
NIVELES_RIESGO  = ["bajo", "medio", "alto", "critico"]


def clasificar_nivel(probabilidad: float) -> str:
    for i, (lo, hi) in enumerate(zip(UMBRALES_RIESGO, UMBRALES_RIESGO[1:])):
        if lo <= probabilidad < hi:
            return NIVELES_RIESGO[i]
    return "critico"


def entrenar(df_raw: pd.DataFrame, verbose: bool = True) -> dict:
    df_feat = construir_features(df_raw)
    X = df_feat[FEATURE_COLS].values
    y = df_feat["desabastecido"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Compensar el desbalance de clases (22% positivos / 78% negativos)
    pesos = compute_class_weight("balanced", classes=np.unique(y_train), y=y_train)
    class_weight = {0: pesos[0], 1: pesos[1]}

    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=20,
        max_features="sqrt",
        class_weight=class_weight,
        random_state=42,
        n_jobs=-1,
    )

    # Calibración de probabilidades (Platt scaling)
    modelo = CalibratedClassifierCV(rf, cv=3, method="sigmoid")
    modelo.fit(X_train, y_train)

    y_prob = modelo.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    metricas = {
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "avg_precision": float(average_precision_score(y_test, y_prob)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "pos_rate_train": float(y_train.mean()),
    }

    if verbose:
        print("\n=== MÉTRICAS DEL MODELO ===")
        print(f"  ROC-AUC         : {metricas['roc_auc']:.4f}")
        print(f"  Avg Precision   : {metricas['avg_precision']:.4f}")
        print(f"  Train/Test      : {metricas['n_train']:,} / {metricas['n_test']:,}")
        print(f"  Tasa positivos  : {metricas['pos_rate_train']:.2%}")
        print()
        print(classification_report(y_test, y_pred, target_names=["Activo", "Inactivo/Riesgo"]))

        # Importancia de features (acceder al estimador base del CalibratedClassifierCV)
        try:
            base_rf = modelo.calibrated_classifiers_[0].estimator
            importancias = base_rf.feature_importances_
            print("\n  Importancia de features:")
            for feat, imp in sorted(zip(FEATURE_COLS, importancias), key=lambda x: -x[1]):
                bar = "|" * int(imp * 40)
                print(f"  {feat:<35} {imp:.4f}  {bar}")
        except Exception:
            pass

    # Guardar modelo + metadata
    artefacto = {"modelo": modelo, "features": FEATURE_COLS, "metricas": metricas}
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artefacto, f)

    if verbose:
        print(f"\nModelo guardado en: {MODEL_PATH}")

    return metricas


def cargar_modelo() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modelo no encontrado en {MODEL_PATH}. Ejecuta: python -m app.ml.entrenamiento"
        )
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predecir_batch(features_matrix: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Retorna (probabilidades, niveles_riesgo)."""
    artefacto = cargar_modelo()
    probs = artefacto["modelo"].predict_proba(features_matrix)[:, 1]
    niveles = [clasificar_nivel(float(p)) for p in probs]
    return probs, niveles
