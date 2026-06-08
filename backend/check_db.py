"""Check DB stats using cum_normalizado (replaces old Medicamento-based script)."""
from app.database import SessionLocal, init_db
import app.models

init_db()
from app.models.cum_normalizado import CumNormalizado

db = SessionLocal()
total = db.query(CumNormalizado).count()
mono  = db.query(CumNormalizado).filter(CumNormalizado.tipo_formula == "MONO").count()
bi    = db.query(CumNormalizado).filter(CumNormalizado.tipo_formula == "BI").count()
tri   = db.query(CumNormalizado).filter(CumNormalizado.tipo_formula == "TRI").count()
tetra = db.query(CumNormalizado).filter(CumNormalizado.tipo_formula == "TETRA").count()
activo = db.query(CumNormalizado).filter(CumNormalizado.estado_cum.ilike("activo")).count()

print(f"Total cum_normalizado: {total}")
print(f"  MONO: {mono}  BI: {bi}  TRI: {tri}  TETRA: {tetra}")
print(f"  Activos: {activo}")

sample = db.query(CumNormalizado).filter(CumNormalizado.tipo_formula == "BI").first()
if sample:
    print(f"\nSample BI: {sample.expediente_cum}-{sample.consecutivo_cum} | {sample.nombre_comercial_norm} | dci={sample.principios_dci}")
db.close()
