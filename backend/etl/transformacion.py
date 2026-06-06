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

# Extrae volumen de referencias del CUM: "AMPOLLA POR 3 ML", "1ML", "FRASCO 100 ML"
_VOL_EN_REF = re.compile(r'(\d+(?:[.,]\d+)?)\s*(ml|dl|l)\b', re.IGNORECASE)

# Extrae ratio de concentración del nombre del producto como fallback:
# "DORMICUM® 15MG/3ML" → (15, mg, 3, ml) → "5 mg/mL"
# "BENZOSED® 5MG/ML"   → (5, mg, None, ml) → "5 mg/mL" (denominador implícito = 1)
_CONC_EN_NOMBRE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(mg|g|mcg|µg|ug|ui|iu|meq|mmol)'
    r'\s*/\s*(?:(\d+(?:[.,]\d+)?)\s*)?(ml|dl|l)\b',
    re.IGNORECASE,
)

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

# Patrón CUM frecuente: "5 MG DE MIDAZOLAM", "0.5MG DE ALPRAZOLAM CADA TABLETA"
# La DCI real es la parte posterior a "DE".
_DOSIS_DE_INN = re.compile(
    r"^\d[\d.,]*\s*(?:MG|G|MCG|UI|IU|ML|%)\s+DE\s+(.+)$",
    re.IGNORECASE,
)

# Agrega espacio entre letra y dígito cuando van pegados en nombres del CUM:
# "INYECTABLE5" → "INYECTABLE 5", "DORMICUM5MG" → "DORMICUM 5MG"
_LETRA_DIGITO = re.compile(r'([A-Za-zÁÉÍÓÚÀÈÌÒÙáéíóúàèìòùÑñ])(\d)')

# Sinónimos INN: grafías en inglés, variantes -ina/-ino u otras presentes en el CUM → DCI canónico
_SINONIMOS: dict[str, str] = {
    # Variantes inglés → español
    "METOTREXATE":      "METOTREXATO",
    "METHOTREXATE":     "METOTREXATO",
    "DEXAMETHASONE":    "DEXAMETASONA",
    "PREDNISOLONE":     "PREDNISOLONA",
    "HYDROCORTISONE":   "HIDROCORTISONA",
    "TESTOSTERONE":     "TESTOSTERONA",
    "PROGESTERONE":     "PROGESTERONA",
    "FLUOROURACIL":     "FLUOROURACILO",
    "VINCRISTINE":      "VINCRISTINA",
    "VINBLASTINE":      "VINBLASTINA",
    "CYCLOPHOSPHAMIDE": "CICLOFOSFAMIDA",
    "CHLORAMBUCIL":     "CLORAMBUCILO",
    "MERCAPTOPURINE":   "MERCAPTOPURINA",
    # Variantes -ina/-ino frecuentes en el CUM colombiano
    "NIFEDIPINA":       "NIFEDIPINO",
    "AMLODIPINA":       "AMLODIPINO",
    "FELODIPINA":       "FELODIPINO",
    "LERCANIDIPINA":    "LERCANIDIPINO",
    "LACIDIPINA":       "LACIDIPINO",
    "NISOLDIPINA":      "NISOLDIPINO",
    "NIMODIPINA":       "NIMODIPINO",
    "ISRADIPINA":       "ISRADIPINO",
    "BARNIDIPINA":      "BARNIDIPINO",
}


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

    # Patrón "5 MG DE MIDAZOLAM [CADA AMPOLLA]" → extraer solo el INN
    m_de = _DOSIS_DE_INN.match(p)
    if m_de:
        p = m_de.group(1).strip()
        # Quitar sufijos descriptivos como "CADA AMPOLLA", "POR TABLETA", etc.
        p = re.sub(r'\s+(?:CADA|POR)\s+\w+$', '', p).strip()

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

    # Unificar grafías inglés→español para DCI de un solo token (metotrexate → metotrexato)
    p = _SINONIMOS.get(p, p)

    return p


def terminos_busqueda(query: str) -> list[str]:
    """
    Devuelve el término de búsqueda original más sus sinónimos conocidos,
    para ampliar la query al API y no perder productos con grafías alternativas.

    Ejemplo: "NIFEDIPINO" → ["NIFEDIPINO", "NIFEDIPINA"]
             "NIFEDIPINA" → ["NIFEDIPINA", "NIFEDIPINO"]
    """
    q = query.strip().upper()
    terms: set[str] = {q}
    # Si el término es directamente un sinónimo, agregar la forma canónica
    if q in _SINONIMOS:
        terms.add(_SINONIMOS[q])
    # Si el término es la forma canónica, agregar todas las variantes que apuntan a él
    for variante, canonico in _SINONIMOS.items():
        if canonico == q:
            terms.add(variante)
    return list(terms)


_UNIDADES_MASA = {"MG", "G", "MCG", "µG", "UG", "MEQ", "MMOL", "UI", "IU", "U"}

# ──────────────────────────────────────────────────────────────────────────────
# Formas farmacéuticas agrupadas por equivalencia de intercambio.
# La vía de administración tiene precedencia sobre el nombre de forma
# (capsula oral ≠ capsula vaginal aunque el nombre de forma sea igual).
# Definidas aquí para ser compartidas con alternativas.py (importa desde aquí).
# ──────────────────────────────────────────────────────────────────────────────
FORMAS_EQUIVALENTES: dict[str, frozenset[str]] = {
    # Sólidos orales: tabletas y cápsulas son intercambiables entre sí
    "SOLIDO_ORAL": frozenset({
        "TABLETA", "TABLETA RECUBIERTA", "TABLETA CUBIERTA CON PELICULA",
        "TABLETA MASTICABLE", "COMPRIMIDO", "GRAGEA",
        "CAPSULA", "CAPSULA DURA", "CAPSULA BLANDA", "CAPSULA GELATINOSA",
    }),
    # Sólidos orales de liberación prolongada/controlada/modificada/sostenida
    # Tableta LP y Cápsula LP del mismo PA y dosis son intercambiables entre sí
    # NO son intercambiables con la forma de liberación inmediata (SOLIDO_ORAL)
    "SOLIDO_ORAL_LP": frozenset({
        "TABLETA DE LIBERACION PROLONGADA", "TABLETA DE LIBERACION CONTROLADA",
        "TABLETA DE LIBERACION MODIFICADA", "TABLETA DE LIBERACION SOSTENIDA",
        "TABLETA DE LIBERACION RETARDADA", "TABLETA DE ACCION PROLONGADA",
        "CAPSULA DE LIBERACION PROLONGADA", "CAPSULA DE LIBERACION CONTROLADA",
        "CAPSULA DE LIBERACION MODIFICADA", "CAPSULA DE LIBERACION SOSTENIDA",
        "CAPSULA DE LIBERACION RETARDADA", "CAPSULA DE ACCION PROLONGADA",
        "COMPRIMIDO DE LIBERACION PROLONGADA", "COMPRIMIDO DE LIBERACION CONTROLADA",
    }),
    # Dispersables/efervescentes: misma molécula pero preparación diferente
    "ORAL_DISPERSABLE": frozenset({
        "TABLETA DISPERSABLE", "TABLETA EFERVESCENTE",
        "POLVO PARA SUSPENSION ORAL", "GRANULADO ORAL",
    }),
    # Líquidos orales
    "LIQUIDO_ORAL": frozenset({
        "JARABE", "SOLUCION ORAL", "SUSPENSION ORAL", "ELIXIR",
        "GOTAS ORALES", "SOLUCION", "SUSPENSION", "EMULSION ORAL",
    }),
    # Sublingual/bucal
    "SUBLINGUAL": frozenset({
        "TABLETA SUBLINGUAL", "COMPRIMIDO SUBLINGUAL",
        "TABLETA BUCODISPERSABLE", "FILM SUBLINGUAL",
    }),
    # Parenterales (todas las vías inyectables son intercambiables a nivel de dispensación)
    "INYECTABLE": frozenset({
        "SOLUCION INYECTABLE", "POLVO PARA SOLUCION INYECTABLE",
        "SOLUCION PARA INYECCION", "INYECTABLE",
        "POLVO LIOFILIZADO PARA RECONSTITUIR A SOLUCION INYECTABLE",
        "CONCENTRADO PARA SOLUCION PARA PERFUSION",
        "SUSPENSION INYECTABLE", "EMULSION INYECTABLE",
    }),
    # Tópicos cutáneos
    "TOPICO": frozenset({
        "CREMA", "UNGÜENTO", "GEL", "LOCION", "POMADA", "EMULSION", "ESPUMA",
    }),
    # Inhalados
    "INHALADO": frozenset({
        "AEROSOL PARA INHALACION", "POLVO PARA INHALACION",
        "SOLUCION PARA INHALACION", "INHALADOR",
    }),
    # Oftálmicos
    "OFTALMICO": frozenset({
        "COLIRIO", "SOLUCION OFTALMICA", "GOTAS OFTALMICAS",
        "POMADA OFTALMICA", "GEL OFTALMICO",
    }),
    # Vaginales — NO intercambiables con orales aunque tengan el mismo nombre de forma
    "VAGINAL": frozenset({
        "OVULO", "OVULOS", "CAPSULA VAGINAL", "TABLETA VAGINAL",
        "COMPRIMIDO VAGINAL", "CREMA VAGINAL", "GEL VAGINAL",
        "SOLUCION VAGINAL", "ESPUMA VAGINAL",
    }),
    # Rectales
    "RECTAL": frozenset({
        "SUPOSITORIO", "SUPOSITORIOS", "ENEMA", "CREMA RECTAL",
        "GEL RECTAL", "SOLUCION RECTAL",
    }),
    # Transdérmicos
    "TRANSDERMICO": frozenset({
        "PARCHE TRANSDERMICO", "PARCHE", "GEL TRANSDERMICO",
    }),
    # Óticos
    "OTICO": frozenset({"GOTAS OTICAS", "GOTAS ÓTICAS", "SOLUCION OTICA"}),
    # Nasales
    "NASAL": frozenset({
        "SPRAY NASAL", "GOTAS NASALES", "SOLUCION NASAL", "GEL NASAL",
    }),
}

_FORMA_A_GRUPO: dict[str, str] = {
    f: g for g, fs in FORMAS_EQUIVALENTES.items() for f in fs
}

# La vía de administración tiene precedencia: capsula VAGINAL → VAGINAL,
# aunque la forma farmacéutica "CAPSULA" normalmente mapee a SOLIDO_ORAL.
_VIA_A_GRUPO: dict[str, str] = {
    'VAGINAL': 'VAGINAL',
    'RECTAL': 'RECTAL',
    'SUBLINGUAL': 'SUBLINGUAL',
    'BUCAL': 'SUBLINGUAL',
    'SUBLINGUAL - BUCAL': 'SUBLINGUAL',
    'OFTALMICA': 'OFTALMICO',
    'OCULAR': 'OFTALMICO',
    'OTICA': 'OTICO',
    'AUDITIVA': 'OTICO',
    'NASAL': 'NASAL',
    'INTRANASAL': 'NASAL',
    'INHALATORIA': 'INHALADO',
    'PULMONAR': 'INHALADO',
    'INHALACION': 'INHALADO',
    'TRANSDERMICA': 'TRANSDERMICO',
    'CUTANEA': 'TRANSDERMICO',
    'INTRAVENOSA': 'INYECTABLE',
    'INTRAMUSCULAR': 'INYECTABLE',
    'SUBCUTANEA': 'INYECTABLE',
    'PARENTERAL': 'INYECTABLE',
    'INTRAARTICULAR': 'INYECTABLE',
    'INTRATECAL': 'INYECTABLE',
    'INTRAPERITONEAL': 'INYECTABLE',
}


def _grupo_forma(forma: str, via: str = '') -> str:
    """Clasifica una forma farmacéutica en un grupo de equivalencia.
    La vía de administración tiene precedencia para evitar que, por ejemplo,
    una cápsula vaginal quede en el mismo grupo que una cápsula oral.
    """
    via_u = via.strip().upper()
    if via_u in _VIA_A_GRUPO:
        return _VIA_A_GRUPO[via_u]
    return _FORMA_A_GRUPO.get(forma.strip().upper(), forma.strip().upper())


# Grupos que se normalizan a concentración por mL
_GRUPOS_NORM_ML = frozenset({'INYECTABLE', 'LIQUIDO_ORAL'})
# Grupos donde la unidad de referencia es "por dosis"
_GRUPOS_NORM_DOSIS = frozenset({'INHALADO', 'NASAL'})

# Extrae número de dosis/inhalaciones de la referencia: "200 DOSIS" → 200
_NDOSIS_EN_REF = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(?:dosis|inhalaciones|aplicaciones|sprays|pulsaciones)\b',
    re.IGNORECASE,
)


def _conc_desde_nombre(nombre: str) -> str:
    """
    Extrae concentración por mL desde el nombre del producto como último recurso.
    "DORMICUM® 15MG/3ML"        → "5 mg/mL"
    "BENZOSED® 5MG/ML"          → "5 mg/mL"
    "DORMICUM 5 MG/5 ML"        → "1 mg/mL"
    "METFORMINA 500MG TABLETA"  → ""  (no denominator in mL → sin resultado)
    """
    m = _CONC_EN_NOMBRE.search(nombre)
    if not m:
        return ""
    try:
        qty = float(m.group(1).replace(',', '.'))
        unit = m.group(2)
        vol = float(m.group(3).replace(',', '.')) if m.group(3) else 1.0
        vol_unit = m.group(4).lower()
        if vol == 0:
            return ""
        if vol_unit == 'dl':
            vol *= 100
        elif vol_unit == 'l':
            vol *= 1000
        ratio = qty / vol
        u = "UI" if unit.upper() in ("UI", "IU") else unit.lower()
        return f"{ratio:g} {u}/mL"
    except (ValueError, ZeroDivisionError):
        return ""


def _normalizar_por_forma(conc: str, g_forma: str, nombre_prod: str) -> str:
    """
    Normaliza la concentración según el grupo farmacéutico:
    - INYECTABLE / LIQUIDO_ORAL → ratio /mL; si no se puede calcular desde campos
      estructurados, intenta extraerlo del nombre del producto.
    - INHALADO / NASAL → primer valor+unidad con /dosis (excepto nebulizables
      que ya devuelven /mL desde construir_concentracion).
    - Otros grupos (sólidos orales, tópicos, vaginales…) → sin cambio.
    """
    if g_forma in _GRUPOS_NORM_ML:
        if g_forma == 'LIQUIDO_ORAL':
            # Para líquidos orales el nombre del producto (ej. "AMOXICILINA 250MG/5ML")
            # es más fiable que los campos estructurados: el CUM suele poner el volumen
            # del frasco entero ("FRASCO 100 ML") en unidadreferencia, no la dosis.
            c_fb = _conc_desde_nombre(nombre_prod)
            if c_fb:
                return c_fb
        # Para inyectables (y líquidos orales sin ratio en el nombre):
        # confiar en el /mL calculado desde campos estructurados, o intentar desde nombre.
        if '/mL' in conc or '/ml' in conc:
            return conc
        c_fb = _conc_desde_nombre(nombre_prod)
        return c_fb if c_fb else conc
    if g_forma in _GRUPOS_NORM_DOSIS:
        # nebulizables ya vienen como X mg/mL — conservar
        if '/dosis' in conc.lower() or '/mL' in conc or '/ml' in conc:
            return conc
        m = re.match(r'^(\d+(?:[.,]\d+)?)\s*(\S+)', conc)
        if m:
            return f"{m.group(1)} {m.group(2)}/dosis"
        return conc
    return conc


def _extraer_presentacion(row: pd.Series, g_forma: str, nombre_prod: str) -> str:
    """
    Extrae la cantidad total por envase/unidad de dispensación.
    Complementa la concentración: mientras la concentración describe cuánto
    principio activo hay por unidad de volumen, la presentación describe el
    tamaño total del envase o la unidad de dispensación.

    Ejemplos:
      INYECTABLE  "AMPOLLA POR 3 ML"      → "3 mL"
      INYECTABLE  "AMPOLLA" + "15MG/3ML"  → "3 mL" (desde nombre)
      INYECTABLE  "BENZOSED 5MG/ML"       → "1 mL" (denominador implícito)
      LIQUIDO_ORAL "FRASCO 60 ML"         → "60 mL"
      INHALADO    "200 DOSIS"             → "200 dosis"
    """
    unidad_ref = str(row.get("unidadreferencia", "")).strip()

    if g_forma == 'INYECTABLE':
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            vol = float(vol_m.group(1).replace(',', '.'))
            vol_unit = vol_m.group(2).lower()
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        # Fallback: denominador del ratio en el nombre del producto
        nm = _CONC_EN_NOMBRE.search(nombre_prod)
        if nm:
            vol = float(nm.group(3).replace(',', '.')) if nm.group(3) else 1.0
            vol_unit = nm.group(4).lower() if nm.group(4) else 'ml'
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        return ""

    if g_forma == 'LIQUIDO_ORAL':
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            vol = float(vol_m.group(1).replace(',', '.'))
            vol_unit = vol_m.group(2).lower()
            if vol_unit == 'dl': vol *= 100
            elif vol_unit == 'l': vol *= 1000
            return f"{vol:g} mL"
        return ""

    if g_forma == 'INHALADO':
        m_d = _NDOSIS_EN_REF.search(unidad_ref)
        if m_d:
            n = int(float(m_d.group(1).replace(',', '.')))
            return f"{n} dosis"
        return ""

    return ""


def construir_concentracion(row: pd.Series) -> str:
    """
    Construye la concentración real a partir de cantidad + unidad + unidadreferencia.
    El campo 'concentracion' del API contiene letras (A/B/S), no valores.

    Para líquidos/inyectables, normaliza a concentración por mL cuando la referencia
    contiene un volumen: "15 mg / AMPOLLA POR 3 ML" → "5 mg/mL" (=5 mg/mL).
    Esto permite comparar correctamente 15mg/3mL, 50mg/10mL y 5mg/1mL como idénticos.
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

    # Normalizar a por-mL cuando unidad_ref contiene un volumen numérico y la unidad
    # es de masa (mg, mcg, UI…). Ejemplos:
    #   "15 mg" + "AMPOLLA POR 3 ML"  → 15/3 = 5   → "5 mg/mL"
    #   "50 mg" + "AMPOLLA POR 10 ML" → 50/10 = 5  → "5 mg/mL"
    #   " 5 mg" + "1 ML DE SOLUCION"  → 5/1  = 5   → "5 mg/mL"
    #   " 1 mg" + "1ML"               → 1/1  = 1   → "1 mg/mL"
    if (unidad_ref and unidad_ref.upper() not in _INVALIDOS
            and unidad_real.upper() in _UNIDADES_MASA):
        vol_m = _VOL_EN_REF.search(unidad_ref)
        if vol_m:
            try:
                qty = float(cantidad.replace(',', '.'))
                vol = float(vol_m.group(1).replace(',', '.'))
                vol_unit = vol_m.group(2).lower()
                if vol > 0:
                    if vol_unit == 'dl':
                        vol *= 100
                    elif vol_unit == 'l':
                        vol *= 1000
                    ratio = qty / vol
                    u = "UI" if unidad_real.upper() in ("UI", "IU") else unidad_real.lower()
                    return f"{ratio:g} {u}/mL"
            except (ValueError, ZeroDivisionError):
                pass

    # Casing consistente con el path normalizado: UI en mayúsculas, resto en minúsculas
    unidad_display = "UI" if unidad_real.upper() in ("UI", "IU") else unidad_real.lower()
    base = f"{cantidad} {unidad_display}"

    # Agregar referencia de presentación SOLO si contiene un valor numérico,
    # lo que indica volumen/cantidad real (ej. "AMPOLLA POR 5 ML", "FRASCO 100 ML").
    # Si no tiene dígitos es solo el nombre de la forma farmacéutica (ej. "TABLETA RECUBIERTA",
    # "COMPRIMIDO") que ya está en forma_farmaceutica y no aporta al filtro de concentración.
    # Excluir conteos de dosis ("200 DOSIS", "120 INHALACIONES") — van a presentacion, no a concentración.
    if (unidad_ref and unidad_ref.upper() not in _INVALIDOS
            and unidad_ref.upper() != unidad_real.upper()
            and re.search(r'\d', unidad_ref)
            and not _NDOSIS_EN_REF.search(unidad_ref)):
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
    presentacion: str                    # tamaño del envase/unidad: "3 mL", "60 mL", "200 dosis", ""
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
        primera = grupo.iloc[0]

        # Deduplicar por principio activo (hay filas duplicadas por fabricante/importador)
        grupo_uniq = grupo.drop_duplicates(subset=["principioactivo"])

        principios_raw = grupo_uniq["principioactivo"].dropna().tolist()
        principios_dci = [normalizar_principio(p) for p in principios_raw]

        # Eliminar vacíos, repetidos, y valores basura del CUM (códigos de 1-2 chars como "A", "S")
        vistos: set[str] = set()
        principios_dci_uniq: list[str] = []
        principios_raw_uniq: list[str] = []
        for raw, dci in zip(principios_raw, principios_dci):
            if dci and len(dci) >= 3 and dci not in vistos:
                vistos.add(dci)
                principios_dci_uniq.append(dci)
                principios_raw_uniq.append(raw)

        n = len(principios_dci_uniq)
        tipo = _TIPO_FORMULA.get(n, "tetraconjugado" if n >= 4 else "monocomponente")

        nombre_prod = _LETRA_DIGITO.sub(r'\1 \2', str(primera.get("producto", "")).strip())
        nombre_prod = re.sub(r' {2,}', ' ', nombre_prod).strip()
        g_forma = _grupo_forma(
            str(primera.get("formafarmaceutica", "")).strip().upper(),
            str(primera.get("viaadministracion", "")).strip().upper(),
        )

        # Concentraciones por componente, normalizadas según forma farmacéutica
        concentraciones: list[str] = []
        _conc_vistos: set[str] = set()
        for _, fila in grupo_uniq.iterrows():
            c = construir_concentracion(fila)
            if c:
                c_norm = _normalizar_por_forma(c, g_forma, nombre_prod)
                if c_norm not in _conc_vistos:
                    _conc_vistos.add(c_norm)
                    concentraciones.append(c_norm)

        # Texto de concentración para mostrar
        # Monocomponente: solo la concentración (el DCI ya se muestra en otro campo)
        # Multicomponente: "DCI1 conc1 + DCI2 conc2" para distinguir cuál dosis es cuál
        if not concentraciones:
            concentracion_display = ""
        elif len(principios_dci_uniq) == 1:
            concentracion_display = concentraciones[0]
        elif len(principios_dci_uniq) == len(concentraciones):
            partes = [f"{dci} {c}" for dci, c in zip(principios_dci_uniq, concentraciones)]
            concentracion_display = " + ".join(partes)
        else:
            concentracion_display = " + ".join(concentraciones)

        # Valor numérico de la dosis del primer componente (para comparar exacto en alternativas)
        dosis_numerica: float | None = None
        if concentraciones:
            m_num = _NUM_DOSIS.search(concentraciones[0])
            if m_num:
                try:
                    dosis_numerica = float(m_num.group(1).replace(',', '.'))
                except ValueError:
                    pass

        resultados.append(MedicamentoTransformado(
            cum_id=f"{exped}-{consec}",
            expedientecum=str(exped),
            consecutivocum=str(consec),
            nombre_comercial=nombre_prod,
            principios_activos_raw=principios_raw_uniq,
            principios_dci=principios_dci_uniq,
            tipo_formula=tipo,
            concentraciones=concentraciones,
            concentracion_display=concentracion_display,
            dosis_numerica=dosis_numerica,
            presentacion=_extraer_presentacion(primera, g_forma, nombre_prod),
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
