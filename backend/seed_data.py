"""Carga datos iniciales: departamentos de Colombia y medicamentos de ejemplo."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
import app.models  # noqa

Base.metadata.create_all(bind=engine)

DEPARTAMENTOS = [
    ("Amazonas", "91", -1.4429, -71.5724),
    ("Antioquia", "05", 7.1986, -75.3412),
    ("Arauca", "81", 6.5477, -71.0054),
    ("Atlántico", "08", 10.6966, -74.8741),
    ("Bolívar", "13", 8.6704, -74.0313),
    ("Boyacá", "15", 5.4545, -73.3620),
    ("Caldas", "17", 5.2983, -75.2479),
    ("Caquetá", "18", 1.6147, -75.6128),
    ("Casanare", "85", 5.7589, -71.5724),
    ("Cauca", "19", 2.5359, -76.6248),
    ("Cesar", "20", 9.8968, -73.7026),
    ("Chocó", "27", 5.6921, -76.6578),
    ("Córdoba", "23", 8.4061, -75.5812),
    ("Cundinamarca", "25", 4.5709, -74.2973),
    ("Guainía", "94", 2.5854, -68.5247),
    ("Guaviare", "95", 2.0413, -72.3417),
    ("Huila", "41", 2.5359, -75.5277),
    ("La Guajira", "44", 11.3548, -72.5205),
    ("Magdalena", "47", 10.4113, -74.4057),
    ("Meta", "50", 3.9960, -73.5484),
    ("Nariño", "52", 1.2136, -77.2811),
    ("Norte de Santander", "54", 7.9463, -72.8988),
    ("Putumayo", "86", 0.4359, -76.6248),
    ("Quindío", "63", 4.5339, -75.6751),
    ("Risaralda", "66", 5.3158, -75.9928),
    ("San Andrés y Providencia", "88", 12.5847, -81.7006),
    ("Santander", "68", 6.6437, -73.6536),
    ("Sucre", "70", 9.0438, -75.0788),
    ("Tolima", "73", 4.0925, -75.1545),
    ("Valle del Cauca", "76", 3.8609, -76.5019),
    ("Vaupés", "97", 0.8554, -70.8122),
    ("Vichada", "99", 4.4234, -69.2875),
    ("Bogotá D.C.", "11", 4.7110, -74.0721),
]

MEDICAMENTOS_EJEMPLO = [
    ("10006696", "ACETAMINOFEN 500MG TABLETAS", "ACETAMINOFEN", "ACETAMINOFÉN", "500 mg", "Tableta", "GENFAR", "2025M-0001", "N02BE01", "Analgésicos y antipiréticos", 450.0, False),
    ("10006697", "IBUPROFENO 400MG TABLETAS", "IBUPROFENO", "IBUPROFENO", "400 mg", "Tableta", "TECNOQUIMICAS", "2025M-0002", "M01AE01", "Antiinflamatorios no esteroideos", 650.0, False),
    ("10006698", "AMOXICILINA 500MG CAPSULAS", "AMOXICILINA", "AMOXICILINA", "500 mg", "Cápsula", "LAFRANCOL", "2025M-0003", "J01CA04", "Antibióticos betalactámicos", 1200.0, True),
    ("10006699", "METFORMINA 850MG TABLETAS", "METFORMINA", "METFORMINA", "850 mg", "Tableta", "NOVARTIS", "2025M-0004", "A10BA02", "Antidiabéticos orales", 980.0, True),
    ("10006700", "ENALAPRIL 10MG TABLETAS", "ENALAPRIL", "ENALAPRIL", "10 mg", "Tableta", "SANOFI", "2025M-0005", "C09AA02", "IECA antihipertensivos", 850.0, True),
    ("10006701", "LOSARTAN 50MG TABLETAS", "LOSARTAN", "LOSARTÁN POTÁSICO", "50 mg", "Tableta", "BAYER", "2025M-0006", "C09CA01", "ARA II antihipertensivos", 1100.0, True),
    ("10006702", "OMEPRAZOL 20MG CAPSULAS", "OMEPRAZOL", "OMEPRAZOL", "20 mg", "Cápsula", "PFIZER", "2025M-0007", "A02BC01", "Inhibidores bomba de protones", 700.0, False),
    ("10006703", "ATORVASTATINA 20MG TABLETAS", "ATORVASTATINA", "ATORVASTATINA CÁLCICA", "20 mg", "Tableta", "PFIZER", "2025M-0008", "C10AA05", "Estatinas hipolipemiantes", 1500.0, True),
    ("10006704", "SALBUTAMOL 100MCG INHALADOR", "SALBUTAMOL", "SALBUTAMOL", "100 mcg/dosis", "Inhalador", "GSK", "2025M-0009", "R03AC02", "Broncodilatadores beta2", 12000.0, True),
    ("10006705", "HIDROCLOROTIAZIDA 25MG TABLETAS", "HIDROCLOROTIAZIDA", "HIDROCLOROTIAZIDA", "25 mg", "Tableta", "MERCK", "2025M-0010", "C03AA03", "Diuréticos tiazídicos", 550.0, True),
]

ALTERNATIVAS_EJEMPLO = [
    (1, 2, "equivalente_terapeutico", "Alternativa para dolor leve-moderado"),
    (2, 1, "equivalente_terapeutico", "Alternativa para fiebre y dolor"),
    (5, 6, "equivalente_terapeutico", "Otro antihipertensivo de primera línea"),
    (6, 5, "equivalente_terapeutico", "IECA como alternativa a ARA II"),
    (5, 10, "equivalente_terapeutico", "Diurético como antihipertensivo alternativo"),
]


def seed():
    db = SessionLocal()
    try:
        from app.models.region import Region
        from app.models.medicamento import Medicamento, Alternativa

        if db.query(Region).count() == 0:
            for nombre, codigo, lat, lon in DEPARTAMENTOS:
                db.add(Region(nombre=nombre, codigo_dane=codigo, latitud=lat, longitud=lon))
            db.commit()
            print(f"OK: {len(DEPARTAMENTOS)} departamentos cargados")

        if db.query(Medicamento).count() == 0:
            for datos in MEDICAMENTOS_EJEMPLO:
                cum, nom_com, nom_gen, principio, conc, forma, lab, reg, atc, grupo, precio, formula = datos
                db.add(Medicamento(
                    cum=cum, nombre_comercial=nom_com, nombre_generico=nom_gen,
                    principio_activo=principio, concentracion=conc, forma_farmaceutica=forma,
                    laboratorio=lab, registro_sanitario=reg, codigo_atc=atc,
                    grupo_terapeutico=grupo, precio_maximo=precio, requiere_formula=formula,
                ))
            db.commit()
            print(f"OK: {len(MEDICAMENTOS_EJEMPLO)} medicamentos de ejemplo cargados")

        if db.query(Alternativa).count() == 0:
            for med_id, alt_id, tipo, obs in ALTERNATIVAS_EJEMPLO:
                db.add(Alternativa(medicamento_id=med_id, alternativa_id=alt_id, tipo=tipo, observaciones=obs))
            db.commit()
            print(f"OK: {len(ALTERNATIVAS_EJEMPLO)} relaciones de alternativas cargadas")

        print("Base de datos lista para usar")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
