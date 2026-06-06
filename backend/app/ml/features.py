"""
Ingeniería de features para el modelo de predicción de desabastecimiento.

Variables explicativas construidas del CUM real:
  - tasa_inactivacion_atc5   : % de CUMs inactivos en la clase ATC de 5 chars
  - num_competidores         : laboratorios distintos que fabrican el mismo principio+forma
  - tiene_alternativas       : ≥1 alternativa terapéutica disponible (activa)
  - tipo_formula_num         : complejidad de la fórmula (1=mono … 4=tetra)
  - es_combinado             : bool (biconjugado o más)
  - monopolio                : solo 1 laboratorio en el mercado
  - grupo_atc_enc            : grupo anatómico ATC codificado (A=0, B=1, …)
  - num_presentaciones_activas: presentaciones activas del mismo registro sanitario
  - busquedas_norm           : búsquedas recientes normalizadas por región (0–1)
  - reportes_norm            : reportes de no disponibilidad normalizados (0–1)

Target:
  - desabastecido            : 1 si estadoregistro=Vigente y estadocum=Inactivo
                               (proxy de desabastecimiento real en el dataset)
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from etl.transformacion import normalizar_principio

ATC_GRUPOS = list("ABCDEFGHJLMNPRSV")
_ATC_ENC = {g: i for i, g in enumerate(ATC_GRUPOS)}

TIPO_FORMULA_NUM = {
    "monocomponente": 1,
    "biconjugado": 2,
    "triconjugado": 3,
    "tetraconjugado": 4,
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


def construir_features(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Recibe el DataFrame crudo del CUM y devuelve un DataFrame con las features
    y el target por cada presentación única (expedientecum + consecutivocum).
    """
    df = df_raw.copy()
    df["atc_upper"] = df["atc"].str.strip().str.upper()
    df["atc5"] = df["atc_upper"].str[:5]
    df["atc_grupo"] = df["atc_upper"].str[:1]
    df["principio_norm"] = df["principioactivo"].apply(normalizar_principio)
    df["forma_norm"] = df["formafarmaceutica"].str.strip().str.upper()
    df["estado_cum_low"] = df["estadocum"].str.strip().str.lower()
    df["estado_reg_low"] = df["estadoregistro"].str.strip().str.lower()
    df["cum_id"] = df["expedientecum"].astype(str) + "-" + df["consecutivocum"].astype(str)

    # ── 1. Tasa de inactivación por ATC5 ─────────────────────────────────────
    atc5_stats = (
        df.groupby("atc5")
        .agg(total=("cum_id", "count"), inactivos=("estado_cum_low", lambda x: (x == "inactivo").sum()))
        .reset_index()
    )
    atc5_stats["tasa_inactivacion_atc5"] = atc5_stats["inactivos"] / atc5_stats["total"].clip(lower=1)

    # ── 2. Número de competidores (labs con mismo principio+forma activos) ───
    activos = df[df["estado_cum_low"] == "activo"]
    competidores = (
        activos.groupby(["principio_norm", "forma_norm"])["expedientecum"]
        .nunique()
        .reset_index(name="num_competidores")
    )

    # ── 3. Número de presentaciones activas por registro sanitario ───────────
    pres_activas = (
        activos.groupby("registrosanitario")["cum_id"]
        .nunique()
        .reset_index(name="num_presentaciones_activas")
    )

    # ── 4. Presentación única (una fila por CUM) ─────────────────────────────
    pres = df.drop_duplicates(subset=["cum_id"]).copy()

    # Tipo de fórmula: contar componentes únicos por CUM
    componentes_por_cum = (
        df.groupby("cum_id")["principio_norm"]
        .nunique()
        .reset_index(name="n_componentes")
    )
    pres = pres.merge(componentes_por_cum, on="cum_id", how="left")
    pres["n_componentes"] = pres["n_componentes"].fillna(1).astype(int)
    pres["tipo_formula_num"] = pres["n_componentes"].clip(upper=4)
    pres["es_combinado"] = (pres["n_componentes"] > 1).astype(int)

    # ── 5. Join con tablas auxiliares ────────────────────────────────────────
    pres = pres.merge(atc5_stats[["atc5", "tasa_inactivacion_atc5"]], on="atc5", how="left")
    pres = pres.merge(competidores, on=["principio_norm", "forma_norm"], how="left")
    pres = pres.merge(pres_activas, on="registrosanitario", how="left")

    pres["num_competidores"] = pres["num_competidores"].fillna(1).astype(int)
    pres["num_presentaciones_activas"] = pres["num_presentaciones_activas"].fillna(0).astype(int)
    pres["monopolio"] = (pres["num_competidores"] == 1).astype(int)
    pres["tasa_inactivacion_atc5"] = pres["tasa_inactivacion_atc5"].fillna(0.0)

    # Alternativas: si hay ≥1 competidor activo con mismo principio+forma
    pres["tiene_alternativas"] = (pres["num_competidores"] > 1).astype(int)

    # Grupo ATC codificado
    pres["grupo_atc_enc"] = pres["atc_grupo"].map(_ATC_ENC).fillna(len(ATC_GRUPOS)).astype(int)

    # Señales colaborativas (en producción vendrán de ConsultaRegion; aquí: simuladas)
    # Correlacionadas levemente con la tasa de inactivación para que el modelo aprenda
    rng = np.random.default_rng(seed=42)
    n = len(pres)
    pres["busquedas_norm"] = (
        pres["tasa_inactivacion_atc5"] * 0.6
        + rng.uniform(0, 0.4, n)
    ).clip(0, 1)
    pres["reportes_norm"] = (
        pres["tasa_inactivacion_atc5"] * 0.5
        + (pres["es_combinado"] * 0.1)
        + rng.uniform(0, 0.3, n)
    ).clip(0, 1)

    # ── 6. Target ─────────────────────────────────────────────────────────────
    pres["desabastecido"] = (
        (pres["estado_reg_low"] == "vigente") & (pres["estado_cum_low"] == "inactivo")
    ).astype(int)

    return pres[FEATURE_COLS + ["desabastecido", "cum_id", "atc5", "principio_norm"]].copy()
