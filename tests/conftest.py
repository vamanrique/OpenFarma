"""
conftest.py — configuración global de pytest para OpenFarma.

Debe importarse ANTES que cualquier módulo de app/ para que DATABASE_URL
apunte al archivo correcto independientemente del directorio de trabajo.
"""
import os
import pathlib

# Apunta al DB real en backend/ — usa forward slashes para compatibilidad SQLite
_REPO_ROOT = pathlib.Path(__file__).parent.parent
_DB_PATH = (_REPO_ROOT / "backend" / "openfarma.db").as_posix()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-placeholder")
os.environ.setdefault("ENVIRONMENT", "test")
