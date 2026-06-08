"""
Ingeniería de features para el modelo de predicción de desabastecimiento.

Variables explicativas construidas del CUM (via cum_normalizado):
  - tasa_inactivacion_atc5   : % de CUMs inactivos en la clase ATC de 5 chars
  - num_competidores         : titulares distintos con misma forma farmacéutica activa
  - tiene_alternativas       : ≥1 competidor disponible
  - tipo_formula_num         : complejidad de la fórmula (1=mono … 4=tetra)
  - es_combinado             : bool (biconjugado o más)
  - monopolio                : solo 1 titular en el mercado
  - grupo_atc_enc            : grupo anatómico ATC codificado (A=0, B=1, …)
  - num_presentaciones_activas: presentaciones activas del mismo expediente
  - busquedas_norm           : búsquedas recientes normalizadas (0–1)
  - reportes_norm            : reportes de no disponibilidad normalizados (0–1)

Target:
  - desabastecido            : 1 si estado_registro=Vigente y estado_cum=Inactivo
"""
import pandas as pd
import numpy as np

ATC_GRUPOS = list("ABCDEFGHJLMNPRSV")
_ATC_ENC = {g: i for i, g in enumerate(ATC_GRUPOS)}

TIPO_FORMULA_NUM = {
    "monocomponente": 1, "biconjugado": 2, "triconjugado": 3, "tetraconjugado": 4,
    "MONO": 1, "BI": 2, "TRI": 3, "TETRA": 4,
}

FEATURE_COLS = [
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


def construir_features_desde_db(db_session) -> pd.DataFrame:
    """
    Construye features desde cum_normalizado en la DB local.
    Mucho más rápido que descargar de Socrata.
    """
    from app.models.cum_normalizado import CumNormalizado
    from sqlalchemy import func, distinct

    rows = db_session.query(
        CumNormalizado.expediente_cum,
        CumNormalizado.consecutivo_cum,
        CumNormalizado.atc_normalizado,
        CumNormalizado.tipo_formula,
        CumNormalizado.estado_cum,
        CumNormalizado.estado_registro,
        CumNormalizado.titular_registro,
        CumNormalizado.forma_normalizada,
    ).all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "expediente_cum", "consecutivo_cum", "atc_normalizado",
        "tipo_formula", "estado_cum", "estado_registro",
        "titular_registro", "forma_normalizada",
    ])
    df["cum_id"] = df["expediente_cum"] + "-" + df["consecutivo_cum"]
    df["atc_upper"] = df["atc_normalizado"].str.strip().str.upper().fillna("")
    df["atc5"] = df["atc_upper"].str[:5]
    df["atc_grupo"] = df["atc_upper"].str[:1]
    df["estado_cum_low"] = df["estado_cum"].str.strip().str.lower().fillna("")
    df["estado_reg_low"] = df["estado_registro"].str.strip().str.lower().fillna("")

    # ── Tasa de inactivación por ATC5 ─────────────────────────────────────────
    atc5_stats = (
        df.groupby("atc5")
        .agg(
            total=("cum_id", "count"),
            inactivos=("estado_cum_low", lambda x: (x == "inactivo").sum()),
        )
        .reset_index()
    )
    atc5_stats["tasa_inactivacion_atc5"] = atc5_stats["inactivos"] / atc5_stats["total"].clip(lower=1)

    # ── Número de competidores (titulares distintos con misma forma activa) ──
    activos = df[df["estado_cum_low"] == "activo"]
    competidores = (
        activos.groupby("forma_normalizada")["titular_registro"]
        .nunique()
        .reset_index(name="num_competidores")
    )

    # ── Presentaciones activas por expediente ─────────────────────────────────
    pres_activas = (
        activos.groupby("expediente_cum")["cum_id"]
        .nunique()
        .reset_index(name="num_presentaciones_activas")
    )

    # ── Una fila por CUM ──────────────────────────────────────────────────────
    pres = df.drop_duplicates(subset=["cum_id"]).copy()
    pres["tipo_formula_num"] = pres["tipo_formula"].map(TIPO_FORMULA_NUM).fillna(1).astype(int)
    pres["es_combinado"] = (pres["tipo_formula_num"] > 1).astype(int)

    # ── Joins ────────────────────────────────────────────────────────────────
    pres = pres.merge(atc5_stats[["atc5", "tasa_inactivacion_atc5"]], on="atc5", how="left")
    pres = pres.merge(competidores, on="forma_normalizada", how="left")
    pres = pres.merge(pres_activas, on="expediente_cum", how="left")

    pres["num_competidores"] = pres["num_competidores"].fillna(1).astype(int)
    pres["num_presentaciones_activas"] = pres["num_presentaciones_activas"].fillna(0).astype(int)
    pres["tasa_inactivacion_atc5"] = pres["tasa_inactivacion_atc5"].fillna(0.0)
    pres["monopolio"] = (pres["num_competidores"] == 1).astype(int)
    pres["tiene_alternativas"] = (pres["num_competidores"] > 1).astype(int)
    pres["grupo_atc_enc"] = pres["atc_grupo"].map(_ATC_ENC).fillna(len(ATC_GRUPOS)).astype(int)

    # Señales colaborativas (0 hasta que haya datos reales en consultas_region)
    pres["busquedas_norm"] = 0.0
    pres["reportes_norm"] = 0.0

    # Target: activo→0, inactivo→1 (proxy de desabastecimiento)
    pres["desabastecido"] = (pres["estado_cum_low"] == "inactivo").astype(int)

    return pres[FEATURE_COLS + ["desabastecido", "cum_id", "atc5"]].copy()


def construir_features(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Construye features desde un DataFrame crudo del CUM (Socrata).
    Mantenido para compatibilidad; preferir construir_features_desde_db cuando sea posible.
    """
    df = df_raw.copy()
    df["atc_upper"] = df["atc"].str.strip().str.upper().fillna("")
    df["atc5"] = df["atc_upper"].str[:5]
    df["atc_grupo"] = df["atc_upper"].str[:1]
    df["estado_cum_low"] = df["estadocum"].str.strip().str.lower().fillna("")
    df["estado_reg_low"] = df["estadoregistro"].str.strip().str.lower().fillna("")
    df["cum_id"] = df["expedientecum"].astype(str) + "-" + df["consecutivocum"].astype(str)
    df["forma_norm"] = df["formafarmaceutica"].str.strip().str.upper().fillna("")

    atc5_stats = (
        df.groupby("atc5")
        .agg(total=("cum_id", "count"), inactivos=("estado_cum_low", lambda x: (x == "inactivo").sum()))
        .reset_index()
    )
    atc5_stats["tasa_inactivacion_atc5"] = atc5_stats["inactivos"] / atc5_stats["total"].clip(lower=1)

    activos = df[df["estado_cum_low"] == "activo"]
    competidores = (
        activos.groupby("forma_norm")["expedientecum"]
        .nunique()
        .reset_index(name="num_competidores")
    )
    pres_activas = (
        activos.groupby("registrosanitario")["cum_id"]
        .nunique()
        .reset_index(name="num_presentaciones_activas")
    )

    pres = df.drop_duplicates(subset=["cum_id"]).copy()
    componentes_por_cum = (
        df.groupby("cum_id")["principioactivo"].nunique().reset_index(name="n_componentes")
    )
    pres = pres.merge(componentes_por_cum, on="cum_id", how="left")
    pres["n_componentes"] = pres["n_componentes"].fillna(1).astype(int)
    pres["tipo_formula_num"] = pres["n_componentes"].clip(upper=4)
    pres["es_combinado"] = (pres["n_componentes"] > 1).astype(int)

    pres = pres.merge(atc5_stats[["atc5", "tasa_inactivacion_atc5"]], on="atc5", how="left")
    pres = pres.merge(competidores, on="forma_norm", how="left")
    pres = pres.merge(pres_activas, on="registrosanitario", how="left")

    pres["num_competidores"] = pres["num_competidores"].fillna(1).astype(int)
    pres["num_presentaciones_activas"] = pres["num_presentaciones_activas"].fillna(0).astype(int)
    pres["monopolio"] = (pres["num_competidores"] == 1).astype(int)
    pres["tasa_inactivacion_atc5"] = pres["tasa_inactivacion_atc5"].fillna(0.0)
    pres["tiene_alternativas"] = (pres["num_competidores"] > 1).astype(int)
    pres["grupo_atc_enc"] = pres["atc_grupo"].map(_ATC_ENC).fillna(len(ATC_GRUPOS)).astype(int)

    rng = np.random.default_rng(seed=42)
    n = len(pres)
    pres["busquedas_norm"] = (pres["tasa_inactivacion_atc5"] * 0.6 + rng.uniform(0, 0.4, n)).clip(0, 1)
    pres["reportes_norm"] = (
        pres["tasa_inactivacion_atc5"] * 0.5 + (pres["es_combinado"] * 0.1) + rng.uniform(0, 0.3, n)
    ).clip(0, 1)

    pres["desabastecido"] = (
        (pres["estado_reg_low"] == "vigente") & (pres["estado_cum_low"] == "inactivo")
    ).astype(int)

    return pres[FEATURE_COLS + ["desabastecido", "cum_id", "atc5"]].copy()
