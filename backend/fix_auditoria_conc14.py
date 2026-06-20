"""
fix_auditoria_conc14.py — Decimocuarta ronda de auditoría.

Correcciones — Multi-componente con concentración incompleta o sumada:
  A) INHALADO/LÍQUIDO ORAL — ETL omitió o sumó segundo componente:
     - id=438  FENOTEROL||IPRATROPIO INHALADO: "0.5 mg/mL" -> "0.5 mg/mL + 0.25 mg/mL"
     - id=3437 AMBROXOL||SALBUTAMOL LIQUIDO_ORAL: "3.4 mg/mL" -> "3 mg/mL + 0.4 mg/mL" (ETL sumó)
     - id=3190 BROMHEXINA||GUAIFENESINA LIQUIDO_ORAL: "0.4 mg/mL" -> "0.4 mg/mL + 10 mg/mL"
     - id=3251 ACETILCISTEINA||GUAIACOLATO DE GLICERILO: "20 mg/mL" -> "20 mg/mL + 20 mg/mL"
     - id=3691 ACETILCISTEINA||GUAIFENESINA: "20 mg/mL" -> "20 mg/mL + 20 mg/mL"
     - id=2947 CETIRIZINA||CLEMBUTEROL||DEXTROMETORFANO: "0.36 mg/mL" -> "0.36 mg/mL + 0.001 mg/mL + 2 mg/mL"
     - id=2946 CETIRIZINA||CLENBUTEROL||DEXTROMETORFANO: "4.4 mg/mL" -> "0.36 mg/mL + 0.002 mg/mL + 4 mg/mL"
  B) OFTALMICO — ETL sumó concentraciones o dejó sólo la mayor:
     - id=3291 FENILEFRINA||PREDNISOLONA: "11.2 mg/mL" -> "1.2 mg/mL + 10 mg/mL" (1.2+10=11.2, ETL sumó)
     - id=3680 LOTEPREDNOL||TOBRAMICINA: "5 mg/mL" -> "5 mg/mL + 3 mg/mL"
     - id=3352 CONDROITINA SULFATO DE SODIO||HIALURONATO DE SODIO: "1.8 mg/mL" -> "1.8 mg/mL + 1 mg/mL"
  C) INYECTABLE:
     - id=766  EPINEFRINA||MEPIVACAINA: "20 mg/mL" -> "0.01 mg/mL + 20 mg/mL"
  D) INSULINA DEGLUDEC||LIRAGLUTIDA id=2685: "100 UI/mL" -> "100 UI/mL + 3.6 mg/mL"
     - Xultophy 100/3.6: degludec 100 UI/mL + liraglutida 3.6 mg/mL
  E) CLEMBUTEROL DCI typo -> CLENBUTEROL en id=2947 (dci_key + cum_normalizado)
  F) Post-fix auto-merge duplicados
"""
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "farmavigia.db"


def merge_into(con, keep_id: int, del_id: int) -> int:
    cur = con.cursor()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos FROM grupos_equivalencia WHERE id=?", (del_id,))
    rem = cur.fetchone()
    if not keep or not rem:
        print(f"  [SKIP merge] {del_id}->{keep_id}: missing")
        return 0
    merged = list(dict.fromkeys(
        json.loads(keep[0] or '[]') + json.loads(rem[0] or '[]')
    ))
    cur.execute("UPDATE grupos_equivalencia SET cum_ids=?, n_productos=? WHERE id=?",
                (json.dumps(merged), len(merged), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (del_id,))
    print(f"  [MERGE] {del_id}->{keep_id}: total={len(merged)}")
    return 1


def fix_conc(cur, gid: int, new_conc: str, tag: str) -> int:
    cur.execute("SELECT concentracion_norm FROM grupos_equivalencia WHERE id=?", (gid,))
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] id={gid} no existe")
        return 0
    if row[0] == new_conc:
        print(f"  [OK ya] id={gid}")
        return 0
    cur.execute("UPDATE grupos_equivalencia SET concentracion_norm=? WHERE id=?", (new_conc, gid))
    print(f"  [{tag}] id={gid}: '{row[0]}' -> '{new_conc}'")
    return 1


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    n = {k: 0 for k in ['A', 'B', 'C', 'D', 'E', 'merge']}

    # -- A. Inhalado / Líquido oral: segundo componente faltante o sumado ----------
    print("\n=== A. INHALADO/LIQUIDO_ORAL multi-componente ===")
    # Berodual (fenoterol 0.5 + ipratropio 0.25) F<I alphabetical
    n['A'] += fix_conc(cur, 438, "0.5 mg/mL + 0.25 mg/mL", "A_fenoterol_ipratropio")
    # Tos-Xol: ETL sumó 3.0+0.4=3.4; componentes: AMBROXOL=3, SALBUTAMOL=0.4 A<S
    n['A'] += fix_conc(cur, 3437, "3 mg/mL + 0.4 mg/mL", "A_ambroxol_salbutamol_sum")
    # Broncodex: ETL usó sólo BROMHEXINA=0.4; GUAIFENESINA=10 B<G
    n['A'] += fix_conc(cur, 3190, "0.4 mg/mL + 10 mg/mL", "A_bromhexina_guaifenesina")
    # Flemalis: ACETILCISTEINA=20 + GUAIACOLATO DE GLICERILO=20 A<G
    n['A'] += fix_conc(cur, 3251, "20 mg/mL + 20 mg/mL", "A_acetilcisteina_guaiacolato")
    # Luckov/Flexvi: ACETILCISTEINA=20 + GUAIFENESINA=20 A<G
    n['A'] += fix_conc(cur, 3691, "20 mg/mL + 20 mg/mL", "A_acetilcisteina_guaifenesina")
    # Broncochem F Niños: CETIRIZINA=0.36 + CLEMBUTEROL=0.001 + DEXTROMETORFANO=2.0
    # (Nota: CLEMBUTEROL typo se corrige en paso E)
    n['A'] += fix_conc(cur, 2947, "0.36 mg/mL + 0.001 mg/mL + 2 mg/mL", "A_cetiri_clenbu_dextro_ninos")
    # Broncochem F Adultos: CETIRIZINA=0.36 + CLENBUTEROL=0.002 + DEXTROMETORFANO=4.0
    # ETL sumó: 0.36+0.002+4.0≈4.4
    n['A'] += fix_conc(cur, 2946, "0.36 mg/mL + 0.002 mg/mL + 4 mg/mL", "A_cetiri_clenbu_dextro_adultos_sum")

    # -- B. OFTALMICO: concentración sumada o componente faltante ------------------
    print("\n=== B. OFTALMICO multi-componente ===")
    # Cortioftal-F: FENILEFRINA=1.2 + PREDNISOLONA=10 => ETL sumó 11.2 F<P
    n['B'] += fix_conc(cur, 3291, "1.2 mg/mL + 10 mg/mL", "B_fenilefrina_prednisolona_sum")
    # Lotemicin/Zylet: LOTEPREDNOL=5 + TOBRAMICINA=3 L<T
    n['B'] += fix_conc(cur, 3680, "5 mg/mL + 3 mg/mL", "B_loteprednol_tobramicina")
    # Humylub: CONDROITINA SULFATO DE SODIO=1.8 + HIALURONATO=1.0 C<H
    n['B'] += fix_conc(cur, 3352, "1.8 mg/mL + 1 mg/mL", "B_condroitina_hialuronato")

    # -- C. INYECTABLE: Odontocaina anestésico dental ----------------------------
    print("\n=== C. INYECTABLE: EPINEFRINA||MEPIVACAINA ===")
    # Odontocaina 2%: EPINEFRINA=0.01 + MEPIVACAINA=20 (1:100000 epinefrina) E<M
    n['C'] += fix_conc(cur, 766, "0.01 mg/mL + 20 mg/mL", "C_epinefrina_mepivacaina")

    # -- D. INSULINA DEGLUDEC||LIRAGLUTIDA id=2685 --------------------------------
    print("\n=== D. INSULINA DEGLUDEC||LIRAGLUTIDA id=2685 ===")
    # Xultophy 100/3.6: degludec 100 UI/mL + liraglutida 3.6 mg/mL (I<L alphabetical)
    n['D'] += fix_conc(cur, 2685, "100 UI/mL + 3.6 mg/mL", "D_xultophy_degludec_liraglutida")

    # -- E. CLEMBUTEROL DCI typo: id=2947 -----------------------------------------
    print("\n=== E. CLEMBUTEROL typo -> CLENBUTEROL ===")
    cur.execute("SELECT dci_key FROM grupos_equivalencia WHERE id=2947")
    row = cur.fetchone()
    if row and 'CLEMBUTEROL' in (row[0] or ''):
        new_dci = row[0].replace('CLEMBUTEROL', 'CLENBUTEROL')
        cur.execute("UPDATE grupos_equivalencia SET dci_key=? WHERE id=2947", (new_dci,))
        print(f"  [E] id=2947: dci '{row[0]}' -> '{new_dci}'")
        n['E'] += 1
    # Sync cum_normalizado principios_dci
    cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=2947")
    g = cur.fetchone()
    if g:
        cids = json.loads(g[0] or '[]')
        updated = 0
        for cid in cids:
            exp, consec = cid.split('-')
            cur.execute("SELECT principios_dci FROM cum_normalizado WHERE expediente_cum=? AND consecutivo_cum=?", (exp, consec))
            p = cur.fetchone()
            if p and p[0]:
                pdci = json.loads(p[0])
                new_pdci = ["CLENBUTEROL" if d == "CLEMBUTEROL" else d for d in pdci]
                if new_pdci != pdci:
                    cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                                (json.dumps(new_pdci), exp, consec))
                    updated += 1
        print(f"  [E] cum_normalizado: {updated} productos CLEMBUTEROL->CLENBUTEROL")
    # Also fix any stray CLEMBUTEROL in cum_normalizado globally
    cur.execute("""
        SELECT expediente_cum, consecutivo_cum, principios_dci
        FROM cum_normalizado WHERE principios_dci LIKE '%CLEMBUTEROL%'
    """)
    rows = cur.fetchall()
    extra = 0
    for exp, consec, pdci_json in rows:
        pdci = json.loads(pdci_json)
        new_pdci = ["CLENBUTEROL" if d == "CLEMBUTEROL" else d for d in pdci]
        if new_pdci != pdci:
            cur.execute("UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                        (json.dumps(new_pdci), exp, consec))
            extra += 1
    if extra:
        print(f"  [E] cum_normalizado global: {extra} adicionales CLEMBUTEROL->CLENBUTEROL")

    # -- F. Post-fix auto-merge duplicados ----------------------------------------
    print("\n=== F. Post-fix auto-merge ===")
    cur.execute("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as cnt,
               GROUP_CONCAT(id || ':' || n_productos ORDER BY n_productos DESC)
        FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING cnt > 1
    """)
    for dci, via, conc, cnt, ids_str in cur.fetchall():
        pairs = [(int(x.split(':')[0]), int(x.split(':')[1])) for x in ids_str.split(',')]
        keep_id = pairs[0][0]
        for del_id, _ in pairs[1:]:
            n['merge'] += merge_into(con, keep_id, del_id)

    # -- Fix n_productos -----------------------------------------------------------
    cur.execute("""
        UPDATE grupos_equivalencia
        SET n_productos = (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
        WHERE n_productos != (LENGTH(cum_ids) - LENGTH(REPLACE(cum_ids, ',', '')) + 1)
    """)

    con.commit()

    # -- Resumen -------------------------------------------------------------------
    print("\n=== RESUMEN ===")
    for k, v in n.items():
        if v:
            print(f"  {k}: {v}")

    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grupos_equivalencia WHERE concentracion_norm='SIN_CONCENTRACION'")
    sin = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM grupos_equivalencia
        GROUP BY dci_key, grupo_via, concentracion_norm HAVING COUNT(*) > 1
    """)
    dups = len(cur.fetchall())
    print(f"\nDB: {total} grupos | {sin} SIN_CONCENTRACION | {dups} duplicados")
    con.close()


if __name__ == "__main__":
    main()
