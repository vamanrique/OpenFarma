#!/bin/bash
set -e

DATA_DB="/data/farmavigia.db"
BUNDLE_DB="/app/backend/farmavigia.db"

# Siempre copiar el bundled DB al volumen para que cada deploy tenga datos frescos.
# El bundled DB en git es la fuente de verdad — incluye INVIMA, CUM, modelo ML, etc.
if [ -f "$BUNDLE_DB" ]; then
  echo "Actualizando base de datos desde bundle ($(du -sh "$BUNDLE_DB" | cut -f1))..."
  cp "$BUNDLE_DB" "$DATA_DB"
  echo "OK: $DATA_DB actualizado."
else
  echo "WARN: bundle DB no encontrado en $BUNDLE_DB"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
