"""
Parser para PDFs de Seguimiento de Abastecimiento y Desabastecimiento de Medicamentos - INVIMA.

Dos tipos de documento:
  2026: 3 secciones, layout en columnas con muchos bloques pequeños
  2025: layout compacto, bloques grandes con toda la información

Estrategia general:
  - Separar documento en secciones (MON, NO_DESAB, NO_COM) por títulos de página
  - Para sección MON 2026: bloques col-A (header/nombre/forma) + col-B (ATC+estado+causas+titulares)
  - Para secciones 2-3 2026 y doc 2025: bloques más compactos, parseo línea a línea
  - Identificar entradas por número (1-999)
  - Asociar bloques cercanos usando coordenadas Y
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

ATC_RE = re.compile(r"\b[A-Z]\d{2}[A-Z]{2}\d{2}\b")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
NUM_ONLY_RE = re.compile(r"^\d{1,3}$")
TITULAR_RE = re.compile(r"[«\xab]|<<|>>")
UMD_RE = re.compile(r"\(UMD\)\s*:\s*([\d\.\,]+)", re.IGNORECASE)

# Patrón que excluye la detección de número de entrada cuando va seguido de unidad farmacéutica
# Ej: "500 UI/vial", "300 UI/ml", "740 MBq", "250 mg", "2 g / vial"
_UNIT_WORDS_RE = re.compile(
    r"^(\d{1,3})\s+(?:UI|UF|UG|UBQ|MBQ|GBQ|MG|ML|MCG|G\b|%|KG|L\b|IU|IU/|MOL|MMOL|MEQ|"
    r"mg|ml|mcg|ug|g\b|%|UI/|UF/|L/|mol|mmol|mEq|MBq|GBq|kBq|kDa|Da|"
    r"UI\b|UF\b|IU\b)\s*[/\d]", re.I
)

ESTADO_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("DESABASTECIDO",    re.compile(r"\bDesabastecido\b|\bDESABASTECIDO\b")),
    ("EN_RIESGO",        re.compile(r"[Ee]n\s+[Rr]iesgo\s+de\s+[Dd]esab|[Rr]iesgo\s+de\s+[Dd]esab")),
    ("EN_MONITORIZACION",re.compile(r"[Ee]n\s+[Mm]onitorizaci[oó]n")),
    ("NO_DESABASTECIDO", re.compile(r"[Nn]o\s+desabastecido")),
    ("NO_COMERCIALIZADO",re.compile(r"[Nn]o\s+comercializado")),
    ("DESCONTINUADO",    re.compile(r"[Dd]escontinuado")),
]

SECCION_MON_RE    = re.compile(r"MONITORIZACI[OÓ]N.*RIESGO|RIESGO.*MONITORIZACI[OÓ]N", re.I)
SECCION_NO_DESAB_RE = re.compile(r"NO\s+DES[AB]ASTECIDOS?\s+COMO|ESTADO\s+NO\s+DES[AB]", re.I)
SECCION_NO_COM_RE = re.compile(r"NO\s+COMERCIALIZADO.*DESCONTINUADO|DESCONTINUADO.*NO\s+COMERCIALIZADO", re.I)

# Excel-export 2025 format detection: column-letter header A/B/C/D/...
_EXCEL_HEADER_RE = re.compile(r"^A\s*\nB\s*\nC", re.M)

# Formas farmacéuticas comunes (para distinguirlas de principios activos)
FORMA_WORDS = re.compile(
    r"\b(?:TABLETA|CAPSULA|SOLUCION|SUSPENSION|INYECTABLE|JARABE|CREMA|GEL|POMADA|"
    r"UNGÜENTO|UNGUENTO|POLVO|AMPOLLA|VIAL|PARCHE|SUPOSITORIO|AEROSOL|SPRAY|COLIRIO|"
    r"LOCION|LOCIO|GLOBULO|GRAGEA|COMPRIMIDO|OVULO|SUPOSITORIO|GOTAS|GRANULO|"
    r"EMULSION|INHALADOR|INHALER|NEBULIZADOR|IMPLANTE|PELLET|LIOFILIZADO|RECONSTITUIR)\b",
    re.I
)

CONC_RE = re.compile(r"\d+\s*(?:mg|ml|mcg|ug|g|%|mEq|UI|IU|MG|ML|MCG|UG)\b", re.I)

# ---------------------------------------------------------------------------
# Post-processing: clean and validate
# ---------------------------------------------------------------------------

_GARBAGE_PA_RE = re.compile(
    r"UNIDADES\s+DISPONIBLES|CUENTA\s+CON\s*:|"
    r"\(UMD\)\s*:|EN\s+EL\s+MERCADO\b|CANAL\s+COMERCIAL|"
    r"TITULARES?\s+DE\s+REGISTRO|DECLARADOS?\s+COMO|"
    r"A\s+LA\s+FECHA\s*=|PRODUCTO\s+DISPONIBLE",
    re.I,
)

_ESTADO_PA_RE = re.compile(
    r"^(En\s+riesgo|Desabastecido|En\s+monitoriz|No\s+comercializ|"
    r"Descontinuado|No\s+desabastecido|Productos\s+declarados)",
    re.I,
)

_VALID_ESTADOS = {
    "DESABASTECIDO", "EN_RIESGO", "EN_MONITORIZACION",
    "NO_DESABASTECIDO", "NO_COMERCIALIZADO", "DESCONTINUADO",
}

# Sin \b: captura ATC concatenado directamente al nombre (CICLOFOSFAMIDAL01AA01)
_ATC_CONCAT_RE = re.compile(r"([A-Z]\d{2}[A-Z]{2}\d{2})")


def _limpiar_entrada(e: dict) -> bool:
    """
    Limpia y valida una entrada parseada del PDF.
    - Si el ATC quedó concatenado al principio_activo, lo separa.
    - Descarta entradas con texto de pie de tabla o descripciones de estado como nombre.
    Retorna True si la entrada es válida, False si debe descartarse.
    """
    pa = e.get("principio_activo", "").strip()

    # Intentar recuperar cuando el ATC quedó pegado al nombre sin separador
    # Ej: "CICLOFOSFAMIDAL01AA01" → principio_activo="CICLOFOSFAMIDA", atc="L01AA01"
    # Usamos _ATC_CONCAT_RE (sin \b) porque entre letra mayúscula y letra no hay word boundary
    atc_m = _ATC_CONCAT_RE.search(pa)
    if atc_m:
        pa_before = pa[:atc_m.start()].strip().rstrip("–-·,").strip()
        if (len(pa_before) >= 3
                and not _GARBAGE_PA_RE.search(pa_before)
                and not _ESTADO_PA_RE.match(pa_before)):
            if not e.get("atc"):
                e["atc"] = atc_m.group()
            e["principio_activo"] = pa_before
            pa = pa_before
        else:
            return False  # texto basura o descripción de estado — descartar

    if len(pa) < 3:
        return False
    if len(pa) > 150:
        return False
    if _GARBAGE_PA_RE.search(pa):
        return False
    if _ESTADO_PA_RE.match(pa):
        return False
    if e.get("estado") not in _VALID_ESTADOS:
        return False

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return " ".join(s.split()).strip() if s else ""

def _get_estado(text: str) -> str | None:
    for key, pat in ESTADO_PATTERNS:
        if pat.search(text):
            return key
    return None

def _get_atc(text: str) -> str | None:
    m = ATC_RE.search(text)
    return m.group() if m else None

def _get_dates(text: str) -> tuple[str | None, str | None]:
    dates = DATE_RE.findall(text)
    return (dates[0] if dates else None, dates[1] if len(dates) >= 2 else None)

def _sum_umd(text: str) -> int | None:
    total = 0.0
    found = False
    for m in UMD_RE.finditer(text):
        try:
            v = float(m.group(1).replace(".", "").replace(",", "."))
            total += v
            found = True
        except ValueError:
            pass
    return int(total) if found else None

def _new_entry(mes: int, anio: int, num: int) -> dict:
    return dict(
        mes=mes, anio=anio, numero_entrada=num,
        principio_activo="", forma="", concentracion="",
        nombre_medicamento="", atc=None, estado=None,
        causas="", fecha_inicio=None, fecha_ultimo=None,
        total_titulares=0, disponibilidad_total_umd=None,
        _umd=[],
    )

def _finalize_entry(e: dict) -> dict:
    umd_chunks = e.pop("_umd", [])
    e["disponibilidad_total_umd"] = _sum_umd(" ".join(umd_chunks)) if umd_chunks else None
    parts = [e["principio_activo"], e["forma"], e["concentracion"]]
    e["nombre_medicamento"] = _clean(" ".join(p for p in parts if p))
    return e

def _detect_section_from_blocks(blocks: list) -> str | None:
    for b in blocks:
        t = b[4] if len(b) > 4 else ""
        if SECCION_NO_COM_RE.search(t):   return "NO_COM"
        if SECCION_NO_DESAB_RE.search(t): return "NO_DESAB"
        if SECCION_MON_RE.search(t):      return "MON"
        if "CANAL COMERCIAL" in t and "CANAL INSTITUCIONAL" in t: return "MON"
    return None


# ---------------------------------------------------------------------------
# Parse lines helper — usado en formatos compactos
# ---------------------------------------------------------------------------

def _absorb_lines(entry: dict, lines: list[str]) -> None:
    """
    Dada una lista de líneas de texto de un bloque, llena los campos del entry.
    Ya sabemos que el entry tiene el principio_activo desde el header.
    """
    in_causas = bool(entry["estado"])
    atc_seen = bool(entry["atc"])

    for line in lines:
        line = line.strip()
        if not line:
            continue

        line_atc   = _get_atc(line)
        line_dates = DATE_RE.findall(line)
        line_state = _get_estado(line)

        # Si contiene titular «, es UMD
        if TITULAR_RE.search(line):
            entry["total_titulares"] += 1
            entry["_umd"].append(line)
            continue

        if line_atc and not atc_seen:
            entry["atc"] = line_atc
            atc_seen = True
            # Fechas en la misma línea
            if line_dates and not entry["fecha_inicio"]:
                entry["fecha_inicio"]  = line_dates[0]
                entry["fecha_ultimo"]  = line_dates[1] if len(line_dates) >= 2 else None
            if line_state and not entry["estado"]:
                entry["estado"] = line_state
                in_causas = True
                # Causas inline (post-estado)
                for _, pat in ESTADO_PATTERNS:
                    m = pat.search(line)
                    if m:
                        post = line[m.end():].strip()
                        if post and not ATC_RE.search(post) and "UMD" not in post:
                            entry["causas"] = _clean(entry["causas"] + " " + post)
                        break
            continue

        if line_state and not entry["estado"]:
            entry["estado"] = line_state
            in_causas = True
            continue

        if line_dates and atc_seen and not entry["fecha_inicio"]:
            entry["fecha_inicio"] = line_dates[0]
            entry["fecha_ultimo"] = line_dates[1] if len(line_dates) >= 2 else None
            continue

        if in_causas:
            if "UMD" not in line and not ATC_RE.search(line) and not DATE_RE.match(line):
                entry["causas"] = _clean(entry["causas"] + " " + line)
            continue

        # Pre-ATC: forma / concentración
        if not atc_seen:
            # ¿Ya tenemos el principio activo definido?
            if not entry["principio_activo"]:
                entry["principio_activo"] = _clean(line)
            elif not entry["forma"] and FORMA_WORDS.search(line):
                entry["forma"] = _clean(line)
            elif not entry["forma"] and not CONC_RE.search(line):
                entry["forma"] = _clean(line)
            elif not entry["concentracion"]:
                entry["concentracion"] = _clean(line)


# ---------------------------------------------------------------------------
# Sección MON (2026) — layout en 4 columnas
# ---------------------------------------------------------------------------

def _parse_mon_2026(
    blocks_with_page: list[tuple],   # (x0, y0, x1, y1, text, page_num)
    mes: int, anio: int
) -> dict[int, dict]:
    """
    Sección 1 de 2026. Columnas:
      COL A  (x0 ≤ 137): header (número + nombre)  y sub-header (forma/conc)
      COL B  (137 < x0 ≤ 290, sin «): ATC + fechas + Estado + Causas
      COL B' (137 < x0 ≤ 420, con «): bloque de titular
      COL C  (x0 > 275, con «): titular canal comercial/institucional
    """
    sorted_blocks = sorted(blocks_with_page, key=lambda b: (b[5], round(b[1]/8)*8, b[0]))

    entries: dict[int, dict] = {}
    # Lista de (num, page, y0) para localizar la entrada más cercana
    header_info: list[tuple[int, int, float]] = []

    def nearest_entry(page_num: int, y0: float) -> dict | None:
        best, best_d = None, 1e9
        for num, hp, hy in header_info:
            if hp == page_num:
                d = y0 - hy  # positivo = bloque debajo del header
                if -8 <= d < 250 and d < best_d:
                    best_d, best = d, entries[num]
        if best is None:
            # fallback: última entrada de la página anterior
            for num, hp, hy in reversed(header_info):
                if hp == page_num - 1:
                    return entries[num]
        return best

    # --- PRIMERA PASADA: registrar headers de COL A (bloques con número de entrada) ---
    # Necesario porque algunos bloques de nombre/forma llegan antes del header numérico
    # (diferencia subpíxel en y0 los pone en un bucket de sorted distinto)
    for b in sorted_blocks:
        x0, y0, x1, y1, text, page_num = b
        text_stripped = text.strip()
        if not text_stripped or x0 > 137:
            continue
        lines = [l.strip() for l in text_stripped.split("\n") if l.strip()]
        if not lines:
            continue
        num = None
        rest = lines[:]
        if NUM_ONLY_RE.match(lines[0]):
            num = int(lines[0])
            rest = lines[1:]
        elif re.match(r"^(\d{1,3})\s+[A-ZÁÉÍÓÚÑ]", lines[0]) and not _UNIT_WORDS_RE.match(lines[0]):
            m_num = re.match(r"^(\d{1,3})\s+(.+)$", lines[0])
            if m_num:
                num = int(m_num.group(1))
                rest = [m_num.group(2)] + lines[1:]
        if num is not None and num not in entries:
            e = _new_entry(mes, anio, num)
            e["_section"] = "MON"
            e["_page"] = page_num
            e["_y"] = y0
            entries[num] = e
            header_info.append((num, page_num, y0))

    # --- SEGUNDA PASADA: procesar todos los bloques (incluyendo COL A completo) ---
    for b in sorted_blocks:
        x0, y0, x1, y1, text, page_num = b
        text = text.strip()
        if not text:
            continue

        is_tit = bool(TITULAR_RE.search(text))
        has_atc = bool(ATC_RE.search(text))

        # ---- COLUMNA A: header (número + nombre medicamento) ----
        if x0 <= 137:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            num = None
            rest = lines[:]
            if NUM_ONLY_RE.match(lines[0]):
                num = int(lines[0])
                rest = lines[1:]
            elif re.match(r"^(\d{1,3})\s+[A-ZÁÉÍÓÚÑ]", lines[0]) and not _UNIT_WORDS_RE.match(lines[0]):
                # Solo si el resto empieza con letra mayúscula (nombre de medicamento)
                # Excluye "20 mg / mL", "100 mg", "500 UI/vial", "740 MBq", etc.
                m = re.match(r"^(\d{1,3})\s+(.+)$", lines[0])
                if m:
                    num = int(m.group(1))
                    rest = [m.group(2)] + lines[1:]

            # En pass 1 ya registramos la entrada; en pass 2 solo procesamos las líneas de contenido
            if num is not None and num in entries:
                e = entries[num]
                # Parsear líneas restantes del bloque header:
                # Primero checar estado en el bloque completo (puede haber "En riesgo de\ndesabastecimiento")
                rest_text = " ".join(rest)
                block_estado = _get_estado(rest_text)
                if block_estado and not e["estado"]:
                    e["estado"] = block_estado
                    for _, pat in ESTADO_PATTERNS:
                        m2 = pat.search(rest_text)
                        if m2:
                            # Avanzar al final de la palabra actual (para no capturar "astecimiento")
                            end_pos = m2.end()
                            while end_pos < len(rest_text) and rest_text[end_pos].isalpha():
                                end_pos += 1
                            post = rest_text[end_pos:].strip()
                            causa_lines = [l2.strip() for l2 in post.split(" ")
                                           if l2.strip() and "UMD" not in l2
                                           and not DATE_RE.match(l2.strip())]
                            if causa_lines:
                                e["causas"] = _clean(" ".join(causa_lines))
                            break

                for l in rest:
                    if not l:
                        continue
                    line_atc = _get_atc(l)
                    if line_atc and not e["atc"]:
                        e["atc"] = line_atc
                        fi, fu = _get_dates(l)
                        if fi and not e["fecha_inicio"]:
                            e["fecha_inicio"] = fi
                        if fu and not e["fecha_ultimo"]:
                            e["fecha_ultimo"] = fu
                        continue
                    if TITULAR_RE.search(l):
                        e["total_titulares"] += 1
                        e["_umd"].append(l)
                        continue
                    if DATE_RE.match(l) and e["atc"]:
                        fi2, fu2 = _get_dates(l)
                        if fi2 and not e["fecha_inicio"]:
                            e["fecha_inicio"] = fi2
                        if fu2 and not e["fecha_ultimo"]:
                            e["fecha_ultimo"] = fu2
                        continue
                    if _get_estado(l) or (e["estado"] and "riesgo" in l.lower() and "desab" in l.lower()):
                        continue
                    if not e["principio_activo"] and not FORMA_WORDS.search(l) and not CONC_RE.search(l) and not DATE_RE.match(l):
                        e["principio_activo"] = _clean(l)
                    elif not e["forma"] and FORMA_WORDS.search(l):
                        e["forma"] = _clean(l)
                    elif not e["concentracion"] and CONC_RE.search(l):
                        e["concentracion"] = _clean(l)

            elif num is None:
                # Bloque sub-header: nombre/forma/concentración (o estado si viene antes del nombre)
                # Asignar al header más cercano en la misma página.
                # El header puede estar ligeramente arriba (hy <= y0+5) o ligeramente abajo
                # (y0 <= hy <= y0+5) cuando los bloques de texto tienen y0 ligeramente diferente
                # por subpíxeles (ej: PREGABALINA en y=267.998, "331" en y=268.238).
                best = None
                best_hy = -1e9
                for hn, hp, hy in header_info:
                    # Acepta headers ligeramente encima o al mismo nivel (hy <= y0+5)
                    if hp == page_num and hy <= y0 + 5 and hy > best_hy:
                        best_hy = hy
                        best = entries[hn]
                # Si no encontramos header arriba/mismo nivel, buscar header LIGERAMENTE ABAJO
                # (hasta 5 unidades abajo, para manejar subpíxeles)
                if best is None:
                    best_fwd_hy = 1e9
                    for hn, hp, hy in header_info:
                        if hp == page_num and y0 < hy <= y0 + 5 and hy < best_fwd_hy:
                            best_fwd_hy = hy
                            best = entries[hn]
                    if best is not None:
                        best_hy = best_fwd_hy
                if best is not None and abs(y0 - best_hy) < 45:
                    lines2 = [l.strip() for l in text.split("\n") if l.strip()]
                    # Verificar estado en el bloque completo (puede haber "En riesgo de\ndesabastecimiento")
                    block_estado2 = _get_estado(text)
                    if block_estado2 and not best["estado"]:
                        best["estado"] = block_estado2
                        for _, pat in ESTADO_PATTERNS:
                            m2 = pat.search(text)
                            if m2:
                                end_pos = m2.end()
                                while end_pos < len(text) and text[end_pos].isalpha():
                                    end_pos += 1
                                post = text[end_pos:].strip()
                                causa_lines = [l3.strip() for l3 in post.split("\n")
                                               if l3.strip() and "UMD" not in l3
                                               and not DATE_RE.match(l3.strip())
                                               and not ATC_RE.search(l3)
                                               and not FORMA_WORDS.search(l3)
                                               and not CONC_RE.search(l3)]
                                if causa_lines:
                                    best["causas"] = _clean(" ".join(causa_lines))
                                break
                    for l in lines2:
                        if ATC_RE.search(l):
                            continue
                        # Ignorar líneas de estado (ya capturado arriba)
                        if _get_estado(l):
                            continue
                        # Ignorar fragmentos de "desabastecimiento" (segunda línea del estado)
                        if best["estado"] and re.match(r"^desabastecimiento", l, re.I):
                            continue
                        # Si el entry aún no tiene principio_activo y la línea parece
                        # un nombre de medicamento (sin forma ni concentración)
                        if not best["principio_activo"] and not FORMA_WORDS.search(l) and not CONC_RE.search(l) and not DATE_RE.match(l):
                            best["principio_activo"] = _clean(l)
                        elif not best["forma"]:
                            if FORMA_WORDS.search(l):
                                best["forma"] = _clean(l)
                            elif not CONC_RE.search(l):
                                best["forma"] = _clean(l)
                            else:
                                best["concentracion"] = _clean(l)
                        elif not best["concentracion"]:
                            best["concentracion"] = _clean(l)

        # ---- COLUMNA B sin «: ATC + Estado + Causas ----
        elif 137 < x0 <= 290 and has_atc and not is_tit:
            e = nearest_entry(page_num, y0)
            if e is None:
                continue
            atc = _get_atc(text)
            estado = _get_estado(text)
            fi, fu = _get_dates(text)
            if atc and not e["atc"]:
                e["atc"] = atc
            if fi and not e["fecha_inicio"]:
                e["fecha_inicio"] = fi
            if fu and not e["fecha_ultimo"]:
                e["fecha_ultimo"] = fu
            if estado and not e["estado"]:
                e["estado"] = estado
                # causas: lo que sigue al estado en el bloque (antes de cualquier «)
                for _, pat in ESTADO_PATTERNS:
                    m = pat.search(text)
                    if m:
                        # Avanzar al final de la palabra (evita capturar "astecimiento")
                        end_pos = m.end()
                        while end_pos < len(text) and text[end_pos].isalpha():
                            end_pos += 1
                        post = text[end_pos:]
                        # Cortar en el primer titular «
                        tit_m = TITULAR_RE.search(post)
                        if tit_m:
                            post = post[:tit_m.start()]
                        causa_lines = [l.strip() for l in post.split("\n")
                                       if l.strip() and "UMD" not in l
                                       and not DATE_RE.match(l.strip())]
                        if causa_lines:
                            e["causas"] = _clean(" ".join(causa_lines))
                        break
            # Si el bloque también contiene titular inline (poco frecuente)
            if TITULAR_RE.search(text):
                e["total_titulares"] += 1
                e["_umd"].append(text)

        # ---- COLUMNA B' con «: ATC + datos titular ----
        elif 137 < x0 <= 420 and has_atc and is_tit:
            e = nearest_entry(page_num, y0)
            if e is None:
                continue
            atc = _get_atc(text)
            if atc and not e["atc"]:
                e["atc"] = atc
            fi, fu = _get_dates(text)
            if fi and not e["fecha_inicio"]:
                e["fecha_inicio"] = fi
            if fu and not e["fecha_ultimo"]:
                e["fecha_ultimo"] = fu
            # El estado puede estar en las primeras líneas (antes del «)
            tit_start = min((m.start() for m in TITULAR_RE.finditer(text)), default=len(text))
            pre_tit = text[:tit_start]
            estado = _get_estado(pre_tit)
            if estado and not e["estado"]:
                e["estado"] = estado
                for _, pat in ESTADO_PATTERNS:
                    m2 = pat.search(pre_tit)
                    if m2:
                        end_pos = m2.end()
                        while end_pos < len(pre_tit) and pre_tit[end_pos].isalpha():
                            end_pos += 1
                        post = pre_tit[end_pos:].strip()
                        causa_lines = [l.strip() for l in post.split("\n")
                                       if l.strip() and "UMD" not in l]
                        if causa_lines:
                            e["causas"] = _clean(" ".join(causa_lines))
                        break
            e["total_titulares"] += 1
            e["_umd"].append(text)

        # ---- COLUMNA C/D: titular (x > 275, con «) ----
        elif x0 > 275 and is_tit:
            e = nearest_entry(page_num, y0)
            if e is not None:
                e["total_titulares"] += 1
                e["_umd"].append(text)

        # ---- Bloque de estado/causas adicional (x 137-290, sin ATC, sin «) ----
        # Cubre bloques en x~140-290 que contienen estado o causas sin código ATC
        # Ejemplo: entrada 8 (ALENDRONATO): estado 'En riesgo...' en x=214
        elif 137 < x0 <= 290 and not has_atc and not is_tit and len(text) > 3:
            e = nearest_entry(page_num, y0)
            if e is not None:
                estado = _get_estado(text)
                if estado and not e["estado"]:
                    e["estado"] = estado
                    # Causas inline: lo que sigue al patrón de estado
                    for _, pat in ESTADO_PATTERNS:
                        m2 = pat.search(text)
                        if m2:
                            end_pos = m2.end()
                            while end_pos < len(text) and text[end_pos].isalpha():
                                end_pos += 1
                            post = text[end_pos:].strip()
                            causa_lines = [l.strip() for l in post.split("\n")
                                           if l.strip() and "UMD" not in l
                                           and not DATE_RE.match(l.strip())]
                            if causa_lines:
                                e["causas"] = _clean(" ".join(causa_lines))
                            break
                elif not e["causas"] and not estado:
                    # Puede ser causas adicionales
                    if not CONC_RE.search(text) and not FORMA_WORDS.search(text):
                        e["causas"] = _clean(text)

    return entries


# ---------------------------------------------------------------------------
# Sección NO_DESAB / NO_COM (2026) — layout compacto sin titulares
# ---------------------------------------------------------------------------

def _parse_compact_section_2026(
    blocks_with_page: list[tuple],
    mes: int, anio: int, section_label: str
) -> dict[int, dict]:
    """
    Secciones 2 y 3 de 2026 (No desabastecido, No comercializado/Descontinuado).

    Patrones observados en estos bloques (todos con x0 < 200):
      Caso A: '12\nAFATINIB\nTABLETA\n20 mg\nL01EB03\n...\nNo desabastecido\n...'  (todo en un bloque)
      Caso B: '1\nACETAMINOFEN + CODEINA' + 'TABLETA\n 325 mg\nN02AJ06\n...'      (2 bloques)
      Caso C: '5' + 'ACETATO DE ALUMINIO' + 'LOCIÓN\n0.05\nD02AX99\n...'           (3 bloques)
      Caso D: '10' + 'ACTIVADOR TISULAR... (muy largo)' + 'forma' + '50 mg\nATC\n...' (3-4 bloques)
    """
    # Ordenar: página, y0, x0
    sorted_blocks = sorted(blocks_with_page, key=lambda b: (b[5], round(b[1]/8)*8, b[0]))

    entries: dict[int, dict] = {}
    # Lista de (num, page, y0, x0)
    header_info: list[tuple[int, int, float, float]] = []

    def nearest(page_num: int, y0: float, x0: float) -> dict | None:
        """Busca la entrada más cercana por y0."""
        best, best_d = None, 1e9
        for hn, hp, hy, hx in header_info:
            if hp == page_num:
                dy = abs(y0 - hy)
                if dy < 80 and dy < best_d:
                    best_d, best = dy, entries[hn]
        if best is None:
            for hn, hp, hy, hx in reversed(header_info):
                if hp == page_num - 1:
                    return entries[hn]
        return best

    for b in sorted_blocks:
        x0, y0, x1, y1, text, page_num = b
        text = text.strip()
        if not text or x0 > 600:
            continue

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            continue

        # Ignorar bloques de headers de tabla (No., Nombre, ATC, Fecha...)
        if "Nombre del medicamento" in text or "ATC" == text:
            continue

        has_atc  = bool(ATC_RE.search(text))
        has_date = bool(DATE_RE.search(text))
        has_state = bool(_get_estado(text))

        # ¿Tiene número de entrada?
        num = None
        rest_lines = lines[:]
        if NUM_ONLY_RE.match(lines[0]):
            num = int(lines[0])
            rest_lines = lines[1:]
        elif re.match(r"^(\d{1,3})\s+[A-ZÁÉÍÓÚÑ]", lines[0]) and not _UNIT_WORDS_RE.match(lines[0]):
            m = re.match(r"^(\d{1,3})\s+(.+)$", lines[0])
            if m:
                num = int(m.group(1))
                rest_lines = [m.group(2)] + lines[1:]

        if num is not None and num not in entries:
            e = _new_entry(mes, anio, num)
            e["_section"] = section_label
            e["_page"] = page_num
            e["_y"] = y0
            entries[num] = e
            header_info.append((num, page_num, y0, x0))
            # Parsear el resto de las líneas del mismo bloque
            _absorb_lines(e, rest_lines)

        elif num is not None and num in entries:
            # Entrada ya existe: puede ser un bloque adicional del mismo número
            _absorb_lines(entries[num], rest_lines)

        else:
            # Bloque sin número: pertenece a la entrada más cercana
            if not has_atc and not has_date and not has_state:
                # Puede ser nombre de medicamento o forma farmacéutica
                e = nearest(page_num, y0, x0)
                if e is not None and abs(y0 - e.get("_y", 0)) < 25:
                    # Asignar como nombre/forma/conc dependiendo de qué falta
                    if not e["principio_activo"]:
                        e["principio_activo"] = _clean(text)
                    elif not e["forma"] and FORMA_WORDS.search(text):
                        e["forma"] = _clean(text)
                    elif not e["concentracion"] and CONC_RE.search(text):
                        e["concentracion"] = _clean(text)
                    elif not e["forma"]:
                        e["forma"] = _clean(text)
            else:
                # Bloque de datos (ATC/fechas/estado) — asignar a entrada cercana
                e = nearest(page_num, y0, x0)
                if e is not None:
                    _absorb_lines(e, lines)

    return entries


# ---------------------------------------------------------------------------
# Parser 2025 formato Excel-exportado (abril–noviembre 2025)
# ---------------------------------------------------------------------------
#
# Estructura del PDF (exportado desde Excel):
#   - Columna Excel A (x~4–67): números de fila Excel (1, 2, 3…) → ignorar
#   - Columna No. (x~12–67): "N\nNOMBRE_MEDICAMENTO\nFORMA?\n" (primer bloque de entrada)
#   - Columna conc/forma (x~65–120): concentración / forma separada en bloque aparte
#   - Columna ATC+datos (x~95–200): "ATC\nFECHA\nFECHA\nESTADO\nCAUSAS\nTITULAR_DATOS\n"
#   - Columnas titulares canal comercial/institucional (x>350): UMD por titular
#
# Truco de detección: bloque "A\nB\nC\nD\nE\nF\nG\nH\nI\n" en primeras páginas.

def _parse_excel_2025(doc: fitz.Document, mes: int, anio: int) -> list[dict]:
    """
    Parser para PDFs INVIMA 2025 exportados desde Excel.

    Estructura de columnas (varía según el PDF pero sigue este patrón):
      ColA (x<50)    : números de fila Excel (ignorar)
      ColNo (x~12-70): "N\\nNOMBRE\\nFORMA?" → bloque de entrada (num + nombre + forma)
      ColConc (x<130): concentración/forma separada (bloque auxiliar)
      ColATC (x<250) : "ATC\\nFECHA\\nFECHA\\nESTADO\\nCAUSAS\\n" (bloque de datos)
      ColUMD (x>350) : datos UMD por titular (con «)
    """
    # Key: (section, num) para separar entradas de distintas secciones con el mismo número
    entries: dict[tuple[str, int], dict] = {}
    current_section = "MON"
    # (section, num, page_num, y0)
    header_info: list[tuple[str, int, int, float]] = []

    # Detectar sección a partir de bloques de texto
    _SECCION_MON_XL    = re.compile(r"MONITORIZACI[OÓ]N|RIESGO DE DESBASTECIMIENT", re.I)
    _SECCION_NODESAB_XL = re.compile(r"NO\s+DESBASTECIDOS?\s+COMO|ESTADO\s+NO\s+DESBASTECIDOS?", re.I)
    _SECCION_NOCOM_XL   = re.compile(r"NO\s+COMERCIALIZADO.*DESCONTINUADO|DESCONTINUADO.*NO\s+COMERCIALIZADO", re.I)

    def _detect_xl_section(blocks: list) -> str | None:
        for b in blocks:
            t = b[4] if len(b) > 4 else ""
            if _SECCION_NOCOM_XL.search(t):    return "NO_COM"
            if _SECCION_NODESAB_XL.search(t):  return "NO_DESAB"
            if _SECCION_MON_XL.search(t) and len(t) > 30: return "MON"
        return None

    def nearest_entry(page_num: int, y0: float) -> dict | None:
        """Entrada más cercana al bloque dado (misma sección, misma página o anterior)."""
        best, best_d = None, 1e9
        for sec, num, hp, hy in header_info:
            if hp == page_num and sec == current_section:
                d = y0 - hy
                if -5 <= d < 350 and d < best_d:
                    best_d, best = d, entries[(sec, num)]
        if best is None:
            for sec, num, hp, hy in reversed(header_info):
                if hp == page_num - 1 and sec == current_section:
                    return entries[(sec, num)]
        return best

    for page_num in range(len(doc)):
        raw_blocks = doc[page_num].get_text("blocks")

        # Detectar cambio de sección
        sec = _detect_xl_section(raw_blocks)
        if sec:
            current_section = sec

        # Ordenar: y0 agrupado, luego x0
        page_blocks = sorted(
            [(b[0], b[1], b[2], b[3], b[4]) for b in raw_blocks if len(b) >= 5],
            key=lambda b: (round(b[1] / 8) * 8, b[0])
        )

        for x0, y0, x1, y1, text in page_blocks:
            text = text.strip()
            if not text:
                continue

            # Ignorar bloques de encabezado de columnas Excel (A/B/C/D/...)
            if _EXCEL_HEADER_RE.match(text):
                continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            # --- Bloques de fila Excel pura (solo número) → ignorar ---
            if len(lines) == 1 and re.match(r"^\d{1,3}$", lines[0]):
                continue

            # --- Ignorar bloques de encabezado de tabla ---
            if lines[0] in ("No.", "No") and ("Nombre" in text or "ATC" in text):
                continue
            if text in ("ATC",):
                continue

            # -------- Columna principal izquierda: bloque de entrada --------
            # Patrón: primera línea = número de entrada (1–999), resto = nombre+forma
            # SOLO si tiene al menos 2 líneas (número + nombre); si tiene solo un número
            # y ya fue filtrado arriba como "fila Excel pura", no llega aquí.
            num = None
            rest = lines[:]

            if NUM_ONLY_RE.match(lines[0]) and len(lines) >= 2:
                # "1\nACIDO VALPROICO\nSOLUCION INYECTABLE"
                num = int(lines[0])
                rest = lines[1:]
            elif re.match(r"^(\d{1,3})\s+[A-ZÁÉÍÓÚÑÀ-ɏ]", lines[0]) and not _UNIT_WORDS_RE.match(lines[0]):
                m_num = re.match(r"^(\d{1,3})\s+(.+)$", lines[0])
                if m_num:
                    num = int(m_num.group(1))
                    rest = [m_num.group(2)] + lines[1:]

            if num is not None:
                key = (current_section, num)
                if key not in entries:
                    e = _new_entry(mes, anio, num)
                    e["_section"] = current_section
                    e["_page"] = page_num
                    e["_y"] = y0
                    entries[key] = e
                    header_info.append((current_section, num, page_num, y0))
                    # Decidir cómo parsear el resto: si contiene ATC o estado → _absorb_lines
                    # (bloque compacto con todo en uno: "N\nNOMBRE\nATC\nFECHA\nESTADO\n...")
                    # Si solo tiene nombre/forma → _absorb_entry_header
                    rest_text_j = " ".join(r.strip() for r in rest)
                    if ATC_RE.search(rest_text_j) or _get_estado(rest_text_j):
                        # Bloque compacto: primero separar nombre del resto
                        # La primera línea del rest sin ATC/fecha/estado → nombre
                        header_lines = []
                        data_lines = []
                        for rl in rest:
                            if (not header_lines and not ATC_RE.search(rl)
                                    and not DATE_RE.search(rl) and not _get_estado(rl)
                                    and not TITULAR_RE.search(rl)
                                    and not CONC_RE.search(rl)):
                                # Probablemente nombre o forma
                                if not FORMA_WORDS.search(rl):
                                    header_lines.append(rl)
                                else:
                                    data_lines.append(rl)
                            else:
                                data_lines.append(rl)
                        _absorb_entry_header(e, header_lines)
                        _absorb_lines(e, data_lines)
                    else:
                        _absorb_entry_header(e, rest)
                else:
                    # Mismo número ya existe en esta sección: bloque adicional → datos
                    _absorb_lines(entries[key], rest)
                continue

            # -------- Bloques de datos (ATC / estado / causas / titulares) --------
            e = nearest_entry(page_num, y0)
            if e is None:
                continue

            # Verificar estado en el texto completo (el estado puede ser multi-línea:
            # "En riesgo de \ndesabastecimiento" → _get_estado(text) con \s+ lo detecta)
            text_joined = " ".join(text.split())  # colapsar newlines/espacios
            has_atc = bool(ATC_RE.search(text))
            has_state = bool(_get_estado(text_joined))
            is_tit = bool(TITULAR_RE.search(text))

            if is_tit and (has_atc or has_state):
                # Bloque mixto: ATC/estado seguido de «titular».
                # Parsear la parte pre-« y luego el resto como UMD.
                first_tit = min(m.start() for m in TITULAR_RE.finditer(text))
                pre_tit = text[:first_tit]
                post_tit = text[first_tit:]
                pre_lines = [l.strip() for l in pre_tit.split("\n") if l.strip()]
                # Primero, intentar detectar estado en el bloque pre-tit completo
                pre_joined = " ".join(pre_tit.split())
                if not e["estado"]:
                    blk_estado = _get_estado(pre_joined)
                    if blk_estado:
                        e["estado"] = blk_estado
                        for _, pat in ESTADO_PATTERNS:
                            m2 = pat.search(pre_joined)
                            if m2:
                                end_pos = m2.end()
                                while end_pos < len(pre_joined) and pre_joined[end_pos].isalpha():
                                    end_pos += 1
                                post_caus = pre_joined[end_pos:].strip()
                                # Quitar fechas y texto de canal
                                causa_toks = [t for t in post_caus.split()
                                              if not re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t)
                                              and t not in ("EN", "EL", "CANAL", "COMERCIAL", "INSTITUCIONAL")]
                                if causa_toks:
                                    e["causas"] = _clean(" ".join(causa_toks[:10]))
                                break
                _absorb_lines(e, pre_lines)
                e["total_titulares"] += 1
                e["_umd"].append(post_tit)
            elif is_tit:
                e["total_titulares"] += 1
                e["_umd"].append(text)
            elif has_atc or has_state:
                # Intentar detectar estado multi-línea primero
                if not e["estado"]:
                    blk_estado = _get_estado(text_joined)
                    if blk_estado:
                        e["estado"] = blk_estado
                        for _, pat in ESTADO_PATTERNS:
                            m2 = pat.search(text_joined)
                            if m2:
                                end_pos = m2.end()
                                while end_pos < len(text_joined) and text_joined[end_pos].isalpha():
                                    end_pos += 1
                                post_caus = text_joined[end_pos:].strip()
                                causa_toks = [t for t in post_caus.split()
                                              if not re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t)]
                                if causa_toks:
                                    e["causas"] = _clean(" ".join(causa_toks[:15]))
                                break
                _absorb_lines(e, lines)
            elif x0 < 200:
                # Bloque de concentración/forma separado (entre columna No. y ATC)
                _absorb_entry_header(e, lines)
            # Bloques en x>=200 sin ATC/estado/«: causas adicionales fragmentadas
            # → ignorar para evitar capturar texto no relevante

    # Finalizar en orden
    result = []
    for key, e in sorted(entries.items(), key=lambda kv: (
        {"MON": 0, "NO_DESAB": 1, "NO_COM": 2}.get(kv[1].get("_section", "MON"), 3),
        kv[1].get("numero_entrada", 0)
    )):
        sec = e.pop("_section", current_section)
        e.pop("_page", None)
        e.pop("_y", None)
        if not e["estado"]:
            if sec == "NO_DESAB": e["estado"] = "NO_DESABASTECIDO"
            elif sec == "NO_COM": e["estado"] = "NO_COMERCIALIZADO"
        result.append(_finalize_entry(e))
    return result


def _absorb_entry_header(entry: dict, lines: list[str]) -> None:
    """
    Parsea las líneas de un bloque de encabezado de entrada (nombre, forma, concentración).
    No toca ATC, fechas ni estado (esos van a _absorb_lines).
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ATC_RE.search(line) or DATE_RE.search(line) or _get_estado(line) or TITULAR_RE.search(line):
            continue
        if not entry["principio_activo"] and not FORMA_WORDS.search(line) and not CONC_RE.search(line):
            entry["principio_activo"] = _clean(line)
        elif not entry["forma"] and FORMA_WORDS.search(line):
            entry["forma"] = _clean(line)
        elif not entry["concentracion"] and CONC_RE.search(line):
            entry["concentracion"] = _clean(line)
        elif not entry["forma"]:
            entry["forma"] = _clean(line)
        elif not entry["concentracion"]:
            entry["concentracion"] = _clean(line)


# ---------------------------------------------------------------------------
# Parser 2025 (formato compacto, sin separación clara de columnas)
# ---------------------------------------------------------------------------

def _parse_2025(doc: fitz.Document, mes: int, anio: int) -> list[dict]:
    entries: dict[int, dict] = {}
    current_section = "MON"
    header_info: list[tuple[int, int, float]] = []  # (num, page, y0)

    # Detectar si es formato "large-scale" (2025 mid-year: julio-noviembre)
    # en el que los bloques ATC están en x~560-580, y los marcadores de página en x=7-10.
    # En ese caso, ignoramos bloques de solo número con x0 ≤ 15.
    _is_large_scale = False
    for pn in range(min(2, len(doc))):
        for b in doc[pn].get_text("blocks"):
            if len(b) >= 5 and ATC_RE.search(b[4]) and b[0] > 300:
                _is_large_scale = True
                break
        if _is_large_scale:
            break

    for page_num in range(len(doc)):
        page = doc[page_num]
        raw_blocks = page.get_text("blocks")

        # Detectar sección
        sec = _detect_section_from_blocks(raw_blocks)
        if sec:
            current_section = sec

        # Ordenar bloques: y0, x0
        page_blocks = sorted(
            [(b[0], b[1], b[2], b[3], b[4]) for b in raw_blocks if len(b) >= 5],
            key=lambda b: (round(b[1]/8)*8, b[0])
        )

        for x0, y0, x1, y1, text in page_blocks:
            text = text.strip()
            if not text:
                continue

            # Columnas derechas en 2025:
            # - Titular (con «): asignar UMD al entry más cercano
            # - ATC/estado (sin «, pero con ATC): procesar como bloque de datos
            # - Causas extra (texto sin ATC ni «): ignorar (ya están en el ATC block)
            if x0 >= 400:
                has_atc_right = bool(ATC_RE.search(text))
                is_tit_right = bool(TITULAR_RE.search(text))

                if is_tit_right:
                    # Asignar al entry más cercano
                    best, bd = None, 1e9
                    for hn, hp, hy in header_info:
                        if hp in (page_num, page_num - 1):
                            d = abs(y0 - hy) + (0 if hp == page_num else 500)
                            if d < bd:
                                bd, best = d, entries[hn]
                    if best is not None:
                        best["total_titulares"] += 1
                        best["_umd"].append(text)
                    continue
                elif has_atc_right:
                    # Bloque ATC en formato large-scale 2025 (x~568)
                    # Asignar al entry más cercano
                    best, bd = None, 1e9
                    for hn, hp, hy in header_info:
                        if hp in (page_num, page_num - 1):
                            d = abs(y0 - hy) + (0 if hp == page_num else 500)
                            if d < bd:
                                bd, best = d, entries[hn]
                    if best is not None:
                        lines_atc = [l.strip() for l in text.split("\n") if l.strip()]
                        _absorb_lines(best, lines_atc)
                    continue
                else:
                    # Texto secundario (causas, notas) — ignorar
                    continue

            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not lines:
                continue

            # Buscar número de entrada
            num = None
            rest = lines[:]
            if NUM_ONLY_RE.match(lines[0]):
                num = int(lines[0])
                rest = lines[1:]
            elif re.match(r"^(\d{1,3})\s+[A-ZÁÉÍÓÚÑ]", lines[0]) and not _UNIT_WORDS_RE.match(lines[0]):
                m = re.match(r"^(\d{1,3})\s+(.+)$", lines[0])
                if m:
                    num = int(m.group(1))
                    rest = [m.group(2)] + lines[1:]

            # En formato large-scale (2025 mid-year), ignorar marcadores de página
            # que aparecen como números solos en x ≤ 15 (vs entradas reales en x ≥ 35)
            if num is not None and _is_large_scale and x0 <= 15 and not rest:
                num = None

            if num is not None and num not in entries:
                e = _new_entry(mes, anio, num)
                e["_section"] = current_section
                e["_page"] = page_num
                e["_y"] = y0
                entries[num] = e
                header_info.append((num, page_num, y0))
                _absorb_lines(e, rest)

            elif num is not None and num in entries:
                _absorb_lines(entries[num], rest)

            else:
                # Bloque sin número: datos extra del entry más reciente cercano
                best, bd = None, 1e9
                for hn, hp, hy in header_info:
                    if hp == page_num:
                        dy = y0 - hy
                        if 0 <= dy < 80 and dy < bd:
                            bd, best = dy, entries[hn]
                if best is not None:
                    # Si el bloque no contiene ATC/fecha/estado/titular y el entry ya tiene
                    # estado asignado, intentar rellenar forma/concentración antes de ir a causas
                    has_atc_blk = bool(ATC_RE.search(text))
                    has_date_blk = bool(DATE_RE.search(text))
                    has_state_blk = bool(_get_estado(text))
                    has_tit_blk = bool(TITULAR_RE.search(text))
                    if (not has_atc_blk and not has_date_blk and not has_state_blk and not has_tit_blk
                            and best.get("estado") and x0 < 400):
                        # Es probable que sea forma/conc del entry
                        for l in lines:
                            if not l:
                                continue
                            if not best["forma"]:
                                if FORMA_WORDS.search(l) or not CONC_RE.search(l):
                                    best["forma"] = _clean(l)
                                else:
                                    best["concentracion"] = _clean(l)
                            elif not best["concentracion"]:
                                best["concentracion"] = _clean(l)
                    else:
                        _absorb_lines(best, lines)

    # Finalizar
    result = []
    for num, e in sorted(entries.items()):
        sec = e.pop("_section", current_section)
        e.pop("_page", None)
        e.pop("_y", None)
        if not e["estado"]:
            if sec == "NO_DESAB":    e["estado"] = "NO_DESABASTECIDO"
            elif sec == "NO_COM":    e["estado"] = "NO_COMERCIALIZADO"
        result.append(_finalize_entry(e))
    return result


# ---------------------------------------------------------------------------
# Parser 2026 principal
# ---------------------------------------------------------------------------

def _parse_2026(doc: fitz.Document, mes: int, anio: int) -> list[dict]:
    # Asignar sección a cada página
    page_sections: dict[int, str] = {}
    current_section = "MON"
    for page_num in range(len(doc)):
        raw = doc[page_num].get_text("blocks")
        sec = _detect_section_from_blocks(raw)
        if sec:
            current_section = sec
        page_sections[page_num] = current_section

    # Recopilar todos los bloques con página
    all_blocks: list[tuple] = []
    for page_num in range(len(doc)):
        for b in doc[page_num].get_text("blocks"):
            if len(b) >= 5:
                all_blocks.append((b[0], b[1], b[2], b[3], b[4], page_num))

    blocks_mon    = [b for b in all_blocks if page_sections[b[5]] == "MON"]
    blocks_no_des = [b for b in all_blocks if page_sections[b[5]] == "NO_DESAB"]
    blocks_no_com = [b for b in all_blocks if page_sections[b[5]] == "NO_COM"]

    e1 = _parse_mon_2026(blocks_mon, mes, anio)
    e2 = _parse_compact_section_2026(blocks_no_des, mes, anio, "NO_DESAB")
    e3 = _parse_compact_section_2026(blocks_no_com, mes, anio, "NO_COM")

    result = []
    for entries, default_estado in [(e1, None), (e2, "NO_DESABASTECIDO"), (e3, "NO_COMERCIALIZADO")]:
        for num, e in sorted(entries.items()):
            sec = e.pop("_section", "MON")
            e.pop("_page", None)
            e.pop("_y", None)
            if not e["estado"]:
                if sec == "NO_DESAB":   e["estado"] = "NO_DESABASTECIDO"
                elif sec == "NO_COM":   e["estado"] = "NO_COMERCIALIZADO"
                elif default_estado:    e["estado"] = default_estado
            result.append(_finalize_entry(e))

    doc.close()
    return result


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------

def parsear_pdf(pdf_path: str | Path, mes: int, anio: int) -> list[dict]:
    """
    Parsea un PDF INVIMA de seguimiento de abastecimiento.

    Parámetros
    ----------
    pdf_path : ruta al PDF
    mes      : mes del listado (1-12)
    anio     : año del listado

    Retorna
    -------
    Lista de dicts con los campos:
      mes, anio, numero_entrada, nombre_medicamento, principio_activo,
      forma, concentracion, atc, estado, causas, fecha_inicio, fecha_ultimo,
      total_titulares, disponibilidad_total_umd
    """
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))

    if anio >= 2026:
        raw = _parse_2026(doc, mes, anio)
    else:
        # Detectar formato Excel-exportado (abril–noviembre 2025):
        # contiene bloque "A\nB\nC\nD\nE..." de letras de columna Excel en las primeras páginas.
        _is_excel_fmt = False
        for pn in range(min(3, len(doc))):
            for b in doc[pn].get_text("blocks"):
                if len(b) >= 5 and _EXCEL_HEADER_RE.match(b[4].strip()):
                    _is_excel_fmt = True
                    break
            if _is_excel_fmt:
                break
        if _is_excel_fmt:
            raw = _parse_excel_2025(doc, mes, anio)
            doc.close()
        elif len(doc) > 2:
            p1_blocks = doc[1].get_text("blocks")
            has_cols = any(
                130 <= b[0] < 290 and ATC_RE.search(b[4] if len(b) > 4 else "") and not TITULAR_RE.search(b[4] if len(b) > 4 else "")
                for b in p1_blocks
            )
            if has_cols:
                all_blocks = []
                page_sections: dict[int, str] = {}
                current_section = "MON"
                for page_num in range(len(doc)):
                    raw_b = doc[page_num].get_text("blocks")
                    sec = _detect_section_from_blocks(raw_b)
                    if sec:
                        current_section = sec
                    page_sections[page_num] = current_section
                    for b in raw_b:
                        if len(b) >= 5:
                            all_blocks.append((b[0], b[1], b[2], b[3], b[4], page_num))

                blocks_mon    = [b for b in all_blocks if page_sections[b[5]] == "MON"]
                blocks_no_des = [b for b in all_blocks if page_sections[b[5]] == "NO_DESAB"]
                blocks_no_com = [b for b in all_blocks if page_sections[b[5]] == "NO_COM"]

                e1 = _parse_mon_2026(blocks_mon, mes, anio)
                e2 = _parse_compact_section_2026(blocks_no_des, mes, anio, "NO_DESAB")
                e3 = _parse_compact_section_2026(blocks_no_com, mes, anio, "NO_COM")

                raw = []
                for entries, default_estado in [(e1, None), (e2, "NO_DESABASTECIDO"), (e3, "NO_COMERCIALIZADO")]:
                    for num, e in sorted(entries.items()):
                        sec = e.pop("_section", "MON")
                        e.pop("_page", None); e.pop("_y", None)
                        if not e["estado"]:
                            if sec == "NO_DESAB": e["estado"] = "NO_DESABASTECIDO"
                            elif sec == "NO_COM": e["estado"] = "NO_COMERCIALIZADO"
                        raw.append(_finalize_entry(e))
                doc.close()
            else:
                raw = _parse_2025(doc, mes, anio)
                doc.close()
        else:
            raw = _parse_2025(doc, mes, anio)
            doc.close()

    # Post-processing: limpiar y descartar entradas malformadas
    result = []
    for e in raw:
        if _limpiar_entrada(e):
            result.append(e)
        else:
            import logging as _log
            _log.getLogger(__name__).debug(
                "Entrada descartada (malformada): %s",
                (e.get("principio_activo") or "")[:80],
            )
    return result


# ---------------------------------------------------------------------------
# Inferencia de mes/año desde contenido del PDF
# ---------------------------------------------------------------------------

_MESES_MAP_PARSER = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

def inferir_mes_anio_desde_pdf(pdf_path: str | Path) -> tuple[int, int] | None:
    """
    Lee el encabezado del PDF para extraer mes y año del listado INVIMA.
    Busca el año (202x) y nombre de mes en español en las primeras ~2000 chars.
    Retorna (mes, anio) o None si no puede inferirlos.
    """
    pdf_path = Path(pdf_path)
    try:
        doc = fitz.open(str(pdf_path))
        header_text = ""
        for page_num in range(min(2, len(doc))):
            header_text += doc[page_num].get_text()
            if len(header_text) > 2000:
                break
        doc.close()
    except Exception:
        return None

    # Buscar año en los primeros 2000 caracteres del texto
    header_lower = header_text[:2000].lower()
    year_m = re.search(r"\b(202[0-9])\b", header_lower)
    if not year_m:
        return None
    anio = int(year_m.group(1))

    # Buscar nombre de mes cerca del año (ventana ±200 chars alrededor del año)
    y_start = max(0, year_m.start() - 200)
    y_end   = min(len(header_lower), year_m.end() + 200)
    window  = header_lower[y_start:y_end]

    for mes_str, mes_num in sorted(_MESES_MAP_PARSER.items(), key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(mes_str) + r"\b", window):
            return mes_num, anio

    # Fallback: buscar mes en todo el header sin restricción de ventana
    for mes_str, mes_num in sorted(_MESES_MAP_PARSER.items(), key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(mes_str) + r"\b", header_lower):
            return mes_num, anio

    return None


# ---------------------------------------------------------------------------
# CLI para pruebas rápidas
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, json
    from collections import Counter

    if len(sys.argv) < 4:
        print("Uso: python invima_parser.py <pdf_path> <mes> <anio>")
        sys.exit(1)

    path, mes, anio = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    results = parsear_pdf(path, mes, anio)
    print(f"Total entradas: {len(results)}")
    estados = Counter(r["estado"] for r in results)
    for k, v in sorted(estados.items(), key=lambda x: -(x[1] or 0)):
        print(f"  {k}: {v}")
    print()
    # Mostrar primeras 5
    for r in results[:5]:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print()
