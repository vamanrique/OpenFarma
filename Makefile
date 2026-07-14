# Detecta el intérprete Python del venv según el OS
ifeq ($(OS),Windows_NT)
    PYTHON=.venv/Scripts/python.exe
else
    PYTHON=.venv/bin/python
endif

.PHONY: backend frontend test retrain checkpoint

backend:
	python -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	cd backend && ../$(PYTHON) -m uvicorn app.main:app --reload

frontend:
	cd frontend && npm install && npm run dev

test:
	PYTHONPATH=backend $(PYTHON) -m pytest tests/ -v

retrain:
	$(PYTHON) retrain_invima.py --db openfarma.db

checkpoint:
	$(PYTHON) -c "import sqlite3; c=sqlite3.connect('backend/openfarma.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close(); print('WAL checkpoint OK')"
