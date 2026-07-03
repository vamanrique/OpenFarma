#!/bin/bash
set -e

DATA_DB="/data/farmavigia.db"
BUNDLE_DB="/app/backend/farmavigia.db"

if [ ! -f "$BUNDLE_DB" ]; then
  echo "WARN: bundle DB no encontrado en $BUNDLE_DB"
else
  echo "Actualizando base de datos desde bundle ($(du -sh "$BUNDLE_DB" | cut -f1))..."

  python3 - <<'PYEOF'
import sqlite3, shutil, os

DATA_DB   = "/data/farmavigia.db"
BUNDLE_DB = "/app/backend/farmavigia.db"

# Tablas con datos generados por usuarios — deben sobrevivir cada deploy
PRESERVE = ["reportes_no_disponibilidad", "consultas_region"]

saved = {}
if os.path.exists(DATA_DB):
    conn = sqlite3.connect(DATA_DB)
    for tbl in PRESERVE:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
            if rows:
                saved[tbl] = (cols, rows)
                print(f"  Guardando {len(rows)} fila(s) de {tbl}")
        except Exception as e:
            print(f"  {tbl}: {e}")
    conn.close()

shutil.copy(BUNDLE_DB, DATA_DB)
print("  Bundle copiado.")

if saved:
    conn = sqlite3.connect(DATA_DB)
    for tbl, (cols, rows) in saved.items():
        ph = ",".join(["?"] * len(cols))
        try:
            conn.executemany(
                f"INSERT OR IGNORE INTO {tbl} ({','.join(cols)}) VALUES ({ph})",
                rows
            )
            print(f"  Restauradas {len(rows)} fila(s) de {tbl}")
        except Exception as e:
            print(f"  Error restaurando {tbl}: {e}")
    conn.commit()
    conn.close()
    print("OK: datos de usuarios preservados.")
else:
    print("OK: primera vez o sin datos de usuarios previos.")
PYEOF

fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
