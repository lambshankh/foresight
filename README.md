# Foresight

Foresight is a domain-specific language (DSL) and validation engine for aviation maintenance scheduling. It checks whether staff assigned to maintenance tasks hold valid, current qualifications — detecting expiry, recency lapses, missing prerequisites, and insufficient staffing over the task window.

## Overview

A `.aero` file declares:

- **Qualifications** — licences and type ratings with validity/recency durations and prerequisite chains
- **Training** — courses that renew qualifications
- **Staff** — engineers with their qualification records and scheduled training
- **Tasks** — maintenance jobs with time windows, required qualifications, and staff preferences
- **Subsumption rules** — e.g. a B1 licence satisfies A1 subcategory requirements

The validator produces a ranked list of eligible staff per task and a report of any violations.

## DSL Syntax

```
qualification EASA_Part66_B1 {
    category: licence
    regulatory_body: "EASA"
    validity: 60 months
    recency: 24 months
    renewal: training
    prerequisites: []
    min_experience: none
}

training B737_Recurrent {
    renews: B737_TypeRating
    type: continuation
}

staff JohnSmith {
    role: certifying
    base: LHR
    career_start: 2015-03-01
    day_rate: 450

    holds EASA_Part66_B1 {
        issued: 2022-03-15
        last_used: 2024-11-20
    }
}

task B737_CCheck_LHR {
    type: base_maintenance
    aircraft: B737
    location: LHR

    window {
        start: 2025-09-01
        end: 2025-09-14
    }

    requires {
        qualification: EASA_Part66_B1
        role: certifying
        min_staff: 2
    }

    prefer: least_flexible_first
}
```

See [foresight/examples/example.aero](foresight/examples/example.aero) for a full scenario.

### Staff preference strategies

| Value | Description |
|---|---|
| `least_flexible_first` | Prioritise staff whose qualifications expire soonest |
| `most_experience_first` | Prioritise staff with the longest career |
| `lowest_cost_first` | Prioritise staff with the lowest day rate |
| `latest_expiry_first` | Prioritise staff whose qualifications expire latest |
| `earliest_expiry_first` | Prioritise staff whose qualifications expire earliest |

## Installation

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

## Running the backend

```bash
uvicorn foresight.api:app --reload
```

The API runs at `http://localhost:8000`. The single endpoint is:

```
POST /validate
  Content-Type: multipart/form-data
  Body: file=<.aero file>
```

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. Upload a `.aero` file to see the validation report across four tabs: Overview, Tasks, Staff, and Violations.

The frontend expects the backend at `http://localhost:8000`. To change this, edit the `API_URL` constant at the top of [frontend/src/App.jsx](frontend/src/App.jsx).

## Running tests

```bash
python -m pytest foresight/tests/ -v
```

## Benchmarking

```bash
python scale_bench.py            # parse + validate
python scale_bench.py --parse    # parse only
python scale_bench.py --validate # validate only
```

## Violation kinds

| Kind | Description |
|---|---|
| `missing` | Staff does not hold a required qualification |
| `expired` | Qualification has passed its validity date |
| `expires_during_task` | Qualification expires before the task ends |
| `not_recent` | Qualification has not been used within its recency window |
| `recency_lapses_during_task` | Recency will lapse before the task ends |
| `no_recency_evidence` | No last-used date recorded |
| `prerequisite_missing` | A prerequisite qualification is not held |
| `prerequisite_expired` | A prerequisite qualification is expired |
| `insufficient_experience` | Staff career start does not meet the min_experience requirement |
| `insufficient_staff` | Fewer eligible staff than min_staff for the task |

## Project structure

```
foresight/
  grammar.lark        Lark EBNF grammar (Earley parser)
  models.py           Dataclass domain model
  parser.py           Lark transformer → ForesightModel
  validator.py        Temporal validation engine
  api.py              FastAPI application
  examples/           Reference .aero scenarios
  tests/              Unit tests (pytest)
frontend/
  src/App.jsx         React dashboard
e2e/
  test_app.py         Playwright end-to-end tests
scale_bench.py        Performance benchmark (parse + validate at scale)
```
