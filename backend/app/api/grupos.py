"""
grupos.py
---------
FastAPI router for drug equivalence groups.

GET /grupos/medicamentos/{cum_id}
  Returns primary group, same-route alternatives, and other-route alternatives
  for the given drug product.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.cum_normalizado import CumNormalizado
from app.models.grupo_equivalencia import GrupoEquivalencia

router = APIRouter()

# ── Label mapping (mirrors frontend GRUPO_LABEL) ──────────────────────────────
GRUPO_LABEL: dict[str, str] = {
    "SOLIDO_ORAL":       "Sólido oral",
    "SOLIDO_ORAL_LP":    "Liberación prolongada",
    "ORAL_DISPERSABLE":  "Dispersable / Polvo",
    "LIQUIDO_ORAL":      "Líquido oral",
    "SUBLINGUAL":        "Sublingual / Bucal",
    "INYECTABLE":        "Inyectable",
    "TOPICO":            "Tópico",
    "INHALADO":          "Inhalado",
    "OFTALMICO":         "Oftálmico",
    "VAGINAL":           "Vaginal",
    "RECTAL":            "Rectal",
    "TRANSDERMICO":      "Transdérmico",
    "OTICO":             "Ótico",
    "NASAL":             "Nasal",
    # aliases que pueden venir de forma_normalizada sin mapear
    "SUSPENSION_ORAL":   "Líquido oral",
    "SUSPENSION":        "Líquido oral",
    "SOLUCION_ORAL":     "Líquido oral",
    "POLVO_ORAL":        "Dispersable / Polvo",
}

# Order for otras_vias display
OTRAS_VIAS_ORDER = [
    "SOLIDO_ORAL", "SOLIDO_ORAL_LP", "ORAL_DISPERSABLE", "SUBLINGUAL",
    "LIQUIDO_ORAL", "INYECTABLE", "TOPICO", "INHALADO",
    "OFTALMICO", "OTICO", "NASAL", "TRANSDERMICO", "VAGINAL", "RECTAL",
]


def _via_order(gv: str) -> int:
    try:
        return OTRAS_VIAS_ORDER.index(gv)
    except ValueError:
        return len(OTRAS_VIAS_ORDER)


# ── Dependency ────────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductoEnGrupo(BaseModel):
    cum_id: str
    nombre_comercial: str
    laboratorio: str | None
    registro_sanitario: str | None
    estado_cum: str
    fuente: str


class GrupoDetalle(BaseModel):
    id: int
    grupo_via: str
    grupo_via_label: str
    concentracion_norm: str | None
    concentracion_valor: float | None
    concentracion_unidad: str | None
    n_productos: int
    productos: list[ProductoEnGrupo]
    revisado_ia: bool


class GruposEquivalenciaResponse(BaseModel):
    dci: str            # human-readable, e.g. "ACICLOVIR"
    dci_key: str        # internal key
    mi_grupo: GrupoDetalle | None
    misma_via: list[GrupoDetalle]    # same grupo_via, different concentracion
    otras_vias: list[GrupoDetalle]   # different grupo_via
    grupos_fallback: bool            # True if grupos_equivalencia is not built yet


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_dci_key(cum: CumNormalizado) -> str | None:
    principios = cum.principios_dci or []
    if not principios:
        return None
    return "||".join(sorted(principios))


def _dci_human(dci_key: str) -> str:
    """Return human-readable DCI from internal key (replace || with ' + ')."""
    return dci_key.replace("||", " + ")


def _hydrate_group(
    grupo: GrupoEquivalencia,
    db: Session,
    lookup: dict[str, CumNormalizado] | None = None,
    max_productos: int = 30,
) -> GrupoDetalle:
    """Build GrupoDetalle from pre-fetched lookup. Deduplicates by nombre+lab."""
    cum_ids: list[str] = grupo.cum_ids or []
    if lookup is None:
        # Fallback: build own lookup (used when called standalone)
        pares = [(cid.split("-",1)[0], cid.split("-",1)[1], cid) for cid in cum_ids if "-" in cid]
        if pares:
            conds = or_(*[and_(CumNormalizado.expediente_cum==e, CumNormalizado.consecutivo_cum==c) for e,c,_ in pares])
            rows = db.query(CumNormalizado).filter(conds).all()
            lookup = {f"{r.expediente_cum}-{r.consecutivo_cum}": r for r in rows}
        else:
            lookup = {}

    vistos: set[str] = set()
    productos: list[ProductoEnGrupo] = []
    for cum_id in cum_ids:
        cum = lookup.get(cum_id)
        key = (f"{(cum.nombre_comercial_norm or '').upper()}|{(cum.titular_registro or '').upper()}"
               if cum else cum_id)
        if key in vistos:
            continue
        vistos.add(key)
        if cum:
            productos.append(ProductoEnGrupo(
                cum_id=cum_id,
                nombre_comercial=cum.nombre_comercial_norm or cum_id,
                laboratorio=cum.titular_registro,
                registro_sanitario=cum.registro_sanitario,
                estado_cum=cum.estado_cum or "",
                fuente=cum.fuente or "CUM_ACTIVO",
            ))
        if len(productos) >= max_productos:
            break

    return GrupoDetalle(
        id=grupo.id,
        grupo_via=grupo.grupo_via,
        grupo_via_label=GRUPO_LABEL.get(grupo.grupo_via, grupo.grupo_via),
        concentracion_norm=grupo.concentracion_norm,
        concentracion_valor=grupo.concentracion_valor,
        concentracion_unidad=grupo.concentracion_unidad,
        n_productos=grupo.n_productos,
        productos=productos,
        revisado_ia=grupo.revisado_ia,
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/medicamentos/{cum_id}", response_model=GruposEquivalenciaResponse)
def get_grupos_equivalencia(cum_id: str, db: Session = Depends(get_db)):
    """
    Returns equivalence groups for a given drug product.

    Groups:
    - mi_grupo: the group containing this exact product (same DCI + via + concentration)
    - misma_via: other concentrations of the same DCI and route
    - otras_vias: same DCI but different route
    """
    # 1. Find the product
    parts = cum_id.split("-", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid cum_id format. Expected: expediente-consecutivo")

    exp, consec = parts
    cum = db.query(CumNormalizado).filter(
        CumNormalizado.expediente_cum == exp,
        CumNormalizado.consecutivo_cum == consec,
    ).first()

    if not cum:
        raise HTTPException(status_code=404, detail=f"Producto no encontrado: {cum_id}")

    # 2. Get dci_key
    dci_key = _build_dci_key(cum)
    if not dci_key:
        return GruposEquivalenciaResponse(
            dci=cum.nombre_comercial_norm or cum_id,
            dci_key="",
            mi_grupo=None,
            misma_via=[],
            otras_vias=[],
            grupos_fallback=True,
        )

    # 3. Check if grupos_equivalencia table has data for this DCI
    total_in_table = db.query(GrupoEquivalencia).count()
    if total_in_table == 0:
        return GruposEquivalenciaResponse(
            dci=_dci_human(dci_key),
            dci_key=dci_key,
            mi_grupo=None,
            misma_via=[],
            otras_vias=[],
            grupos_fallback=True,
        )

    # 4. Query all groups for this dci_key
    all_grupos = db.query(GrupoEquivalencia).filter(
        GrupoEquivalencia.dci_key == dci_key
    ).all()

    if not all_grupos:
        return GruposEquivalenciaResponse(
            dci=_dci_human(dci_key),
            dci_key=dci_key,
            mi_grupo=None,
            misma_via=[],
            otras_vias=[],
            grupos_fallback=False,
        )

    # 5. Find which group contains cum_id
    mi_grupo_raw: GrupoEquivalencia | None = None
    for g in all_grupos:
        if cum_id in (g.cum_ids or []):
            mi_grupo_raw = g
            break

    # 6. Split into misma_via and otras_vias
    mi_via = mi_grupo_raw.grupo_via if mi_grupo_raw else None

    misma_via_raw: list[GrupoEquivalencia] = []
    otras_vias_raw: list[GrupoEquivalencia] = []

    for g in all_grupos:
        if g is mi_grupo_raw:
            continue
        if mi_via and g.grupo_via == mi_via:
            misma_via_raw.append(g)
        else:
            otras_vias_raw.append(g)

    # 7. Sort misma_via by concentracion_valor ascending
    misma_via_raw.sort(key=lambda g: (g.concentracion_valor is None, g.concentracion_valor or 0))

    # 8. Sort otras_vias by predefined order
    otras_vias_raw.sort(key=lambda g: (_via_order(g.grupo_via), g.concentracion_valor or 0))

    # 9. Hydrate all groups in a single DB query
    all_grupos_to_hydrate = (
        ([mi_grupo_raw] if mi_grupo_raw else []) + misma_via_raw + otras_vias_raw
    )
    all_cum_ids: list[str] = []
    for g in all_grupos_to_hydrate:
        all_cum_ids.extend(g.cum_ids or [])

    # One batch query: filter by expediente IN (...) then resolve in Python
    needed_ids: set[str] = {cid for cid in all_cum_ids if "-" in cid}
    expedientes = list({cid.split("-", 1)[0] for cid in needed_ids})
    global_lookup: dict[str, CumNormalizado] = {}
    if expedientes:
        rows = db.query(CumNormalizado).filter(
            CumNormalizado.expediente_cum.in_(expedientes)
        ).all()
        global_lookup = {
            f"{r.expediente_cum}-{r.consecutivo_cum}": r
            for r in rows
            if f"{r.expediente_cum}-{r.consecutivo_cum}" in needed_ids
        }

    def hydrate(g: GrupoEquivalencia) -> GrupoDetalle:
        return _hydrate_group(g, db, lookup=global_lookup)

    mi_grupo = hydrate(mi_grupo_raw) if mi_grupo_raw else None
    misma_via = [hydrate(g) for g in misma_via_raw]
    otras_vias = [hydrate(g) for g in otras_vias_raw]

    return GruposEquivalenciaResponse(
        dci=_dci_human(dci_key),
        dci_key=dci_key,
        mi_grupo=mi_grupo,
        misma_via=misma_via,
        otras_vias=otras_vias,
        grupos_fallback=False,
    )
