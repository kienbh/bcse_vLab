# Backend — VJU Hardware Lab Portal

FastAPI 0.110+ on Python 3.11+. Async SQLAlchemy 2 + Alembic + Redis/RQ.

## Local dev

```bash
python -m venv .venv
source .venv/bin/activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

cp ../.env.example ../.env   # then edit values

uvicorn app.main:app --reload --port 8000
```

Health: <http://localhost:8000/api/health> · Docs: <http://localhost:8000/api/docs>

## Tests

```bash
pytest                       # full suite with coverage
pytest -k health             # subset
ruff check . && ruff format --check .
mypy app
```

## Migrations

```bash
alembic revision --autogenerate -m "M1: initial schema"
alembic upgrade head
alembic downgrade -1
```

> M0 ships with no models. Real schema lands in M1 per `docs/04-database-schema.md`.

## Layout

```
app/
├── main.py              # ASGI factory
├── core/
│   ├── config.py        # Settings (pydantic-settings)
│   └── logging.py       # Loguru JSON logger
├── api/routes/          # FastAPI routers (health, auth, devices, ...)
├── models/              # SQLAlchemy ORM (M1+)
├── schemas/             # Pydantic DTOs
└── services/            # business logic (access_control, ssh_manager, plug_controller)
migrations/              # Alembic revisions
tests/                   # pytest
```
