from collections import Counter, defaultdict
from dataclasses import asdict

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import ForesightError
from .parser import parse_foresight
from .validator import validate, check_references, rank_eligible

app = FastAPI(title="Foresight")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


def _date_str(d):
    return str(d) if d else None


def _serialise_violation(v):
    row = asdict(v)
    row["on_date"] = _date_str(row["on_date"])
    return row



def _build_response(model, violations):
    by_task = defaultdict(list)
    for v in violations:
        by_task[v.task].append(v)

    by_staff = defaultdict(list)
    for v in violations:
        if v.staff:
            by_staff[v.staff].append(v)

    task_eligible_staff = {}
    for task in model.tasks.values():
        if not task.window or not task.requires:
            continue
        non_compliant = {v.staff for v in by_task.get(task.name, []) if v.staff}
        task_eligible_staff[task.name] = [
            s for s in model.staff.values()
            if (not task.requires.role or s.role == task.requires.role)
            and s.name not in non_compliant
        ]

    eligibility_counts = Counter(
        s.name for eligible in task_eligible_staff.values() for s in eligible
    )

    tasks_out = []
    covered = 0
    for task in model.tasks.values():
        if not task.window or not task.requires:
            continue

        task_violations = by_task.get(task.name, [])
        staff_violations = [v for v in task_violations if v.staff]

        ranked = rank_eligible(task_eligible_staff[task.name], task, model, eligibility_counts)

        needed = task.requires.min_staff or 1
        is_covered = len(ranked) >= needed
        if is_covered:
            covered += 1

        tasks_out.append({
            "name": task.name,
            "window": {"start": _date_str(task.window.start), "end": _date_str(task.window.end)},
            "location": task.location,
            "aircraft": task.aircraft,
            "required_quals": list(task.requires.qualifications),
            "min_staff": needed,
            "eligible": [s.name for s in ranked],
            "prefer": task.prefer,
            "status": "covered" if is_covered else "at_risk",
            "violations": [_serialise_violation(v) for v in staff_violations],
        })

    tasks_out.sort(key=lambda t: (0 if t["status"] == "at_risk" else 1, t["name"]))

    task_names = [t["name"] for t in tasks_out]
    staff_out = []
    for s in model.staff.values():
        eligible_for = [t["name"] for t in tasks_out if s.name in t["eligible"]]
        staff_out.append({
            "name": s.name,
            "role": s.role,
            "base": s.base,
            "tasks_eligible": eligible_for,
            "tasks_checked": task_names,
            "violation_count": len(by_staff.get(s.name, [])),
            "violations": [_serialise_violation(v) for v in by_staff.get(s.name, [])],
        })

    all_violations = [_serialise_violation(v) for v in violations]
    by_kind = dict(Counter(v.kind for v in violations))

    return {
        "tasks": tasks_out,
        "staff": staff_out,
        "overview": {
            "total_tasks": len(tasks_out),
            "covered": covered,
            "at_risk": len(tasks_out) - covered,
            "total_staff": len(model.staff),
            "total_violations": len(violations),
            "by_kind": by_kind,
        },
        "violations": all_violations,
    }


@app.post("/validate")
async def validate_plan(file: UploadFile):
    text = (await file.read()).decode()
    try:
        model = parse_foresight(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {e}")

    try:
        check_references(model)
    except ForesightError as e:
        raise HTTPException(status_code=422, detail=f"Semantic error: {e}")

    violations = validate(model)
    return _build_response(model, violations)
