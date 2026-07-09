"""Prueba de integración: verifica que el JSON del CUM se transforma correctamente."""
import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from etl.transformacion import agrupar_y_transformar


def test_transformacion_monocomponente():
    """Una fila de ibuprofeno oral debe producir un MedicamentoTransformado válido."""
    filas = [{
        "expedientecum": "20176695",
        "consecutivocum": "1",
        "producto": "IBUPROFENO GENFAR 400MG",
        "principioactivo": "IBUPROFENO",
        "estadocum": "Activo",
        "atc": "M01AE01",
        "forma": "TABLETA RECUBIERTA",
        "via": "ORAL",
        "concentracion": "400MG",
        "titular": "GENFAR S.A.",
        "registro": "INVIMA 2017M-0023456",
        "estado": "Vigente",
    }]
    df = pd.DataFrame(filas)
    resultados = agrupar_y_transformar(df)

    assert len(resultados) == 1
    med = resultados[0]
    assert med.cum_id == "20176695-1"
    assert "IBUPROFENO" in (med.principios_dci or [])
    assert med.estado_cum == "Activo"


def test_transformacion_combinado():
    """Dos filas del mismo expediente con principios distintos deben agruparse en un combinado."""
    filas = [
        {
            "expedientecum": "20098000",
            "consecutivocum": "1",
            "producto": "AMOXICILINA + ACIDO CLAVULANICO 500/125MG",
            "principioactivo": "AMOXICILINA",
            "estadocum": "Activo",
            "atc": "J01CR02",
            "forma": "TABLETA RECUBIERTA",
            "via": "ORAL",
            "concentracion": "500MG",
            "titular": "GENFAR S.A.",
            "registro": "INVIMA 2015M-0011111",
            "estado": "Vigente",
        },
        {
            "expedientecum": "20098000",
            "consecutivocum": "1",
            "producto": "AMOXICILINA + ACIDO CLAVULANICO 500/125MG",
            "principioactivo": "ACIDO CLAVULANICO",
            "estadocum": "Activo",
            "atc": "J01CR02",
            "forma": "TABLETA RECUBIERTA",
            "via": "ORAL",
            "concentracion": "125MG",
            "titular": "GENFAR S.A.",
            "registro": "INVIMA 2015M-0011111",
            "estado": "Vigente",
        },
    ]
    df = pd.DataFrame(filas)
    resultados = agrupar_y_transformar(df)

    assert len(resultados) == 1
    med = resultados[0]
    assert med.tipo_formula == "combinado"
    dcis = set(med.principios_dci or [])
    assert "AMOXICILINA" in dcis
    assert "ACIDO CLAVULANICO" in dcis
