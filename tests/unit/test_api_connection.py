"""Prueba de conectividad básica a la API Socrata del CUM."""
import pytest
import httpx

SOCRATA_URL = "https://www.datos.gov.co/resource/i7cb-raxc.json"


@pytest.mark.asyncio
async def test_socrata_reachable():
    """Verifica que el servidor de datos.gov.co responde."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SOCRATA_URL, params={"$limit": 1})
    assert resp.status_code == 200, f"Socrata retornó {resp.status_code}"


@pytest.mark.asyncio
async def test_socrata_returns_cum_fields():
    """Verifica que el JSON contiene los campos esperados del CUM."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SOCRATA_URL, params={
            "$where": "upper(producto) like '%IBUPROFENO%' AND estadocum='Activo'",
            "$limit": 1,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0, "No se encontró ibuprofeno en el CUM"
    fila = data[0]
    campos_requeridos = {"expedientecum", "consecutivocum", "producto", "principioactivo", "estadocum"}
    for campo in campos_requeridos:
        assert campo in fila, f"Campo '{campo}' ausente en respuesta Socrata"
