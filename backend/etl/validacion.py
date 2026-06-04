"""
Validación de integridad del CUM.

Reglas aplicadas:
  V1  Campo obligatorio vacío / "SIN DATO" en registros Vigentes
  V2  Código ATC con formato inválido
  V3  Registro INVIMA con formato inválido
  V4  Estado inconsistente: estadoregistro=Vigente pero estadocum=Inactivo
  V5  Concentración no numérica (letras A/B/S — código interno INVIMA sin valor)
  V6  principioactivo no coincide con descripcionatc para el mismo ATC
  V7  fechainactivo presente en registros con estadocum=Activo (contradicción)
  V8  Duplicado exacto (mismo CUM + misma forma + mismo principio + misma concentración)
"""
import re
import pandas as pd
from pathlib import Path

ATC_REGEX = re.compile(r"^[A-Z]\d{2}[A-Z]{1,2}\d{0,2}$")
INVIMA_REGEX = re.compile(r"^INVIMA\s+\d{4}[A-Z]-\d+", re.IGNORECASE)
SIN_DATO = {"SIN DATO", "SIN_DATO", "N/A", "NA", "", "NaN", "nan"}

CAMPOS_OBLIGATORIOS_VIGENTE = [
    "principioactivo", "formafarmaceutica", "viaadministracion",
    "registrosanitario", "atc",
]


def _es_sin_dato(valor) -> bool:
    if pd.isna(valor):
        return True
    return str(valor).strip().upper() in SIN_DATO


def validar(df: pd.DataFrame, verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Retorna (df_limpio, df_problemas).
    df_problemas tiene columnas: expedientecum, regla, descripcion, severidad.
    """
    problemas: list[dict] = []

    def registrar(mask: pd.Series, regla: str, descripcion: str, severidad: str):
        for idx in df[mask].index:
            problemas.append({
                "expedientecum": df.at[idx, "expedientecum"] if "expedientecum" in df.columns else idx,
                "producto": df.at[idx, "producto"] if "producto" in df.columns else "",
                "regla": regla,
                "descripcion": descripcion,
                "severidad": severidad,
            })

    vigentes = df["estadoregistro"].str.strip().str.lower() == "vigente" if "estadoregistro" in df.columns else pd.Series(True, index=df.index)

    # V1 — Campos obligatorios vacíos en vigentes
    for campo in CAMPOS_OBLIGATORIOS_VIGENTE:
        if campo in df.columns:
            mask = vigentes & df[campo].apply(_es_sin_dato)
            registrar(mask, "V1", f"Campo obligatorio vacío: {campo}", "ERROR")

    # V2 — ATC inválido
    if "atc" in df.columns:
        def atc_invalido(v):
            if _es_sin_dato(v):
                return False  # ya capturado por V1
            return not ATC_REGEX.match(str(v).strip().upper())
        mask = df["atc"].apply(atc_invalido)
        registrar(mask, "V2", "Código ATC con formato inválido", "ERROR")

    # V3 — Registro sanitario INVIMA inválido
    if "registrosanitario" in df.columns:
        def reg_invalido(v):
            if _es_sin_dato(v):
                return False
            return not INVIMA_REGEX.match(str(v).strip())
        mask = df["registrosanitario"].apply(reg_invalido)
        registrar(mask, "V3", "Registro sanitario con formato inválido", "ADVERTENCIA")

    # V4 — estadoregistro=Vigente pero estadocum=Inactivo
    if "estadoregistro" in df.columns and "estadocum" in df.columns:
        mask = (
            vigentes &
            (df["estadocum"].str.strip().str.lower() == "inactivo")
        )
        registrar(mask, "V4", "estadoregistro=Vigente pero estadocum=Inactivo", "ADVERTENCIA")

    # V5 — Concentración no numérica (letras sueltas)
    if "concentracion" in df.columns:
        def conc_no_numerica(v):
            if _es_sin_dato(v):
                return False
            s = str(v).strip()
            return bool(re.match(r"^[A-Za-z]{1,3}$", s))
        mask = df["concentracion"].apply(conc_no_numerica)
        registrar(mask, "V5", "Concentración es código interno (letra), no valor numérico", "INFORMACION")

    # V6 — principioactivo ≠ descripcionatc para el mismo ATC (por mayoría)
    if "atc" in df.columns and "principioactivo" in df.columns and "descripcionatc" in df.columns:
        atc_correcto = (
            df[~df["atc"].apply(_es_sin_dato) & ~df["descripcionatc"].apply(_es_sin_dato)]
            .groupby("atc")["descripcionatc"]
            .agg(lambda x: x.mode()[0] if len(x) > 0 else None)
        )
        def descripcion_inconsistente(row):
            atc = str(row.get("atc", "")).strip()
            desc = str(row.get("descripcionatc", "")).strip()
            if _es_sin_dato(atc) or _es_sin_dato(desc) or atc not in atc_correcto:
                return False
            return desc.upper() != str(atc_correcto[atc]).upper()
        mask = df.apply(descripcion_inconsistente, axis=1)
        registrar(mask, "V6", "descripcionatc no coincide con la mayoría para este ATC", "ADVERTENCIA")

    # V7 — fechainactivo presente en estadocum=Activo
    if "fechainactivo" in df.columns and "estadocum" in df.columns:
        mask = (
            (df["estadocum"].str.strip().str.lower() == "activo") &
            df["fechainactivo"].notna() &
            ~df["fechainactivo"].apply(_es_sin_dato)
        )
        registrar(mask, "V7", "fechainactivo registrada en CUM con estadocum=Activo", "ADVERTENCIA")

    # V8 — Duplicados exactos
    dup_cols = [c for c in ["expedientecum", "consecutivocum", "principioactivo", "formafarmaceutica", "concentracion", "nombrerol"] if c in df.columns]
    if dup_cols:
        dup_mask = df.duplicated(subset=dup_cols, keep="first")
        registrar(dup_mask, "V8", f"Registro duplicado exacto ({', '.join(dup_cols)})", "ADVERTENCIA")

    df_problemas = pd.DataFrame(problemas) if problemas else pd.DataFrame(
        columns=["expedientecum", "producto", "regla", "descripcion", "severidad"]
    )

    # Construir df_limpio: excluir registros con error crítico
    errores_idx = set(
        df_problemas[df_problemas["severidad"] == "ERROR"]["expedientecum"].tolist()
    ) if not df_problemas.empty else set()

    df_limpio = df[~df["expedientecum"].isin(errores_idx)].copy() if errores_idx else df.copy()

    if verbose:
        _imprimir_resumen(df, df_problemas, df_limpio)

    return df_limpio, df_problemas


def _imprimir_resumen(df_original: pd.DataFrame, df_problemas: pd.DataFrame, df_limpio: pd.DataFrame):
    total = len(df_original)
    print("\n" + "="*60)
    print("REPORTE DE VALIDACION DE INTEGRIDAD - CUM")
    print("="*60)
    print(f"  Registros totales descargados : {total:>10,}")
    print(f"  Registros que pasan validacion: {len(df_limpio):>10,}")
    print(f"  Registros con problemas       : {len(df_problemas):>10,}")
    print()

    if df_problemas.empty:
        print("  Sin problemas encontrados.")
        return

    resumen = df_problemas.groupby(["regla", "severidad", "descripcion"]).size().reset_index(name="count")
    for _, row in resumen.iterrows():
        print(f"  [{row['severidad']:<12}] {row['regla']} — {row['descripcion']}: {row['count']:,}")

    print()
    errores = df_problemas[df_problemas["severidad"] == "ERROR"]
    advertencias = df_problemas[df_problemas["severidad"] == "ADVERTENCIA"]
    info = df_problemas[df_problemas["severidad"] == "INFORMACION"]
    print(f"  Total ERRORES      : {len(errores):,} (excluidos del dataset limpio)")
    print(f"  Total ADVERTENCIAS : {len(advertencias):,} (incluidos con marca)")
    print(f"  Total INFORMATIVOS : {len(info):,}")
    print("="*60)


def guardar_reporte(df_problemas: pd.DataFrame, ruta: Path):
    ruta.parent.mkdir(exist_ok=True)
    df_problemas.to_csv(ruta, index=False, encoding="utf-8-sig")
    print(f"Reporte guardado en: {ruta}")
