"""
Muestra el estado actual del cache de normalizacion LLM.
Uso: python etl/estado_cache.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

def _stats_fuente(conn, where: str = "1=1"):
    q = lambda s: conn.execute(text(f"SELECT {s} FROM cum_normalizado WHERE {where}")).scalar()
    total     = q("COUNT(*)")
    mono      = q("COUNT(*) FILTER (WHERE tipo_formula='MONO')")
    bi        = q("COUNT(*) FILTER (WHERE tipo_formula='BI')")
    tri       = q("COUNT(*) FILTER (WHERE tipo_formula='TRI')")
    tetra     = q("COUNT(*) FILTER (WHERE tipo_formula='TETRA')")
    con_dci   = q("COUNT(*) FILTER (WHERE principios_dci IS NOT NULL)")
    con_dosis = q("COUNT(*) FILTER (WHERE dosis_total_mg IS NOT NULL)")
    con_conc  = q("COUNT(*) FILTER (WHERE concentracion_mg_ml IS NOT NULL)")
    sin_metrica = q("COUNT(*) FILTER (WHERE dosis_total_mg IS NULL AND concentracion_mg_ml IS NULL)")
    ultimo    = q("MAX(procesado_en)")
    return dict(total=total, mono=mono, bi=bi, tri=tri, tetra=tetra,
                con_dci=con_dci, con_dosis=con_dosis, con_conc=con_conc,
                sin_metrica=sin_metrica, ultimo=ultimo)

def _print_stats(label: str, s: dict):
    sep = "-" * 52
    pct = lambda n: f"{n/s['total']*100:.1f}%" if s['total'] else "0%"
    print(f"\n{sep}")
    print(f"  {label}")
    print(sep)
    print(f"  Total registros    : {s['total']:,}")
    print(f"  MONO               : {s['mono']:,} ({pct(s['mono'])})")
    print(f"  BI                 : {s['bi']:,}  ({pct(s['bi'])})")
    print(f"  TRI                : {s['tri']:,}  ({pct(s['tri'])})")
    print(f"  TETRA              : {s['tetra']:,}  ({pct(s['tetra'])})")
    print(sep)
    print(f"  Con DCI            : {s['con_dci']:,} ({pct(s['con_dci'])})")
    print(f"  Con dosis_mg       : {s['con_dosis']:,} ({pct(s['con_dosis'])})")
    print(f"  Con conc_mg_ml     : {s['con_conc']:,} ({pct(s['con_conc'])})")
    print(f"  Sin ninguna metrica: {s['sin_metrica']:,} (UI/topicos - esperado)")
    print(f"  Ultimo procesado   : {s['ultimo']}")
    print(sep)

with engine.connect() as conn:
    total_all  = _stats_fuente(conn)
    activo     = _stats_fuente(conn, "fuente='CUM_ACTIVO' OR fuente IS NULL")
    renovacion = _stats_fuente(conn, "fuente='CUM_RENOVACION'")

_print_stats("Cache CUM_ACTIVO (estadocum=Activo)", activo)
_print_stats("Cache CUM_RENOVACION (en tramite renovacion)", renovacion)
_print_stats("TOTAL COMBINADO", total_all)
print()
