"""
fix_auditoria_conc.py — Auditoría y corrección de concentracion_norm en grupos_equivalencia.

Correcciones aplicadas:
  A) OFTALMICO % → mg/mL (regla del proyecto: OFTALMICO siempre mg/mL)
  B) INHALADO gases/anestésicos → SIN_CONCENTRACION; per-vial nebulizables → mg/mL
  C) LIQUIDO_ORAL mg/NmL → mg/mL (convertir dosis/5mL, etc.)
  D) LIQUIDO_ORAL g/100mL → mg/mL y mg/100mL → mg/mL
  E) LIQUIDO_ORAL per-sachet (mg por sobre sin /mL) → SIN_CONCENTRACION
  F) LIQUIDO_ORAL mEq/millones/% variables → SIN_CONCENTRACION
  G) TOPICO mg/mL → %
  H) Fusionar grupos duplicados (mismo dci+via+conc)
  I) Correcciones puntuales manuales
"""
import sqlite3, sys, re, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"

# ── A. OFTALMICO % → mg/mL ───────────────────────────────────────────────────
# Regla: 1% = 10 mg/mL. Grupos mixtos (UI+%) → SIN_CONCENTRACION
OFTALMICO_SIN = {2645, 2803}  # DEXAMETASONA+NEOMICINA+POLIMIXINA (UI/g mixto), K+Na 5% electrolito

# ── B. INHALADO → SIN_CONCENTRACION ─────────────────────────────────────────
INHALADO_SIN = {
    2896, 2898, 2899, 2900, 2903, 2904, 2905,  # OXIGENO varios %
    2928,  # SEVOFLURANO 100%
    2942,  # ISOFLURANO 100%
    2943,  # DESFLURANO 100%
    3368,  # OXIDO NITROSO 99%
    3405, 3406,  # HELIO||OXIGENO mezclas
    3563,  # OXIDO NITROSO||OXIGENO 50% v/v
    3521,  # OXIDO NITRICO 800 PPM
    2307,  # METOXIFLURANO 2997 mg (inhalador Penthrox — dosis total)
    2239,  # ACETILCISTEINA 300 mg nebulizable — reconstitución variable
    1726,  # COLISTINA 150 mg — polvo, reconstitución variable
}
# Fijos conocidos (per-vial nebulizables)
INHALADO_FIX = {
    462:  "1 mg/mL",   # DORNASA ALFA: 2.5mg/2.5mL ampoule
    1455: "60 mg/mL",  # TOBRAMICINA TOBI: 300mg/5mL ampoule
}

# ── E. LIQUIDO_ORAL per-sachet → SIN_CONCENTRACION ──────────────────────────
# Productos donde la "concentración" es la dosis total por sobre/comprimido efervescente,
# no una concentración por mL. Se identifican porque tienen mg sin denominador /mL.
LIQUIDO_SACHET_SIN = {
    # Condroitina/Glucosamina sachets
    747, 754, 951, 1002, 1220, 1383,
    # Calcio + VitD sachets
    826, 830,
    # ORS / electrolitos per-sachet
    1089, 2547, 2910,
    # Combinaciones frías per-sachet
    3, 1346, 1784, 1787, 1788, 2302,
    # Antidiarreicos/laxantes por sobre
    1795, 2018, 2745, 2746,
    # Mucolíticos effervescentes por sobre
    2810, 2811,
    # Vitaminas por sobre
    2815,
    # Antiparasitarios / antibióticos por sobre
    3129, 3140,
    # Laxantes por sobre
    3159,
    # Combinaciones frías por sobre
    3268, 3269, 3270, 3381,
    # Omeprazol per granulado (10mg)
    3331,
    # Dextrosa per-bolsa (24.8g)
    3373,
    # Hierro por sobre
    3402,
    # Desloratadina||Fenilefrina per-sachet
    3409,
    # Vitamina D3 per drop dose
    3422,
    # PEG 3350 polvo
    3444,
    # Saccharomyces boulardii per sachet
    3467,
    # Diosmectita por sobre
    2997,
}

# ── F. Unidades no convertibles → SIN_CONCENTRACION ─────────────────────────
LIQUIDO_MEQ_SIN = {
    # mEq ORS / electrolitos
    3449, 3454, 3460, 3466, 3472, 3492, 3493, 3509, 3511, 3655, 3659,
    # Citrato potasio+sodio 45g/100mL: es contenido de sachet, no concentración/mL
    3462,
    # Bacillus Clausii millones
    3176,
    # CLORURO DE POTASIO inyectable mEq
    3149,
    # Diálisis peritoneal LIQUIDO_ORAL (clasificación incorrecta, concentración % variable)
    2734, 2735, 2736,
    # DEXTROSA||POTASIO ORS
    3655,
}

# ── G. TOPICO mg/mL → % ──────────────────────────────────────────────────────
TOPICO_FIX = {
    3070: "0.025%",      # MATRICARIA: 0.25 mg/mL → 0.025%
    3377: "0.4% + 0.4%", # POLIETILENGLICOL||PROPILENGLICOL: 4+4 mg/mL → 0.4%+0.4%
}

# ── I. Correcciones puntuales ────────────────────────────────────────────────
PUNTUALES = {
    # LIQUIDO_ORAL Bromhexina||Guaiacol: valores en mg/100mL son incorrectos
    # la presentación real es bromhexina 4mg/5mL = 0.8mg/mL; guaiacol 100mg/5mL = 20mg/mL
    3565: "0.8 mg/mL + 20 mg/mL",
    3566: "1.6 mg/mL + 40 mg/mL",
    # CLORURO DE POTASIO INYECTABLE en mEq/mL → convertir: 2mEq/mL = 149.1mg/mL ≈ SIN_CONCENTRACION
    2961: "SIN_CONCENTRACION",
    # INHALADO Oximetazolina 5mg/mL — en realidad es nasal spray, pero mg/mL es correcto para nasal
    # No tocar (985)
    # LIQUIDO_ORAL ALGINATO||BICARBONATO — ya en la lista LIQUIDO_MGXML convertir
    # INYECTABLE INSULINA GLARGINA||LIXISENATIDA — "g/mL" en el valor es mcg/mL, OK como mcg
}

# ── Regex helpers ────────────────────────────────────────────────────────────

def pct_to_mgml(conc_str: str) -> str:
    """Convert each X% component to X*10 mg/mL. Handles '+' separated combos."""
    parts = [p.strip() for p in conc_str.split('+')]
    out = []
    for p in parts:
        m = re.match(r'^([\d.]+)\s*%$', p)
        if m:
            val = float(m.group(1)) * 10
            # Format nicely
            if val == int(val):
                out.append(f"{int(val)} mg/mL")
            else:
                out.append(f"{round(val, 4)} mg/mL")
        else:
            out.append(p)  # keep as-is (e.g. UI/g part)
    return ' + '.join(out)


def convert_per_nml(conc_str: str) -> str | None:
    """
    Convert 'X mg/5mL + Y mg/5mL' → 'X/5 mg/mL + Y/5 mg/mL'.
    Also handles g/100mL → mg/mL (×10) and mg/100mL → mg/mL (÷100).
    Returns None if cannot parse cleanly.
    """
    parts = [p.strip() for p in conc_str.split('+')]
    out = []
    for p in parts:
        # mg/NmL
        m = re.match(r'^([\d.]+)\s*mg\s*/\s*(\d+)\s*mL$', p, re.I)
        if m:
            val = float(m.group(1)) / float(m.group(2))
            val = round(val, 4)
            out.append(f"{val:g} mg/mL")
            continue
        # g/100mL
        m = re.match(r'^([\d.]+)\s*g\s*/\s*100\s*mL$', p, re.I)
        if m:
            val = float(m.group(1)) * 10
            val = round(val, 4)
            out.append(f"{val:g} mg/mL")
            continue
        # mg/100mL
        m = re.match(r'^([\d.]+)\s*mg\s*/\s*100\s*mL$', p, re.I)
        if m:
            val = float(m.group(1)) / 100
            val = round(val, 6)
            out.append(f"{val:g} mg/mL")
            continue
        # UI/NmL
        m = re.match(r'^([\d.]+)\s*UI\s*/\s*(\d+)\s*mL$', p, re.I)
        if m:
            val = float(m.group(1)) / float(m.group(2))
            val = round(val, 4)
            out.append(f"{val:g} UI/mL")
            continue
        # millones/5mL
        m = re.match(r'^([\d.]+)\s*millones\s*/\s*(\d+)\s*mL$', p, re.I)
        if m:
            # Keep as SIN — biological count unit
            return None
        # Already /mL or no conversion needed
        out.append(p)
    result = ' + '.join(out)
    # If nothing changed, return None to signal no fix needed
    if result == conc_str:
        return None
    return result


def is_per_sachet(conc_str: str) -> bool:
    """
    True if the concentration looks like a per-dose amount (mg without /mL).
    Excludes valid: %, mg/mL, UI, mcg/dosis, /mL, mEq.
    """
    if not conc_str or conc_str == 'SIN_CONCENTRACION':
        return False
    if any(u in conc_str for u in ['/mL', '%', 'mcg/dosis', 'mg/dosis', 'mEq', 'PPM', 'v/v']):
        return False
    # Has 'mg' or 'UI' or 'g' alone
    if re.search(r'\bmg\b', conc_str):
        return True
    if re.search(r'\bUI\b', conc_str) and '/mL' not in conc_str:
        return True
    return False


def merge_groups(con, keep_id: int, delete_id: int):
    """Merge cum_ids from delete_id into keep_id, then delete."""
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (delete_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP MERGE] id={keep_id} o id={delete_id} no existe")
        return

    keep_ids = json.loads(keep[0]) if keep[0] else []
    rem_ids  = json.loads(rem[0])  if rem[0]  else []
    merged = list(dict.fromkeys(keep_ids + rem_ids))
    cur.execute(
        "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
        (json.dumps(merged), len(merged), keep_id)
    )
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (delete_id,))
    print(f"  [MERGE] id={delete_id} -> id={keep_id} ({keep[1]}+{rem[1]}={len(merged)} productos)")


def apply(cur, gid: int, new_conc: str, old_conc: str, tag: str):
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{old_conc}' -> '{new_conc}'")


def main(dry_run: bool = False):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    stats = {k: 0 for k in ['A_oft_pct', 'B_inh_sin', 'B_inh_fix', 'C_liq_nml',
                              'D_liq_g100', 'E_sachet', 'F_meq', 'G_top_mgml',
                              'H_merge', 'I_puntual']}

    # ── A. OFTALMICO % → mg/mL ───────────────────────────────────────────────
    print("\n=== A. OFTALMICO % → mg/mL ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='OFTALMICO' AND concentracion_norm != 'SIN_CONCENTRACION'")
    for gid, dci, conc in cur.fetchall():
        if conc is None:
            continue
        if '%' in conc and 'mg/mL' not in conc:
            if gid in OFTALMICO_SIN:
                if not dry_run:
                    apply(cur, gid, 'SIN_CONCENTRACION', conc, 'A_SIN')
                else:
                    print(f"  [DRY A_SIN] id={gid}: '{conc}' -> SIN_CONCENTRACION")
            else:
                new_conc = pct_to_mgml(conc)
                if new_conc != conc:
                    if not dry_run:
                        apply(cur, gid, new_conc, conc, 'A_PCT->MG/ML')
                    else:
                        print(f"  [DRY A] id={gid}: '{conc}' -> '{new_conc}'")
                    stats['A_oft_pct'] += 1

    # ── B. INHALADO ───────────────────────────────────────────────────────────
    print("\n=== B. INHALADO ===")
    for gid in INHALADO_SIN:
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != 'SIN_CONCENTRACION':
            if not dry_run:
                apply(cur, gid, 'SIN_CONCENTRACION', row[0], 'B_SIN')
            else:
                print(f"  [DRY B_SIN] id={gid}: '{row[0]}' -> SIN_CONCENTRACION")
            stats['B_inh_sin'] += 1

    for gid, new_conc in INHALADO_FIX.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != new_conc:
            if not dry_run:
                apply(cur, gid, new_conc, row[0], 'B_FIX')
            else:
                print(f"  [DRY B_FIX] id={gid}: '{row[0]}' -> '{new_conc}'")
            stats['B_inh_fix'] += 1

    # ── C. LIQUIDO_ORAL mg/NmL → mg/mL ──────────────────────────────────────
    print("\n=== C. LIQUIDO_ORAL mg/NmL → mg/mL ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='LIQUIDO_ORAL' AND concentracion_norm != 'SIN_CONCENTRACION'")
    for gid, dci, conc in cur.fetchall():
        if conc is None:
            continue
        if gid in LIQUIDO_SACHET_SIN or gid in LIQUIDO_MEQ_SIN or gid in PUNTUALES:
            continue  # handled in E/F/I
        # Has /NmL (N >= 2): /5mL, /10mL, /100mL etc.
        needs_conv = bool(re.search(r'/\s*(?:[2-9]|\d{2,})\s*mL', conc, re.I)) or \
                     bool(re.search(r'g\s*/\s*100\s*mL', conc, re.I))
        if needs_conv:
            new_conc = convert_per_nml(conc)
            if new_conc and new_conc != conc:
                if not dry_run:
                    apply(cur, gid, new_conc, conc, 'C_NML->ML')
                else:
                    print(f"  [DRY C] id={gid} {dci[:40]}: '{conc}' -> '{new_conc}'")
                stats['C_liq_nml'] += 1

    # ── D. LIQUIDO_ORAL mg/100mL → mg/mL ────────────────────────────────────
    print("\n=== D. LIQUIDO_ORAL /100mL ===")
    cur.execute("SELECT id, dci_key, concentracion_norm FROM grupos_equivalencia WHERE grupo_via='LIQUIDO_ORAL' AND concentracion_norm LIKE '%/100mL%'")
    for gid, dci, conc in cur.fetchall():
        if gid in LIQUIDO_SACHET_SIN or gid in LIQUIDO_MEQ_SIN or gid in PUNTUALES:
            continue
        new_conc = convert_per_nml(conc)
        if new_conc and new_conc != conc:
            if not dry_run:
                apply(cur, gid, new_conc, conc, 'D_100ML->ML')
            else:
                print(f"  [DRY D] id={gid} {dci[:40]}: '{conc}' -> '{new_conc}'")
            stats['D_liq_g100'] += 1

    # ── E. Per-sachet → SIN_CONCENTRACION ───────────────────────────────────
    print("\n=== E. Per-sachet LIQUIDO_ORAL → SIN_CONCENTRACION ===")
    for gid in LIQUIDO_SACHET_SIN:
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != 'SIN_CONCENTRACION':
            if not dry_run:
                apply(cur, gid, 'SIN_CONCENTRACION', row[0], 'E_SACHET')
            else:
                print(f"  [DRY E] id={gid}: '{row[0]}' -> SIN_CONCENTRACION")
            stats['E_sachet'] += 1

    # ── F. mEq/millones → SIN_CONCENTRACION ──────────────────────────────────
    print("\n=== F. mEq/millones → SIN_CONCENTRACION ===")
    for gid in LIQUIDO_MEQ_SIN:
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != 'SIN_CONCENTRACION':
            if not dry_run:
                apply(cur, gid, 'SIN_CONCENTRACION', row[0], 'F_MEQ')
            else:
                print(f"  [DRY F] id={gid}: '{row[0]}' -> SIN_CONCENTRACION")
            stats['F_meq'] += 1

    # ── G. TOPICO mg/mL → % ──────────────────────────────────────────────────
    print("\n=== G. TOPICO mg/mL → % ===")
    for gid, new_conc in TOPICO_FIX.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != new_conc:
            if not dry_run:
                apply(cur, gid, new_conc, row[0], 'G_TOP_MGM->PCT')
            else:
                print(f"  [DRY G] id={gid}: '{row[0]}' -> '{new_conc}'")
            stats['G_top_mgml'] += 1

    # ── H. Fusionar duplicados ────────────────────────────────────────────────
    print("\n=== H. Fusionar grupos duplicados ===")
    if not dry_run:
        # keep lower id, delete higher id
        merge_groups(con, 3124, 3125)   # BETAMETASONA||CALCIPOTRIOL TOPICO
        merge_groups(con, 3025, 3026)   # BISMUTO SUBSALICILATO LIQUIDO_ORAL
        merge_groups(con, 2625, 3193)   # CIPROFLOXACINO||DEXAMETASONA OTICO
        merge_groups(con, 98,   3815)   # HIDROCORTISONA||LIDOCAINA RECTAL
        stats['H_merge'] = 4
    else:
        print("  [DRY H] Fusionar: (3124<-3125), (3025<-3026), (2625<-3193), (98<-3815)")

    # ── I. Puntuales ─────────────────────────────────────────────────────────
    print("\n=== I. Correcciones puntuales ===")
    for gid, new_conc in PUNTUALES.items():
        cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
        row = cur.fetchone()
        if row and row[0] != new_conc:
            if not dry_run:
                apply(cur, gid, new_conc, row[0], 'I_PUNTUAL')
            else:
                print(f"  [DRY I] id={gid}: '{row[0]}' -> '{new_conc}'")
            stats['I_puntual'] += 1

    if not dry_run:
        con.commit()

    # ── Resumen ───────────────────────────────────────────────────────────────
    print("\n=== RESUMEN ===")
    total = sum(stats.values())
    for k, v in stats.items():
        if v:
            print(f"  {k}: {v}")
    print(f"  TOTAL cambios: {total}")

    if not dry_run:
        cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
        sin = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
        tot = cur.fetchone()[0]
        print(f"\nEstado DB: {tot} grupos | {sin} SIN_CONCENTRACION ({100*sin/tot:.1f}%)")

    con.close()


if __name__ == "__main__":
    dry = '--dry-run' in sys.argv
    if dry:
        print("=== DRY RUN — no se escribe nada ===")
    main(dry_run=dry)
