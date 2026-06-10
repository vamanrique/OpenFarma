"""
Fix accented characters in grupos_equivalencia.dci_key and cum_normalizado.principios_dci.
ETL should strip accents from DCI names but some escaped normalization.
"""
import sqlite3
import json
import unicodedata
import re

DB_PATH = "farmavigia.db"


def strip_accents(s: str) -> str:
    """Remove accents: ÁCIDO → ACIDO, ONDANSETRÓN → ONDANSETRON"""
    nfd = unicodedata.normalize('NFD', s)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def normalize_dci_key(key: str) -> str:
    """Strip accents and rebuild sorted dci_key."""
    parts = [strip_accents(p) for p in key.split('||')]
    return '||'.join(sorted(parts))


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Fix grupos_equivalencia.dci_key
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia WHERE dci_key GLOB '*[ÁÉÍÓÚÑÜ]*'")
    # Note: GLOB is case-sensitive on Windows, but accented chars are above ASCII
    # Use Python filtering instead
    cur.execute("SELECT id, dci_key FROM grupos_equivalencia")
    all_groups = cur.fetchall()

    fixed_groups = 0
    for gid, key in all_groups:
        if key == strip_accents(key):
            continue
        new_key = normalize_dci_key(key)
        print(f'  grupos id={gid:5d}  {key[:60]!r}')
        print(f'           -> {new_key[:60]!r}')
        cur.execute(
            "UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (new_key, gid)
        )
        fixed_groups += 1

    conn.commit()
    print(f"\nFixed {fixed_groups} grupos_equivalencia dci_key values")

    # Fix cum_normalizado.principios_dci
    cur.execute("SELECT expediente_cum, consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci IS NOT NULL")
    cum_rows = cur.fetchall()

    fixed_cum = 0
    for exp, consec, pdci in cum_rows:
        if pdci == strip_accents(pdci):
            continue
        # principios_dci is a JSON array like '["AMOXICILINA", "ÁCIDO CLAVULÁNICO"]'
        try:
            parts = json.loads(pdci)
            new_parts = sorted([strip_accents(p) for p in parts])
            new_pdci = json.dumps(new_parts, ensure_ascii=False)
            # Actually keep original order since principios_dci is not guaranteed sorted
            # but should match dci_key which IS sorted
            # Re-sort to match dci_key convention
            new_pdci = json.dumps(sorted(set(strip_accents(p) for p in parts)), ensure_ascii=False)
        except Exception:
            new_pdci = strip_accents(pdci)

        if new_pdci != pdci:
            cur.execute(
                "UPDATE cum_normalizado SET principios_dci=? WHERE expediente_cum=? AND consecutivo_cum=?",
                (new_pdci, exp, consec)
            )
            fixed_cum += 1

    conn.commit()
    print(f"Fixed {fixed_cum} cum_normalizado principios_dci values")

    # Find and merge resulting duplicates in grupos_equivalencia
    print("\n=== Finding duplicates after accent normalization ===")
    cur.execute("""
        SELECT g1.id, g1.dci_key, g1.concentracion_norm, g1.n_productos,
               g2.id, g2.n_productos
        FROM grupos_equivalencia g1
        JOIN grupos_equivalencia g2
          ON g1.dci_key=g2.dci_key
         AND g1.grupo_via=g2.grupo_via
         AND g1.concentracion_norm=g2.concentracion_norm
         AND g1.id < g2.id
        ORDER BY g1.dci_key, g1.concentracion_norm
    """)
    dupes = cur.fetchall()
    print(f"Found {len(dupes)} duplicate pairs")

    merged = 0
    processed: set[int] = set()
    for g1id, dci_key, conc, n1, g2id, n2 in dupes:
        if g1id in processed or g2id in processed:
            continue
        keep_id, drop_id = (g1id, g2id) if n1 >= n2 else (g2id, g1id)

        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (drop_id,))
        s = cur.fetchone()
        cur.execute("SELECT cum_ids FROM grupos_equivalencia WHERE id=?", (keep_id,))
        t = cur.fetchone()
        if not s or not t:
            continue

        src_ids = json.loads(s[0]) if s[0] else []
        tgt_ids = json.loads(t[0]) if t[0] else []
        union = list(dict.fromkeys(tgt_ids + src_ids))
        added = len(union) - len(tgt_ids)

        print(f"  Merge id={drop_id} -> id={keep_id} +{added}  {conc!r}  {dci_key[:40]!r}")
        cur.execute(
            "UPDATE grupos_equivalencia SET cum_ids=?, n_productos=?, actualizado_en=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(union), len(union), keep_id)
        )
        cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))
        processed.add(g1id)
        processed.add(g2id)
        merged += 1

    conn.commit()
    conn.close()
    print(f"\nMerged {merged} duplicate pairs")
    print("Done.")


if __name__ == "__main__":
    main()
