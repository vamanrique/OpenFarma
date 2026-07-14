"""
invima_scraper.py — Descarga PDFs nuevos del portal INVIMA y los inserta en DB.

Flujo:
  1. Fetch HTML de la página de desabastecimientos INVIMA
  2. Extraer todos los enlaces a PDFs de listados de abastecimiento
  3. Para cada PDF encontrado:
     a. Descargarlo a un directorio temporal
     b. Leer su contenido para inferir mes/año (no desde URL/filename)
     c. Saltarlo si ese mes/año ya está en la DB
     d. Insertar en DB si es nuevo
  4. Retornar resumen: cuántos PDFs nuevos, cuántos registros insertados
"""
from __future__ import annotations

import re
import sys
import time
import logging
import sqlite3
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ── Constantes ─────────────────────────────────────────────────────────────────
INVIMA_BASE  = "https://www.invima.gov.co"
INVIMA_PAGE  = (
    "https://www.invima.gov.co/productos-vigilados/"
    "medicamentos-y-productos-biologicos/desabastecimientos"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Palabras clave que deben aparecer en la URL o texto del enlace PDF
KEYWORDS_POSITIVOS = {
    "abastecimiento", "desabastecimiento", "desabastecidos",
    "listado", "seguimiento", "medicamentos",
}
KEYWORDS_NEGATIVOS = {
    "circular", "resolucion", "comunicado",
    "instructivo", "guia",
}


# ── Parser HTML minimalista para extraer enlaces ───────────────────────────────
class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict] = []   # [{url, text}]
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._in_anchor = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href:
                self._current_href = href
                self._current_text = []
                self._in_anchor = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_anchor:
            self.links.append({
                "url": self._current_href or "",
                "text": " ".join(self._current_text).strip(),
            })
            self._in_anchor = False
            self._current_href = None
            self._current_text = []

    def handle_data(self, data):
        if self._in_anchor:
            self._current_text.append(data.strip())


# ── Lógica principal ───────────────────────────────────────────────────────────

def _es_pdf_listado(url: str, text: str) -> bool:
    """Determina si un enlace es un PDF de listado de abastecimiento."""
    url_lower  = url.lower()
    text_lower = text.lower()
    combined   = url_lower + " " + text_lower

    if ".pdf" not in url_lower:
        return False

    if any(kw in combined for kw in KEYWORDS_NEGATIVOS):
        return False

    if any(kw in combined for kw in KEYWORDS_POSITIVOS):
        return True

    return False


def scrape_urls_invima(timeout: int = 20) -> list[dict]:
    """
    Descarga la página INVIMA y extrae URLs de PDFs de listados de abastecimiento.
    Retorna lista de [{url, filename}] — sin mes/anio (se infiere del PDF).
    """
    try:
        import httpx
    except ImportError:
        import urllib.request as _req
        class _FakeHttpx:
            class Client:
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def get(self, url, headers=None, follow_redirects=True, timeout=20):
                    class R:
                        def __init__(s):
                            req = _req.Request(url, headers=headers or {})
                            with _req.urlopen(req, timeout=timeout) as resp:
                                s.text = resp.read().decode("utf-8", errors="replace")
                                s.status_code = resp.status
                        def raise_for_status(s): pass
                    return R()
        httpx = _FakeHttpx()

    logger.info("Fetching %s ...", INVIMA_PAGE)
    try:
        with httpx.Client() as client:
            resp = client.get(
                INVIMA_PAGE,
                headers=HEADERS,
                follow_redirects=True,
                timeout=timeout,
            )
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.error("Error descargando página INVIMA: %s", exc)
        return []

    parser = _LinkExtractor()
    parser.feed(html)

    results: list[dict] = []
    seen_urls: set[str] = set()

    for link in parser.links:
        url  = link["url"].strip()
        text = link["text"]

        if not url or url in seen_urls:
            continue

        # Normalizar URL relativa → absoluta
        if url.startswith("/"):
            url = INVIMA_BASE + url
        elif not url.startswith("http"):
            url = urljoin(INVIMA_PAGE, url)

        if not _es_pdf_listado(url, text):
            continue

        seen_urls.add(url)
        filename = urlparse(url).path.split("/")[-1]
        results.append({"url": url, "filename": filename})
        logger.info("  Enlace PDF: %s", filename)

    logger.info("Total PDFs encontrados en página: %d", len(results))
    return results


def meses_en_db(db_path: Path) -> set[tuple[int, int]]:
    """Retorna el conjunto de (mes, anio) ya presentes en invima_seguimiento."""
    if not db_path.exists():
        return set()
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT DISTINCT mes, anio FROM invima_seguimiento"
        ).fetchall()
        conn.close()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def descargar_pdf(url: str, dest_dir: Path, timeout: int = 60) -> Path | None:
    """Descarga un PDF a dest_dir. Retorna la ruta local o None si falla."""
    try:
        import httpx
        filename = urlparse(url).path.split("/")[-1] or "invima.pdf"
        dest = dest_dir / filename
        with httpx.Client() as client:
            with client.stream("GET", url, headers=HEADERS,
                               follow_redirects=True, timeout=timeout) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)
        logger.info("  Descargado: %s (%.1f KB)", filename, dest.stat().st_size / 1024)
        return dest
    except Exception as exc:
        logger.error("  Error descargando %s: %s", url, exc)
        return None


def insertar_desde_pdf(
    pdf_path: Path, mes: int, anio: int, db_path: Path
) -> tuple[int, int]:
    """Parsea el PDF e inserta en DB. Retorna (insertados, actualizados)."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from etl.invima_parser import parsear_pdf

    entradas = parsear_pdf(pdf_path, mes, anio)
    if not entradas:
        logger.warning("  PDF sin entradas parseadas: %s", pdf_path.name)
        return 0, 0

    conn = sqlite3.connect(str(db_path))
    insertados = actualizados = 0
    for e in entradas:
        try:
            cur = conn.execute("""
                INSERT INTO invima_seguimiento
                    (mes, anio, numero_entrada, nombre_medicamento, principio_activo,
                     forma, concentracion, atc, estado, causas, fecha_inicio, fecha_ultimo,
                     total_titulares, disponibilidad_total_umd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mes, anio, principio_activo, forma, concentracion) DO UPDATE SET
                    nombre_medicamento      = excluded.nombre_medicamento,
                    numero_entrada          = excluded.numero_entrada,
                    atc                     = excluded.atc,
                    estado                  = excluded.estado,
                    causas                  = excluded.causas,
                    fecha_inicio            = excluded.fecha_inicio,
                    fecha_ultimo            = excluded.fecha_ultimo,
                    total_titulares         = excluded.total_titulares,
                    disponibilidad_total_umd= excluded.disponibilidad_total_umd
            """, (
                e["mes"], e["anio"], e["numero_entrada"],
                e["nombre_medicamento"], e["principio_activo"],
                e["forma"], e["concentracion"],
                e["atc"], e["estado"], e["causas"],
                e["fecha_inicio"], e["fecha_ultimo"],
                e["total_titulares"], e["disponibilidad_total_umd"],
            ))
            if cur.rowcount == 1 and cur.lastrowid:
                insertados += 1
            else:
                actualizados += 1
        except sqlite3.Error as exc:
            logger.error("  DB error: %s", exc)
    conn.commit()
    conn.close()

    logger.info("  %s: %d insertados, %d actualizados", pdf_path.name, insertados, actualizados)
    return insertados, actualizados


def verificar_y_actualizar(
    db_path: Path,
    temp_dir: Path | None = None,
    solo_anio: int | None = None,
) -> dict:
    """
    Pipeline completo: scrape → descargar PDFs → leer contenido → insertar si nuevo.

    El mes/año se infiere del contenido del PDF descargado, no del URL ni del filename.

    Args:
        db_path:   ruta a openfarma.db
        temp_dir:  directorio donde guardar PDFs descargados (None = tempfile)
        solo_anio: si se especifica, solo procesar PDFs de ese año

    Returns:
        {
            "pdfs_encontrados": int,
            "pdfs_procesados": int,
            "pdfs_saltados": int,
            "registros_insertados": int,
            "registros_actualizados": int,
            "errores": int,
            "meses_nuevos": [(mes, anio), ...],
        }
    """
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from etl.invima_parser import inferir_mes_anio_desde_pdf

    resultado = {
        "pdfs_encontrados": 0,
        "pdfs_procesados": 0,
        "pdfs_saltados": 0,
        "registros_insertados": 0,
        "registros_actualizados": 0,
        "errores": 0,
        "meses_nuevos": [],
    }

    # 1. Obtener URLs disponibles
    pdfs_web = scrape_urls_invima()
    resultado["pdfs_encontrados"] = len(pdfs_web)
    if not pdfs_web:
        logger.warning("No se encontraron PDFs en la página INVIMA.")
        return resultado

    # 2. Meses ya presentes en DB
    ya_procesados = meses_en_db(db_path)
    logger.info("Meses ya en DB: %s", sorted(ya_procesados))

    # 3. Preparar directorio de trabajo
    use_temp = temp_dir is None
    work_dir = Path(tempfile.mkdtemp(prefix="invima_")) if use_temp else temp_dir
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        for pdf_info in pdfs_web:
            logger.info("Descargando %s ...", pdf_info["filename"])
            pdf_path = descargar_pdf(pdf_info["url"], work_dir)
            if pdf_path is None:
                resultado["errores"] += 1
                continue

            time.sleep(1)  # cortesía con el servidor INVIMA

            # 4. Leer el PDF para determinar mes/año (fuente de verdad: contenido del PDF)
            mes_anio = inferir_mes_anio_desde_pdf(pdf_path)
            if mes_anio is None:
                logger.warning(
                    "  No se pudo inferir mes/año desde el contenido de %s — descartando",
                    pdf_path.name,
                )
                resultado["errores"] += 1
                if use_temp:
                    pdf_path.unlink(missing_ok=True)
                continue

            mes, anio = mes_anio
            logger.info("  Mes/año detectado desde PDF: %d/%d", mes, anio)

            # 5. Filtro por año opcional
            if solo_anio and anio != solo_anio:
                logger.info("  Saltando %d/%d (solo_anio=%d)", mes, anio, solo_anio)
                resultado["pdfs_saltados"] += 1
                if use_temp:
                    pdf_path.unlink(missing_ok=True)
                continue

            # 6. Saltar si ya está en DB
            if (mes, anio) in ya_procesados:
                logger.info("  Ya en DB: %d/%d — saltando", mes, anio)
                resultado["pdfs_saltados"] += 1
                if use_temp:
                    pdf_path.unlink(missing_ok=True)
                continue

            # 7. Insertar
            ins, act = insertar_desde_pdf(pdf_path, mes, anio, db_path)
            resultado["pdfs_procesados"] += 1
            resultado["registros_insertados"] += ins
            resultado["registros_actualizados"] += act
            resultado["meses_nuevos"].append((mes, anio))
            ya_procesados.add((mes, anio))  # evitar reprocesar si la URL aparece duplicada

            if use_temp:
                pdf_path.unlink(missing_ok=True)

    finally:
        if use_temp:
            try:
                work_dir.rmdir()
            except Exception:
                pass

    return resultado


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Scraper INVIMA desabastecimiento")
    parser.add_argument("--db", type=Path,
                        default=Path(__file__).parent.parent / "openfarma.db",
                        help="Ruta a openfarma.db")
    parser.add_argument("--anio", type=int, default=None,
                        help="Filtrar solo PDFs de este año (ej: 2026)")
    parser.add_argument("--check-only", action="store_true",
                        help="Solo verificar sin descargar (muestra URLs encontradas)")
    args = parser.parse_args()

    if args.check_only:
        pdfs = scrape_urls_invima()
        ya   = meses_en_db(args.db)
        print(f"PDFs disponibles en la página: {len(pdfs)}")
        print(f"Meses ya en DB: {sorted(ya)}")
        for p in pdfs:
            print(f"  {p['filename']}  — {p['url']}")
        sys.exit(0)

    res = verificar_y_actualizar(args.db, solo_anio=args.anio)
    print(f"\nResultado:")
    print(f"  PDFs encontrados    : {res['pdfs_encontrados']}")
    print(f"  PDFs procesados     : {res['pdfs_procesados']}")
    print(f"  PDFs saltados       : {res['pdfs_saltados']}")
    print(f"  Registros insertados: {res['registros_insertados']}")
    print(f"  Registros actlz.    : {res['registros_actualizados']}")
    print(f"  Errores             : {res['errores']}")
    if res["meses_nuevos"]:
        print(f"  Meses nuevos        : {res['meses_nuevos']}")
