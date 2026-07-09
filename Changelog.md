# Changelog

Todos los cambios relevantes del proyecto FarmaVigia se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

---

## [1.3.0] — 2026-07-08

### Añadido
- Fallback de búsqueda local cuando datos.gov.co (Socrata) no está disponible
- Los 52,830 medicamentos del CUM normalizado quedan accesibles sin conexión a internet
- Mensaje diferenciado en el frontend: distingue error de Socrata vs. error de backend

### Corregido
- Error 500 en `/buscar` cuando la API Socrata retornaba timeout o error HTTP
- Error 500 en `/modelo/info` cuando el archivo pkl no estaba accesible

---

## [1.2.0] — 2026-07-03

### Añadido
- Pipeline de reportes ciudadanos conectado al modelo ML (`reportes_norm` feature)
- OG tags para compartir en redes sociales (portada del proyecto)
- Preservación de reportes entre deploys Railway (volumen persistente)

---

## [1.1.0] — 2026-06-30

### Añadido
- Modelo predictivo de desabastecimiento v1: `CalibratedClassifierCV` + `RandomForestClassifier`
- ROC-AUC 0.87 con split temporal honesto (últimos 3 meses como test)
- 15 features: 10 de estructura de mercado CUM + 5 de historial INVIMA
- Endpoint `/predicciones/{cum_id}` con nivel de riesgo (Bajo/Medio/Alto/Crítico)
- Auditoría INN ronda 104: 3,204 grupos con concentración 100% normalizada, 0 duplicados

### Corregido
- Data leakage en el entrenamiento del modelo (split aleatorio → split temporal)
- ATC de medicamentos en INVIMA que no coincidían con CUM: corregidos con LLM

---

## [1.0.0] — 2026-06-08

### Añadido
- Búsqueda en tiempo real del CUM vía Socrata API (datos.gov.co)
- Sistema de grupos de equivalencia terapéutica (3,204 grupos)
- Alternativas A0–A7: mismo grupo (A0-A3) + clase ATC (A4-A7)
- Integración con historial INVIMA: 17 meses, 9,795 registros (ene 2025 – may 2026)
- Estado de alerta INVIMA en tiempo real en la ficha de cada medicamento
- Normalización 100% de DCIs (Denominación Común Internacional) — 52,830 productos
- Rediseño de UI: búsqueda hero, accesibilidad de fuentes, navegación por teclado

### Técnico
- ETL INVIMA: scraper de PDFs del portal INVIMA con inferencia de mes/año
- `cum_normalizado`: tabla local con 52,830 productos para búsqueda offline
- `grupos_equivalencia`: tabla central del sistema de equivalencia
- Pipeline DeepSeek para clasificación farmacológica ATC y normalización INN

---

## [0.1.0] — 2026-05-15

### Añadido
- Prototipo inicial: búsqueda de medicamentos en CUM activos
- Backend FastAPI + frontend React básico
- Deploy inicial en Railway

---

*FarmaVigia — Concurso Datos al Ecosistema 2026*
