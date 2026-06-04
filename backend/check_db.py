from app.database import SessionLocal, init_db
import app.models
init_db()
from app.models.medicamento import Medicamento
db = SessionLocal()

total = db.query(Medicamento).count()
with_tipo = db.query(Medicamento).filter(Medicamento.tipo_formula != None).count()
bi = db.query(Medicamento).filter(Medicamento.tipo_formula == "biconjugado").count()
tri = db.query(Medicamento).filter(Medicamento.tipo_formula == "triconjugado").count()
tetra = db.query(Medicamento).filter(Medicamento.tipo_formula == "tetraconjugado").count()
mono = db.query(Medicamento).filter(Medicamento.tipo_formula == "monocomponente").count()
none_ = db.query(Medicamento).filter(Medicamento.tipo_formula == None).count()

print(f"Total: {total}")
print(f"Con tipo_formula: {with_tipo}")
print(f"  monocomponente: {mono}")
print(f"  biconjugado:    {bi}")
print(f"  triconjugado:   {tri}")
print(f"  tetraconjugado: {tetra}")
print(f"  sin tipo:       {none_}")

# Sample with dci
sample = db.query(Medicamento).filter(Medicamento.tipo_formula == "biconjugado").first()
if sample:
    print(f"\nSample biconjugado: {sample.cum} | {sample.nombre_comercial} | dci={sample.principios_dci}")
db.close()
