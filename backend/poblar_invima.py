"""
Script standalone para poblar la tabla invima_seguimiento en openfarma.db
a partir de los PDFs de seguimiento INVIMA en:
  C:\\Users\\aewal\\Downloads\\Desabastecidos INVIMA\\2025\\
  C:\\Users\\aewal\\Downloads\\Desabastecidos INVIMA\\2026\\
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

# Asegurar que el módulo del parser sea importable
sys.path.insert(0, str(Path(__file__).parent))

from etl.invima_parser import parsear_pdf

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

PDF_BASE = Path(r"C:\Users\aewal\Downloads\Desabastecidos INVIMA")
DB_PATH = Path(r"C:\Users\aewal\farmavigia-concurso\backend\openfarma.db")

# Meses en español → número
MESES_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # abreviaturas / variantes usadas en nombres de archivos
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def inferir_mes_anio(filename: str) -> tuple[int, int] | None:
    """
    Infiere mes y año del nombre del archivo PDF.
    Ejemplos:
      listado_abastecimiento_y_desabastecimiento_medicamentos_enero_de_2025_-_publicado.pdf → (1, 2025)
      LISTADO DE ABASTECIMIENTO MAYO 2026.pdf → (5, 2026)
      LISTADO DE ABASTECIMIENTO Y DESABASTECIMIENTO DE MEDICAMENTOS EN SEGUIMIENTO - ENERO 2026.pdf → (1, 2026)
      LISTADO DE ABASTECIMIENTO Y DESABASTECIMIENTO DE MEDICAMENTOS EN SEGUIMIENTO - DICIEMBRE DE 2025.pdf → (12, 2025)
      LISTADO DE ABASTECIMIENTO Y DESABASTECIMIENTO NOVIEMBRE DE 2025.pdf → (11, 2025)
      LISTADO DE ABASTECIMIENTO Y DESABASTECIMIENTO DE MEDICAMENTOS OCT 2025.pdf → (10, 2025)
      listado_abastecimiento_septiembre_2025_def.pdf → (9, 2025)
    """
    name_lower = filename.lower().replace("_", " ").replace("-", " ")

    # Buscar año (4 dígitos)
    year_match = re.search(r"\b(202[0-9])\b", name_lower)
    if not year_match:
        return None
    anio = int(year_match.group(1))

    # Buscar mes
    for mes_str, mes_num in MESES_MAP.items():
        # Palabra completa
        if re.search(r"\b" + mes_str + r"\b", name_lower):
            return mes_num, anio

    return None


def crear_tabla(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS invima_seguimiento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mes INTEGER NOT NULL,
        anio INTEGER NOT NULL,
        numero_entrada INTEGER,
        nombre_medicamento TEXT,
        principio_activo TEXT,
        forma TEXT,
        concentracion TEXT,
        atc TEXT,
        estado TEXT,
        causas TEXT,
        fecha_inicio TEXT,
        fecha_ultimo TEXT,
        total_titulares INTEGER DEFAULT 0,
        disponibilidad_total_umd INTEGER,
        UNIQUE(mes, anio, principio_activo, forma, concentracion)
    );

    CREATE INDEX IF NOT EXISTS idx_invima_atc
        ON invima_seguimiento(atc, anio, mes);

    CREATE INDEX IF NOT EXISTS idx_invima_estado
        ON invima_seguimiento(estado, anio, mes);

    CREATE INDEX IF NOT EXISTS idx_invima_pa
        ON invima_seguimiento(principio_activo, anio, mes);
    """)
    conn.commit()


def insertar_entradas(conn: sqlite3.Connection, entradas: list[dict]) -> tuple[int, int]:
    """Inserta o actualiza entradas. Retorna (insertados, actualizados)."""
    insertados = 0
    actualizados = 0

    for e in entradas:
        try:
            cur = conn.execute(
                """
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
                """,
                (
                    e["mes"], e["anio"], e["numero_entrada"],
                    e["nombre_medicamento"], e["principio_activo"],
                    e["forma"], e["concentracion"],
                    e["atc"], e["estado"], e["causas"],
                    e["fecha_inicio"], e["fecha_ultimo"],
                    e["total_titulares"], e["disponibilidad_total_umd"],
                ),
            )
            if cur.lastrowid and cur.rowcount == 1:
                insertados += 1
            else:
                actualizados += 1
        except sqlite3.Error as exc:
            print(f"  ERROR insertando {e.get('nombre_medicamento','?')}: {exc}")

    conn.commit()
    return insertados, actualizados


def main() -> None:
    print(f"Base de datos: {DB_PATH}")
    print(f"PDFs base: {PDF_BASE}\n")

    conn = sqlite3.connect(DB_PATH)
    crear_tabla(conn)

    # Recopilar todos los PDFs
    pdfs: list[tuple[Path, int, int]] = []
    for pdf_file in sorted(PDF_BASE.rglob("*.pdf")):
        resultado = inferir_mes_anio(pdf_file.name)
        if resultado is None:
            print(f"  ADVERTENCIA: no se pudo inferir mes/año de: {pdf_file.name}")
            continue
        mes, anio = resultado
        pdfs.append((pdf_file, mes, anio))

    print(f"Total PDFs encontrados: {len(pdfs)}\n")

    total_insertados = 0
    total_actualizados = 0
    total_entradas_parseadas = 0

    for pdf_path, mes, anio in sorted(pdfs, key=lambda x: (x[2], x[1])):
        print(f"Procesando: {pdf_path.name} -> {mes:02d}/{anio}")
        try:
            entradas = parsear_pdf(pdf_path, mes, anio)
            print(f"  Entradas parseadas: {len(entradas)}")

            # Debug: mostrar distribución de estados
            from collections import Counter
            estados = Counter(e.get("estado") or "None" for e in entradas)
            for estado, n in sorted(estados.items()):
                print(f"    {estado}: {n}")

            ins, act = insertar_entradas(conn, entradas)
            print(f"  Insertados: {ins}  Actualizados: {act}")
            total_insertados += ins
            total_actualizados += act
            total_entradas_parseadas += len(entradas)

        except Exception as exc:
            import traceback
            print(f"  ERROR procesando {pdf_path.name}: {exc}")
            traceback.print_exc()

        print()

    conn.close()

    print("=" * 60)
    print(f"Total entradas parseadas:  {total_entradas_parseadas}")
    print(f"Total registros insertados: {total_insertados}")
    print(f"Total registros actualizados: {total_actualizados}")
    print()

    # Verificación: ejecutar queries de validación
    print("=== QUERY DE VERIFICACIÓN 1 ===")
    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row

    rows = conn2.execute("""
        SELECT anio, mes, estado, COUNT(*) as n
        FROM invima_seguimiento
        GROUP BY anio, mes, estado
        ORDER BY anio, mes, estado
    """).fetchall()
    print(f"{'anio':>6}  {'mes':>4}  {'estado':<25}  {'n':>6}")
    print("-" * 50)
    for r in rows:
        print(f"{r['anio']:>6}  {r['mes']:>4}  {r['estado'] or 'NULL':<25}  {r['n']:>6}")

    print()
    print("=== QUERY DE VERIFICACIÓN 2 (2026, mes 5) ===")
    rows2 = conn2.execute("""
        SELECT estado, COUNT(DISTINCT principio_activo) as n_pa
        FROM invima_seguimiento
        WHERE anio=2026 AND mes=5
        GROUP BY estado
    """).fetchall()
    print(f"{'estado':<25}  {'n_pa':>6}")
    print("-" * 35)
    for r in rows2:
        print(f"{r['estado'] or 'NULL':<25}  {r['n_pa']:>6}")

    # Total en DB
    total_db = conn2.execute("SELECT COUNT(*) FROM invima_seguimiento").fetchone()[0]
    print(f"\nTotal registros en invima_seguimiento: {total_db}")
    conn2.close()


if __name__ == "__main__":
    main()
