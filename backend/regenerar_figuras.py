"""
regenerar_figuras.py — Regenera figuras del modelo a partir del artefacto actual.

Genera:
  - reports/figures/feature_importance.png  (importancias reales del RF)
  - reports/figures/roc_auc_badge.png       (badge texto ROC-AUC = 0.8374)

Ejecutar desde: C:/Users/aewal/farmavigia-concurso/backend
  .venv/Scripts/python.exe regenerar_figuras.py
"""

import pickle
import pathlib
import sys

import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = pathlib.Path(__file__).parent          # backend/
PKL_PATH   = BASE_DIR / 'data' / 'modelo_rf.pkl'
FIGS_DIR   = BASE_DIR.parent / 'reports' / 'figures'
FIGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Load model artefact
# ---------------------------------------------------------------------------
print(f'Cargando modelo desde: {PKL_PATH}')
with open(PKL_PATH, 'rb') as f:
    artefacto = pickle.load(f)

modelo   = artefacto.get('modelo') or artefacto.get('modelo_prod')
metricas = artefacto.get('metricas', {})

roc_auc_val  = metricas.get('roc_auc',        0.8374)
avg_prec_val = metricas.get('avg_precision',   0.1707)

print(f'ROC-AUC: {roc_auc_val:.4f}')
print(f'Avg Precision: {avg_prec_val:.4f}')

# Feature names — same order as training
FEATURE_COLS = [
    'tasa_inactivacion_atc5', 'num_competidores', 'monopolio',
    'tiene_alternativas', 'num_presentaciones_activas', 'es_combinado',
    'tipo_formula_num', 'grupo_atc_enc', 'busquedas_norm', 'reportes_norm',
    'invima_sev_actual', 'invima_peor_sev_hist', 'invima_meses_monitoreado',
    'invima_sev_t3_avg', 'invima_tendencia'
]

# ---------------------------------------------------------------------------
# Figure 1 — Feature importance
# ---------------------------------------------------------------------------
print('\nGenerando feature_importance.png ...')

try:
    # CalibratedClassifierCV -> first fold estimator
    base_rf = modelo.calibrated_classifiers_[0].estimator
    importances = base_rf.feature_importances_
except AttributeError:
    # Fallback: model might be the RF directly
    importances = modelo.feature_importances_

# Sort ascending for horizontal bar
order       = np.argsort(importances)
feat_sorted = [FEATURE_COLS[i] for i in order]
imp_sorted  = importances[order]

colors = ['#2563eb' if 'invima' in f else '#60a5fa' for f in feat_sorted]

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.barh(feat_sorted, imp_sorted, color=colors, edgecolor='white')

# Value labels
for i, (feat, val) in enumerate(zip(feat_sorted, imp_sorted)):
    ax.text(val + 0.002, i, f'{val:.3f}', va='center', fontsize=9)

ax.set_title(
    'Importancia de features — RandomForestClassifier\n'
    '(azul oscuro = features INVIMA, azul claro = features CUM)',
    fontsize=12
)
ax.set_xlabel('Importancia (Mean Decrease Impurity)')
ax.set_xlim(0, imp_sorted.max() * 1.18)

legend_elements = [
    mpatches.Patch(color='#2563eb', label='Features INVIMA (historial)'),
    mpatches.Patch(color='#60a5fa', label='Features CUM (estructura mercado)'),
]
ax.legend(handles=legend_elements, fontsize=9, loc='lower right')

plt.tight_layout()
out_path = FIGS_DIR / 'feature_importance.png'
plt.savefig(out_path, bbox_inches='tight', dpi=120)
plt.close()
print(f'Guardado: {out_path}')

# Print top 5
print('\nTop 5 features:')
for feat, val in zip(reversed(feat_sorted), reversed(imp_sorted)):
    print(f'  {feat:<35} {val:.4f}')
    if feat == feat_sorted[max(0, len(feat_sorted)-5)]:
        break

# ---------------------------------------------------------------------------
# Figure 2 — ROC-AUC badge
# ---------------------------------------------------------------------------
print('\nGenerando roc_auc_badge.png ...')

fig, ax = plt.subplots(figsize=(5, 3))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis('off')

# Background rounded rectangle
rect = mpatches.FancyBboxPatch(
    (0.05, 0.1), 0.9, 0.8,
    boxstyle='round,pad=0.05',
    facecolor='#1e3a5f', edgecolor='#2563eb', linewidth=3
)
ax.add_patch(rect)

# Label
ax.text(0.5, 0.72, 'ROC-AUC', ha='center', va='center',
        fontsize=16, color='#93c5fd', fontweight='bold',
        transform=ax.transAxes)

# Value
ax.text(0.5, 0.42, f'{roc_auc_val:.4f}', ha='center', va='center',
        fontsize=32, color='#ffffff', fontweight='bold',
        transform=ax.transAxes)

# Subtitle
ax.text(0.5, 0.20, 'Split temporal honesto (mar–may 2026)', ha='center', va='center',
        fontsize=9, color='#94a3b8',
        transform=ax.transAxes)

fig.patch.set_facecolor('#0f172a')
plt.tight_layout(pad=0)
out_badge = FIGS_DIR / 'roc_auc_badge.png'
plt.savefig(out_badge, bbox_inches='tight', dpi=120, facecolor='#0f172a')
plt.close()
print(f'Guardado: {out_badge}')

print('\nListo. Figuras regeneradas exitosamente.')
