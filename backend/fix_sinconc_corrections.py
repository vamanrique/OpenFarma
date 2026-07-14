"""
Correcciones post-DeepSeek: arregla concentraciones incorrectas o mal formateadas.

Cambios:
  A) Revertir a SIN_CONCENTRACION (datos incompletos / mal interpretados)
  B) Corregir valores incorrectos
  C) Reformatear unidades no estándar (g/100mL → mg/mL)
"""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "openfarma.db"

# ── A. Revertir a SIN_CONCENTRACION ─────────────────────────────────────────
REVERT = {
    2981: "999.7 mg/g",           # Magnesia Guillot Polvo — 'mg/g' no tiene sentido para un polvo oral
    3488: "1.188 g + 0.006 g",    # Pedialyte ORS — dosis por sobre, no concentración/mL
    3214: None,                   # Prenavit multivitamin — unidades mixtas (UI+mg+mcg) inconciliables
    3158: "0.44 g + 0.44 g + 0.44 g",  # Bilaxan Polvo phytotherapy — por sobre
    351:  "2.2 g",                # Sanidex Polvo topico — polvo por sobre
    3153: "36.45% + 36.45%",      # Aluminio||Calcio topico — interpretación incorrecta de polvo
    3583: "5.2 mg",               # Nexobrid Bromelaina — unidades enzimáticas, no mg/g topico
    3641: "100 g/100 g",          # Polietilenglicol polvo — polvo sin dilución definida
    2769: None,                   # Solución de irrigación oftálmica (electrolitos variables)
    3595: "0.054% + 0.054% + 0.054%",  # Dermotrizol — DeepSeek calculó % incorrectos
    3059: "111.3 mg/100mL + 55.3 mg/100mL",  # Hemocyton Elixir — solo 2 de 6 componentes
    3227: "1 g/100mL",            # Kaoxitura — solo pectina (Caolin faltante)
    3400: "2 g/100mL",            # Fluturan — solo ibuprofeno (faltan desloratadina+fenilefrina)
    2829: "66 mg/mL",             # Espaflat — solo simeticona (papaverina faltante)
    3221: "50 mg/mL + 5 g/100 mL",  # Pyralvex — unidades inconsistentes entre componentes
    3307: "1 million unit/100 g + 0.1 g/100 g",  # OQ-Plus — polimixina B en UI no estándar
    3306: "500 UI/g + 0.1 g/100 g + 10000 UI/g", # Altraciene-A — unidades mixtas
}

# ── B. Correcciones de valor ─────────────────────────────────────────────────
CORRECTIONS = {
    # Clavulin Junior 12H: 400mg amox + 57mg clav por 5mL → dividir a mg/mL
    3802: "80 mg/mL + 11.4 mg/mL",
    # Milpax Plus: 0.633g/100mL + 2.39g/100mL → mg/mL
    2912: "6.33 mg/mL + 23.9 mg/mL",
    # T-P Ofteno: fenilefrina 2.5% (25mg/mL) + tropicamida 0.5% (5mg/mL)
    3264: "25 mg/mL + 5 mg/mL",
    # Opdualag: nivolumab 12mg/mL + relatlimab 4mg/mL
    3693: "12 mg/mL + 4 mg/mL",
}

def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n_rev = n_fix = 0

    # Aplicar reversiones
    for gid, expected in REVERT.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row is None:
            print(f"  [SKIP] id={gid} — no existe en DB")
            continue
        actual = row[0]
        # Si la DB tiene el valor "malo" esperado, revertir; si ya es SIN_CONCENTRACION, skip
        if actual == "SIN_CONCENTRACION":
            print(f"  [OK ya] id={gid} ya es SIN_CONCENTRACION")
            continue
        if expected is not None and actual != expected:
            print(f"  [WARN] id={gid} tiene '{actual}' (esperaba '{expected}') — revirtiendo igual")
        print(f"  [REVERT] id={gid} '{actual}' -> SIN_CONCENTRACION")
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm='SIN_CONCENTRACION' WHERE id=?", (gid,))
        n_rev += 1

    # Aplicar correcciones
    for gid, new_conc in CORRECTIONS.items():
        cur.execute("SELECT dci_key, concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row is None:
            print(f"  [SKIP] id={gid} — no existe")
            continue
        dci_key, actual = row
        if actual == new_conc:
            print(f"  [OK ya] id={gid} ya tiene '{new_conc}'")
            continue
        print(f"  [FIX] id={gid} {dci_key[:40]} '{actual}' -> '{new_conc}'")
        cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
        n_fix += 1

    con.commit()
    print(f"\nListo: {n_rev} revertidos a SIN_CONCENTRACION, {n_fix} corregidos")

    # Estadísticas finales
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    print(f"Estado DB: {total} grupos total | {sin} SIN_CONCENTRACION ({100*sin/total:.1f}%)")
    con.close()

if __name__ == "__main__":
    main()
