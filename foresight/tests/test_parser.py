"""Test the Foresight parser against the example DSL file."""

from pathlib import Path
from foresight.parser import parse_file
from foresight.models import (
    Qualification, Training, Staff, Task, Duration, ForesightModel,
)

_EXAMPLE = Path(__file__).parent.parent / "examples" / "example.aero"


def _load():
    return parse_file(str(_EXAMPLE))


# -- pytest tests --

def test_parses_without_error():
    model = _load()
    assert isinstance(model, ForesightModel)

def test_qualifications_present():
    model = _load()
    assert len(model.qualifications) > 0
    for q in model.qualifications.values():
        assert isinstance(q, Qualification)
        assert q.name

def test_trainings_present():
    model = _load()
    assert len(model.trainings) > 0
    for t in model.trainings.values():
        assert isinstance(t, Training)
        assert t.renews

def test_staff_present():
    model = _load()
    assert len(model.staff) > 0
    for s in model.staff.values():
        assert isinstance(s, Staff)
        assert s.role in ("certifying", "non_certifying")

def test_tasks_present():
    model = _load()
    assert len(model.tasks) > 0
    for t in model.tasks.values():
        assert isinstance(t, Task)

def test_qualification_fields():
    model = _load()
    q = next(iter(model.qualifications.values()))
    assert q.category in ("licence", "type_rating", "company_authorisation")
    if q.validity:
        assert isinstance(q.validity, Duration)

def test_staff_holds():
    model = _load()
    for s in model.staff.values():
        for h in s.holds:
            assert h.qualification
            assert h.issued is not None

def test_task_window():
    model = _load()
    for t in model.tasks.values():
        if t.window:
            assert t.window.start <= t.window.end


# -- standalone pretty-print --

def _print_model(model):
    print("=" * 60)
    print("PARSE RESULT")
    print("=" * 60)

    print(f"\nQualifications ({len(model.qualifications)}):")
    for name, q in model.qualifications.items():
        print(f"  {name}")
        print(f"    category:       {q.category}")
        print(f"    validity:       {q.validity}")
        print(f"    recency:        {q.recency}")
        print(f"    renewal:        {q.renewal}")
        print(f"    prerequisites:  {q.prerequisites}")
        print(f"    min_experience: {q.min_experience}")

    print(f"\nTraining Definitions ({len(model.trainings)}):")
    for name, t in model.trainings.items():
        print(f"  {name}")
        print(f"    renews:   {t.renews}")
        print(f"    duration: {t.duration}")
        print(f"    type:     {t.type}")
        print(f"    location: {t.location}")
        print(f"    capacity: {t.capacity}")
        print(f"    cost:     {t.cost}")

    print(f"\nStaff ({len(model.staff)}):")
    for name, s in model.staff.items():
        print(f"  {name}")
        print(f"    role:         {s.role}")
        print(f"    base:         {s.base}")
        print(f"    career_start: {s.career_start}")
        print(f"    day_rate:     {s.day_rate}")
        print(f"    holds:")
        for h in s.holds:
            print(f"      {h.qualification} (issued: {h.issued})")
        if s.trainings:
            print(f"    scheduled training:")
            for tr in s.trainings:
                print(f"      {tr.training} (scheduled: {tr.scheduled})")

    print(f"\nTasks ({len(model.tasks)}):")
    for name, t in model.tasks.items():
        print(f"  {name}")
        print(f"    type:     {t.type}")
        print(f"    aircraft: {t.aircraft}")
        print(f"    location: {t.location}")
        if t.window:
            print(f"    window:   {t.window.start} to {t.window.end}")
        if t.requires:
            print(f"    requires:")
            for q in t.requires.qualifications:
                print(f"      qualification: {q}")
            print(f"      role:      {t.requires.role}")
            print(f"      min_staff: {t.requires.min_staff}")
        print(f"    prefer:   {t.prefer}")

    print("\n" + "=" * 60)
    print("PARSE SUCCESSFUL")
    print("=" * 60)


if __name__ == "__main__":
    _print_model(_load())