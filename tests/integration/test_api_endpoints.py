"""
Pruebas de integración: endpoints clave de la API FarmaVigia.

Usa TestClient contra la app real con la DB de backend/farmavigia.db.
Todos los tests son de sólo lectura — no modifican datos.
"""
import sys
import os
import pathlib
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "backend"))

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# /medicamentos/buscar
# ---------------------------------------------------------------------------

def test_buscar_retorna_lista(client):
    """Búsqueda de ibuprofeno devuelve una lista no vacía de medicamentos."""
    resp = client.get("/api/v1/medicamentos/buscar", params={"q": "ibuprofeno", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_buscar_campos_requeridos(client):
    """Cada resultado tiene los campos definidos en MedicamentoLiveRead."""
    resp = client.get("/api/v1/medicamentos/buscar", params={"q": "amoxicilina", "limit": 3})
    assert resp.status_code == 200
    for med in resp.json():
        assert "cum_id" in med
        assert "nombre_comercial" in med
        assert "principios_dci" in med
        assert isinstance(med["principios_dci"], list)


def test_buscar_minimo_2_chars(client):
    """Términos de menos de 2 caracteres deben retornar 422."""
    resp = client.get("/api/v1/medicamentos/buscar", params={"q": "a"})
    assert resp.status_code == 422


def test_buscar_solo_activos_default(client):
    """Por defecto solo_activos=True — ningún resultado debe tener estado_cum inactivo."""
    resp = client.get("/api/v1/medicamentos/buscar", params={"q": "metformina", "limit": 10})
    assert resp.status_code == 200
    for med in resp.json():
        assert (med.get("estado_cum") or "").lower() != "inactivo"


# ---------------------------------------------------------------------------
# /reportes
# ---------------------------------------------------------------------------

def test_reportes_total(client):
    """El endpoint /reportes/total retorna un entero >= 0."""
    resp = client.get("/api/v1/reportes/total")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert isinstance(data["total"], int)
    assert data["total"] >= 0


def test_reportes_dashboard_estructura(client):
    """El dashboard de reportes tiene la estructura correcta."""
    resp = client.get("/api/v1/reportes/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "resumen" in data
    assert "top_reportados" in data
    assert "senales_anticipadas" in data
    resumen = data["resumen"]
    assert "total_reportes_historico" in resumen
    assert "total_reportes_30d" in resumen
    assert "medicamentos_con_spike" in resumen
    assert "senales_anticipadas" in resumen


def test_reportes_recientes(client):
    """El endpoint /reportes/recientes retorna una lista."""
    resp = client.get("/api/v1/reportes/recientes", params={"limit": 5})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# /predicciones
# ---------------------------------------------------------------------------

def test_prediccion_cum_invalido(client):
    """CUM con formato incorrecto retorna 400 o 404."""
    resp = client.get("/api/v1/predicciones/INVALID_FORMAT")
    assert resp.status_code in (400, 404)


def test_prediccion_estructura(client):
    """Si el CUM existe, la predicción tiene estructura válida."""
    # Ibuprofeno Genfar — CUM conocido que existe en cum_normalizado
    resp = client.get("/api/v1/predicciones/20176695-1")
    if resp.status_code == 200:
        data = resp.json()
        assert "cum_id" in data
        assert "probabilidad" in data
        assert "nivel_riesgo" in data
        assert "nivel_num" in data
        assert 0.0 <= data["probabilidad"] <= 1.0
        assert data["nivel_riesgo"] in ("Bajo", "Medio", "Alto", "Crítico")
        assert data["nivel_num"] in (1, 2, 3, 4)
    else:
        # CUM no en DB local: aceptable
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /grupos
# ---------------------------------------------------------------------------

def test_grupos_cum_conocido(client):
    """Los grupos de equivalencia para un CUM conocido retornan estructura válida."""
    resp = client.get("/api/v1/grupos/medicamentos/20176695-1")
    if resp.status_code == 200:
        data = resp.json()
        assert "dci" in data
        assert "mi_grupo" in data or "misma_via" in data
    else:
        assert resp.status_code in (404, 422)
