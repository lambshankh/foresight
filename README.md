# Foresight

A domain-specific language and temporal validation engine for aviation maintenance staff qualification compliance (EASA Part 66 / Part 145).

## Overview

Foresight lets you describe maintenance tasks, staff qualification records, and scheduling rules in a `.aero` file. The validator checks whether each assigned staff member holds every required qualification — valid, current, and not lapsing during the task window — and returns a ranked eligibility list alongside a structured violation report.

Detected violation kinds: `missing`, `expired`, `expires_during_task`, `not_recent`, `recency_lapses_during_task`, `no_recency_evidence`, `prerequisite_missing`, `prerequisite_expired`, `insufficient_experience`, `insufficient_staff`.

See [foresight/examples/example.aero](foresight/examples/example.aero) for a reference scenario.

## Getting Started

### Backend setup

Requires Python 3.11+.

```bash
python -m venv .venv && pip install -r requirements.txt && pip install -e .
uvicorn foresight.api:app --reload
```

The API runs at `http://localhost:8000`. Upload a `.aero` file via:

```
POST /validate
  Content-Type: multipart/form-data
  Body: file=<.aero file>
```

### Frontend setup

Requires Node.js 18+.

```bash
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. The dashboard has four tabs: Overview, Tasks, Staff, and Violations. It expects the backend at `http://localhost:8000`; change `API_URL` in [frontend/src/App.jsx](frontend/src/App.jsx) if needed.

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite contains 123 tests with 100% coverage. The `e2e/` directory contains 22 Playwright end-to-end tests; these require the backend and frontend to be running first.

## Project Structure

| Path | Description |
|---|---|
| `foresight/__init__.py` | Package entry point |
| `foresight/api.py` | FastAPI application (`POST /validate`) |
| `foresight/models.py` | Dataclass domain model |
| `foresight/parser.py` | Lark transformer → `ForesightModel` |
| `foresight/validator.py` | Temporal validation engine |
| `foresight/grammar.lark` | Lark EBNF grammar (Earley parser) |
| `foresight/examples/` | Reference `.aero` scenarios |
| `foresight/tests/` | Unit tests (pytest) |
| `e2e/` | Playwright end-to-end tests |
| `frontend/src/` | React dashboard (Vite) |
