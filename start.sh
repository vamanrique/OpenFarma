#!/bin/bash
set -e
pip install -r backend/requirements.txt
cd backend
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
