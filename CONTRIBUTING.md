# Contributing to OpenFarma

Thank you for your interest in contributing to OpenFarma — an open-source early warning system for pharmaceutical shortages in Colombia. This guide covers everything you need to get started.

---

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Running Tests](#running-tests)
3. [Branch Strategy](#branch-strategy)
4. [Reporting Bugs](#reporting-bugs)
5. [Contributing a New INN Normalization Rule](#contributing-a-new-inn-normalization-rule)
6. [Code Style](#code-style)
7. [Database (WAL Checkpoint)](#database-wal-checkpoint)

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Git

### Backend

```bash
# From the repo root
python -m venv .venv
source .venv/Scripts/activate   # Windows
# source .venv/bin/activate      # macOS/Linux

pip install -r requirements.txt

cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.
Interactive docs (Swagger UI): `http://localhost:8000/docs`

You will need a `backend/.env` file with:

```
DEEPSEEK_API_KEY=your_key_here
```

Contact the maintainer for a development key if you do not have one.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The React app will be available at `http://localhost:5173`.
It proxies `/api` requests to the backend at port 8000 (configured in `vite.config.ts`).

---

## Running Tests

Tests live in the `tests/` directory and use pytest with asyncio support.

```bash
# From the repo root, with the virtualenv activated
pytest tests/

# Run a specific test file
pytest tests/test_predicciones.py

# Run with verbose output
pytest tests/ -v

# Run only fast unit tests (skip integration tests that need the DB)
pytest tests/ -m "not integration"
```

The test suite covers:
- API endpoint responses (FastAPI `TestClient`)
- ML model loading and prediction shape
- INN normalization rules in `etl/transformacion.py`
- INVIMA parser edge cases

---

## Branch Strategy

We follow a lightweight feature-branch workflow:

```
main
 └── feature/<short-description>
 └── fix/<short-description>
 └── docs/<short-description>
```

1. **Branch from `main`:** `git checkout -b feature/my-feature`
2. **Make your changes** in small, focused commits.
3. **Open a Pull Request** targeting `main` on GitHub.
4. A maintainer will review and merge. Railway auto-deploys from `main`.

Branch naming examples:
- `feature/add-departamento-filter`
- `fix/invima-parser-footer-text`
- `docs/update-model-card`

Avoid long-lived branches. If your PR is blocked, open a draft PR early to get feedback.

---

## Reporting Bugs

Use [GitHub Issues](https://github.com/vamanrique/OpenFarma/issues) to report bugs.

Please include:

- **Describe the bug**: What did you expect to happen? What happened instead?
- **Steps to reproduce**: Minimal steps to trigger the issue.
- **Environment**: OS, Python version, Node version (if frontend).
- **Logs**: Paste any relevant stack traces or API error responses.
- **CUM ID or drug name** (if the bug is search or prediction related).

For security vulnerabilities, do **not** open a public issue. Email `vamanrique@gmail.com` directly.

---

## Contributing a New INN Normalization Rule

INN (International Nonproprietary Name) normalization is handled in `backend/etl/transformacion.py` via two structures:

- `_SINONIMOS`: maps variant names → canonical INN (e.g., `"ACETAMINOFEN"` → `"PARACETAMOL"`)
- `_SUFIJOS_SAL`: salt/ester suffixes stripped during normalization (e.g., `"CLORHIDRATO"`, `"SULFATO"`)

### Adding a synonym

1. Open `backend/etl/transformacion.py`.
2. Find the `_SINONIMOS` dictionary.
3. Add an entry: `"VARIANT_NAME": "CANONICAL_INN"`.
   - Keys and values must be uppercase, no accents (ASCII only).
   - The canonical form should match the INN-Sp (Spanish INN list from OMS/INVIMA).
4. Add a test in `tests/test_normalizacion.py` asserting the mapping.

### Important conventions (established across 105 audit rounds)

- **Word order**: `ACIDO` always first — `ACIDO FOLICO`, not `FOLICO ACIDO`.
- **No salt in the canonical name**: unless the salt IS the INN (e.g., `CONDROITINA SULFATO`).
  - Do **not** apply `normalizar_principio()` to such names — `_SUFIJOS_SAL` would corrupt them.
- **Spanish over English**: `DONEPEZILO` not `DONEPEZIL`; `SITAGLIPTINA` not `SITAGLIPTIN`.
- **No accents**: the database uses uppercase ASCII — `ACIDO` not `ÁCIDO`.
- **Radiopharmaceuticals**: use the final radiopharmaceutical INN with isotope in parentheses — `TECNECIO (99MTC) SESTAMIBI`, not `SESTAMIBI` alone.
- See the full convention list in `CLAUDE.md` under "Auditoría INN — convenciones aprendidas".

### Running an INN audit round

If you are systematically fixing a batch of products:

```bash
# From backend/ with venv activated
python fix_auditoria_concXXX.py --dry-run   # preview changes
python fix_auditoria_concXXX.py             # apply changes
```

Always run `--dry-run` first and review the diff before applying.

---

## Code Style

### Python (backend)

- Follow **PEP 8**: 4-space indentation, max line length 99 characters.
- Use **type hints** for all function signatures.
- Docstrings for public functions (Google style preferred).
- Run `flake8` or `ruff` before committing:

```bash
pip install ruff
ruff check backend/
```

- SQL queries use SQLAlchemy `text()` with named bind parameters — do **not** use string interpolation in queries.
- Migrations are manual, managed via `app/migrations.py` (no Alembic). Add new migrations as numbered steps in that file.

### TypeScript / React (frontend)

- Follow the **ESLint** configuration in `frontend/eslint.config.js`.
- Run lint before committing:

```bash
cd frontend
npm run lint
```

- Component files use `.tsx`, utility files use `.ts`.
- Prefer `const` over `let`; avoid `any` types.
- Use Tailwind CSS utility classes — avoid inline `style` attributes.
- Keep components small and focused. Extract reusable logic into custom hooks under `src/hooks/`.

---

## Database (WAL Checkpoint)

SQLite runs in WAL (Write-Ahead Logging) mode. Before committing `backend/openfarma.db`, you **must** flush the WAL file to the main database file:

```bash
python -c "import sqlite3; c=sqlite3.connect('backend/openfarma.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()"
```

If you skip this step, the `-wal` and `-shm` sidecar files may contain uncommitted data that is not included in the git commit, causing the deployed database on Railway to be inconsistent.

This step is required any time `openfarma.db` is modified by a script and you intend to commit the result.
