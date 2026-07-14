"""
retrain_invima.py — Reentrena el modelo usando datos INVIMA como ground truth.

Estrategia (split temporal):
  - Genera una fila de entrenamiento por cada (atc7, mes_target) desde el mes 2
    hasta el último mes disponible.
  - Features de cada fila: ventana histórica de TODOS los meses anteriores al target.
  - Target y=1: el ATC tiene DESABASTECIDO o EN_RIESGO (sev >= 4) en mes_target.
  - Split temporal: últimos 3 meses = test, el resto = train.
    -> Sin data leakage: el modelo nunca ve el futuro durante el entrenamiento.

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
    "invima_sev_actual",          # severidad en lag-1 (mes inmediatamente anterior)  0-5
    "invima_sev_t3_avg",          # promedio severidad últimos 3 meses históricos      0-5
    "invima_meses_monitoreado",   # meses con cualquier estado en INVIMA               0-N
    "invima_peor_sev_hist",       # severidad máxima histórica                         0-5
    "invima_tendencia",           # promedio últimos 3 − promedio anteriores 3        [-5, 5]
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
    pres["busquedas_norm"]             = 0.0  # historial: no había log; se enriquece para modelo producción
    pres["reportes_norm"]              = 0.0

    print(f"  {len(pres):,} productos CUM cargados")
    return pres[FEATURE_COLS_BASE + ["cum_id", "atc_upper"]].copy()


# ── INVIMA temporal features (multi-mes) ──────────────────────────────────────
def _construir_invima_temporal(db) -> pd.DataFrame:
    """
    Genera una fila de entrenamiento por cada (atc7, mes_target).
    Para cada mes_target M, las features se calculan exclusivamente
    sobre los meses anteriores a M (sin data leakage).

    Retorna columnas: atc7, period (YYYYMM), features INVIMA (5 cols), desabastecido.
    """
    hist = db.execute(text("""
        SELECT atc, estado, anio, mes
        FROM invima_seguimiento
        WHERE atc IS NOT NULL
        ORDER BY anio, mes, atc
    """)).fetchall()

    if not hist:
        print("  AVISO: invima_seguimiento vacía — usando solo features CUM")
        return pd.DataFrame(columns=["atc7", "period"] + FEATURE_COLS_INVIMA + ["desabastecido"])

    df_hist = pd.DataFrame(hist, columns=["atc7", "estado", "anio", "mes"])
    df_hist["sev"]    = df_hist["estado"].map(INVIMA_SEV).fillna(0).astype(float)
    df_hist["period"] = df_hist["anio"] * 100 + df_hist["mes"]

    # Severidad máxima por (atc7, period) — hay múltiples formas del mismo ATC
    monthly = df_hist.groupby(["atc7", "period"])["sev"].max().reset_index()
    all_periods = sorted(monthly["period"].unique())

    print(f"  {len(all_periods)} meses INVIMA disponibles: {all_periods[0]} - {all_periods[-1]}")

    records = []
    for i, target_period in enumerate(all_periods):
        if i == 0:
            continue  # Necesitamos al menos un mes de historial

        hist_periods = all_periods[:i]
        hist_data    = monthly[monthly["period"].isin(hist_periods)]

        # Target del mes actual
        target_data = monthly[monthly["period"] == target_period].set_index("atc7")["sev"]

        # Ventanas temporales para features
        lag1     = hist_periods[-1]
        recent_3 = set(hist_periods[-3:])
        prev_3   = set(hist_periods[-6:-3]) if len(hist_periods) >= 6 else set()

        # ATCs a considerar: los que aparecen en el target O en el historial
        all_atcs = set(target_data.index) | set(hist_data["atc7"].unique())

        for atc7 in all_atcs:
            atc_hist = hist_data[hist_data["atc7"] == atc7]

            sev_t1    = float(atc_hist.loc[atc_hist["period"] == lag1, "sev"].max()
                              if not atc_hist[atc_hist["period"] == lag1].empty else 0.0)
            recent_v  = atc_hist.loc[atc_hist["period"].isin(recent_3), "sev"].values
            prev_v    = atc_hist.loc[atc_hist["period"].isin(prev_3),   "sev"].values
            meses     = int(atc_hist["period"].nunique())
            peor      = float(atc_hist["sev"].max()) if not atc_hist.empty else 0.0
            sev_t3    = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
            avg_r     = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
            avg_p     = float(prev_v.mean())   if len(prev_v)   > 0 else 0.0
            tendencia = float(avg_r - avg_p)
            target    = int(target_data.get(atc7, 0.0) >= 4)

            records.append({
                "atc7":                     atc7,
                "period":                   target_period,
                "invima_sev_actual":        sev_t1,
                "invima_sev_t3_avg":        sev_t3,
                "invima_meses_monitoreado": meses,
                "invima_peor_sev_hist":     peor,
                "invima_tendencia":         tendencia,
                "desabastecido":            target,
            })

    df_inv = pd.DataFrame(records)
    n_pos = df_inv["desabastecido"].sum()
    print(f"  Filas generadas: {len(df_inv):,} | positivos (y=1): {n_pos} ({n_pos/len(df_inv):.2%})")
    return df_inv


# ── Búsquedas recientes (busquedas_log) para enriquecer modelo producción ──────
def _cargar_busquedas_norm(db) -> dict:
    """Retorna {cum_id: busquedas_norm} desde busquedas_log últimos 30 días."""
    try:
        rows = db.execute(text("""
            SELECT cum_id, COUNT(*) as n
            FROM busquedas_log
            WHERE fecha > datetime('now', '-30 days')
            GROUP BY cum_id
        """)).fetchall()
        return {r[0]: min(float(r[1]) / 100.0, 1.0) for r in rows}
    except Exception:
        return {}


# ── Features para inferencia en producción (snapshot del mes más reciente) ────
def _construir_invima_produccion(db) -> pd.DataFrame:
    """
    Para generar predicciones en producción: features derivadas de todos los
    meses históricos disponibles (target = mes actual, features = todo lo anterior).
    Retorna columnas: atc7, features INVIMA (5 cols), desabastecido (placeholder=0).
    """
    row = db.execute(
        text("SELECT anio, mes FROM invima_seguimiento ORDER BY anio DESC, mes DESC LIMIT 1")
    ).fetchone()
    if row is None:
        return pd.DataFrame(columns=["atc7"] + FEATURE_COLS_INVIMA + ["desabastecido"])

    target_anio, target_mes = row
    target_period = target_anio * 100 + target_mes

    hist = db.execute(text("""
        SELECT atc, estado, anio, mes
        FROM invima_seguimiento
        WHERE atc IS NOT NULL
          AND NOT (anio = :ta AND mes = :tm)
        ORDER BY atc, anio, mes
    """), {"ta": target_anio, "tm": target_mes}).fetchall()

    target_rows = db.execute(text("""
        SELECT atc, MAX(CASE estado
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
    target_by_atc7 = {r[0]: int(r[1] or 0) for r in target_rows if r[0]}

    df_hist = pd.DataFrame(hist, columns=["atc7", "estado", "anio", "mes"])
    df_hist["sev"]    = df_hist["estado"].map(INVIMA_SEV).fillna(0).astype(float)
    df_hist["period"] = df_hist["anio"] * 100 + df_hist["mes"]
    monthly = df_hist.groupby(["atc7", "period"])["sev"].max().reset_index()

    all_periods_sorted = sorted(monthly["period"].unique(), reverse=True)
    lag1_period = all_periods_sorted[0] if all_periods_sorted else None
    recent_3    = set(all_periods_sorted[:3])
    prev_3      = set(all_periods_sorted[3:6])

    records = []
    all_atcs = set(monthly["atc7"]) | set(target_by_atc7.keys())
    for atc7 in all_atcs:
        atc_hist  = monthly[monthly["atc7"] == atc7]
        sev_t1    = float(atc_hist.loc[atc_hist["period"] == lag1_period, "sev"].max()
                          if lag1_period and not atc_hist[atc_hist["period"] == lag1_period].empty else 0.0)
        recent_v  = atc_hist.loc[atc_hist["period"].isin(recent_3), "sev"].values
        prev_v    = atc_hist.loc[atc_hist["period"].isin(prev_3),   "sev"].values
        meses     = int(atc_hist["period"].nunique())
        peor      = float(atc_hist["sev"].max()) if not atc_hist.empty else 0.0
        sev_t3    = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
        avg_r     = float(recent_v.mean()) if len(recent_v) > 0 else 0.0
        avg_p     = float(prev_v.mean())   if len(prev_v)   > 0 else 0.0
        records.append({
            "atc7":                     atc7,
            "invima_sev_actual":        sev_t1,
            "invima_sev_t3_avg":        sev_t3,
            "invima_meses_monitoreado": meses,
            "invima_peor_sev_hist":     peor,
            "invima_tendencia":         float(avg_r - avg_p),
            "desabastecido":            int(target_by_atc7.get(atc7, 0) >= 4),
        })

    return pd.DataFrame(records)


# ── Train ──────────────────────────────────────────────────────────────────────
def main():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, classification_report
    )
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.utils.class_weight import compute_class_weight

    print("=== Reentrenamiento con datos INVIMA (split temporal) ===\n")
    init_db()
    db = SessionLocal()
    try:
        print("1. Construyendo features base (CUM)...")
        df_base = _construir_base(db)

        print("2. Construyendo series temporales INVIMA (multi-mes)...")
        df_inv = _construir_invima_temporal(db)

        print("3. Construyendo features de producción (mes más reciente)...")
        df_inv_prod = _construir_invima_produccion(db)

        print("3b. Cargando busquedas_norm reales (últimos 30 días)...")
        busquedas_map = _cargar_busquedas_norm(db)
        print(f"   {len(busquedas_map)} productos con búsquedas recientes")
    finally:
        db.close()

    if df_inv.empty:
        print("ERROR: sin datos INVIMA para entrenar.")
        return

    # ── Split temporal: últimos 3 meses como test ──────────────────────────────
    all_periods = sorted(df_inv["period"].unique())
    n_test_months = 3
    if len(all_periods) <= n_test_months:
        print(f"ERROR: se necesitan más de {n_test_months} meses para split temporal.")
        return

    split_period = all_periods[-n_test_months]
    train_periods = [p for p in all_periods if p < split_period]
    test_periods  = [p for p in all_periods if p >= split_period]

    print(f"\n   Split temporal:")
    print(f"   Train: {len(train_periods)} meses ({train_periods[0]} -> {train_periods[-1]})")
    print(f"   Test : {len(test_periods)} meses  ({test_periods[0]} -> {test_periods[-1]})")

    df_train_inv = df_inv[df_inv["period"].isin(train_periods)]
    df_test_inv  = df_inv[df_inv["period"].isin(test_periods)]

    # ── Unir con features CUM ──────────────────────────────────────────────────
    print("\n4. Uniendo con features CUM (join por ATC7)...")

    def _merge_cum(df_i: pd.DataFrame) -> tuple:
        merged = df_base.merge(
            df_i[["atc7"] + FEATURE_COLS_INVIMA + ["desabastecido"]],
            left_on="atc_upper", right_on="atc7",
            how="left",
        )
        for col in FEATURE_COLS_INVIMA:
            merged[col] = merged[col].fillna(0.0)
        merged["desabastecido"] = merged["desabastecido"].fillna(0).astype(int)
        return merged[FEATURE_COLS].values, merged["desabastecido"].values

    X_train, y_train = _merge_cum(df_train_inv)
    X_test,  y_test  = _merge_cum(df_test_inv)

    print(f"   Train: {len(X_train):,} muestras | positivos: {y_train.sum()} ({y_train.mean():.2%})")
    print(f"   Test : {len(X_test):,} muestras  | positivos: {y_test.sum()} ({y_test.mean():.2%})")

    if y_train.sum() == 0 or y_test.sum() == 0:
        print("ERROR: train o test sin muestras positivas — revisa los datos INVIMA.")
        return

    # ── Entrenar sobre TODOS los datos (train+test) para modelo de producción ──
    # Evaluamos métricas en test (honesto), pero el modelo final se entrena
    # en todos los datos para máxima cobertura en producción.
    print("\n5. Entrenando RandomForest + calibración Platt (sobre datos de train)...")

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
    modelo_eval = CalibratedClassifierCV(rf, cv=3, method="sigmoid")
    modelo_eval.fit(X_train, y_train)

    y_prob = modelo_eval.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    roc_auc       = float(roc_auc_score(y_test, y_prob))
    avg_precision = float(average_precision_score(y_test, y_prob))

    print(f"\n=== MÉTRICAS (test temporal — meses {test_periods[0]}->{test_periods[-1]}) ===")
    print(f"  ROC-AUC       : {roc_auc:.4f}")
    print(f"  Avg Precision : {avg_precision:.4f}")
    print(f"  Train/Test    : {len(X_train):,} / {len(X_test):,}")
    print()
    print(classification_report(y_test, y_pred,
                                target_names=["Sin alerta", "DESABASTECIDO/EN_RIESGO"]))

    # ── Modelo de producción: reentrenar en todos los datos ────────────────────
    print("6. Reentrenando modelo final en TODOS los datos (train + test)...")

    # Para producción, usar el snapshot del mes más reciente (features actualizadas)
    df_all = df_base.merge(
        df_inv_prod[["atc7"] + FEATURE_COLS_INVIMA + ["desabastecido"]],
        left_on="atc_upper", right_on="atc7",
        how="left",
    )
    for col in FEATURE_COLS_INVIMA:
        df_all[col] = df_all[col].fillna(0.0)
    df_all["desabastecido"] = df_all["desabastecido"].fillna(0).astype(int)

    # Enriquecer con búsquedas reales para el modelo de producción
    if busquedas_map:
        df_all["busquedas_norm"] = df_all["cum_id"].map(busquedas_map).fillna(0.0)
        n_enriq = (df_all["busquedas_norm"] > 0).sum()
        print(f"   busquedas_norm: {n_enriq} productos con valor > 0 (máx {df_all['busquedas_norm'].max():.3f})")

    X_all = df_all[FEATURE_COLS].values
    y_all = df_all["desabastecido"].values

    clases_all = np.unique(y_all)
    pesos_all  = compute_class_weight("balanced", classes=clases_all, y=y_all)
    cw_all     = {int(c): float(p) for c, p in zip(clases_all, pesos_all)}

    rf_prod = RandomForestClassifier(
        n_estimators=300,
        max_depth=14,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight=cw_all,
        random_state=42,
        n_jobs=-1,
    )
    modelo_prod = CalibratedClassifierCV(rf_prod, cv=3, method="sigmoid")
    modelo_prod.fit(X_all, y_all)

    print(f"   Modelo de producción: {len(X_all):,} muestras | positivos: {y_all.sum()}")

    # Importancia de features
    try:
        base_rf = modelo_prod.calibrated_classifiers_[0].estimator
        print("\n  Importancia de features (modelo producción):")
        for feat, imp in sorted(zip(FEATURE_COLS, base_rf.feature_importances_), key=lambda x: -x[1]):
            bar = "|" * int(imp * 40)
            print(f"  {feat:<35} {imp:.4f}  {bar}")
    except Exception:
        pass

    # ── Guardar ────────────────────────────────────────────────────────────────
    print("\n7. Guardando modelo...")
    metricas = {
        "roc_auc":        roc_auc,
        "avg_precision":  avg_precision,
        "n_train":        int(len(X_all)),
        "n_test":         int(len(X_test)),
        "pos_rate_train": float(y_all.mean()),
        "split_temporal": {
            "train_periods": train_periods,
            "test_periods":  test_periods,
        },
        "target": "invima_sev>=4_(DESABASTECIDO|EN_RIESGO)_en_mes_target",
        "features": FEATURE_COLS,
    }

    artefacto = {"modelo": modelo_prod, "features": FEATURE_COLS, "metricas": metricas}
    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(artefacto, f)
    print(f"   Guardado en: {MODEL_PATH}")
    print(f"\nListo. ROC-AUC (temporal): {roc_auc:.4f} | AvgP: {avg_precision:.4f}")


if __name__ == "__main__":
    main()
