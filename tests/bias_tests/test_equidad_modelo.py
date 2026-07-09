"""
Pruebas de equidad: verifica que el modelo no clasifica sistemáticamente
medicamentos por grupo ATC o tipo de fórmula sin señal real.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


def test_modelo_cargable():
    """El modelo puede ser cargado desde el archivo pkl."""
    try:
        from app.ml.modelo import cargar_modelo
        artefacto = cargar_modelo()
        assert artefacto is not None
        assert "modelo" in artefacto
        assert "metricas" in artefacto
        assert "features" in artefacto
    except FileNotFoundError:
        pytest.skip("modelo_rf.pkl no disponible en este entorno")


def test_sin_sesgo_por_atc_grupo():
    """
    Medicamentos sin historial INVIMA y con igual estructura de mercado
    deben recibir scores similares sin importar su grupo ATC.

    Verifica que grupo_atc_enc no domina el score cuando las features
    de historial INVIMA son neutras.
    """
    try:
        from app.ml.modelo import cargar_modelo
        import numpy as np
        artefacto = cargar_modelo()
        modelo = artefacto["modelo"]
    except (FileNotFoundError, ImportError):
        pytest.skip("modelo_rf.pkl no disponible en este entorno")

    # Construir dos filas idénticas salvo en grupo_atc_enc
    # Features: [tasa_inac, num_comp, tiene_alt, tipo_formula_num, es_combinado,
    #            monopolio, grupo_atc_enc, num_pres,
    #            busquedas_norm, reportes_norm,
    #            invima_sev_actual, invima_sev_t3_avg, invima_meses_mon,
    #            invima_peor_sev_hist, invima_tendencia]
    base = [0.05, 5, 1, 1, 0, 0, 0, 3, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0]

    scores = []
    for atc_group in range(0, 26, 5):  # A, F, K, P, U
        fila = base.copy()
        fila[6] = atc_group
        prob = modelo.predict_proba([fila])[0][1]
        scores.append(prob)

    # La varianza de los scores solo por grupo ATC (sin señal INVIMA) debe ser pequeña
    varianza = float(max(scores) - min(scores))
    assert varianza < 0.15, (
        f"El score varía {varianza:.3f} solo por grupo ATC (sin señal INVIMA). "
        f"Posible sesgo estructural. Scores: {[f'{s:.3f}' for s in scores]}"
    )
