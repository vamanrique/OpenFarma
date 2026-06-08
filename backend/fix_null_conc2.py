"""
fix_null_conc2.py
-----------------
Segunda pasada de recuperación de concentraciones NULL:
1. OFTALMICO: usa concentracion_mg_ml (que compute_concentracion no manejaba)
2. Regex expandido para U.I. / I.U. en nombres comerciales
3. Fusión de grupos duplicados resultantes

Uso:
    python fix_null_conc2.py [--dry-run]
"""
import os, sys, io, re, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from sqlalchemy import text
from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia

# ── Concentration extraction from name (expanded: handles U.I. / I.U. with dots) ──
_CONC_FROM_NAME = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(mg|mcg|g|u\.?i\.?|i\.?u\.?|mEq|mmol|%|UI|IU)"
    r"(?:\s*/\s*(\d+(?:[.,]\d+)?)\s*(mL|g|dosis))?",
    re.I
)

UNIT_NORM = {
    "u.i.": "UI", "u.i": "UI", "ui": "UI", "iu": "UI", "i.u.": "UI",
    "i.u": "UI", "mcg": "mcg", "mg": "mg", "g": "g", "meq": "mEq",
    "mmol": "mmol", "%": "%",
}


def _fmt_conc(val: float, unit: str, denom_val: str | None, denom_unit: str | None) -> tuple:
    unit_n = UNIT_NORM.get(unit.lower(), unit.upper())
    if denom_val and denom_unit:
        norm = f"{val:g} {unit_n}/{denom_val} {denom_unit}"
    else:
        norm = f"{val:g} {unit_n}"
    return norm, val, unit_n


def extract_conc_from_name(name: str):
    """Returns (cnorm, cval, cunit) or (None, None, None)."""
    m = _CONC_FROM_NAME.search(name or "")
    if not m:
        return None, None, None
    try:
        val = float(m.group(1).replace(",", "."))
        unit = m.group(2)
        return _fmt_conc(val, unit, m.group(3), m.group(4))
    except (ValueError, AttributeError):
        return None, None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 60)
        print("FIX NULL CONC v2" + (" [DRY-RUN]" if args.dry_run else " [GUARDANDO]"))
        print("=" * 60)

        null_groups = db.query(GrupoEquivalencia).filter(
            GrupoEquivalencia.concentracion_norm == None
        ).all()
        print(f"Grupos con NULL concentracion_norm: {len(null_groups)}")

        fixed_mg_ml = 0
        fixed_name = 0

        for g in null_groups:
            ids = g.cum_ids or []
            if not ids:
                continue

            best_cnorm = best_cval = best_cunit = None

            for cid in ids:
                parts = cid.split("-", 1)
                if len(parts) != 2:
                    continue
                cum = db.query(CumNormalizado).filter_by(
                    expediente_cum=parts[0], consecutivo_cum=parts[1]
                ).first()
                if not cum:
                    continue

                # Method 1: OFTALMICO/NASAL/OTICO with conc_mg_ml
                if g.grupo_via in ("OFTALMICO", "NASAL", "OTICO") and cum.concentracion_mg_ml and cum.concentracion_mg_ml > 0:
                    v = round(cum.concentracion_mg_ml, 3)
                    if v == int(v):
                        display = f"{int(v)} mg/mL"
                    elif v >= 1:
                        display = f"{v:.1f} mg/mL"
                    else:
                        display = f"{v:.3g} mg/mL"
                    best_cnorm, best_cval, best_cunit = display, v, "mg/mL"
                    break

                # Method 2: extract from commercial name (expanded regex with U.I.)
                cnorm, cval, cunit = extract_conc_from_name(cum.nombre_comercial_norm or "")
                if cnorm:
                    best_cnorm, best_cval, best_cunit = cnorm, cval, cunit
                    break

            if best_cnorm:
                tag = "(mg/mL)" if best_cunit == "mg/mL" and g.grupo_via in ("OFTALMICO", "NASAL", "OTICO") else "(name)"
                print(f"  [{g.id}] {g.dci_key[:35]} | {g.grupo_via} -> {best_cnorm} {tag}")
                if not args.dry_run:
                    g.concentracion_norm = best_cnorm
                    g.concentracion_valor = best_cval
                    g.concentracion_unidad = best_cunit
                if tag == "(mg/mL)":
                    fixed_mg_ml += 1
                else:
                    fixed_name += 1

        print(f"\nRecuperadas via conc_mg_ml: {fixed_mg_ml}")
        print(f"Recuperadas via nombre:     {fixed_name}")

        if not args.dry_run:
            db.flush()

            # Merge any resulting duplicates (same dci_key + grupo_via + concentracion_norm)
            print("\n=== Fusionando duplicados resultantes ===")
            dupes = db.execute(text("""
                SELECT dci_key, grupo_via, concentracion_norm, COUNT(*) as n
                FROM grupos_equivalencia
                WHERE concentracion_norm IS NOT NULL
                GROUP BY dci_key, grupo_via, concentracion_norm
                HAVING COUNT(*) > 1
                ORDER BY n DESC
            """)).fetchall()

            print(f"  Grupos duplicados (misma clave): {len(dupes)}")
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
                target.revisado_ia = any(g.revisado_ia for g in groups)
                print(f"  MERGE {n} grupos: {dci_key[:30]} {grupo_via} {conc_norm}")
                merged += n - 1

            db.flush()
            db.commit()
            print(f"\nGrupos fusionados: {merged}")
            print("=== GUARDADO EXITOSO ===")
        else:
            db.rollback()
            print("\n=== DRY-RUN completado ===")

        # Final stats
        null_count = db.query(GrupoEquivalencia).filter(GrupoEquivalencia.concentracion_norm == None).count()
        total = db.query(GrupoEquivalencia).count()
        print(f"\nEstado final:")
        print(f"  Total grupos: {total}")
        print(f"  NULL concentracion_norm: {null_count} ({null_count/total*100:.1f}%)")

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
