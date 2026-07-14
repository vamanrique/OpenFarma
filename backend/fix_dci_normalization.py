"""
Migración: normaliza dci_key en grupos_equivalencia y principios_dci en cum_normalizado.
Corrige variantes -ina/-ino de fluoroquinolonas, eritropoyetinas, y otros sinónimos.
"""
import sqlite3
import json
import sys
from datetime import datetime

DB_PATH = "openfarma.db"

# Mapa de renombrado: old_dci -> new_dci (para componentes individuales)
DCI_RENAMES: dict[str, str] = {
    # Fluoroquinolonas (-ina -> -ino según INN español oficial)
    "CIPROFLOXACINA":   "CIPROFLOXACINO",
    "LEVOFLOXACINA":    "LEVOFLOXACINO",
    "MOXIFLOXACINA":    "MOXIFLOXACINO",
    "NORFLOXACINA":     "NORFLOXACINO",
    "GATIFLOXACINA":    "GATIFLOXACINO",
    "OFLOXACINA":       "OFLOXACINO",
    # Eritropoyetinas
    "EPOETIN ALFA":                          "EPOETINA ALFA",
    "ERITROPOYETINA ALFA":                   "EPOETINA ALFA",
    "ERITROPOYETINA RECOMBINANTE HUMANA":    "ERITROPOYETINA HUMANA RECOMBINANTE",
    "METOXIPOLIETILENGLICOL EPOETINA-BETA":  "METOXIPOLIETILENGLICOL-EPOETINA BETA",
    # Inmunusupresores
    "MICOFENOLATO DE MOFETILO":  "MICOFENOLATO MOFETILO",
    "MICOFENOLATO DE SODIO":     "MICOFENOLATO SODICO",
    # Laxantes
    "PICOSULFATO SODICO":        "PICOSULFATO DE SODIO",
    # Analgésicos
    "METAMIZOL SODICO":          "METAMIZOL",
    # Antivíricos - INN español
    "ACYCLOVIR":       "ACICLOVIR",
    "VALACYCLOVIR":    "VALACICLOVIR",
    # Antihistamínicos
    "CETIRIZINE":      "CETIRIZINA",
    "LORATADINE":      "LORATADINA",
    "DESLORATADINE":   "DESLORATADINA",
    "FEXOFENADINE":    "FEXOFENADINA",
    # Estatinas
    "ATORVASTATIN":    "ATORVASTATINA",
    "SIMVASTATIN":     "SIMVASTATINA",
    "ROSUVASTATIN":    "ROSUVASTATINA",
    # IECAs/ARAs
    "FUROSEMIDE":      "FUROSEMIDA",
    "HYDROCHLOROTHIAZIDE": "HIDROCLOROTIAZIDA",
    # Otros
    "WARFARIN":        "WARFARINA",
    "METFORMIN":       "METFORMINA",
    "GLIBENCLAMIDE":   "GLIBENCLAMIDA",
}


def normalizar_dci_componente(dci: str) -> str:
    """Aplica DCI_RENAMES a un único componente DCI."""
    return DCI_RENAMES.get(dci.strip(), dci.strip())


def normalizar_dci_key(dci_key: str) -> str:
    """Re-normaliza un dci_key (puede contener || para compuestos)."""
    partes = [p.strip() for p in dci_key.split("||")]
    partes_norm = [normalizar_dci_componente(p) for p in partes]
    return "||".join(sorted(partes_norm))


def normalizar_principios_list(principios_json: str) -> tuple[str, bool]:
    """
    Toma un JSON list de principios, normaliza cada elemento.
    Devuelve (nuevo_json, cambio_realizado).
    """
    try:
        lista = json.loads(principios_json)
    except (json.JSONDecodeError, TypeError):
        return principios_json, False

    nueva_lista = [normalizar_dci_componente(p) for p in lista]
    # dci_key usa orden alfabético
    nueva_lista_sorted = sorted(nueva_lista)
    original_sorted = sorted(lista)
    cambio = nueva_lista_sorted != original_sorted

    # Preservar el orden original pero con nombres normalizados
    return json.dumps(nueva_lista, ensure_ascii=False), cambio


def merge_grupos(conn: sqlite3.Connection, keep_id: int, drop_id: int) -> None:
    """Fusiona drop_id en keep_id: combina cum_ids, suma n_productos, elimina drop_id."""
    cur = conn.cursor()
    cur.execute("SELECT cum_ids, n_productos, revisado_ia, notas FROM grupos_equivalencia WHERE id=?", (keep_id,))
    keep = cur.fetchone()
    cur.execute("SELECT cum_ids, n_productos, revisado_ia, notas FROM grupos_equivalencia WHERE id=?", (drop_id,))
    drop = cur.fetchone()

    if not keep or not drop:
        return

    keep_ids = json.loads(keep[0] or "[]")
    drop_ids = json.loads(drop[0] or "[]")
    merged_ids = list(dict.fromkeys(keep_ids + drop_ids))  # deduplica manteniendo orden

    merged_n = keep[1] + drop[1]
    merged_revisado = keep[2] or drop[2]
    notas_parts = [n for n in [keep[3], drop[3]] if n]
    merged_notas = "; ".join(notas_parts) if notas_parts else None

    cur.execute("""
        UPDATE grupos_equivalencia
        SET cum_ids=?, n_productos=?, revisado_ia=?, notas=?, actualizado_en=?
        WHERE id=?
    """, (json.dumps(merged_ids, ensure_ascii=False), merged_n, merged_revisado, merged_notas,
          datetime.utcnow().isoformat(), keep_id))
    cur.execute("DELETE FROM grupos_equivalencia WHERE id=?", (drop_id,))


def run(dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print(f"{'[DRY RUN] ' if dry_run else ''}Iniciando normalización de DCIs...")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")

    # ─── 1. Actualizar cum_normalizado.principios_dci ─────────────────────────
    print("\n=== [1/3] Actualizando cum_normalizado.principios_dci ===")
    cur.execute("SELECT consecutivo_cum, principios_dci FROM cum_normalizado WHERE principios_dci IS NOT NULL")
    rows = cur.fetchall()

    actualizados_cn = 0
    for row in rows:
        nuevo_json, cambio = normalizar_principios_list(row["principios_dci"])
        if cambio:
            if not dry_run:
                cur.execute(
                    "UPDATE cum_normalizado SET principios_dci=? WHERE consecutivo_cum=?",
                    (nuevo_json, row["consecutivo_cum"])
                )
            actualizados_cn += 1
            if dry_run:
                old = json.loads(row["principios_dci"])
                new = json.loads(nuevo_json)
                print(f"  CUM {row['consecutivo_cum']}: {old} -> {new}")

    print(f"  Registros actualizados en cum_normalizado: {actualizados_cn}")

    # ─── 2. Actualizar grupos_equivalencia.dci_key ────────────────────────────
    print("\n=== [2/3] Actualizando grupos_equivalencia.dci_key ===")
    cur.execute("SELECT id, dci_key, grupo_via, concentracion_norm FROM grupos_equivalencia")
    grupos = cur.fetchall()

    renames_ge = []
    for g in grupos:
        nuevo_key = normalizar_dci_key(g["dci_key"])
        if nuevo_key != g["dci_key"]:
            renames_ge.append((g["id"], g["dci_key"], nuevo_key, g["grupo_via"], g["concentracion_norm"]))

    print(f"  Grupos con dci_key a cambiar: {len(renames_ge)}")
    for gid, old_key, new_key, via, conc in renames_ge:
        if dry_run:
            print(f"  id={gid:5d} [{via:20}] [{str(conc):15}]  {old_key} -> {new_key}")
        else:
            cur.execute("UPDATE grupos_equivalencia SET dci_key=?, actualizado_en=? WHERE id=?",
                        (new_key, datetime.utcnow().isoformat(), gid))

    # ─── 3. Fusionar grupos duplicados ────────────────────────────────────────
    print("\n=== [3/3] Fusionando grupos con mismo (dci_key, grupo_via, concentracion_norm) ===")
    if not dry_run:
        # Recargar después de los renames
        cur.execute("""
            SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as n,
                   MIN(id) as keep_id, GROUP_CONCAT(id) as all_ids
            FROM grupos_equivalencia
            GROUP BY dci_key, grupo_via, concentracion_norm
            HAVING n > 1
        """)
        duplicados = cur.fetchall()
        print(f"  Grupos duplicados a fusionar: {len(duplicados)}")
        grupos_eliminados = 0
        for dup in duplicados:
            all_ids = [int(x) for x in dup["all_ids"].split(",")]
            keep_id = dup["keep_id"]
            drop_ids = [x for x in all_ids if x != keep_id]
            for drop_id in drop_ids:
                merge_grupos(conn, keep_id, drop_id)
                grupos_eliminados += 1
                print(f"  Fusionado id={drop_id} -> id={keep_id} "
                      f"[{dup['dci_key']} | {dup['grupo_via']} | {dup['concentracion_norm']}]")
        print(f"  Grupos eliminados por fusión: {grupos_eliminados}")
    else:
        # En dry_run, simular qué se fusionaría aplicando los renames
        # Construir tabla simulada de los nuevos dci_key
        from collections import defaultdict
        simulated: dict[tuple, list] = defaultdict(list)
        for g in grupos:
            nuevo_key = normalizar_dci_key(g["dci_key"])
            simulated[(nuevo_key, g["grupo_via"], g["concentracion_norm"])].append(g["id"])
        futuros_dup = {k: v for k, v in simulated.items() if len(v) > 1}
        print(f"  Grupos que se fusionarían: {len(futuros_dup)}")
        for (dci, via, conc), ids in futuros_dup.items():
            print(f"  {dci} | {via} | {conc}  ->  ids={ids}")

    if not dry_run:
        conn.commit()
        # Estadísticas finales
        cur.execute("SELECT COUNT(*) FROM grupos_equivalencia")
        total = cur.fetchone()[0]
        print(f"\n✓ Completado. Total grupos restantes: {total}")
    else:
        print(f"\n[DRY RUN] Sin cambios. Total cambios pendientes: {actualizados_cn} en cum_normalizado, "
              f"{len(renames_ge)} dci_key en grupos_equivalencia")

    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
