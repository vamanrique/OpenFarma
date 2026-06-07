"""
Normalización LLM de registros CUM usando DeepSeek.

Flujo:
  DataFrame raw CUM
    → agrupar por (expedientecum, consecutivocum)
    → revisar caché en tabla cum_normalizado
    → enviar en batch a DeepSeek lo que no esté cacheado o haya cambiado
    → persistir resultado normalizado
    → retornar DataFrame enriquecido con columnas normalizadas

Uso típico:
    from etl.normalizador_llm import NormalizadorLLM
    from app.database import SessionLocal

    normalizador = NormalizadorLLM(api_key="sk-...")
    with SessionLocal() as db:
        df_norm = normalizador.procesar_dataframe(df_raw, db, limite=500)
"""
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
from openai import OpenAI, RateLimitError, APIError
from sqlalchemy.orm import Session

from app.models.cum_normalizado import CumNormalizado

logger = logging.getLogger(__name__)

BATCH_SIZE    = 15    # registros por llamada LLM
MAX_WORKERS   = 10    # llamadas LLM concurrentes
MODEL         = "deepseek-chat"
BASE_URL      = "https://api.deepseek.com"
MAX_REINTENTOS = 3
PAUSA_REINTENTO = 5  # segundos

# Formas y vías válidas — el LLM debe elegir una de estas
FORMAS_VALIDAS = {
    "TABLETA", "CAPSULA", "SOLUCION_ORAL", "SUSPENSION_ORAL",
    "INYECTABLE", "TOPICO", "INHALADO", "OFTALMICO",
    "VAGINAL", "RECTAL", "TRANSDERMICO", "OTICO", "NASAL", "OTRO",
}
VIAS_VALIDAS = {
    "ORAL", "SUBLINGUAL",
    "PARENTERAL", "INTRAVENOSA", "INTRAMUSCULAR", "SUBCUTANEA", "INTRATECAL", "INTRADERMICA",
    "INHALATORIA", "NASAL",
    "TOPICA", "TRANSDERMICA",
    "OFTALMICA", "OTICA",
    "VAGINAL", "RECTAL",
    "OTRA",
}

SYSTEM_PROMPT = """\
Eres un asistente experto en normalización de datos del registro farmacéutico colombiano CUM-INVIMA.

Recibirás un array JSON de registros con datos crudos del CUM. Para cada registro devuelve un objeto JSON normalizado.

CAMPOS DE ENTRADA — ACLARACIONES IMPORTANTES:
- concentracion_codigo: Código del Decreto 677 colombiano. NO es un valor numérico.
  "A" = por unidad dosificada (ej. tableta, ampolla), "C" = por unidad de masa/volumen.
  Ignora este campo para calcular concentraciones; usa componentes_raw en su lugar.
- componentes_raw: Lista de componentes activos del medicamento. Cada elemento tiene:
    * principio_activo: Nombre crudo (puede tener sinónimos, sufijos de sal, texto extra como "EQUIVALENTE A")
    * cantidad: Cantidad numérica por unidad de referencia. Puede ser "No"/"Si" (inválido del CUM) — inferir.
    * unidad_medida: Unidad de la cantidad ("mg", "mcg", "g", "UI", etc.). Puede ser "No"/"Si" — inferir.
  Para un medicamento mono-componente, la lista tiene 1 elemento.
  Para bi/tri/tetra-componente, la lista tiene 2/3/4 elementos con sus propias cantidades.
- unidad_referencia: Descripción del contenedor de referencia. Interpretación por caso:
    * "AMPOLLA POR 3 ML", "VIAL POR 10 ML" → volumen en mL de la unidad.
    * "CADA 100 G", "CADA 100 G DE PRODUCTO", "CADA 100 G DE SUSPENSIÓN", "100 ML DE SUSPENSIÓN NASAL",
      "100 G DE SUSPENSIÓN", "100 G DE SOLUCIÓN", o cualquier variante → concentración porcentual.
      OBLIGATORIO: busca la dosis por unidad/dosis/puff en TODOS los campos de texto, en este orden:
        0. unidad_referencia contiene "X MCG" o "X MICROGRAMOS" (dosis embebida, ej. "1 DOSIS CORRESPONDE 50 MCG" → 0.05 mg)
        1. descripcion_comercial contiene "X MCG/DOSIS", "X MCG" o "X MICROGRAMOS"
        2. principio_activo_raw contiene "X MCG", "X MICROGRAMOS", "X MICROGRAMAS" (incluso en paréntesis como "(CADA APLICACIÓN PROPORCIONA 50 MICROGRAMOS)")
        3. nombre_comercial contiene "X MCG", "XMCG", "XMCGDOSIS" (puede no haber espacio, ej. "50 MCGDOSIS" → 0.05 mg)
      Si encuentras la dosis en CUALQUIERA de estos campos → dosis_total_mg = valor en mg (mcg ÷ 1000).
      Solo si NINGUNO de los cuatro campos contiene información de dosis → dosis_total_mg = null.
    * "DOSIS", "INHALACIÓN (DOSIS)", "INHALACION" → cantidad ES la dosis por disparo/inhalación.
      Interpretar cantidad como mcg si el valor es compatible (ej. 50, 100, 200, 250) y convertir a mg.
      Ejemplo: cantidad="50", ref="INHALACIÓN (DOSIS)" → dosis_total_mg = 0.05 (mg).
      Ejemplo: cantidad="100", ref="DOSIS" → dosis_total_mg = 0.1 (mg).
REGLAS DE NORMALIZACIÓN:
1. principios_dci: Lista con el DCI/INN (OMS, español, mayúsculas) de CADA componente en componentes_raw.
   Debe tener exactamente un elemento por cada componente válido — NUNCA omitir ingredientes.
   - Resuelve sinónimos: ACETAMINOFÉN→PARACETAMOL, MEPERIDINA→PETIDINA, DIPIRONA→METAMIZOL, NIFEDIPINA→NIFEDIPINO, VITAMINA C→ACIDO ASCORBICO
   - Elimina sufijos de sal: CLORHIDRATO, FOSFATO, SODICO, POTASICO, TRIHIDRATO, BESILATO, MALEATO, FUMARATO, SUCCINATO
   - Extrae el INN de expresiones como "5 MG DE MIDAZOLAM" → "MIDAZOLAM", "EQUIVALENTE A 500 MG DE AMOXICILINA" → "AMOXICILINA"
   - Descarta valores no válidos: letras sueltas ("A", "B"), números, "SIN PRINCIPIO ACTIVO"
   - Ordena alfabéticamente
   - Ejemplo bi-componente: componentes_raw = [{"principio_activo":"BENZOIL METRONIDAZOL...", "cantidad":"5"}, {"principio_activo":"NIFUROXAZIDA","cantidad":"4"}]
     → principios_dci = ["METRONIDAZOL","NIFUROXAZIDA"]

2. nombre_comercial_norm: Nombre comercial limpiado (Title Case, sin espacios extra, sin puntuación al final).
   Si el nombre incluye la dosis y esta ya está en concentración, elimínala del nombre.

3. concentracion_mg_ml: Concentración por mL normalizada a mg/mL (número decimal).
   - Fuente principal: cantidad + unidad_medida dividido por volumen (de unidad_referencia).
   - Convierte unidades: g/mL × 1000, mcg/mL ÷ 1000, UI/mL → null (unidades biológicas)
   - Ejemplo: cantidad="15", unidad_medida="mg", unidad_referencia="AMPOLLA POR 3 ML" → 15/3 = 5.0
   - Para sólidos (tabletas, cápsulas): null

4. volumen_ml_por_unidad: Volumen de la unidad dispensada primaria en mL.
   - Fuente principal: unidad_referencia. "AMPOLLA POR 3 ML" → 3.0, "VIAL POR 10 ML" → 10.0
   - Fuente secundaria: presentacion_raw o nombre_comercial si unidad_referencia está vacío.
   - Para sólidos: null

5. dosis_total_mg: Dosis total en mg por unidad primaria.
   - Líquidos: usa cantidad + unidad_medida directamente (ej. cantidad="15", unidad_medida="mg" → 15.0).
     Convierte si es necesario: g × 1000, mcg ÷ 1000.
   - Sólidos: cantidad en mg por tableta/cápsula.
   - Para combinaciones: dosis_total_mg es la suma de los componentes si tienen la misma unidad.

6. unidades_por_envase: Número entero de unidades primarias por envase.
   - "CAJA X 30 TABLETAS" → 30, "CAJA X 10 AMPOLLAS" → 10, "FRASCO X 100 ML" → 1
   - null si no se puede determinar

7. forma_normalizada: UNO de: TABLETA, CAPSULA, SOLUCION_ORAL, SUSPENSION_ORAL, INYECTABLE,
   TOPICO, INHALADO, OFTALMICO, VAGINAL, RECTAL, TRANSDERMICO, OTICO, NASAL, OTRO

8. via_normalizada: UNO de los siguientes valores exactos:
   ORAL, SUBLINGUAL,
   INTRAVENOSA, INTRAMUSCULAR, SUBCUTANEA, INTRATECAL, INTRADERMICA, PARENTERAL,
   INHALATORIA, NASAL,
   TOPICA, TRANSDERMICA,
   OFTALMICA, OTICA,
   VAGINAL, RECTAL,
   OTRA
   El campo de entrada es "vias_administracion": lista con TODAS las vías registradas en el CUM.
   Devuelve "vias_normalizadas" como LISTA con todas las vías aplicables (puede tener más de una).
   Reglas:
   - Agrupa las vías parenterales: si hay INTRAVENOSA + INTRAMUSCULAR (sin otras) → ["PARENTERAL"].
   - Si hay vías parenterales + otras no parenterales → inclúyelas por separado: ["PARENTERAL", "RECTAL"].
   - Si solo hay una vía → lista de un elemento: ["ORAL"].
   - "SUBLINGUAL" solo si forma o nombre indica comprimido/tableta sublingual.
   Nota: el campo de salida se llama "vias_normalizadas" (plural, lista), NO "via_normalizada".

9. atc: Código ATC de 7 caracteres. Si atc_raw parece correcto (formato A99XX99), confirmarlo.
   Si está vacío o incorrecto, inferir desde el principio activo si tienes certeza. Sino null.

10. sinonimos_resueltos: Objeto con los sinónimos que resolviste. {} si ninguno.
    Ejemplo: {"ACETAMINOFÉN": "PARACETAMOL"}

11. tipo_formula: Clasificación por número de principios activos:
    "MONO" (1 componente), "BI" (2), "TRI" (3), "TETRA" (4), "OTRO" (más de 4 o sin datos).

12. componentes: Lista de objetos con datos normalizados POR COMPONENTE, en el mismo orden que principios_dci.
    Cada objeto: {"dci": "NOMBRE_DCI", "concentracion_mg_ml": null_o_numero, "dosis_mg": null_o_numero}
    - concentracion_mg_ml: mg del componente por mL (null para sólidos).
    - dosis_mg: mg del componente por unidad dosificada (tableta/ampolla/puff). null para líquidos sin dosis fija.
    Para MONO: lista de 1 elemento. Para BI/TRI: lista de 2/3 elementos.
    Ejemplo bi-componente suspensión 5g+4g/100mL:
      [{"dci":"METRONIDAZOL","concentracion_mg_ml":50.0,"dosis_mg":null},
       {"dci":"NIFUROXAZIDA","concentracion_mg_ml":40.0,"dosis_mg":null}]

13. notas: String con observación breve si el registro tiene datos ambiguos o problemáticos.
    "" si todo está claro.

DEVUELVE ÚNICAMENTE un objeto JSON con la clave "registros" conteniendo un array con
exactamente un objeto por cada registro de entrada, en el mismo orden.\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hash_grupo(grupo_df: "pd.DataFrame") -> str:
    """Hash MD5 de los campos raw que determinan la normalización (todos los componentes)."""
    primera = grupo_df.iloc[0].to_dict()
    # Un fragmento por componente (ordenado para que sea determinístico)
    comp_parts = []
    for principio, comp_rows in sorted(grupo_df.groupby('principioactivo', sort=False)):
        if not principio or (isinstance(principio, float) and pd.isna(principio)):
            continue
        cr = comp_rows.iloc[0].to_dict()
        comp_parts.append(f"{principio}|{cr.get('cantidad','')}|{cr.get('unidadmedida','')}")
    campos = [
        '||'.join(comp_parts),
        str(primera.get('unidadreferencia', '')),
        str(primera.get('concentracion', '')),
        str(primera.get('formafarmaceutica', '')),
        str(primera.get('viaadministracion', '')),
        str(primera.get('descripcioncomercial', '')),
        str(primera.get('producto', '')),
    ]
    return hashlib.md5('||'.join(campos).encode()).hexdigest()


def _grupo_a_input(grupo_df: "pd.DataFrame", vias: list[str]) -> dict:
    """Convierte un grupo al formato de entrada para el LLM con datos por componente."""
    primera = grupo_df.iloc[0].to_dict()
    componentes_raw = []
    for principio, comp_rows in grupo_df.groupby('principioactivo', sort=False):
        if not principio or (isinstance(principio, float) and pd.isna(principio)):
            continue
        cr = comp_rows.iloc[0].to_dict()
        componentes_raw.append({
            'principio_activo': str(principio).strip(),
            'cantidad':         str(cr.get('cantidad', '')).strip(),
            'unidad_medida':    str(cr.get('unidadmedida', '')).strip(),
        })
    return {
        'nombre_comercial':      str(primera.get('producto', '')).strip(),
        'descripcion_comercial': str(primera.get('descripcioncomercial', '')).strip(),
        'componentes_raw':       componentes_raw,
        'unidad_referencia':     str(primera.get('unidadreferencia', '')).strip(),
        'concentracion_codigo':  str(primera.get('concentracion', '')).strip(),
        'forma_farmaceutica':    str(primera.get('formafarmaceutica', '')).strip(),
        'vias_administracion':   vias,
        'atc_raw':               str(primera.get('codigoatc', primera.get('atc', ''))).strip(),
    }


def _coerce_output(raw: dict) -> dict:
    """Valida y coerce los tipos del output del LLM."""
    def _float(v):
        try:    return float(v) if v is not None else None
        except: return None

    def _int(v):
        try:    return int(v) if v is not None else None
        except: return None

    # Normalizar lista de componentes
    raw_comps = raw.get('componentes') or []
    componentes = []
    for c in raw_comps:
        if not isinstance(c, dict):
            continue
        dci = str(c.get('dci') or '').upper().strip()
        if dci:
            componentes.append({
                'dci':                dci,
                'concentracion_mg_ml': _float(c.get('concentracion_mg_ml')),
                'dosis_mg':           _float(c.get('dosis_mg')),
            })

    tipo_formula_map = {1: 'MONO', 2: 'BI', 3: 'TRI', 4: 'TETRA'}
    principios_dci = [str(d).upper().strip() for d in (raw.get('principios_dci') or []) if d]
    n_comp = len(componentes) or len(principios_dci)

    return {
        'nombre_comercial_norm':  str(raw.get('nombre_comercial_norm') or '').strip(),
        'principios_dci':         principios_dci,
        'sinonimos_resueltos':    raw.get('sinonimos_resueltos') if isinstance(raw.get('sinonimos_resueltos'), dict) else {},
        'concentracion_mg_ml':    _float(raw.get('concentracion_mg_ml')),
        'volumen_ml_por_unidad':  _float(raw.get('volumen_ml_por_unidad')),
        'dosis_total_mg':         _float(raw.get('dosis_total_mg')),
        'unidades_por_envase':    _int(raw.get('unidades_por_envase')),
        'forma_normalizada':      str(raw.get('forma_normalizada') or 'OTRO').upper() if raw.get('forma_normalizada') in FORMAS_VALIDAS else 'OTRO',
        'via_normalizada':        [v.upper() for v in (raw.get('vias_normalizadas') or [])
                                   if str(v).upper() in VIAS_VALIDAS]
                                  or ['OTRA'],
        'atc':                    str(raw.get('atc') or '').strip().upper() or None,
        'tipo_formula':           tipo_formula_map.get(n_comp, 'OTRO'),
        'componentes':            componentes,
        'notas':                  str(raw.get('notas') or '').strip(),
    }


# ── Clase principal ────────────────────────────────────────────────────────────

class NormalizadorLLM:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # ── API call ───────────────────────────────────────────────────────────────

    def _llamar_deepseek(self, inputs: list[dict]) -> list[dict]:
        """Envía un batch a DeepSeek y retorna lista de outputs normalizados."""
        payload = json.dumps(inputs, ensure_ascii=False)
        for intento in range(MAX_REINTENTOS):
            try:
                resp = self.client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user',   'content': payload},
                    ],
                    response_format={'type': 'json_object'},
                    temperature=0,
                    max_tokens=8192,
                )
                raw = json.loads(resp.choices[0].message.content)
                # Extraer el array "registros"
                if isinstance(raw, dict) and 'registros' in raw:
                    return raw['registros']
                # Fallback: buscar el primer valor que sea lista
                for v in raw.values():
                    if isinstance(v, list):
                        return v
                raise ValueError(f"Estructura inesperada en respuesta: {list(raw.keys())}")

            except RateLimitError:
                wait = PAUSA_REINTENTO * (intento + 1)
                logger.warning(f"Rate limit — esperando {wait}s (intento {intento+1}/{MAX_REINTENTOS})")
                time.sleep(wait)
            except APIError as e:
                logger.error(f"APIError en intento {intento+1}: {e}")
                if intento == MAX_REINTENTOS - 1:
                    raise

        raise RuntimeError("Máximo de reintentos alcanzado")

    # ── Caché ──────────────────────────────────────────────────────────────────

    def _buscar_cache(self, db: Session, exp: str, cons: str, h: str) -> CumNormalizado | None:
        obj = db.query(CumNormalizado).filter_by(
            expediente_cum=exp, consecutivo_cum=cons
        ).first()
        return obj if (obj and obj.data_hash == h) else None

    def _guardar(self, db: Session, exp: str, cons: str, h: str,
                 output: dict, fila: dict, existing: CumNormalizado | None,
                 fuente: str = 'CUM_ACTIVO') -> CumNormalizado:
        obj = existing or CumNormalizado(expediente_cum=exp, consecutivo_cum=cons)
        obj.data_hash            = h
        obj.nombre_comercial_norm = output['nombre_comercial_norm']
        obj.principios_dci        = output['principios_dci']
        obj.sinonimos_resueltos   = output['sinonimos_resueltos']
        obj.concentracion_mg_ml   = output['concentracion_mg_ml']
        obj.volumen_ml_por_unidad = output['volumen_ml_por_unidad']
        obj.dosis_total_mg        = output['dosis_total_mg']
        obj.unidades_por_envase   = output['unidades_por_envase']
        obj.forma_normalizada     = output['forma_normalizada']
        obj.via_normalizada       = output['via_normalizada']
        obj.atc_normalizado       = output['atc']
        obj.tipo_formula          = output.get('tipo_formula')
        obj.componentes           = output.get('componentes') or []
        obj.notas                 = output['notas']
        # Passthrough sin LLM
        obj.fuente            = fuente
        obj.titular_registro  = str(fila.get('titular', fila.get('laboratorio', ''))).strip()
        obj.registro_sanitario = str(fila.get('registrosanitario', '')).strip()
        obj.estado_cum        = str(fila.get('estadocum', '')).strip()
        obj.estado_registro   = str(fila.get('estadoregistro', fila.get('estado', ''))).strip()
        obj.procesado_en      = datetime.now(timezone.utc)
        obj.modelo            = MODEL
        obj.intentos          = (obj.intentos or 0) + 1
        if not existing:
            db.add(obj)
        return obj

    # ── Procesamiento principal ────────────────────────────────────────────────

    def _procesar_batch(
        self,
        batch: list[tuple],
        batch_num: int,
        total_batches: int,
        fuente: str = 'CUM_ACTIVO',
    ) -> int:
        """Procesa un batch de grupos en su propio hilo con sesión DB propia."""
        from app.database import SessionLocal
        inputs = [item[3] for item in batch]
        try:
            outputs = self._llamar_deepseek(inputs)
        except Exception as e:
            logger.error(f"Batch {batch_num}/{total_batches} fallo: {e}")
            return 0

        procesados = 0
        with SessionLocal() as db:
            for (exp, cons, h, _, primera, _), raw_out in zip(batch, outputs):
                try:
                    existing = db.query(CumNormalizado).filter_by(
                        expediente_cum=exp, consecutivo_cum=cons
                    ).first()
                    output = _coerce_output(raw_out)
                    self._guardar(db, exp, cons, h, output, primera, existing, fuente=fuente)
                    procesados += 1
                except Exception as e:
                    logger.error(f"Error guardando {exp}-{cons}: {e}")
            db.commit()

        logger.info(f"Batch {batch_num}/{total_batches} — {procesados} guardados")
        return procesados

    def procesar_dataframe(
        self,
        df: pd.DataFrame,
        db: Session,
        limite: int | None = None,
        fuente: str = 'CUM_ACTIVO',
    ) -> pd.DataFrame:
        """
        Recibe el DataFrame raw del CUM, procesa cada grupo (expediente+consecutivo)
        y retorna un DataFrame con columnas normalizadas añadidas.
        """
        if df.empty:
            return df

        grupos = df.groupby(['expedientecum', 'consecutivocum'], sort=False)
        grupos_lista = list(grupos)
        if limite:
            grupos_lista = grupos_lista[:limite]

        total = len(grupos_lista)
        hits  = 0
        a_enviar: list[tuple] = []  # (exp, cons, h, input_dict, primera_fila, None)

        # Paso 1: separar hits de caché vs a procesar
        for (exp, cons), grupo_df in grupos_lista:
            exp, cons = str(exp).strip(), str(cons).strip()
            h      = _hash_grupo(grupo_df)
            cached = self._buscar_cache(db, exp, cons, h)
            if cached:
                hits += 1
            else:
                vias    = [v for v in grupo_df['viaadministracion'].dropna().unique().tolist()
                           if str(v).strip()]
                inp     = _grupo_a_input(grupo_df, vias)
                primera = grupo_df.iloc[0].to_dict()
                a_enviar.append((exp, cons, h, inp, primera, None))

        logger.info(f"Total grupos: {total} | Cache: {hits} | A procesar: {len(a_enviar)}")

        # Paso 2: enviar en batches paralelos
        batches = [a_enviar[i:i + BATCH_SIZE] for i in range(0, len(a_enviar), BATCH_SIZE)]
        total_batches = len(batches)
        procesados = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._procesar_batch, batch, i + 1, total_batches, fuente): i
                for i, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                try:
                    procesados += future.result()
                except Exception as e:
                    logger.error(f"Worker fallo: {e}")

        logger.info(f"Procesamiento completo: {hits} cache hits + {procesados} nuevos")

        # Paso 3: enriquecer el DataFrame original con columnas normalizadas
        return self._enriquecer_df(df, db)

    def _enriquecer_df(self, df: pd.DataFrame, db: Session) -> pd.DataFrame:
        """Añade columnas llm_* al DataFrame usando el caché."""
        pares = df[['expedientecum', 'consecutivocum']].drop_duplicates()
        registros = {}
        for _, row in pares.iterrows():
            exp  = str(row['expedientecum']).strip()
            cons = str(row['consecutivocum']).strip()
            obj  = db.query(CumNormalizado).filter_by(
                expediente_cum=exp, consecutivo_cum=cons
            ).first()
            if obj:
                registros[(exp, cons)] = obj

        def _col(row, campo):
            key = (str(row['expedientecum']).strip(), str(row['consecutivocum']).strip())
            obj = registros.get(key)
            return getattr(obj, campo, None) if obj else None

        columnas = [
            ('llm_principios_dci',        'principios_dci'),
            ('llm_concentracion_mg_ml',   'concentracion_mg_ml'),
            ('llm_volumen_ml_por_unidad',  'volumen_ml_por_unidad'),
            ('llm_dosis_total_mg',         'dosis_total_mg'),
            ('llm_forma_normalizada',      'forma_normalizada'),
            ('llm_via_normalizada',        'via_normalizada'),
            ('llm_atc',                    'atc_normalizado'),
            ('llm_nombre_comercial_norm',  'nombre_comercial_norm'),
            ('llm_tipo_formula',           'tipo_formula'),
            ('llm_componentes',            'componentes'),
            ('llm_notas',                  'notas'),
        ]
        df_out = df.copy()
        for col_name, attr in columnas:
            df_out[col_name] = df_out.apply(lambda r, a=attr: _col(r, a), axis=1)
        return df_out

    # ── Lookup individual (para uso en cum_live.py) ────────────────────────────

    def get_normalizado(self, db: Session, exp: str, cons: str) -> CumNormalizado | None:
        """Retorna el registro normalizado para un CUM específico, o None."""
        return db.query(CumNormalizado).filter_by(
            expediente_cum=exp, consecutivo_cum=cons
        ).first()
