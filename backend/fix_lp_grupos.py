"""
fix_lp_grupos.py
----------------
Mueve productos de liberación prolongada (LP/SR/ER/XL/etc) de grupos
SOLIDO_ORAL a grupos SOLIDO_ORAL_LP.

Uso:
    python fix_lp_grupos.py [--dry-run]
"""
import os, sys, io, json, re, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia
from sqlalchemy import text
from collections import defaultdict
from datetime import datetime, timezone

LP_RE = re.compile(
    r"(?<!\w)(LP|SR|ER|XL|MR|CD|OROS|ZOK|RETARD)(?!\w)"
    r"|LIBERACI[OÓ]N\s+(PROLONGADA|CONTROLADA|MODIFICADA|SOSTENIDA)"
    r"|ACCI[OÓ]N\s+PROLONGADA",
    re.I
)


def is_lp_name(nombre: str) -> bool:
    return bool(LP_RE.search(nombre or ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 60)
        print("FIX LP GRUPOS" + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]"))
        print("=" * 60)

        # 1. Load all SOLIDO_ORAL groups
        so_groups = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.grupo_via == "SOLIDO_ORAL"
        ).all()
        print(f"SOLIDO_ORAL groups: {len(so_groups)}")

        # Build lookup: cum_id → nombre_comercial_norm
        all_so_cum_ids = []
        for g in so_groups:
            all_so_cum_ids.extend(g.cum_ids or [])

        # Batch-load all product names
        needed = {cid for cid in all_so_cum_ids if "-" in cid}
        expedientes = list({cid.split("-", 1)[0] for cid in needed})

        name_lookup: dict[str, str] = {}
        BATCH = 500
        for i in range(0, len(expedientes), BATCH):
            batch = expedientes[i:i+BATCH]
            rows = db.query(CumNormalizado).filter(
                CumNormalizado.expediente_cum.in_(batch)
            ).all()
            for r in rows:
                cid = f"{r.expediente_cum}-{r.consecutivo_cum}"
                if cid in needed:
                    name_lookup[cid] = r.nombre_comercial_norm or ""

        # 2. For each SOLIDO_ORAL group, split into LP and non-LP products
        stats = {"groups_split": 0, "products_moved": 0, "lp_groups_created": 0}
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for g in so_groups:
            lp_ids = []
            non_lp_ids = []
            for cid in (g.cum_ids or []):
                name = name_lookup.get(cid, "")
                if is_lp_name(name):
                    lp_ids.append(cid)
                else:
                    non_lp_ids.append(cid)

            if not lp_ids:
                continue

            print(f"\nGroup [{g.id}] {g.dci_key[:35]} | {g.concentracion_norm} | n={g.n_productos}")
            print(f"  LP: {len(lp_ids)}, non-LP: {len(non_lp_ids)}")
            # Sample LP names
            for cid in lp_ids[:3]:
                print(f"    LP: {name_lookup.get(cid,'?')[:50]}")

            if args.dry_run:
                stats["groups_split"] += 1
                stats["products_moved"] += len(lp_ids)
                continue

            # Find or create SOLIDO_ORAL_LP group with same (dci_key, concentracion_norm)
            lp_group = db.query(GrupoEquivalencia).filter(
                GrupoEquivalencia.dci_key == g.dci_key,
                GrupoEquivalencia.grupo_via == "SOLIDO_ORAL_LP",
                GrupoEquivalencia.concentracion_norm == g.concentracion_norm,
            ).first()

            if lp_group:
                # Add LP products to existing LP group
                existing_ids = set(lp_group.cum_ids or [])
                new_ids = list(lp_group.cum_ids or [])
                for cid in lp_ids:
                    if cid not in existing_ids:
                        new_ids.append(cid)
                        existing_ids.add(cid)
                lp_group.cum_ids = new_ids
                lp_group.n_productos = len(new_ids)
                lp_group.revisado_ia = True
            else:
                # Create new SOLIDO_ORAL_LP group
                lp_group = GrupoEquivalencia(
                    dci_key=g.dci_key,
                    grupo_via="SOLIDO_ORAL_LP",
                    concentracion_norm=g.concentracion_norm,
                    concentracion_valor=g.concentracion_valor,
                    concentracion_unidad=g.concentracion_unidad,
                    cum_ids=lp_ids,
                    n_productos=len(lp_ids),
                    revisado_ia=True,
                    notas="Migrado de SOLIDO_ORAL por nombre LP",
                    actualizado_en=now,
                )
                db.add(lp_group)
                stats["lp_groups_created"] += 1

            # Update original SOLIDO_ORAL group
            if non_lp_ids:
                g.cum_ids = non_lp_ids
                g.n_productos = len(non_lp_ids)
            else:
                # All products were LP → delete the SOLIDO_ORAL group
                db.delete(g)

            stats["groups_split"] += 1
            stats["products_moved"] += len(lp_ids)

        if not args.dry_run:
            db.flush()

            # 3. Merge any duplicate SOLIDO_ORAL_LP groups for same (dci_key, concentracion_norm)
            print("\n=== Merging LP group duplicates ===")
            from sqlalchemy import text as sql_text
            dupes = db.execute(sql_text("""
                SELECT dci_key, concentracion_norm, COUNT(*) as n
                FROM grupos_equivalencia
                WHERE grupo_via='SOLIDO_ORAL_LP'
                GROUP BY dci_key, concentracion_norm
                HAVING COUNT(*) > 1
                ORDER BY n DESC
            """)).fetchall()

            print(f"LP duplicate (dci, conc) pairs: {len(dupes)}")
            for dci_key, conc_norm, n in dupes:
                groups = db.query(GrupoEquivalencia).filter(
                    GrupoEquivalencia.dci_key == dci_key,
                    GrupoEquivalencia.grupo_via == "SOLIDO_ORAL_LP",
                    GrupoEquivalencia.concentracion_norm == conc_norm,
                ).all()
                if len(groups) <= 1:
                    continue
                groups.sort(key=lambda x: x.n_productos, reverse=True)
                target = groups[0]
                seen = set(target.cum_ids or [])
                combined = list(target.cum_ids or [])
                for g in groups[1:]:
                    for cid in (g.cum_ids or []):
                        if cid not in seen:
                            seen.add(cid)
                            combined.append(cid)
                    db.delete(g)
                target.cum_ids = combined
                target.n_productos = len(combined)
                stats["lp_groups_created"] -= 1

            db.flush()
            db.commit()
            print("\n=== GUARDADO EXITOSO ===")
        else:
            db.rollback()
            print("\n=== DRY-RUN completado ===")

        print(f"\nResultados:")
        print(f"  SOLIDO_ORAL groups split: {stats['groups_split']}")
        print(f"  Products moved to LP: {stats['products_moved']}")
        print(f"  New SOLIDO_ORAL_LP groups: {stats['lp_groups_created']}")

        # Final counts
        so_count = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.grupo_via == "SOLIDO_ORAL").count()
        lp_count = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.grupo_via == "SOLIDO_ORAL_LP").count()
        print(f"  SOLIDO_ORAL groups: {so_count}")
        print(f"  SOLIDO_ORAL_LP groups: {lp_count}")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
