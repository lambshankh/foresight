from collections import Counter, defaultdict
from dataclasses import asdict

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .parser import parse_foresight
from .validator import validate

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
    # group violations by task
    by_task = defaultdict(list)
    for v in violations:
        by_task[v.task].append(v)

    # group violations by staff
    by_staff = defaultdict(list)
    for v in violations:
        if v.staff:
            by_staff[v.staff].append(v)

    # build per-task summaries
    tasks_out = []
    covered = 0
    for task in model.tasks.values():
        if not task.window or not task.requires:
            continue

        task_violations = by_task.get(task.name, [])
        staff_violations = [v for v in task_violations if v.staff]
        non_compliant = set(v.staff for v in staff_violations)

        # figure out who's eligible (right role, no violations)
        eligible = []
        for s in model.staff.values():
            if task.requires.role and s.role != task.requires.role:
                continue
            if s.name not in non_compliant:
                eligible.append(s.name)

        needed = task.requires.min_staff or 1
        is_covered = len(eligible) >= needed
        if is_covered:
            covered += 1

        tasks_out.append({
            "name": task.name,
            "window": {"start": _date_str(task.window.start), "end": _date_str(task.window.end)},
            "location": task.location,
            "aircraft": task.aircraft,
            "required_quals": list(task.requires.qualifications),
            "min_staff": needed,
            "eligible": eligible,
            "status": "covered" if is_covered else "at_risk",
            "violations": [_serialise_violation(v) for v in staff_violations],
        })

    # sort: at-risk tasks first
    tasks_out.sort(key=lambda t: (0 if t["status"] == "at_risk" else 1, t["name"]))

    # build per-staff summaries
    task_names = [t["name"] for t in tasks_out]
    staff_out = []
    for s in model.staff.values():
        eligible_for = [t["name"] for t in tasks_out if s.name in t["eligible"]]
        checked = [t["name"] for t in tasks_out
                   if not t.get("_role") or s.role == t.get("_role")]
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

    violations = validate(model)
    return _build_response(model, violations)
