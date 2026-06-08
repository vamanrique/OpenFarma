"""
fix_grupos_calidad.py
---------------------
Script de corrección de calidad para grupos_equivalencia.

Correcciones:
1. Re-clasifica grupos OTRO/ambiguos con DeepSeek
2. Recalcula concentración para grupos con NULL concentracion_norm
3. Merge de grupos singleton con grupos existentes cuando corresponde
4. Elimina cum_ids duplicados dentro de cada grupo

Uso:
    python fix_grupos_calidad.py [--dry-run]
"""

import os, sys, io, json, argparse, httpx, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import defaultdict, Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia
from construir_grupos import compute_concentracion, CHUNK_SIZE

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

VALID_VIAS = {
    "SOLIDO_ORAL", "SOLIDO_ORAL_LP", "ORAL_DISPERSABLE", "SUBLINGUAL",
    "INYECTABLE", "INHALADO", "NASAL", "OFTALMICO", "OTICO",
    "TOPICO", "VAGINAL", "RECTAL", "TRANSDERMICO", "LIQUIDO_ORAL",
}

# ── DeepSeek helper ───────────────────────────────────────────────────────────

def _call_deepseek(groups_info: list[dict]) -> list[dict]:
    """Ask DeepSeek to determine the correct grupo_via for a list of groups."""
    system = (
        "Eres un farmaceútico colombiano experto en el INVIMA. "
        "Para cada grupo de productos farmacéuticos que tiene grupo_via='OTRO' (sin clasificar), "
        "determina cuál es el grupo_via correcto. "
        "Valores válidos: SOLIDO_ORAL, SOLIDO_ORAL_LP, ORAL_DISPERSABLE, SUBLINGUAL, "
        "INYECTABLE, INHALADO, NASAL, OFTALMICO, OTICO, TOPICO, VAGINAL, RECTAL, "
        "TRANSDERMICO, LIQUIDO_ORAL. "
        "Si es un dispositivo intrauterino (DIU/IUD) usa VAGINAL. "
        "Si es un gas médico o vacuna usa INYECTABLE. "
        "Responde SOLO con JSON válido."
    )
    user = json.dumps({
        "grupos": groups_info,
        "instruccion": (
            "Para cada grupo en 'grupos', devuelve su id y el grupo_via correcto. "
            "Respuesta: {'correcciones': [{'id': <int>, 'grupo_via': <str>, 'razon': <str>}]}"
        )
    }, ensure_ascii=False)

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4096,
            },
        )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    return parsed.get("correcciones", [])


# ── Step 1: Fix OTRO groups ───────────────────────────────────────────────────

def fix_otro_groups(db, dry_run: bool) -> int:
    print("\n=== PASO 1: Corrigiendo grupos OTRO ===")
    otro_groups = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.grupo_via == "OTRO").all()
    if not otro_groups:
        print("  No hay grupos OTRO.")
        return 0

    # Classify rule-based first
    rule_fixed = 0
    need_ai = []

    for g in otro_groups:
        # Get sample product info from DB
        ids = (g.cum_ids or [])[:5]
        vias_found = Counter()
        formas_found = Counter()
        for cid in ids:
            parts = cid.split("-", 1)
            if len(parts) == 2:
                row = db.execute(text(
                    "SELECT forma_normalizada, via_normalizada FROM cum_normalizado "
                    "WHERE expediente_cum=:e AND consecutivo_cum=:c"
                ), {"e": parts[0], "c": parts[1]}).fetchone()
                if row:
                    formas_found[row[0] or ""] += 1
                    try:
                        vias = json.loads(row[1]) if row[1] else []
                        for v in vias:
                            vias_found[v] += 1
                    except Exception:
                        pass

        top_via = vias_found.most_common(1)[0][0] if vias_found else ""
        conc = g.concentracion_norm or ""

        # Rule-based classification
        new_via = None
        if top_via == "TOPICA":
            new_via = "TOPICO"
        elif top_via == "ORAL":
            # Liquid oral: has mL in concentracion_norm
            if re.search(r"/\s*mL|/\s*5\s*mL|mg/mL", conc, re.I):
                new_via = "LIQUIDO_ORAL"
            elif re.search(r"\d+\s*mg\s*\+\s*\d+\s*mg", conc):
                new_via = "SOLIDO_ORAL"  # combination tablet
            elif re.search(r"\d+\s*mg$", conc.strip()):
                new_via = "SOLIDO_ORAL"  # single mg → tablet/capsule likely
            else:
                new_via = "SOLIDO_ORAL"  # default oral → solid

        # Additional rules for via=OTRA
        if not new_via and top_via in ("OTRA", ""):
            dci = (g.dci_key or "").upper()
            # Known ophthalmic DCIs
            OFTALM = {
                "LATANOPROST", "BIMATOPROST", "TRAVOPROST", "TIMOLOL", "BRIMONIDINA",
                "DORZOLAMIDA", "BRINZOLAMIDA", "PILOCARPINA", "EPINASTINA", "KETOTIFENO",
                "OLOPATADINA", "CICLOSPORINA", "RANIBIZUMAB", "BEVACIZUMAB", "AFLIBERCEPT",
                "TRIAMCINOLONA", "DEXAMETASONA", "PREDNISOLONA", "FLUOROMETOLONA",
                "GENTAMICINA", "TOBRAMICINA", "CIPROFLOXACINO", "MOXIFLOXACINO",
                "LEVOFLOXACINO", "AZITROMICINA", "NAFAZOLINA", "OXIMETAZOLINA",
                "EPINEFRINA", "EPINASTINA", "DEXTRAN", "HIALURONATO", "POLIVINILO",
            }
            NASAL_DCIS = {"NAFAZOLINA", "XILOMETAZOLINA", "OXIMETAZOLINA", "BUDESONIDA",
                          "FLUTICASONA", "MOMETASONA", "BECLOMETASONA"}
            VAGINAL_DCIS = {"LEVONORGESTREL"}  # IUDs
            SUBLINGUAL_DCIS = {"BENZOCAINA", "CETILPIRIDINIO", "HEXETIDINA"}

            # Check if any component DCI is in the sets
            dcis_in_key = set(dci.split("||"))
            if dcis_in_key & VAGINAL_DCIS:
                new_via = "VAGINAL"
            elif dcis_in_key & SUBLINGUAL_DCIS:
                new_via = "SUBLINGUAL"
            elif dcis_in_key & NASAL_DCIS and not (dcis_in_key & OFTALM):
                new_via = "NASAL"
            elif (dcis_in_key & OFTALM) or "DIOXIDO DE CARBONO" not in dci:
                # Check for DCI combinations that are exclusively ophthalmic
                oftalm_hits = len(dcis_in_key & OFTALM)
                if oftalm_hits > 0 and "DIOXIDO DE CARBONO" not in dci and "BCG" not in dci:
                    new_via = "OFTALMICO"

        if new_via:
            print(f"  RULE [{g.id}] {g.dci_key[:35]} | {conc[:25]} -> {new_via} (top_via={top_via})")
            if not dry_run:
                g.grupo_via = new_via
            rule_fixed += 1
        else:
            need_ai.append(g)

    print(f"  Rule-fixed: {rule_fixed}, need AI: {len(need_ai)}")

    # AI classification in batches of 8 (smaller to avoid JSON truncation)
    ai_fixed = 0
    BATCH = 8
    for i in range(0, len(need_ai), BATCH):
        batch = need_ai[i:i+BATCH]
        groups_info = []
        for g in batch:
            # Gather more product info for AI context
            ids = (g.cum_ids or [])[:8]
            product_names = []
            vias_list = []
            for cid in ids:
                parts = cid.split("-", 1)
                if len(parts) == 2:
                    row = db.execute(text(
                        "SELECT nombre_comercial_norm, via_normalizada, forma_normalizada "
                        "FROM cum_normalizado WHERE expediente_cum=:e AND consecutivo_cum=:c"
                    ), {"e": parts[0], "c": parts[1]}).fetchone()
                    if row:
                        if row[0]: product_names.append(row[0][:40])
                        try:
                            vias_list.extend(json.loads(row[1]) if row[1] else [])
                        except Exception:
                            pass

            groups_info.append({
                "id": g.id,
                "dci_key": g.dci_key,
                "concentracion_norm": g.concentracion_norm,
                "n_productos": g.n_productos,
                "via_normalizada_productos": list(set(vias_list))[:5],
                "nombres_muestra": product_names[:4],
            })

        try:
            corrections = _call_deepseek(groups_info)
            id_map = {g.id: g for g in batch}
            for c in corrections:
                gid = c.get("id")
                new_via = c.get("grupo_via", "").upper().strip()
                if gid in id_map and new_via in VALID_VIAS:
                    g = id_map[gid]
                    print(f"  AI  [{gid}] {g.dci_key[:35]} | {g.concentracion_norm or '(null)':25} → {new_via} ({c.get('razon','')[:40]})")
                    if not dry_run:
                        g.grupo_via = new_via
                    ai_fixed += 1
                else:
                    print(f"  AI  [{gid}] skipped (via='{new_via}' invalid or group not found)")
        except Exception as exc:
            print(f"  [ERROR] AI batch {i//BATCH+1}: {exc}")

    if not dry_run:
        db.flush()
    total_fixed = rule_fixed + ai_fixed
    print(f"  Total OTRO fixed: {total_fixed} / {len(otro_groups)}")
    return total_fixed


# ── Step 2: Recalculate NULL concentrations ───────────────────────────────────

def fix_null_concentrations(db, dry_run: bool) -> int:
    print("\n=== PASO 2: Recalculando concentraciones NULL ===")
    null_groups = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.concentracion_norm == None
    ).all()
    print(f"  Grupos con NULL concentracion_norm: {len(null_groups)}")

    fixed = 0
    for g in null_groups:
        ids = g.cum_ids or []
        # Try to compute concentration from products
        best_cnorm = None
        best_cval = None
        best_cunit = None

        for cid in ids:
            parts = cid.split("-", 1)
            if len(parts) != 2:
                continue
            cum = db.query(CumNormalizado).filter(
                CumNormalizado.expediente_cum == parts[0],
                CumNormalizado.consecutivo_cum == parts[1],
            ).first()
            if cum:
                cnorm, cval, cunit = compute_concentracion(cum, g.grupo_via)
                if cnorm:
                    best_cnorm = cnorm
                    best_cval = cval
                    best_cunit = cunit
                    break

        if best_cnorm:
            if not dry_run:
                g.concentracion_norm = best_cnorm
                g.concentracion_valor = best_cval
                g.concentracion_unidad = best_cunit
            fixed += 1

    if not dry_run:
        db.flush()
    print(f"  Concentraciones recuperadas: {fixed} / {len(null_groups)}")
    return fixed


# ── Step 3: Merge singletons into compatible groups ───────────────────────────

def fix_singletons(db, dry_run: bool) -> int:
    print("\n=== PASO 3: Fusionando singletons con grupos compatibles ===")
    singletons = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.n_productos == 1
    ).all()
    print(f"  Singletons: {len(singletons)}")

    def _norm(s: str) -> str:
        return re.sub(r"\s+", "", (s or "").lower())

    merged = 0
    for sg in singletons:
        if not sg.concentracion_norm or not sg.concentracion_valor or not sg.concentracion_unidad:
            continue

        is_multi = "+" in (sg.concentracion_norm or "")

        candidates = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.dci_key == sg.dci_key,
            GrupoEquivalencia.grupo_via == sg.grupo_via,
            GrupoEquivalencia.id != sg.id,
            GrupoEquivalencia.concentracion_valor != None,
            GrupoEquivalencia.concentracion_unidad == sg.concentracion_unidad,
        ).all()

        best = None
        for c in candidates:
            if is_multi:
                if _norm(c.concentracion_norm) == _norm(sg.concentracion_norm):
                    best = c
                    break
            else:
                ratio = abs(c.concentracion_valor - sg.concentracion_valor) / max(c.concentracion_valor, sg.concentracion_valor)
                if ratio < 0.005:
                    best = c
                    break

        if best:
            singleton_id = (sg.cum_ids or [None])[0]
            print(f"  MERGE [{sg.id}] {sg.dci_key[:28]} {sg.concentracion_norm} -> [{best.id}] {best.concentracion_norm}")
            if not dry_run:
                if singleton_id and singleton_id not in (best.cum_ids or []):
                    best.cum_ids = (best.cum_ids or []) + [singleton_id]
                    best.n_productos = len(best.cum_ids)
                db.delete(sg)
            merged += 1

    if not dry_run:
        db.flush()
    print(f"  Singletons merged: {merged}")
    return merged


# ── Step 4: Merge groups with NULL conc + same (dci_key, grupo_via) ──────────

def merge_null_conc_duplicates(db, dry_run: bool) -> int:
    print("\n=== PASO 4: Fusionando grupos NULL-concentracion duplicados ===")
    # Find (dci_key, grupo_via) pairs that still have multiple NULL-conc groups
    from sqlalchemy import func
    dupes = db.execute(text("""
        SELECT dci_key, grupo_via, COUNT(*) as n
        FROM grupos_equivalencia
        WHERE concentracion_norm IS NULL
        GROUP BY dci_key, grupo_via
        HAVING COUNT(*) > 1
        ORDER BY n DESC
    """)).fetchall()

    print(f"  (dci_key, grupo_via) pairs with multiple NULL-conc groups: {len(dupes)}")
    merged = 0

    for dci_key, grupo_via, n in dupes:
        groups = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.dci_key == dci_key,
            GrupoEquivalencia.grupo_via == grupo_via,
            GrupoEquivalencia.concentracion_norm == None,
        ).all()

        if len(groups) <= 1:
            continue

        # Merge all into the one with the most products
        groups.sort(key=lambda x: x.n_productos, reverse=True)
        target = groups[0]
        others = groups[1:]

        seen = set(target.cum_ids or [])
        combined = list(target.cum_ids or [])
        for g in others:
            for cid in (g.cum_ids or []):
                if cid not in seen:
                    seen.add(cid)
                    combined.append(cid)

        print(f"  MERGE {n} NULL groups for {dci_key[:35]} {grupo_via} → {len(combined)} products")
        if not dry_run:
            target.cum_ids = combined
            target.n_productos = len(combined)
            target.revisado_ia = any(g.revisado_ia for g in groups)
            for g in others:
                db.delete(g)
        merged += len(others)

    if not dry_run:
        db.flush()
    print(f"  Groups eliminated in NULL-conc merge: {merged}")
    return merged


# ── Step 5: Remove duplicate cum_ids within groups ────────────────────────────

def fix_duplicate_cum_ids(db, dry_run: bool) -> int:
    print("\n=== PASO 5: Eliminando cum_ids duplicados dentro de grupos ===")
    all_groups = db.query(GrupoEquivalencia).all()
    fixed = 0
    for g in all_groups:
        ids = g.cum_ids or []
        unique_ids = list(dict.fromkeys(ids))  # preserves order, removes dupes
        if len(unique_ids) < len(ids):
            if not dry_run:
                g.cum_ids = unique_ids
                g.n_productos = len(unique_ids)
            fixed += 1

    if not dry_run:
        db.flush()
    print(f"  Groups with duplicate cum_ids cleaned: {fixed}")
    return fixed


# ── Step 6: Post-merge: merge groups that now share (dci, via, conc) ─────────

def merge_via_duplicates(db, dry_run: bool) -> int:
    """After fixing grupo_via for OTRO groups, merge any new duplicates."""
    print("\n=== PASO 6: Fusionando nuevos duplicados tras corrección de vía ===")
    dupes = db.execute(text("""
        SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as n
        FROM grupos_equivalencia
        WHERE concentracion_norm IS NOT NULL
        GROUP BY dci_key, grupo_via, concentracion_norm
        HAVING COUNT(*) > 1
        ORDER BY n DESC
    """)).fetchall()

    print(f"  Duplicate (dci, via, conc) triples: {len(dupes)}")
    merged = 0

    for dci_key, grupo_via, conc_norm, n in dupes:
        groups = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.dci_key == dci_key,
            GrupoEquivalencia.grupo_via == grupo_via,
            GrupoEquivalencia.concentracion_norm == conc_norm,
        ).all()

        if len(groups) <= 1:
            continue

        groups.sort(key=lambda x: x.n_productos, reverse=True)
        target = groups[0]
        others = groups[1:]

        seen = set(target.cum_ids or [])
        combined = list(target.cum_ids or [])
        for g in others:
            for cid in (g.cum_ids or []):
                if cid not in seen:
                    seen.add(cid)
                    combined.append(cid)

        if not dry_run:
            target.cum_ids = combined
            target.n_productos = len(combined)
            target.revisado_ia = any(g.revisado_ia for g in groups)
            for g in others:
                db.delete(g)
        merged += len(others)

    if not dry_run:
        db.flush()
    print(f"  Duplicate groups eliminated: {merged}")
    return merged


# ── Step 7: Extract concentration from product name for still-NULL groups ─────

_CONC_FROM_NAME = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|g|ui|iu|mEq|mmol|%)\s*(?:/\s*(\d+(?:[.,]\d+)?)\s*(mL|g|dosis))?",
    re.I
)

def fix_conc_from_name(db, dry_run: bool) -> int:
    print("\n=== PASO 7: Extrayendo concentracion del nombre del producto ===")
    null_groups = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.concentracion_norm == None
    ).all()

    fixed = 0
    for g in null_groups:
        ids = (g.cum_ids or [])[:10]
        candidates = []
        for cid in ids:
            parts = cid.split("-", 1)
            if len(parts) != 2:
                continue
            row = db.execute(text(
                "SELECT nombre_comercial_norm FROM cum_normalizado "
                "WHERE expediente_cum=:e AND consecutivo_cum=:c"
            ), {"e": parts[0], "c": parts[1]}).fetchone()
            if row and row[0]:
                m = _CONC_FROM_NAME.search(row[0])
                if m:
                    candidates.append(m.group(0).strip())

        if not candidates:
            continue

        # Use most common extracted concentration
        most_common = Counter(candidates).most_common(1)[0][0]
        # Parse value and unit
        m = _CONC_FROM_NAME.match(most_common)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(",", "."))
            unit = m.group(2).lower()
            denom_val = m.group(3)
            denom_unit = m.group(4)
            if denom_val and denom_unit:
                conc_norm = f"{val:g} {unit}/{denom_val} {denom_unit}"
            else:
                conc_norm = f"{val:g} {unit}"
        except (ValueError, AttributeError):
            continue

        if not dry_run:
            g.concentracion_norm = conc_norm
            g.concentracion_valor = val
            g.concentracion_unidad = unit
        fixed += 1

    if not dry_run:
        db.flush()
    print(f"  Concentraciones extraidas del nombre: {fixed} / {len(null_groups)}")
    return fixed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No guardar cambios")
    args = parser.parse_args()

    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY no encontrada en .env")
        sys.exit(1)

    db = SessionLocal()
    try:
        print("=" * 60)
        print("FIX GRUPOS CALIDAD" + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]"))
        print("=" * 60)

        fix_otro_groups(db, args.dry_run)
        fix_null_concentrations(db, args.dry_run)
        fix_conc_from_name(db, args.dry_run)
        merge_null_conc_duplicates(db, args.dry_run)
        fix_duplicate_cum_ids(db, args.dry_run)
        merge_via_duplicates(db, args.dry_run)
        fix_singletons(db, args.dry_run)

        if not args.dry_run:
            db.commit()
            print("\n=== GUARDADO EXITOSO ===")
        else:
            db.rollback()
            print("\n=== DRY-RUN completado, sin cambios guardados ===")

        # Stats
        total = db.query(GrupoEquivalencia).count()
        otro = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.grupo_via == "OTRO").count()
        null_conc = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.concentracion_norm == None).count()
        singletons = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.n_productos == 1).count()
        print(f"\nEstado final:")
        print(f"  Total grupos: {total}")
        print(f"  Grupos OTRO: {otro}")
        print(f"  Grupos sin concentracion: {null_conc}")
        print(f"  Singletons: {singletons}")

    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
