"""
Genera relaciones de alternativas farmacológicas usando MedicamentoTransformado.
Soporta principios activos mono/bi/tri/tetraconjugados.

Criterios:
  A1 — MISMO_PRINCIPIO_ACTIVO      : mismos DCI (todos los componentes) + misma forma
  A2 — EQUIVALENTE_EXACTO          : mismo ATC 7 chars + misma forma + distintos DCI (sales)
  A3 — EQUIVALENTE_CLASE           : mismo ATC 5 chars + misma forma + distinto ATC7
  A4 — COMPONENTE_COMPARTIDO       : combinados que comparten ≥1 DCI + misma clase ATC5
  A5 — ALTERNATIVA_DIFERENTE_FORMA : mismo ATC 5 chars + distinta forma normalizada
"""
from itertools import combinations
from collections import defaultdict
from dataclasses import dataclass

from etl.transformacion import MedicamentoTransformado

FORMAS_EQUIVALENTES: dict[str, frozenset[str]] = {
    "SOLIDO_ORAL": frozenset({
        "TABLETA", "TABLETA RECUBIERTA", "TABLETA CUBIERTA CON PELICULA",
        "TABLETA MASTICABLE", "TABLETA DISPERSABLE", "TABLETA EFERVESCENTE",
        "COMPRIMIDO", "CAPSULA", "CAPSULA DURA", "CAPSULA BLANDA",
        "CAPSULA GELATINOSA", "GRAGEA",
    }),
    "LIQUIDO_ORAL": frozenset({
        "JARABE", "SOLUCION ORAL", "SUSPENSION ORAL", "ELIXIR",
        "GOTAS ORALES", "SOLUCION", "SUSPENSION",
    }),
    "INYECTABLE": frozenset({
        "SOLUCION INYECTABLE", "POLVO PARA SOLUCION INYECTABLE",
        "SOLUCION PARA INYECCION", "INYECTABLE",
        "POLVO LIOFILIZADO PARA RECONSTITUIR A SOLUCION INYECTABLE",
        "CONCENTRADO PARA SOLUCION PARA PERFUSION",
    }),
    "TOPICO": frozenset({"CREMA", "UNGÜENTO", "GEL", "LOCION", "POMADA", "EMULSION"}),
    "INHALADO": frozenset({
        "AEROSOL PARA INHALACION", "POLVO PARA INHALACION",
        "SOLUCION PARA INHALACION", "INHALADOR",
    }),
    "OFTALMICO": frozenset({
        "COLIRIO", "SOLUCION OFTALMICA", "GOTAS OFTALMICAS",
        "POMADA OFTALMICA", "GEL OFTALMICO",
    }),
}

_FORMA_A_GRUPO: dict[str, str] = {
    f: g for g, fs in FORMAS_EQUIVALENTES.items() for f in fs
}


def _grupo_forma(forma: str) -> str:
    return _FORMA_A_GRUPO.get(forma.strip().upper(), forma.strip().upper())


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
    por_dci_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc7_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc5_forma: dict[tuple, list[MedicamentoTransformado]] = defaultdict(list)
    por_atc5: dict[str, list[MedicamentoTransformado]] = defaultdict(list)

    for m in meds:
        if not m.atc or m.atc in ("nan", "None", ""):
            continue
        g_forma = _grupo_forma(m.forma_farmaceutica)
        dci_key = tuple(sorted(m.principios_dci))

        por_dci_forma[(dci_key, g_forma)].append(m)
        por_atc7_forma[(m.atc, g_forma)].append(m)
        por_atc5_forma[(m.atc[:5], g_forma)].append(m)
        por_atc5[m.atc[:5]].append(m)

    pares_vistos: set[tuple[str, str, str]] = set()
    resultado: list[ParAlternativa] = []

    def agregar(a: MedicamentoTransformado, b: MedicamentoTransformado,
                tipo: str, desc: str, compartidos: list[str]):
        key = (min(a.cum_id, b.cum_id), max(a.cum_id, b.cum_id), tipo)
        if key not in pares_vistos and a.cum_id != b.cum_id:
            pares_vistos.add(key)
            resultado.append(ParAlternativa(
                cum_origen=a.cum_id,
                cum_destino=b.cum_id,
                tipo=tipo,
                descripcion=desc,
                componentes_compartidos=compartidos,
            ))

    # A1 — Mismos DCI + misma forma
    for (dci_key, _), grupo in por_dci_forma.items():
        for a, b in combinations(grupo, 2):
            agregar(a, b, "MISMO_PRINCIPIO_ACTIVO",
                    f"Mismo principio activo ({', '.join(dci_key)}) y forma farmacéutica",
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

    # A5 — Mismo ATC5 + distinta forma
    for atc5, grupo in por_atc5.items():
        for a, b in combinations(grupo, 2):
            if _grupo_forma(a.forma_farmaceutica) != _grupo_forma(b.forma_farmaceutica):
                agregar(a, b, "ALTERNATIVA_DIFERENTE_FORMA",
                        f"Misma clase terapéutica ({atc5}), diferente forma farmacéutica",
                        list(set(a.principios_dci) & set(b.principios_dci)))

    return resultado


def resumen(pares: list[ParAlternativa]):
    from collections import Counter
    conteo = Counter(p.tipo for p in pares)
    print(f"\nTotal pares de alternativas: {len(pares):,}")
    for tipo, n in conteo.most_common():
        print(f"  {tipo:<35}: {n:,}")
