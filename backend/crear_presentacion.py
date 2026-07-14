"""
crear_presentacion.py — Genera RECURSOS/Presentacion.pptx para el concurso
Datos al Ecosistema 2026: IA para Colombia — Categoria Avanzado

Ejecutar desde la raiz del repo:
  python backend/crear_presentacion.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pathlib import Path

# ── Paleta — fondo BLANCO, pitch profesional ──────────────────────────────────
BLANCO        = RGBColor(0xFF, 0xFF, 0xFF)
NAVY          = RGBColor(0x0D, 0x2B, 0x55)   # titulos, fondo portada izq
AZUL          = RGBColor(0x1A, 0x56, 0x8C)   # acento principal
VERDE         = RGBColor(0x00, 0x87, 0x65)   # positivo / exito
ROJO          = RGBColor(0xC8, 0x20, 0x20)   # alerta / riesgo
AMBER         = RGBColor(0xB4, 0x5A, 0x00)   # advertencia / roadmap
TEXTO         = RGBColor(0x1E, 0x29, 0x3B)   # cuerpo texto oscuro
TEXTO_SUB     = RGBColor(0x4A, 0x5B, 0x6E)   # subtitulos / descripcion
GRIS          = RGBColor(0x94, 0xA3, 0xB8)   # pie de pagina
GRIS_BORDE    = RGBColor(0xCB, 0xD5, 0xE1)   # bordes suaves
FONDO_CLARO   = RGBColor(0xF7, 0xF9, 0xFC)   # cajas de contenido
AZUL_CLARO    = RGBColor(0xEB, 0xF4, 0xFF)   # fondo caja azul
VERDE_CLARO   = RGBColor(0xED, 0xFB, 0xF4)   # fondo caja verde
ROJO_CLARO    = RGBColor(0xFE, 0xF2, 0xF2)   # fondo caja roja
AMBER_CLARO   = RGBColor(0xFF, 0xF7, 0xED)   # fondo caja amber

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ── Helpers base ──────────────────────────────────────────────────────────────

def prs_nueva():
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def fondo(slide, color=BLANCO):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def rect(slide, l, t, w, h, fill=None, line=None, line_w=Pt(1)):
    shape = slide.shapes.add_shape(1, l, t, w, h)
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if line:
        shape.line.color.rgb = line
        shape.line.width = line_w
    else:
        shape.line.fill.background()
    return shape


def txt(slide, text, l, t, w, h,
        size=Pt(14), bold=False, color=TEXTO,
        align=PP_ALIGN.LEFT, italic=False):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf  = box.text_frame
    tf.word_wrap = True
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text         = text
    run.font.size    = size
    run.font.bold    = bold
    run.font.italic  = italic
    run.font.color.rgb = color
    return box


def pie(slide):
    txt(slide, "OpenFarma  |  Datos al Ecosistema 2026",
        Inches(8), Inches(7.1), Inches(5), Inches(0.35),
        size=Pt(9), color=GRIS, align=PP_ALIGN.RIGHT)


# ── Componentes reutilizables ─────────────────────────────────────────────────

def cabecera(slide, titulo, acento=AZUL, numero=None):
    """Barra superior + titulo + linea acento."""
    rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.07), fill=acento)
    fondo(slide, BLANCO)
    rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.07), fill=acento)
    txt(slide, titulo,
        Inches(0.55), Inches(0.18), Inches(11.8), Inches(0.85),
        size=Pt(27), bold=True, color=NAVY)
    rect(slide, Inches(0.55), Inches(1.0), Inches(2.8), Inches(0.055), fill=acento)
    if numero:
        txt(slide, numero,
            Inches(12.3), Inches(0.18), Inches(0.9), Inches(0.85),
            size=Pt(28), bold=True, color=acento, align=PP_ALIGN.RIGHT)


def metrica(slide, l, t, w, h, valor, label, sub="", acento=AZUL,
            fondo_caja=AZUL_CLARO):
    """Caja de metrica limpia: fondo claro + borde izq acento + valor grande."""
    rect(slide, l, t, w, h, fill=fondo_caja, line=GRIS_BORDE, line_w=Pt(0.5))
    rect(slide, l, t, Inches(0.07), h, fill=acento)
    txt(slide, valor, l + Inches(0.18), t + Inches(0.08), w - Inches(0.2), Inches(0.75),
        size=Pt(30), bold=True, color=acento, align=PP_ALIGN.CENTER)
    txt(slide, label, l + Inches(0.1), t + Inches(0.8), w - Inches(0.15), Inches(0.45),
        size=Pt(11), bold=True, color=TEXTO, align=PP_ALIGN.CENTER)
    if sub:
        txt(slide, sub, l + Inches(0.1), t + Inches(1.2), w - Inches(0.15), Inches(0.3),
            size=Pt(9), color=TEXTO_SUB, align=PP_ALIGN.CENTER)


def bullet(slide, icono, texto, y, acento=AZUL):
    txt(slide, icono, Inches(0.55), y, Inches(0.45), Inches(0.5),
        size=Pt(15), bold=True, color=acento)
    txt(slide, texto, Inches(1.1), y, Inches(11.7), Inches(0.5),
        size=Pt(15), color=TEXTO)


# ══════════════════════════════════════════════════════════════════════════════
# SLIDES
# ════════��═════════════════════════════════════════════════════════════════════

def slide_01_portada(prs):
    """Portada: panel navy izquierdo + metricas derecha."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fondo(slide, BLANCO)

    # Panel izquierdo — navy
    rect(slide, Inches(0), Inches(0), Inches(7.5), SLIDE_H, fill=NAVY)
    # Acento verde vertical
    rect(slide, Inches(0), Inches(0), Inches(0.14), SLIDE_H, fill=VERDE)

    # Nombre del proyecto
    txt(slide, "OpenFarma",
        Inches(0.35), Inches(0.7), Inches(7.0), Inches(1.5),
        size=Pt(68), bold=True, color=BLANCO)

    # Linea verde
    rect(slide, Inches(0.35), Inches(2.15), Inches(3.2), Inches(0.07), fill=VERDE)

    # Tagline
    txt(slide, "Sistema de Alerta Temprana de\nDesabastecimiento Farmaceutico",
        Inches(0.35), Inches(2.3), Inches(7.0), Inches(1.1),
        size=Pt(21), color=RGBColor(0xBD, 0xD5, 0xF5))

    # Subtitulo
    txt(slide, "Prediccion con IA  ·  CUM + INVIMA  ·  Reportes Ciudadanos",
        Inches(0.35), Inches(3.55), Inches(7.0), Inches(0.55),
        size=Pt(14), color=RGBColor(0x7B, 0xA8, 0xD8))

    # Badges
    rect(slide, Inches(0.35), Inches(4.3), Inches(4.3), Inches(0.6), fill=VERDE)
    txt(slide, "Datos al Ecosistema 2026: IA para Colombia",
        Inches(0.45), Inches(4.34), Inches(4.1), Inches(0.52),
        size=Pt(12), bold=True, color=BLANCO)

    rect(slide, Inches(4.75), Inches(4.3), Inches(2.5), Inches(0.6), fill=AZUL)
    txt(slide, "Categoria: Avanzado",
        Inches(4.85), Inches(4.34), Inches(2.3), Inches(0.52),
        size=Pt(12), bold=True, color=BLANCO)

    # Equipo — BORRADOR
    rect(slide, Inches(0.35), Inches(5.15), Inches(6.8), Inches(1.25),
         fill=RGBColor(0x08, 0x1D, 0x3A), line=RGBColor(0xF5, 0xA6, 0x23), line_w=Pt(1.5))
    txt(slide, "⚠  EQUIPO — BORRADOR",
        Inches(0.5), Inches(5.22), Inches(6.4), Inches(0.38),
        size=Pt(10), bold=True, color=RGBColor(0xF5, 0xA6, 0x23))
    txt(slide, "Lider: [NOMBRE]  ·  Analista ML: [NOMBRE]  ·  Desarrollador: [NOMBRE]",
        Inches(0.5), Inches(5.58), Inches(6.4), Inches(0.35),
        size=Pt(10), color=RGBColor(0xBB, 0xCC, 0xDD))
    txt(slide, "Contacto: vamanrique@gmail.com",
        Inches(0.5), Inches(5.9), Inches(6.4), Inches(0.35),
        size=Pt(10), color=RGBColor(0x7B, 0xA8, 0xD8))

    # URL
    txt(slide, "openfarma-production.up.railway.app",
        Inches(0.35), Inches(6.9), Inches(7.0), Inches(0.45),
        size=Pt(11), color=RGBColor(0x7B, 0xA8, 0xD8))

    # Panel derecho — metricas sobre fondo blanco
    datos = [
        ("52,830", "Medicamentos CUM",    "normalizados",      AZUL,  AZUL_CLARO),
        ("9,795",  "Alertas INVIMA",      "17 meses de historial", VERDE, VERDE_CLARO),
        ("0.8374", "ROC-AUC",            "split temporal honesto", VERDE, VERDE_CLARO),
        ("3,204",  "Grupos terapeuticos", "equivalencia INN",  AZUL,  AZUL_CLARO),
    ]
    for i, (val, lbl, sub, ac, bg) in enumerate(datos):
        row, col = divmod(i, 2)
        x = Inches(7.7 + col * 2.75)
        y = Inches(0.5 + row * 3.3)
        metrica(slide, x, y, Inches(2.55), Inches(1.6), val, lbl, sub, ac, bg)

    txt(slide, "github.com/vamanrique/OpenFarma",
        Inches(7.7), Inches(7.1), Inches(5.5), Inches(0.35),
        size=Pt(9), color=GRIS, align=PP_ALIGN.RIGHT)


def slide_02_problema(prs):
    """El Problema."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "El Problema: Desabastecimiento Farmaceutico", ROJO, "02")

    # Cita de impacto
    rect(slide, Inches(0.55), Inches(1.15), Inches(12.2), Inches(0.85),
         fill=ROJO_CLARO, line=ROJO, line_w=Pt(1))
    txt(slide,
        "Cuando INVIMA publica una alerta, el medicamento ya lleva semanas sin llegar a las farmacias.",
        Inches(0.75), Inches(1.22), Inches(11.8), Inches(0.7),
        size=Pt(16), italic=True, color=ROJO)

    # 3 cifras de impacto
    for i, (num, lbl, desc, ac, bg) in enumerate([
        ("9,795",  "alertas INVIMA",      "ene 2025 – may 2026 (17 meses)", ROJO,  ROJO_CLARO),
        ("5+",     "semanas de retraso",  "entre escasez real y alerta oficial",  AMBER, AMBER_CLARO),
        ("0",      "sistemas preventivos","publicos integrados en Colombia",       AZUL,  AZUL_CLARO),
    ]):
        x = Inches(0.55 + i * 4.25)
        metrica(slide, x, Inches(2.2), Inches(3.9), Inches(1.65),
                num, lbl, desc, ac, bg)

    # Consecuencias
    txt(slide, "Consecuencias concretas:",
        Inches(0.55), Inches(4.05), Inches(4), Inches(0.45),
        size=Pt(13), bold=True, color=NAVY)

    items = [
        "Pacientes con enfermedades cronicas interrumpen tratamientos",
        "IPS y clinicas no pueden anticipar compras de emergencia",
        "INVIMA reacciona cuando la escasez ya es un hecho consumado",
        "No existe senal ciudadana integrada con los datos regulatorios",
    ]
    for i, item in enumerate(items):
        bullet(slide, "▸", item, Inches(4.55 + i * 0.52), ROJO)

    pie(slide)


def slide_03_datos(prs):
    """Los Datos."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "Los Datos: Fuentes Publicas Integradas por Primera Vez", VERDE, "03")

    fuentes = [
        ("CUM Activos",         "52,830",  "presentaciones normalizadas", "datos.gov.co · i7cb-raxc",     AZUL,  AZUL_CLARO),
        ("CUM Renovacion",      "~8,000",  "registros en tramite",        "datos.gov.co · vgr4-gemg",     AZUL,  AZUL_CLARO),
        ("Alertas INVIMA",      "9,795",   "entradas limpias",            "PDFs portal INVIMA · 17 meses", VERDE, VERDE_CLARO),
        ("Reportes ciudadanos", "activo",  "canal propio en crecimiento", "Formulario OpenFarma",              ROJO,  ROJO_CLARO),
    ]
    for i, (titulo, val, sub, fuente, ac, bg) in enumerate(fuentes):
        col, row = i % 2, i // 2
        x = Inches(0.55 + col * 6.3)
        y = Inches(1.2 + row * 2.85)
        rect(slide, x, y, Inches(5.9), Inches(2.6), fill=bg, line=GRIS_BORDE, line_w=Pt(0.5))
        rect(slide, x, y, Inches(5.9), Inches(0.07), fill=ac)
        txt(slide, titulo, x + Inches(0.2), y + Inches(0.15), Inches(5.5), Inches(0.45),
            size=Pt(13), bold=True, color=ac)
        txt(slide, val,    x + Inches(0.2), y + Inches(0.55), Inches(5.5), Inches(0.9),
            size=Pt(34), bold=True, color=NAVY)
        txt(slide, sub,    x + Inches(0.2), y + Inches(1.4), Inches(5.5), Inches(0.35),
            size=Pt(11), color=TEXTO_SUB)
        txt(slide, fuente, x + Inches(0.2), y + Inches(1.8), Inches(5.5), Inches(0.6),
            size=Pt(10), color=GRIS)

    # Nota diferenciadora
    rect(slide, Inches(0.55), Inches(6.9), Inches(12.2), Inches(0.45),
         fill=VERDE_CLARO, line=VERDE, line_w=Pt(1))
    txt(slide, "✓  Primera integracion publica completa CUM + INVIMA + Reportes Ciudadanos en Colombia",
        Inches(0.75), Inches(6.95), Inches(11.8), Inches(0.38),
        size=Pt(12), bold=True, color=VERDE)


def slide_04_arquitectura(prs):
    """Arquitectura."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "Arquitectura: Tres Componentes Integrados", AZUL, "04")

    capas = [
        ("CIUDADANO",       ["Busca medicamento", "Ve alternativas", "Consulta riesgo ML", "Reporta escasez"], VERDE,  VERDE_CLARO),
        ("REACT FRONTEND",  ["React 19 + Vite", "Tailwind CSS", "Recharts", "ARIA a11y"],                      AZUL,   AZUL_CLARO),
        ("FASTAPI BACKEND", ["Busqueda CUM", "Alternativas", "Predicciones ML", "Reportes API", "Cache INVIMA"], AMBER, AMBER_CLARO),
        ("DATOS + ML",      ["SQLite 52K CUM", "3,204 grupos", "INVIMA 17m", "RF + Calibrado", "Bias Tests"],    ROJO,  ROJO_CLARO),
        ("ALERTA",          ["Senales\ntempranas", "30 dias\nantes"],                                           ROJO,  ROJO_CLARO),
    ]
    widths = [Inches(2.3), Inches(2.3), Inches(2.3), Inches(2.3), Inches(1.6)]
    xs = [Inches(0.3), Inches(2.75), Inches(5.2), Inches(7.65), Inches(10.1)]
    arrow_x = [Inches(2.65), Inches(5.1), Inches(7.55), Inches(10.0)]

    for i, ((lbl, items, ac, bg), w, x) in enumerate(zip(capas, widths, xs)):
        rect(slide, x, Inches(1.15), w, Inches(5.9), fill=bg, line=GRIS_BORDE, line_w=Pt(0.5))
        rect(slide, x, Inches(1.15), w, Inches(0.07), fill=ac)
        txt(slide, lbl, x, Inches(1.25), w, Inches(0.5),
            size=Pt(10), bold=True, color=ac, align=PP_ALIGN.CENTER)
        for j, item in enumerate(items):
            txt(slide, item, x + Inches(0.1), Inches(1.85 + j * 0.85), w - Inches(0.2), Inches(0.75),
                size=Pt(11), color=TEXTO, align=PP_ALIGN.CENTER)

    for ax in arrow_x:
        txt(slide, "→", ax, Inches(3.7), Inches(0.5), Inches(0.5),
            size=Pt(22), bold=True, color=GRIS)

    # Deploy info
    txt(slide, "Deploy: Railway · Auto-deploy desde GitHub main · nixpacks.toml",
        Inches(0.55), Inches(7.15), Inches(8), Inches(0.3),
        size=Pt(9), color=GRIS)
    pie(slide)


def slide_05_pipeline(prs):
    """Pipeline ETL."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "Pipeline ETL: Calidad Farmaceutica de Alta Precision", VERDE, "05")

    items = [
        ("52,830",  "medicamentos del CUM descargados via Socrata API (datos.gov.co)"),
        ("420",     "reglas de sinonimia INN + 50 patrones de sal farmaceutica"),
        ("3,204",   "grupos de equivalencia terapeutica — DeepSeek + reglas manuales"),
        ("105",     "rondas de auditoria INN: radiofarmacos, vacunas, biologicos, hemoderivados"),
        ("9,795",   "alertas INVIMA parseadas de PDFs mensuales (17 meses, ene 2025–may 2026)"),
        ("0",       "duplicados · 0 NULL concentracion · 0 mismatches DCI tras auditoria completa"),
    ]
    y = Inches(1.2)
    for val, desc in items:
        rect(slide, Inches(0.55), y, Inches(12.2), Inches(0.6),
             fill=FONDO_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
        txt(slide, val, Inches(0.65), y + Inches(0.05), Inches(1.5), Inches(0.5),
            size=Pt(20), bold=True, color=VERDE)
        txt(slide, desc, Inches(2.3), y + Inches(0.12), Inches(10.3), Inches(0.4),
            size=Pt(14), color=TEXTO)
        y += Inches(0.67)

    # Fila de metricas
    y2 = Inches(5.4)
    kpis = [("100%", "DCIs normalizados", VERDE, VERDE_CLARO),
            ("105",  "Rondas auditoria",  AZUL,  AZUL_CLARO),
            ("0",    "Duplicados finales", VERDE, VERDE_CLARO),
            ("17",   "Meses INVIMA",       AZUL,  AZUL_CLARO)]
    for i, (v, l, ac, bg) in enumerate(kpis):
        metrica(slide, Inches(0.55 + i * 3.1), y2, Inches(2.9), Inches(1.65),
                v, l, acento=ac, fondo_caja=bg)

    txt(slide, "Fallback local: si datos.gov.co no responde, los 52,830 productos siguen disponibles",
        Inches(0.55), Inches(7.15), Inches(12), Inches(0.3),
        size=Pt(9), italic=True, color=GRIS)


def slide_06_modelo(prs):
    """Modelo ML."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "Modelo Predictivo: Integridad Estadistica Rigurosa", ROJO, "06")

    # 4 metricas en fila
    metricas_row = [
        ("0.8374", "ROC-AUC",       "split temporal honesto", VERDE, VERDE_CLARO),
        ("0.1707", "Avg Precision", "1.6% positivos reales",  AZUL,  AZUL_CLARO),
        ("3",      "Meses test",    "mar–may 2026",      AZUL,  AZUL_CLARO),
        ("15",     "Features",      "10 CUM + 5 INVIMA",      ROJO,  ROJO_CLARO),
    ]
    for i, (v, l, s, ac, bg) in enumerate(metricas_row):
        metrica(slide, Inches(0.55 + i * 3.15), Inches(1.2), Inches(2.95), Inches(1.7),
                v, l, s, ac, bg)

    # Columna izq — split temporal
    rect(slide, Inches(0.55), Inches(3.1), Inches(5.8), Inches(3.9),
         fill=FONDO_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
    rect(slide, Inches(0.55), Inches(3.1), Inches(0.07), Inches(3.9), fill=VERDE)
    txt(slide, "Split Temporal (sin Data Leakage)",
        Inches(0.75), Inches(3.18), Inches(5.4), Inches(0.5),
        size=Pt(14), bold=True, color=NAVY)
    split_items = [
        "Train: ene 2025 – feb 2026 (14 meses)",
        "Test:  mar – may 2026 (3 meses, nunca vistos)",
        "Con split aleatorio: ROC-AUC era 1.000 (data leakage)",
        "Con split temporal: ROC-AUC 0.8374 (honesto)",
        "Modelo produccion: reentrenado en todos los datos",
    ]
    for i, item in enumerate(split_items):
        txt(slide, f"▸  {item}",
            Inches(0.75), Inches(3.72 + i * 0.59), Inches(5.4), Inches(0.52),
            size=Pt(12), color=TEXTO)

    # Columna der — top features
    rect(slide, Inches(6.6), Inches(3.1), Inches(6.2), Inches(3.9),
         fill=FONDO_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
    rect(slide, Inches(6.6), Inches(3.1), Inches(0.07), Inches(3.9), fill=ROJO)
    txt(slide, "Top Features por Importancia",
        Inches(6.8), Inches(3.18), Inches(5.8), Inches(0.5),
        size=Pt(14), bold=True, color=NAVY)

    feats = [
        ("invima_sev_actual",       "27.5%", ROJO),
        ("invima_peor_sev_hist",     "21.1%", ROJO),
        ("invima_meses_monitoreado", "12.9%", AMBER),
        ("tasa_inactivacion_atc5",   "11.6%", AMBER),
        ("invima_sev_t3_avg",        "11.5%", AMBER),
    ]
    for i, (feat, pct, ac) in enumerate(feats):
        y = Inches(3.72 + i * 0.59)
        # barra proporcional
        bar_w = float(pct.rstrip("%")) / 30.0
        rect(slide, Inches(6.8), y + Inches(0.12), Inches(bar_w), Inches(0.3), fill=ac)
        txt(slide, feat, Inches(6.8), y, Inches(4.5), Inches(0.48),
            size=Pt(11), color=TEXTO)
        txt(slide, pct, Inches(12.0), y, Inches(0.7), Inches(0.48),
            size=Pt(12), bold=True, color=ac, align=PP_ALIGN.RIGHT)

    txt(slide, "Tipo: CalibratedClassifierCV (Platt scaling) + RandomForestClassifier · scikit-learn 1.9.0",
        Inches(0.55), Inches(7.15), Inches(12.5), Inches(0.3),
        size=Pt(9), color=GRIS)
    pie(slide)


def slide_07_aplicacion(prs):
    """La Aplicacion."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "La Aplicacion: Para Pacientes, Clinicos e INVIMA", AZUL, "07")

    funciones = [
        ("\U0001f50d", "Busqueda en tiempo real: 52,830 medicamentos CUM via Socrata API + fallback local"),
        ("\U0001f48a", "Alternativas terapeuticas en 8 niveles: sustituto directo → clase ATC completa"),
        ("\U0001f916", "Badge de riesgo ML por medicamento: probabilidad 0-100% con nivel Bajo/Medio/Alto/Critico"),
        ("\U0001f4cb", "Formulario de reporte mejorado: busca con ficha CUM completa antes de enviar"),
        ("\U0001f4ca", "Dashboard de vigilancia: top 20 reportados + spike detector vs. alertas INVIMA"),
        ("\U0001f6a8", "Senales anticipadas: spike ciudadano sin alerta INVIMA = riesgo emergente"),
    ]
    y = Inches(1.2)
    for icon, desc in funciones:
        rect(slide, Inches(0.55), y, Inches(12.2), Inches(0.62),
             fill=FONDO_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
        txt(slide, icon, Inches(0.65), y + Inches(0.05), Inches(0.5), Inches(0.52),
            size=Pt(16), color=AZUL)
        txt(slide, desc, Inches(1.25), y + Inches(0.1), Inches(11.3), Inches(0.45),
            size=Pt(14), color=TEXTO)
        y += Inches(0.7)

    # Banner URL + CI
    rect(slide, Inches(0.55), Inches(6.1), Inches(12.2), Inches(0.72),
         fill=AZUL_CLARO, line=AZUL, line_w=Pt(1))
    txt(slide, "\U0001f310  openfarma-production.up.railway.app"
               "  ·  CI/CD GitHub Actions  ·  16/16 tests verdes  ·  MIT License",
        Inches(0.75), Inches(6.17), Inches(11.8), Inches(0.58),
        size=Pt(13), bold=True, color=AZUL)

    txt(slide, "Stack: FastAPI · SQLAlchemy · SQLite · React 19 · Vite · Tailwind · Recharts · scikit-learn",
        Inches(0.55), Inches(7.15), Inches(12), Inches(0.3),
        size=Pt(9), color=GRIS)


def slide_08_impacto(prs):
    """Impacto y Escalabilidad."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "Impacto y Escalabilidad", VERDE, "08")

    # Columna izq — impacto
    rect(slide, Inches(0.55), Inches(1.2), Inches(5.9), Inches(5.4),
         fill=VERDE_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
    rect(slide, Inches(0.55), Inches(1.2), Inches(0.07), Inches(5.4), fill=VERDE)
    txt(slide, "Impacto Inmediato",
        Inches(0.75), Inches(1.3), Inches(5.5), Inches(0.5),
        size=Pt(16), bold=True, color=NAVY)
    impacts = [
        "52,830 medicamentos monitoreados en tiempo real",
        "Canal ciudadano → senal regulatoria directa a INVIMA",
        "Anticipa desabastecimiento 30 dias antes que alertas oficiales",
        "Alternativas terapeuticas: reduce impacto en pacientes",
        "Codigo abierto MIT: cualquier entidad puede adoptarlo",
    ]
    for i, item in enumerate(impacts):
        txt(slide, f"✓  {item}",
            Inches(0.75), Inches(1.9 + i * 0.8), Inches(5.5), Inches(0.72),
            size=Pt(13), color=TEXTO)

    # Columna der — roadmap
    rect(slide, Inches(6.85), Inches(1.2), Inches(6.0), Inches(5.4),
         fill=AMBER_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
    rect(slide, Inches(6.85), Inches(1.2), Inches(0.07), Inches(5.4), fill=AMBER)
    txt(slide, "Escalabilidad y Roadmap",
        Inches(7.05), Inches(1.3), Inches(5.6), Inches(0.5),
        size=Pt(16), bold=True, color=NAVY)
    roadmap = [
        "\U0001f3e5  Integracion directa API INVIMA (alertas automaticas)",
        "\U0001f4f1  Notificaciones push a IPS y farmacias en riesgo",
        "\U0001f30e  Replicable: Ecuador, Peru, Chile (DIGEMID/ISP)",
        "\U0001f4c8  Re-entrenamiento mensual automatico con datos nuevos",
        "\U0001f91d  Partnership con MinSalud para adopcion institucional",
    ]
    for i, item in enumerate(roadmap):
        txt(slide, item,
            Inches(7.05), Inches(1.9 + i * 0.8), Inches(5.6), Inches(0.72),
            size=Pt(13), color=TEXTO)

    # CTA — verde
    rect(slide, Inches(0.55), Inches(6.78), Inches(12.2), Inches(0.58), fill=NAVY)
    txt(slide,
        "⭐  github.com/vamanrique/OpenFarma  ·  "
        "\U0001f310  openfarma-production.up.railway.app  ·  "
        "\U0001f4e7  vamanrique@gmail.com",
        Inches(0.75), Inches(6.84), Inches(11.8), Inches(0.46),
        size=Pt(12), bold=True, color=BLANCO, align=PP_ALIGN.CENTER)


def slide_09_equipo(prs):
    """Equipo — BORRADOR."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cabecera(slide, "El Equipo", AMBER, "09")

    # Banner BORRADOR
    rect(slide, Inches(0.55), Inches(1.12), Inches(12.2), Inches(0.55),
         fill=AMBER_CLARO, line=RGBColor(0xF5, 0xA6, 0x23), line_w=Pt(1.5))
    txt(slide, "⚠  BORRADOR — Informacion de participantes pendiente de confirmacion",
        Inches(0.75), Inches(1.18), Inches(11.8), Inches(0.43),
        size=Pt(12), bold=True, color=AMBER)

    # 3 tarjetas de miembros
    roles = [
        ("Lider de Equipo",          "[NOMBRE COMPLETO]", "[Cargo / Institucion]", "[Ciudad, Colombia]"),
        ("Analista de Datos / ML",   "[NOMBRE COMPLETO]", "[Cargo / Institucion]", "[Ciudad, Colombia]"),
        ("Desarrollador Full-Stack", "[NOMBRE COMPLETO]", "[Cargo / Institucion]", "[Ciudad, Colombia]"),
    ]
    for i, (rol, nombre, org, ciudad) in enumerate(roles):
        x = Inches(0.55 + i * 4.25)
        rect(slide, x, Inches(1.85), Inches(4.0), Inches(4.4),
             fill=FONDO_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
        rect(slide, x, Inches(1.85), Inches(4.0), Inches(0.07), fill=AMBER)
        # Avatar
        rect(slide, x + Inches(1.25), Inches(2.05), Inches(1.5), Inches(1.5),
             fill=AZUL_CLARO, line=GRIS_BORDE, line_w=Pt(0.5))
        txt(slide, "\U0001f464", x + Inches(1.25), Inches(2.1), Inches(1.5), Inches(1.4),
            size=Pt(36), align=PP_ALIGN.CENTER, color=AZUL)
        txt(slide, rol, x, Inches(3.65), Inches(4.0), Inches(0.45),
            size=Pt(10), bold=True, color=AMBER, align=PP_ALIGN.CENTER)
        txt(slide, nombre, x, Inches(4.08), Inches(4.0), Inches(0.45),
            size=Pt(13), bold=True, color=NAVY, align=PP_ALIGN.CENTER)
        txt(slide, org, x, Inches(4.5), Inches(4.0), Inches(0.4),
            size=Pt(10), color=TEXTO_SUB, align=PP_ALIGN.CENTER)
        txt(slide, ciudad, x, Inches(4.88), Inches(4.0), Inches(0.4),
            size=Pt(10), color=GRIS, align=PP_ALIGN.CENTER)

    txt(slide, "Requisito concurso: equipos 2-4 personas · minimo una mujer · al menos un perfil tecnico",
        Inches(0.55), Inches(6.45), Inches(12), Inches(0.4),
        size=Pt(10), italic=True, color=GRIS)
    txt(slide, "vamanrique@gmail.com",
        Inches(0.55), Inches(7.0), Inches(5), Inches(0.4),
        size=Pt(11), color=AZUL)
    pie(slide)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    prs = prs_nueva()

    print("Generando slides...")
    slide_01_portada(prs)     ; print("  [OK] Slide 1: Portada")
    slide_02_problema(prs)    ; print("  [OK] Slide 2: El Problema")
    slide_03_datos(prs)       ; print("  [OK] Slide 3: Los Datos")
    slide_04_arquitectura(prs); print("  [OK] Slide 4: Arquitectura")
    slide_05_pipeline(prs)    ; print("  [OK] Slide 5: Pipeline ETL")
    slide_06_modelo(prs)      ; print("  [OK] Slide 6: Modelo ML")
    slide_07_aplicacion(prs)  ; print("  [OK] Slide 7: La Aplicacion")
    slide_08_impacto(prs)     ; print("  [OK] Slide 8: Impacto y Escalabilidad")
    slide_09_equipo(prs)      ; print("  [OK] Slide 9: Equipo (BORRADOR)")

    out_dir = Path(__file__).parent.parent / "RECURSOS"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "Presentacion.pptx"
    prs.save(str(out_path))
    print(f"\nGuardado: {out_path}")
    print(f"  {len(prs.slides)} slides - {out_path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
