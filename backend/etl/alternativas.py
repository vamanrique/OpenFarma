"""
Genera relaciones de alternativas farmacológicas usando MedicamentoTransformado.
Soporta principios activos mono/bi/tri/tetraconjugados.

Criterios (en orden de prioridad — cada par se clasifica una sola vez):
  A0  — SUSTITUTO_DIRECTO             : mismo DCI + misma dosis + misma forma+vía, distinto lab
  A0b — MISMO_PRINCIPIO_DIFERENTE_FORMA: mismo DCI + misma dosis + distinta forma/vía
  A1  — MISMO_PRINCIPIO_ACTIVO        : mismo DCI + misma forma+vía + distinta dosis
  A2  — EQUIVALENTE_EXACTO            : mismo ATC-7 + misma forma+vía + distintos DCI (sales)
  A3  — EQUIVALENTE_CLASE             : mismo ATC-5 + misma forma+vía + distinto ATC-7
  A4  — COMPONENTE_COMPARTIDO         : combinados que comparten ≥1 DCI + misma clase ATC-5
  A5  — ALTERNATIVA_DIFERENTE_FORMA   : mismo ATC-5 + distinta forma/vía
"""
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


@dataclass
class ParAlternativa:
    cum_origen: str
    cum_destino: str
    tipo: str
    descripcion: str
    componentes_compartidos: list[str]  # DCI en común (relevante para combinados)


def generar_alternativas(meds: list[MedicamentoTransformado]) -> list[ParAlternativa]:
    """
    Recibe lista de MedicamentoTransformado (ya agrupados y normalizados)
    y devuelve pares de alternativas.
    """
    # Índices de búsqueda
    por_producto: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)   # A0
    por_dci_dosis: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)  # A0b
    por_dci_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc7_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc5_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc5: dict[str, list[MedicamentoTransformado]] = defaultdict(list)

    for m in meds:
        if not m.atc or m.atc in ("nan", "None", ""):
            continue
        # La vía de administración determina el grupo: capsula VAGINAL ≠ capsula ORAL
        g_forma = _grupo_forma(m.forma_farmaceutica, m.via_administracion)
        dci_key = tuple(sorted(m.principios_dci))

        por_dci_forma[(dci_key, g_forma)].append(m)
        por_atc7_forma[(m.atc, g_forma)].append(m)
        por_atc5_forma[(m.atc[:5], g_forma)].append(m)
        por_atc5[m.atc[:5]].append(m)

        if m.dosis_numerica is not None:
            dosis_key = round(m.dosis_numerica, 1)
            por_producto[(dci_key, dosis_key, g_forma)].append(m)
            por_dci_dosis[(dci_key, dosis_key)].append(m)

    # Cada par se clasifica con el criterio más específico; sin tipo en la clave
    # para evitar duplicados entre criterios que se solapan (ej. A0b y A5).
    pares_vistos: set[tuple[str, str]] = set()
    resultado: list[ParAlternativa] = []

    def agregar(a: MedicamentoTransformado, b: MedicamentoTransformado,
                tipo: str, desc: str, compartidos: list[str]):
        key = (min(a.cum_id, b.cum_id), max(a.cum_id, b.cum_id))
        if key not in pares_vistos and a.cum_id != b.cum_id:
            pares_vistos.add(key)
            resultado.append(ParAlternativa(
                cum_origen=a.cum_id,
                cum_destino=b.cum_id,
                tipo=tipo,
                descripcion=desc,
                componentes_compartidos=compartidos,
            ))

    # A0 — Sustituto directo: mismo DCI + misma dosis + misma forma, diferente laboratorio
    for (dci_key, dosis, _), grupo in por_producto.items():
        for a, b in combinations(grupo, 2):
            agregar(a, b, "SUSTITUTO_DIRECTO",
                    f"Mismo principio activo ({', '.join(dci_key)}) y concentración ({dosis} mg), diferente laboratorio",
                    list(dci_key))

    # A0b — Mismo DCI + misma dosis + DISTINTA forma (ej. tableta convencional vs LP)
    for (dci_key, dosis), grupo in por_dci_dosis.items():
        for a, b in combinations(grupo, 2):
            ga = _grupo_forma(a.forma_farmaceutica, a.via_administracion)
            gb = _grupo_forma(b.forma_farmaceutica, b.via_administracion)
            if ga != gb:
                agregar(a, b, "MISMO_PRINCIPIO_DIFERENTE_FORMA",
                        f"Mismo principio activo ({', '.join(dci_key)}) y concentración ({dosis} mg), diferente forma farmacéutica ({ga} vs {gb})",
                        list(dci_key))

    # A1 — Mismos DCI + misma forma + DIFERENTE dosis (antes mezclaba todo; A0 cubre la misma dosis)
    for (dci_key, _), grupo in por_dci_forma.items():
        for a, b in combinations(grupo, 2):
            dosis_a = round(a.dosis_numerica, 1) if a.dosis_numerica is not None else None
            dosis_b = round(b.dosis_numerica, 1) if b.dosis_numerica is not None else None
            if dosis_a != dosis_b:
                agregar(a, b, "MISMO_PRINCIPIO_ACTIVO",
                        f"Mismo principio activo ({', '.join(dci_key)}) y forma farmacéutica, diferente concentración",
                        list(dci_key))

    # A2 — Mismo ATC7 + misma forma + distintos DCI (sales del mismo compuesto)
    for (atc7, gf), grupo in por_atc7_forma.items():
        for a, b in combinations(grupo, 2):
            if tuple(sorted(a.principios_dci)) != tuple(sorted(b.principios_dci)):
                agregar(a, b, "EQUIVALENTE_EXACTO",
                        f"Mismo ATC ({atc7}) y forma, distinto principio activo (sales/ésteres)",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    # A3 — Mismo ATC5 + misma forma + distinto ATC7
    for (atc5, gf), grupo in por_atc5_forma.items():
        for a, b in combinations(grupo, 2):
            if a.atc != b.atc:
                agregar(a, b, "EQUIVALENTE_CLASE",
                        f"Misma clase terapéutica ATC ({atc5}) y forma farmacéutica",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    # A4 — Combinados que comparten ≥1 DCI + misma clase ATC5
    for atc5, grupo in por_atc5.items():
        combinados = [m for m in grupo if m.tipo_formula != "monocomponente"]
        monocomp = [m for m in grupo if m.tipo_formula == "monocomponente"]

        # Combinado vs monocomponente: el monocomponente es uno de los DCI del combinado
        for comb in combinados:
            for mono in monocomp:
                compartidos = list(set(comb.principios_dci) & set(mono.principios_dci))
                if compartidos:
                    agregar(comb, mono, "COMPONENTE_COMPARTIDO",
                            f"El combinado contiene {', '.join(mono.principios_dci)} como componente",
                            compartidos)

        # Combinado vs combinado: comparten ≥1 pero no todos
        for a, b in combinations(combinados, 2):
            compartidos = list(set(a.principios_dci) & set(b.principios_dci))
            if 0 < len(compartidos) < max(len(a.principios_dci), len(b.principios_dci)):
                agregar(a, b, "COMPONENTE_COMPARTIDO",
                        f"Combinados con componente(s) en común: {', '.join(compartidos)}",
                        compartidos)

    # A5 — Mismo ATC5 + distinta forma/vía (oral vs vaginal, tableta vs inyectable, etc.)
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
