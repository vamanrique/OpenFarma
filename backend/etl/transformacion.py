"""
Transformaciones del CUM: normalización de principios activos,
detección de conjugaciones, construcción de concentración real.

La fuente es siempre el JSON online — este módulo solo transforma,
no lee ni escribe archivos.
"""
import re
import pandas as pd
from dataclasses import dataclass, field

# Sufijos de sal/éster/forma a eliminar para obtener la DCI (nombre genérico)
_SUFIJOS_SAL = re.compile(
    r"\b(TRIHIDRATO|MONOHIDRATO|DIHIDRATO|ANHIDRO|HEMIHIDRATO|"
    r"SODICO|SODICA|POTASICO|POTASICA|CALCICO|CALCICA|MAGNESICO|"
    r"CLORHIDRATO|DICLORHIDRATO|HIDROCLORURO|BROMHIDRATO|"
    r"FOSFATO|BISFOSFATO|SULFATO|BISULFATO|TARTRATO|BITARTRATO|"
    r"MALEATO|FUMARATO|SUCCINATO|GLUCONATO|ACETATO|PROPIONATO|"
    r"MESILATO|TOSILATO|BESILATO|ACESULATO|ADIPATO|ESTEARATO|"
    r"LACTATO|CITRATO|MALATO|OXALATO|VALERATO|BUTIRATO|"
    r"DIPROPIONATO|FUROATO|PROPIONATO|HEXANOATO|DECANOATO|"
    r"PALMITATO|ESTEARATO|BENZOATO|SALICILATO|"
    r"TRIHIDRATADA?|DIHIDRATADA?|MONOHIDRATADA?|BASE)\b",
    re.IGNORECASE,
)

# Extrae el primer valor numérico de un string de concentración ("25 mg" → 25.0)
_NUM_DOSIS = re.compile(r'(\d+(?:[.,]\d+)?)')

# Patrón para extraer el DCI de "NOMBRE EQUIVALENTE A DCI" — tolera espacio faltante antes del DCI
# cubre tanto "EQUIVALENTE A FENTANILO" como "EQUIVALENTE AFENTANILO" (sin espacio, frecuente en CUM)
_EQUIV_PATRON = re.compile(
    r"EQUIVALENTE\s+A?\s*(.+?)(?:\s*\d[\d.,]*\s*(?:MG|MCG|G|UI|U|ML))?$",
    re.IGNORECASE,
)

# Limpia cualquier residuo "EQUIVALENTE [A] X" que quede tras la extracción parcial
_EQUIV_RESIDUO = re.compile(r"\s+EQUIVALENTE\b.*$", re.IGNORECASE)

# Patrón para limpiar concentraciones incrustadas en el nombre
_CONCENTRACION_INCRUSTADA = re.compile(
    r"\s+\d[\d.,]*\s*(?:MG|MCG|G|UI|U|ML|%)\b.*$",
    re.IGNORECASE,
)


def normalizar_principio(principio: str) -> str:
    """
    Extrae el DCI limpio de un principio activo del CUM.

    Ejemplos:
      "AMOXICILINA TRIHIDRATO EQUIVALENTE A AMOXICILINA" → "AMOXICILINA"
      "CLAVULANATO DE POTASIO EQUIVALENTE A ACIDO CLAVULANICO" → "ACIDO CLAVULANICO"
      "METFORMINA CLORHIDRATO" → "METFORMINA"
      "LEVODOPA" → "LEVODOPA"
    """
    p = str(principio).strip().upper()

    # Si hay "EQUIVALENTE [A] X", tomar la parte posterior (tolera espacio faltante)
    m = _EQUIV_PATRON.search(p)
    if m:
        p = m.group(1).strip()

    # Quitar concentraciones incrustadas al final
    p = _CONCENTRACION_INCRUSTADA.sub("", p).strip()

    # Quitar sufijos de sal/forma
    p = _SUFIJOS_SAL.sub("", p)

    # Limpiar cualquier residuo "EQUIVALENTE ..." que no capturó el patrón principal
    p = _EQUIV_RESIDUO.sub("", p).strip()

    # Limpiar espacios múltiples
    p = re.sub(r"\s{2,}", " ", p).strip()

    return p


def construir_concentracion(row: pd.Series) -> str:
    """
    Construye la concentración real a partir de cantidad + unidad + unidadreferencia.
    El campo 'concentracion' del API contiene letras (A/B/S), no valores.
    """
    cantidad = str(row.get("cantidad", "")).strip()
    unidad = str(row.get("unidad", "")).strip()
    unidad_ref = str(row.get("unidadreferencia", "")).strip()
    unidad_medida = str(row.get("unidadmedida", "")).strip()

    if not cantidad or cantidad in ("nan", "None", ""):
        return ""

    # Valores de campo que no son unidades reales (basura del CUM)
    _INVALIDOS = {"nan", "None", "U", "", "SI", "NO", "S", "N", "N/A", "NA"}

    # Unidad real: preferir unidadmedida, luego unidad; descartar valores inválidos
    unidad_real = unidad_medida if unidad_medida.upper() not in _INVALIDOS else unidad
    if unidad_real.upper() in _INVALIDOS:
        unidad_real = "mg"  # default para sólidos orales

    base = f"{cantidad} {unidad_real}"

    # Agregar referencia de presentación si aporta contexto (ej. "AMPOLLA POR 5 ML")
    if unidad_ref and unidad_ref.upper() not in _INVALIDOS and unidad_ref.upper() != unidad_real.upper():
        base = f"{base}/{unidad_ref}"

    return base.strip()


@dataclass
class MedicamentoTransformado:
    cum_id: str                          # expedientecum-consecutivocum
    expedientecum: str
    consecutivocum: str
    nombre_comercial: str
    principios_activos_raw: list[str]    # tal como vienen del API
    principios_dci: list[str]            # normalizados
    tipo_formula: str                    # monocomponente|biconjugado|triconjugado|tetraconjugado
    concentraciones: list[str]           # una por componente
    concentracion_display: str           # para mostrar en UI
    dosis_numerica: float | None         # primer valor numérico de concentraciones[0] (para comparar exacto)
    forma_farmaceutica: str
    via_administracion: str
    atc: str
    descripcion_atc: str
    laboratorio: str
    registro_sanitario: str
    estado_registro: str
    estado_cum: str
    modalidad: str


_TIPO_FORMULA = {1: "monocomponente", 2: "biconjugado", 3: "triconjugado", 4: "tetraconjugado"}


def agrupar_y_transformar(df: pd.DataFrame) -> list[MedicamentoTransformado]:
    """
    Agrupa las filas del CUM por (expedientecum, consecutivocum) y reconstruye
    cada presentación como un MedicamentoTransformado con su lista de componentes.
    """
    resultados: list[MedicamentoTransformado] = []

    grupo_cols = ["expedientecum", "consecutivocum"]
    for (exped, consec), grupo in df.groupby(grupo_cols):
        # Deduplicar por principio activo (hay filas duplicadas por fabricante/importador)
        grupo_uniq = grupo.drop_duplicates(subset=["principioactivo"])

        principios_raw = grupo_uniq["principioactivo"].dropna().tolist()
        principios_dci = [normalizar_principio(p) for p in principios_raw]

        # Eliminar vacíos o repetidos tras normalización
        vistos: set[str] = set()
        principios_dci_uniq: list[str] = []
        principios_raw_uniq: list[str] = []
        for raw, dci in zip(principios_raw, principios_dci):
            if dci and dci not in vistos:
                vistos.add(dci)
                principios_dci_uniq.append(dci)
                principios_raw_uniq.append(raw)

        n = len(principios_dci_uniq)
        tipo = _TIPO_FORMULA.get(n, "tetraconjugado" if n >= 4 else "monocomponente")

        # Concentraciones por componente
        concentraciones: list[str] = []
        for _, fila in grupo_uniq.iterrows():
            c = construir_concentracion(fila)
            if c:
                concentraciones.append(c)

        # Texto de concentración para mostrar
        if len(principios_dci_uniq) == len(concentraciones):
            partes = [f"{dci} {c}" for dci, c in zip(principios_dci_uniq, concentraciones)]
            concentracion_display = " + ".join(partes)
        elif concentraciones:
            concentracion_display = " + ".join(concentraciones)
        else:
            concentracion_display = ""

        # Valor numérico de la dosis del primer componente (para comparar exacto en alternativas)
        dosis_numerica: float | None = None
        if concentraciones:
            m_num = _NUM_DOSIS.search(concentraciones[0])
            if m_num:
                try:
                    dosis_numerica = float(m_num.group(1).replace(',', '.'))
                except ValueError:
                    pass

        primera = grupo.iloc[0]

        resultados.append(MedicamentoTransformado(
            cum_id=f"{exped}-{consec}",
            expedientecum=str(exped),
            consecutivocum=str(consec),
            nombre_comercial=str(primera.get("producto", "")).strip(),
            principios_activos_raw=principios_raw_uniq,
            principios_dci=principios_dci_uniq,
            tipo_formula=tipo,
            concentraciones=concentraciones,
            concentracion_display=concentracion_display,
            dosis_numerica=dosis_numerica,
            forma_farmaceutica=str(primera.get("formafarmaceutica", "")).strip().upper(),
            via_administracion=str(primera.get("viaadministracion", "")).strip().upper(),
            atc=str(primera.get("atc", "")).strip().upper(),
            descripcion_atc=str(primera.get("descripcionatc", "")).strip().upper(),
            laboratorio=str(primera.get("titular", primera.get("nombrerol", ""))).strip(),
            registro_sanitario=str(primera.get("registrosanitario", "")).strip(),
            estado_registro=str(primera.get("estadoregistro", "")).strip().capitalize(),
            estado_cum=str(primera.get("estadocum", "")).strip().capitalize(),
            modalidad=str(primera.get("modalidad", "")).strip(),
        ))

    return resultados
