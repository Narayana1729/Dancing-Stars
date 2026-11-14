# NISAR Soil Moisture Change — Backend

FastAPI backend for discovering, processing and analysing NISAR L3 SME2 soil moisture products.

## Setup (Windows, Python 3.11)

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # or requirements.lock.txt for exact versions
copy .env.example .env                                     # then add Earthdata credentials
```

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload
```

- Health: http://localhost:8000/api/v1/health
- Docs:   http://localhost:8000/docs

## Test

```powershell
.venv\Scripts\python -m pytest
```

## Layout

```
app/
  main.py          FastAPI app factory, CORS, router mount
  core/config.py   Settings (env vars / .env)
  api/router.py    Aggregates route modules
  api/routes/      Endpoint modules (health, ...)
  services/        Pipeline logic (discovery, acquisition, extraction, ...)
  schemas/         Pydantic request/response models
tests/
```
