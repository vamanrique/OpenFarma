"""
migrations.py — migraciones one-shot que se ejecutan al iniciar la app.

Cada migración es idempotente: detecta si ya fue aplicada antes de actuar.
"""
import logging
from sqlalchemy import text
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _fix_dci_contamination(db) -> int:
    """
    Fase 1 de fix_dci_mismatch: sincroniza principios_dci en cum_normalizado
    usando grupos_equivalencia como fuente de verdad.

    Solo actúa si detecta contaminación masiva (>500 productos con CIPROFLOXACINO
    como único DCI, señal inequívoca de batch contamination).
    """
    import json

    contaminated_count = db.execute(text(
        "SELECT COUNT(*) FROM cum_normalizado "
        "WHERE principios_dci = '[\"CIPROFLOXACINO\"]'"
    )).scalar() or 0

    if contaminated_count < 500:
        return 0  # ya corregido o no contaminado

    logger.warning(
        "DCI contamination detectada: %d productos con CIPROFLOXACINO. "
        "Aplicando fix automático...", contaminated_count
    )

    TIPO_FORMULA = {1: "monocomponente", 2: "biconjugado",
                    3: "triconjugado",   4: "tetraconjugado"}

    groups_rows = db.execute(text(
        "SELECT dci_key, cum_ids FROM grupos_equivalencia"
    )).fetchall()

    fixed = 0
    processed: set[str] = set()

    for dci_key, cum_ids_json in groups_rows:
        try:
            cum_ids = json.loads(cum_ids_json) if cum_ids_json else []
        except Exception:
            continue

        correct_dcis = [d.strip() for d in dci_key.split("||")]
        correct_tipo = TIPO_FORMULA.get(len(correct_dcis), "monocomponente")
        correct_json = json.dumps(correct_dcis, ensure_ascii=False)

        for cum_id in cum_ids:
            if cum_id in processed:
                continue
            processed.add(cum_id)

            parts = cum_id.split("-", 1)
            if len(parts) != 2:
                continue

            db.execute(text(
                "UPDATE cum_normalizado "
                "SET principios_dci = :pdci, tipo_formula = :tf "
                "WHERE expediente_cum = :exp AND consecutivo_cum = :cons "
                "AND principios_dci != :pdci"
            ), {
                "pdci": correct_json,
                "tf": correct_tipo,
                "exp": parts[0],
                "cons": parts[1],
            })
            fixed += 1

    db.commit()
    logger.info("DCI fix completado: %d productos actualizados.", fixed)
    return fixed


def _fix_tipo_formula(db) -> int:
    """
    Normaliza tipo_formula de formato abreviado (MONO/BI/TRI/TETRA/OTRO/NULL)
    al formato canónico (monocomponente/biconjugado/triconjugado/tetraconjugado).

    Idempotente: solo actúa si hay registros con formato incorrecto.
    """
    import json

    bad_count = db.execute(text(
        "SELECT COUNT(*) FROM cum_normalizado "
        "WHERE tipo_formula IN ('MONO','BI','TRI','TETRA','OTRO') "
        "   OR tipo_formula IS NULL"
    )).scalar() or 0

    if bad_count == 0:
        return 0

    logger.info("tipo_formula: %d productos con formato incorrecto, aplicando fix...", bad_count)

    TIPO_MAP = {
        "MONO": "monocomponente", "BI": "biconjugado",
        "TRI": "triconjugado",    "TETRA": "tetraconjugado",
    }
    TIPO_BY_COUNT = {1: "monocomponente", 2: "biconjugado",
                     3: "triconjugado",   4: "tetraconjugado"}

    rows = db.execute(text(
        "SELECT expediente_cum, consecutivo_cum, tipo_formula, principios_dci "
        "FROM cum_normalizado "
        "WHERE tipo_formula IN ('MONO','BI','TRI','TETRA','OTRO') "
        "   OR tipo_formula IS NULL"
    )).fetchall()

    fixed = 0
    for exp, cons, tf, pdci_json in rows:
        nuevo = TIPO_MAP.get(tf or "")
        if nuevo is None:
            try:
                n = len(json.loads(pdci_json or "[]"))
            except Exception:
                n = 1
            nuevo = TIPO_BY_COUNT.get(n, "monocomponente")

        db.execute(text(
            "UPDATE cum_normalizado SET tipo_formula=:tf "
            "WHERE expediente_cum=:exp AND consecutivo_cum=:cons"
        ), {"tf": nuevo, "exp": exp, "cons": cons})
        fixed += 1

    db.commit()
    logger.info("tipo_formula fix completado: %d productos actualizados.", fixed)
    return fixed


def _crear_invima_seguimiento(db) -> bool:
    """Crea la tabla invima_seguimiento e índices si no existen. Idempotente."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS invima_seguimiento (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            mes                    INTEGER NOT NULL,
            anio                   INTEGER NOT NULL,
            numero_entrada         TEXT,
            nombre_medicamento     TEXT,
            principio_activo       TEXT,
            forma                  TEXT,
            concentracion          TEXT,
            atc                    TEXT,
            estado                 TEXT,
            causas                 TEXT,
            fecha_inicio           TEXT,
            fecha_ultimo           TEXT,
            total_titulares        INTEGER,
            disponibilidad_total_umd REAL,
            UNIQUE(mes, anio, principio_activo, forma, concentracion, estado)
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_invima_atc ON invima_seguimiento(atc, anio, mes)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_invima_estado ON invima_seguimiento(estado, anio, mes)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_invima_pa ON invima_seguimiento(principio_activo, anio, mes)"))
    db.commit()
    return True


def _drop_region_fk_from_reportes(db) -> bool:
    """
    SQLite no soporta DROP COLUMN en versiones antiguas, pero sí permite NULL en FKs.
    Hacemos region_id nullable para que los inserts sin ese campo no fallen.
    La columna queda en el schema pero sin FK activa (SQLite no enforza FKs por defecto).
    Idempotente: solo actúa si la columna existe y tiene NOT NULL.
    """
    cols = db.execute(text("PRAGMA table_info(reportes_no_disponibilidad)")).fetchall()
    region_col = next((c for c in cols if c[1] == 'region_id'), None)
    if region_col is None:
        return False  # columna ya no existe
    # SQLite PRAGMA notnull es el índice 3; si notnull=0 ya está nullable
    if region_col[3] == 0:
        return False  # ya es nullable, nada que hacer
    # Recrear tabla sin NOT NULL en region_id (SQLite no tiene ALTER COLUMN)
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS reportes_no_disponibilidad_new (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            cum_id              TEXT,
            nombre_medicamento  TEXT,
            region_id           INTEGER,
            tipo_reporte        TEXT DEFAULT 'sin_stock',
            descripcion         TEXT,
            fecha               DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        INSERT INTO reportes_no_disponibilidad_new
            SELECT id, cum_id, nombre_medicamento, region_id, tipo_reporte, descripcion, fecha
            FROM reportes_no_disponibilidad
    """))
    db.execute(text("DROP TABLE reportes_no_disponibilidad"))
    db.execute(text("ALTER TABLE reportes_no_disponibilidad_new RENAME TO reportes_no_disponibilidad"))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_reportes_cum_id ON reportes_no_disponibilidad(cum_id)"))
    db.commit()
    logger.info("Migración: region_id en reportes_no_disponibilidad → nullable")
    return True


def _crear_busquedas_log(db) -> bool:
    """Crea la tabla busquedas_log si no existe. Idempotente."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS busquedas_log (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            cum_id TEXT NOT NULL,
            fecha  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_busq_cum_fecha ON busquedas_log(cum_id, fecha)"
    ))
    db.commit()
    return True


def run_all():
    """Ejecuta todas las migraciones pendientes al iniciar la app."""
    db = SessionLocal()
    try:
        n = _fix_dci_contamination(db)
        if n:
            logger.info("Migración DCI: %d productos corregidos.", n)
        m = _fix_tipo_formula(db)
        if m:
            logger.info("Migración tipo_formula: %d productos corregidos.", m)
        _crear_invima_seguimiento(db)
        _drop_region_fk_from_reportes(db)
        _crear_busquedas_log(db)
    except Exception as e:
        logger.error("Error en migraciones de startup: %s", e)
        db.rollback()
    finally:
        db.close()
