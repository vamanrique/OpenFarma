"""
Genera relaciones de alternativas farmacológicas usando MedicamentoTransformado.
Soporta principios activos mono/bi/tri/tetraconjugados.

Criterios (en orden de prioridad — cada par se clasifica una sola vez):
  A0  — SUSTITUTO_DIRECTO             : mismo DCI + misma conc + misma presentación + misma forma
  A1  — MISMA_CONC_DIFERENTE_CANTIDAD : mismo DCI + misma conc + misma forma + distinta cantidad
  A2  — MISMA_CONC_DIFERENTE_FORMA    : mismo DCI + misma conc + distinta forma/vía
  A3  — DIFERENTE_CONCENTRACION       : mismo DCI + misma forma/vía + distinta conc
  A4  — EQUIVALENTE_EXACTO            : mismo ATC-7 + misma forma + distintos DCI (sales)
  A5  — EQUIVALENTE_CLASE             : mismo ATC-5 + misma forma + distinto ATC-7
  A6  — COMPONENTE_COMPARTIDO         : combinados que comparten ≥1 DCI + misma clase ATC-5
  A7  — ALTERNATIVA_DIFERENTE_FORMA   : mismo ATC-5 + distinta forma/vía
"""
import re
from itertools import combinations
from collections import defaultdict
from dataclasses import dataclass

from etl.transformacion import (
    MedicamentoTransformado,
    FORMAS_EQUIVALENTES,
    _FORMA_A_GRUPO,
    _VIA_A_GRUPO,
    _grupo_forma,
)

_NUM_EN_PRES = re.compile(r'(\d+(?:[.,]\d+)?)')


def _pres_key(presentacion: str) -> float | None:
    """Extrae valor numérico de presentación para comparación ('3 mL' → 3.0, '' → None)."""
    if not presentacion:
        return None
    m = _NUM_EN_PRES.search(presentacion)
    return round(float(m.group(1).replace(',', '.')), 1) if m else None


@dataclass
class ParAlternativa:
    cum_origen: str
    cum_destino: str
    tipo: str
    descripcion: str
    componentes_compartidos: list[str]


def generar_alternativas(meds: list[MedicamentoTransformado]) -> list[ParAlternativa]:
    """
    Recibe lista de MedicamentoTransformado (ya agrupados y normalizados)
    y devuelve pares de alternativas.
    """
    # Inferir DCIs faltantes desde ATC-7: si otro producto del mismo ATC-7 tiene DCI conocido,
    # usarlo como proxy de molécula para productos cuyo CUM no registra DCI válido (ej. "A").
    atc7_to_dci: dict[str, tuple] = {}
    for m in meds:
        if m.principios_dci and m.atc and len(m.atc) >= 7:
            k = tuple(sorted(m.principios_dci))
            if m.atc not in atc7_to_dci:
                atc7_to_dci[m.atc] = k

    def mol_key(m: MedicamentoTransformado) -> tuple:
        """DCI conocido, o inferido desde ATC-7, o tupla vacía si desconocido."""
        if m.principios_dci:
            return tuple(sorted(m.principios_dci))
        if m.atc and m.atc in atc7_to_dci:
            return atc7_to_dci[m.atc]
        return ()

    por_directo:    dict[tuple, list] = defaultdict(list)  # A0
    por_misma_conc: dict[tuple, list] = defaultdict(list)  # A1 (misma conc + forma, diferente pres)
    por_dci_dosis:  dict[tuple, list] = defaultdict(list)  # A2 (misma conc, diferente forma)
    por_dci_forma:  dict[tuple, list] = defaultdict(list)  # A3 (misma forma, diferente conc)
    por_atc7_forma: dict[tuple, list] = defaultdict(list)
    por_atc5_forma: dict[tuple, list] = defaultdict(list)
    por_atc5:       dict[str, list]   = defaultdict(list)

    for m in meds:
        if not m.atc or m.atc in ("nan", "None", "") or len(m.atc) < 5:
            continue
        g_forma  = _grupo_forma(m.forma_farmaceutica, m.via_administracion)
        dci      = mol_key(m)

        if dci:  # solo indexar en A0-A3 cuando se conoce (o infiere) la molécula
            # tipo_formula incluido en las claves de A0-A3: un biconjugado nunca
            # puede ser sustituto directo ni alternativa de concentración de un mono.
            tf = m.tipo_formula
            por_dci_forma[(dci, g_forma, tf)].append(m)
            if m.dosis_numerica is not None:
                dosis_key = round(m.dosis_numerica, 1)
                pres_key  = _pres_key(m.presentacion)
                por_directo[(dci, dosis_key, pres_key, g_forma, tf)].append(m)
                por_misma_conc[(dci, dosis_key, g_forma, tf)].append(m)
                por_dci_dosis[(dci, dosis_key, tf)].append(m)

        # tipo_formula in A4 key: a bicomponent must never be "equivalente exacto"
        # of a monocomponent — that would be A6 (componente_compartido).
        por_atc7_forma[(m.atc, g_forma, m.tipo_formula)].append(m)
        por_atc5_forma[(m.atc[:5], g_forma)].append(m)
        por_atc5[m.atc[:5]].append(m)

    pares_vistos: set[tuple[str, str]] = set()
    resultado: list[ParAlternativa] = []

    def agregar(a: MedicamentoTransformado, b: MedicamentoTransformado,
                tipo: str, desc: str, compartidos: list[str]):
        key = (min(a.cum_id, b.cum_id), max(a.cum_id, b.cum_id))
        # Mismo expediente = mismo titular: en desabastecimiento todos sus consecutivos
        # estarían igualmente afectados, por lo que no son alternativas reales.
        if key not in pares_vistos and a.cum_id != b.cum_id and a.expedientecum != b.expedientecum:
            pares_vistos.add(key)
            resultado.append(ParAlternativa(
                cum_origen=a.cum_id,
                cum_destino=b.cum_id,
                tipo=tipo,
                descripcion=desc,
                componentes_compartidos=compartidos,
            ))

    # A0 — Sustituto directo: mismo DCI + misma conc + misma presentación + misma forma + mismo tipo
    for (dci, dosis, pres, _, _tf), grupo in por_directo.items():
        dci_str = ', '.join(dci) if dci else '(DCI no registrado)'
        for a, b in combinations(grupo, 2):
            pres_str = f" · {a.presentacion}" if a.presentacion else ""
            agregar(a, b, "SUSTITUTO_DIRECTO",
                    f"Mismo principio activo ({dci_str}), concentración ({dosis} mg/mL){pres_str}, misma forma. Solo difiere el laboratorio.",
                    list(dci))

    # A1 — Misma conc + misma forma + diferente presentación (cantidad total distinta)
    for (dci, dosis, g_forma, _tf), grupo in por_misma_conc.items():
        dci_str = ', '.join(dci) if dci else '(DCI no registrado)'
        for a, b in combinations(grupo, 2):
            if _pres_key(a.presentacion) != _pres_key(b.presentacion):
                pres_a = a.presentacion or "sin especificar"
                pres_b = b.presentacion or "sin especificar"
                agregar(a, b, "MISMA_CONC_DIFERENTE_CANTIDAD",
                        f"Mismo principio activo ({dci_str}) y concentración ({dosis} mg/mL), diferente cantidad: {pres_a} vs {pres_b}",
                        list(dci))

    # A2 — Misma conc + diferente forma/vía
    for (dci, dosis, _tf), grupo in por_dci_dosis.items():
        dci_str = ', '.join(dci) if dci else '(DCI no registrado)'
        for a, b in combinations(grupo, 2):
            ga = _grupo_forma(a.forma_farmaceutica, a.via_administracion)
            gb = _grupo_forma(b.forma_farmaceutica, b.via_administracion)
            if ga != gb:
                agregar(a, b, "MISMA_CONC_DIFERENTE_FORMA",
                        f"Mismo principio activo ({dci_str}) y concentración ({dosis} mg/mL), diferente forma farmacéutica ({ga} vs {gb})",
                        list(dci))

    # A3 — Misma forma + diferente concentración
    for (dci, g_forma, _tf), grupo in por_dci_forma.items():
        dci_str = ', '.join(dci) if dci else '(DCI no registrado)'
        for a, b in combinations(grupo, 2):
            dosis_a = round(a.dosis_numerica, 1) if a.dosis_numerica is not None else None
            dosis_b = round(b.dosis_numerica, 1) if b.dosis_numerica is not None else None
            if dosis_a != dosis_b:
                agregar(a, b, "DIFERENTE_CONCENTRACION",
                        f"Mismo principio activo ({dci_str}) y forma farmacéutica, diferente concentración",
                        list(dci))

    # A4 — Mismo ATC7 + misma forma + distintos DCI (sales del mismo compuesto)
    # Solo cuando AMBOS tienen DCI conocido (evita falsos positivos con DCI vacío por datos CUM)
    for (atc7, gf, _tf), grupo in por_atc7_forma.items():
        for a, b in combinations(grupo, 2):
            dci_a = tuple(sorted(a.principios_dci))
            dci_b = tuple(sorted(b.principios_dci))
            if dci_a and dci_b and dci_a != dci_b:
                agregar(a, b, "EQUIVALENTE_EXACTO",
                        f"Mismo ATC ({atc7}) y forma, distinto principio activo (sales/ésteres)",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    # A5 — Mismo ATC5 + misma forma + distinto ATC7
    for (atc5, gf), grupo in por_atc5_forma.items():
        for a, b in combinations(grupo, 2):
            if a.atc != b.atc:
                agregar(a, b, "EQUIVALENTE_CLASE",
                        f"Misma clase terapéutica ATC ({atc5}) y forma farmacéutica",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    # A6 — Combinados que comparten ≥1 DCI + misma clase ATC5
    for atc5, grupo in por_atc5.items():
        combinados = [m for m in grupo if m.tipo_formula != "monocomponente"]
        monocomp   = [m for m in grupo if m.tipo_formula == "monocomponente"]

        for comb in combinados:
            for mono in monocomp:
                compartidos = list(set(comb.principios_dci) & set(mono.principios_dci))
                if compartidos:
                    agregar(comb, mono, "COMPONENTE_COMPARTIDO",
                            f"El combinado contiene {', '.join(mono.principios_dci)} como componente",
                            compartidos)

        for a, b in combinations(combinados, 2):
            compartidos = list(set(a.principios_dci) & set(b.principios_dci))
            if 0 < len(compartidos) < max(len(a.principios_dci), len(b.principios_dci)):
                agregar(a, b, "COMPONENTE_COMPARTIDO",
                        f"Combinados con componente(s) en común: {', '.join(compartidos)}",
                        compartidos)

    # A7 — Mismo ATC5 + distinta forma/vía
    for atc5, grupo in por_atc5.items():
        for a, b in combinations(grupo, 2):
            ga = _grupo_forma(a.forma_farmaceutica, a.via_administracion)
            gb = _grupo_forma(b.forma_farmaceutica, b.via_administracion)
            if ga != gb:
                agregar(a, b, "ALTERNATIVA_DIFERENTE_FORMA",
                        f"Misma clase terapéutica ({atc5}), diferente vía/forma ({ga} vs {gb})",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    return resultado


def resumen(pares: list[ParAlternativa]):
    from collections import Counter
    conteo = Counter(p.tipo for p in pares)
    print(f"\nTotal pares de alternativas: {len(pares):,}")
    for tipo, n in conteo.most_common():
        print(f"  {tipo:<35}: {n:,}")
