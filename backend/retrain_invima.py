"""
retrain_invima.py — Reentrena el modelo usando datos INVIMA como ground truth.

Estrategia:
  - Target y=1: el ATC7 del producto tiene estado DESABASTECIDO o EN_RIESGO
    en el mes más reciente de invima_seguimiento (severidad >= 4).
    → 21 ATCs / ~1 174 productos (~2.2% positivos)
  - Target y=0: todo lo demás (EN_MONITORIZACION, NO_COMERCIALIZADO, no monitoreado).
  - Split temporal: features INVIMA derivadas de meses ANTERIORES al target
    (sin data leakage). Lag-1 = penúltimo mes.
  - 15 features = 10 estructurales (CUM) + 5 temporales (INVIMA).
    Los 5 features INVIMA para productos SIN cobertura en INVIMA = 0.

Uso:
  cd backend
  python retrain_invima.py
"""
import sys
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.database import SessionLocal, init_db
from app.models.cum_normalizado import CumNormalizado
from app.ml.features import ATC_GRUPOS, _ATC_ENC, TIPO_FORMULA_NUM
from app.ml.modelo import MODEL_PATH

# ── Feature columns ────────────────────────────────────────────────────────────
FEATURE_COLS_BASE = [
    "tasa_inactivacion_atc5",
    "num_competidores",
    "tiene_alternativas",
    "tipo_formula_num",
    "es_combinado",
    "monopolio",
    "grupo_atc_enc",
    "num_presentaciones_activas",
    "busquedas_norm",
    "reportes_norm",
]

FEATURE_COLS_INVIMA = [
    "invima_sev_actual",          # severidad en lag-1 (penúltimo mes)   0-5
    "invima_sev_t3_avg",          # promedio severidad últimos 3 meses históricos  0-5
    "invima_meses_monitoreado",   # meses con cualquier estado en INVIMA  0-17
    "invima_peor_sev_hist",       # severidad máxima histórica  0-5
    "invima_tendencia",           # (promedio últimos 3) − (promedio anteriores 3)  [-5, 5]
]

FEATURE_COLS = FEATURE_COLS_BASE + FEATURE_COLS_INVIMA

INVIMA_SEV = {
    "DESABASTECIDO":     5,
    "EN_RIESGO":         4,
    "EN_MONITORIZACION": 3,
    "NO_COMERCIALIZADO": 2,
    "DESCONTINUADO":     1,
    "NO_DESABASTECIDO":  0,
}


# ── CUM structural features ────────────────────────────────────────────────────
def _construir_base(db) -> pd.DataFrame:
    print("  Cargando cum_normalizado...")
    rows = db.query(
        CumNormalizado.expediente_cum,
        CumNormalizado.consecutivo_cum,
        CumNormalizado.atc_normalizado,
        CumNormalizado.tipo_formula,
        CumNormalizado.estado_cum,
        CumNormalizado.estado_registro,
        CumNormalizado.titular_registro,
        CumNormalizado.forma_normalizada,
    ).all()

    df = pd.DataFrame(rows, columns=[
        "expediente_cum", "consecutivo_cum", "atc_normalizado",
        "tipo_formula", "estado_cum", "estado_registro",
        "titular_registro", "forma_normalizada",
    ])
    df["cum_id"]         = df["expediente_cum"] + "-" + df["consecutivo_cum"]
    df["atc_upper"]      = df["atc_normalizado"].str.strip().str.upper().fillna("")
    df["atc5"]           = df["atc_upper"].str[:5]
    df["atc_grupo"]      = df["atc_upper"].str[:1]
    df["estado_cum_low"] = df["estado_cum"].str.strip().str.lower().fillna("")

    atc5_stats = (
        df.groupby("atc5")
        .agg(total=("cum_id", "count"),
             inactivos=("estado_cum_low", lambda x: (x == "inactivo").sum()))
        .reset_index()
    )
    atc5_stats["tasa_inactivacion_atc5"] = (
        atc5_stats["inactivos"] / atc5_stats["total"].clip(lower=1)
    )

    activos = df[df["estado_cum_low"] == "activo"]
    competidores = (
        activos.groupby("forma_normalizada")["titular_registro"]
        .nunique().reset_index(name="num_competidores")
    )
    pres_activas = (
        activos.groupby("expediente_cum")["cum_id"]
        .nunique().reset_index(name="num_presentaciones_activas")
    )

    pres = df.drop_duplicates(subset=["cum_id"]).copy()
    pres["tipo_formula_num"]           = pres["tipo_formula"].map(TIPO_FORMULA_NUM).fillna(1).astype(int)
    pres["es_combinado"]               = (pres["tipo_formula_num"] > 1).astype(int)
    pres = pres.merge(atc5_stats[["atc5", "tasa_inactivacion_atc5"]], on="atc5", how="left")
    pres = pres.merge(competidores, on="forma_normalizada", how="left")
    pres = pres.merge(pres_activas, on="expediente_cum", how="left")
    pres["num_competidores"]           = pres["num_competidores"].fillna(1).astype(int)
    pres["num_presentaciones_activas"] = pres["num_presentaciones_activas"].fillna(0).astype(int)
    pres["tasa_inactivacion_atc5"]     = pres["tasa_inactivacion_atc5"].fillna(0.0)
    pres["monopolio"]                  = (pres["num_competidores"] == 1).astype(int)
    pres["tiene_alternativas"]         = (pres["num_competidores"] > 1).astype(int)
    pres["grupo_atc_enc"]              = pres["atc_grupo"].map(_ATC_ENC).fillna(len(ATC_GRUPOS)).astype(int)
    pres["busquedas_norm"]             = 0.0
    pres["reportes_norm"]              = 0.0

    print(f"  {len(pres):,} productos cargados")
    return pres[FEATURE_COLS_BASE + ["cum_id", "atc_upper"]].copy()


# ── INVIMA temporal features ───────────────────────────────────────────────────
def _construir_invima(db) -> pd.DataFrame:
    """
    Retorna un DataFrame con columnas:
        atc7 (ATC completo), features INVIMA (5 cols), desabastecido (target)

    Target: y=1 si el ATC tiene DESABASTECIDO o EN_RIESGO (sev>=4) en el mes
    más reciente disponible. Features: ventana histórica previa (sin leakage).
    """
    # Mes más reciente = target
    row = db.execute(
        text("SELECT anio, mes FROM invima_seguimiento ORDER BY anio DESC, mes DESC LIMIT 1")
    ).fetchone()
    if row is None:
        print("  AVISO: invima_seguimiento vacía — usando solo features CUM")
        return pd.DataFrame(columns=["atc7"] + FEATURE_COLS_INVIMA + ["desabastecido"])

    target_anio, target_mes = row
    print(f"  Mes target (ground truth): {target_anio}-{target_mes:02d}")

    # Target: severidad máxima por ATC en el mes target
    target_rows = db.execute(text("""
        SELECT atc,
               MAX(CASE estado
                   WHEN 'DESABASTECIDO'     THEN 5
                   WHEN 'EN_RIESGO'         THEN 4
                   WHEN 'EN_MONITORIZACION' THEN 3
                   WHEN 'NO_COMERCIALIZADO' THEN 2
                   WHEN 'DESCONTINUADO'     THEN 1
                   ELSE 0 END) AS max_sev
        FROM invima_seguimiento
        WHERE anio = :ta AND mes = :tm AND atc IS NOT NULL
        GROUP BY atc
    """), {"ta": target_anio, "tm": target_mes}).fetchall()

    # dict: atc7 -> max_sev_target
    target_by_atc7 = {r[0]: int(r[1] or 0) for r in target_rows if r[0]}

    n_pos  = sum(1 for s in target_by_atc7.values() if s >= 4)
    n_mon  = sum(1 for s in target_by_atc7.values() if s == 3)
    print(f"  ATCs en target mes: {len(target_by_atc7)} total "
          f"({n_pos} con DESABASTECIDO/EN_RIESGO, {n_mon} en monitorización)")

    # Historial: todos los meses EXCEPTO target
    hist = db.execute(text("""
        SELECT atc, estado, anio, mes
        FROM invima_seguimiento
        WHERE atc IS NOT NULL
          AND NOT (anio = :ta AND mes = :tm)
        ORDER BY atc, anio, mes
    """), {"ta": target_anio, "tm": target_mes}).fetchall()

    if not hist:
        # Sin historial: features = 0, target desde target_by_atc7
        records = []
        for atc7, sev in target_by_atc7.items():
            records.append({
                "atc7": atc7,
                "invima_sev_actual": 0.0,
                "invima_sev_t3_avg": 0.0,
                "invima_meses_monitoreado": 0,
                "invima_peor_sev_hist": 0.0,
                "invima_tendencia": 0.0,
                "desabastecido": int(sev >= 4),
            })
        return pd.DataFrame(records)

    # DataFrame histórico
    df_hist = pd.DataFrame(hist, columns=["atc7", "estado", "anio", "mes"])
    df_hist["sev"]    = df_hist["estado"].map(INVIMA_SEV).fillna(0).astype(float)
    df_hist["period"] = df_hist["anio"] * 100 + df_hist["mes"]

    # Severidad máxima por (atc7, period) — puede haber varias formas del mismo ATC
    monthly = df_hist.groupby(["atc7", "period"])["sev"].max().reset_index()

    # Periodos ordenados descendente
    all_periods_sorted = sorted(monthly["period"].unique(), reverse=True)
    lag1_period = all_periods_sorted[0] if all_periods_sorted else None
    recent_3    = set(all_periods_sorted[:3])
    prev_3      = set(all_periods_sorted[3:6])

    records = []
    for atc7, grp in monthly.groupby("atc7"):
        periods_grp = set(grp["period"])

        sev_t1    = float(grp.loc[grp["period"] == lag1_period, "sev"].max()) \
                    if lag1_period and lag1_period in periods_grp else 0.0
        recent_v  = grp.loc[grp["period"].isin(recent_3), "sev"].values
        prev_v    = grp.loc[grp["period"].isin(prev_3),   "sev"].values
        sev_t3    = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
        meses     = int(grp["period"].nunique())
        peor      = float(grp["sev"].max())
        avg_r     = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
        avg_p     = float(prev_v.mean())   if len(prev_v)   > 0 else 0.0
        tendencia = float(avg_r - avg_p)
        target    = int(target_by_atc7.get(atc7, 0) >= 4)

        records.append({
            "atc7": atc7,
            "invima_sev_actual":        sev_t1,
            "invima_sev_t3_avg":        sev_t3,
            "invima_meses_monitoreado": meses,
            "invima_peor_sev_hist":     peor,
            "invima_tendencia":         tendencia,
            "desabastecido": target,
        })

    # ATCs en target pero sin historial previo
    hist_atc7s = {r["atc7"] for r in records}
    for atc7, sev in target_by_atc7.items():
        if atc7 not in hist_atc7s:
            records.append({
                "atc7": atc7,
                "invima_sev_actual":        0.0,
                "invima_sev_t3_avg":        0.0,
                "invima_meses_monitoreado": 0,
                "invima_peor_sev_hist":     0.0,
                "invima_tendencia":         0.0,
                "desabastecido": int(sev >= 4),
            })

    df_inv = pd.DataFrame(records)
    n_pos_df = df_inv["desabastecido"].sum()
    print(f"  ATCs con datos históricos INVIMA: {len(df_inv):,} | positivos: {n_pos_df}")
    return df_inv


# ── Train ──────────────────────────────────────────────────────────────────────
def main():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, classification_report
    )
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.utils.class_weight import compute_class_weight

    print("=== Reentrenamiento con datos INVIMA ===\n")
    init_db()
    db = SessionLocal()
    try:
        print("1. Construyendo features base (CUM)...")
        df_base = _construir_base(db)

        print("2. Construyendo features y target INVIMA...")
        df_inv = _construir_invima(db)
    finally:
        db.close()

    print("3. Uniendo datasets (join por ATC7 exacto)...")
    df = df_base.merge(
        df_inv[["atc7"] + FEATURE_COLS_INVIMA + ["desabastecido"]],
        left_on="atc_upper", right_on="atc7",
        how="left",
    )

    # Productos sin cobertura INVIMA: features=0, target=0
    for col in FEATURE_COLS_INVIMA:
        df[col] = df[col].fillna(0.0)
    df["desabastecido"] = df["desabastecido"].fillna(0).astype(int)

    X = df[FEATURE_COLS].values
    y = df["desabastecido"].values

    pos_rate = y.mean()
    print(f"   Total muestras : {len(y):,}")
    print(f"   Positivos (y=1): {y.sum():,}  ({pos_rate:.2%})")
    print(f"   Features       : {len(FEATURE_COLS)}")

    if y.sum() == 0:
        print("\nERROR: no hay muestras positivas. Verifica que invima_seguimiento tenga datos.")
        return

    print("\n4. Entrenando RandomForest + calibración Platt...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clases = np.unique(y_train)
    pesos  = compute_class_weight("balanced", classes=clases, y=y_train)
    class_weight = {int(c): float(p) for c, p in zip(clases, pesos)}

    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=14,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight=class_weight,
        random_state=42,
        n_jobs=-1,
    )
    modelo = CalibratedClassifierCV(rf, cv=3, method="sigmoid")
    modelo.fit(X_train, y_train)

    y_prob = modelo.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    metricas = {
        "roc_auc":        float(roc_auc_score(y_test, y_prob)),
        "avg_precision":  float(average_precision_score(y_test, y_prob)),
        "n_train":        int(len(X_train)),
        "n_test":         int(len(X_test)),
        "pos_rate_train": float(y_train.mean()),
        "target":         "invima_sev>=4_(DESABASTECIDO|EN_RIESGO)_en_mes_reciente",
        "features":       FEATURE_COLS,
    }

    print(f"\n=== MÉTRICAS ===")
    print(f"  ROC-AUC       : {metricas['roc_auc']:.4f}")
    print(f"  Avg Precision : {metricas['avg_precision']:.4f}")
    print(f"  Train/Test    : {metricas['n_train']:,} / {metricas['n_test']:,}")
    print(f"  Tasa positivos: {metricas['pos_rate_train']:.2%}")
    print()
    print(classification_report(y_test, y_pred,
                                target_names=["Sin alerta", "DESABASTECIDO/EN_RIESGO"]))

    try:
        base_rf = modelo.calibrated_classifiers_[0].estimator
        importancias = base_rf.feature_importances_
        print("  Importancia de features:")
        for feat, imp in sorted(zip(FEATURE_COLS, importancias), key=lambda x: -x[1]):
            bar = "|" * int(imp * 40)
            print(f"  {feat:<35} {imp:.4f}  {bar}")
    except Exception:
        pass

    print("\n5. Guardando modelo...")
    artefacto = {"modelo": modelo, "features": FEATURE_COLS, "metricas": metricas}
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artefacto, f)
    print(f"   Guardado en: {MODEL_PATH}")
    print("\nListo.")


if __name__ == "__main__":
    main()
