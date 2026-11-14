# Development

## Backend
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --reload --port 8000
```
Check: `curl localhost:8000/health`. Config via env vars in `.env.example` (`APP_ENV`, `CORS_ORIGINS`, `DATA_DIR`).

## Frontend
```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build
```
Set `VITE_API_BASE_URL` (default `http://localhost:8000`) in `frontend/.env`.

## Rules
Interfaces raise `NotYetImplemented` (HTTP 501). Never return fabricated observations or statistics. A pre-Phase-1 backup is in `.backup/`.

## Known gaps
No frontend tests, no CI, empty Dockerfile/compose, empty legacy docs (`docs/api-documentation.md`, `dataset-documentation.md`, `contribution-guide.md`, `shared-architecture.md`).
