#!/bin/bash
set -e

DATA_DB="/data/farmavigia.db"
BUNDLE_DB="/app/backend/farmavigia.db"

if [ ! -f "$DATA_DB" ]; then
  echo "Primera ejecución: copiando base de datos al volumen..."
  cp "$BUNDLE_DB" "$DATA_DB"
  echo "OK: $(du -sh "$DATA_DB" | cut -f1) copiados a $DATA_DB"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
