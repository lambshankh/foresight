"""
Scaling benchmark for Foresight.

Measures parse and validate times separately across increasing scenario sizes.
Builds model objects directly for large scenarios (Earley parser is O(n^3) worst
case, so we don't want parsing to mask the validator's scaling behaviour).

Usage: python bench.py
"""

import random
import time
import tracemalloc
from datetime import date, timedelta

from foresight.parser import parse_foresight
from foresight.validator import validate
from foresight.models import (
    Duration, Qualification, Training, HoldsRecord, ScheduledTraining,
    Staff, TimeWindow, Requirements, Task, ForesightModel,
)


def random_date(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(1, delta)))


def build_model(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff):
    """Build a ForesightModel directly, bypassing the parser."""
    random.seed(42)

    qual_names = [f"Qual_{i}" for i in range(n_quals)]
    training_names = [f"Training_{i}" for i in range(n_quals)]

    qualifications = {}
    for name in qual_names:
        qualifications[name] = Qualification(
            name=name,
            category="licence",
            validity=Duration(random.choice([6, 12, 24, 36, 60]), "months"),
            recency=Duration(random.choice([30, 60, 90, 180]), "days"),
            renewal="training",
        )

    trainings = {}
    for i, name in enumerate(training_names):
        trainings[name] = Training(
            name=name,
            renews=qual_names[i % n_quals],
            duration=Duration(3, "days"),
            type="continuation",
            location="LHR",
            capacity=10,
            cost=3000,
        )

    staff = {}
    for i in range(n_staff):
        sname = f"Staff_{i}"
        role = "certifying" if random.random() < 0.7 else "non_certifying"
        held_quals = random.sample(qual_names, min(quals_per_staff, n_quals))
        holds = []
        for q in held_quals:
            issued = random_date(date(2021, 1, 1), date(2024, 12, 1))
            last_used = random_date(issued, date(2025, 5, 1))
            holds.append(HoldsRecord(qualification=q, issued=issued, last_used=last_used))

        scheduled = []
        if random.random() < 0.4:
            tr = random.choice(training_names)
            sched = random_date(date(2025, 3, 1), date(2025, 9, 1))
            scheduled.append(ScheduledTraining(training=tr, scheduled=sched))

        staff[sname] = Staff(
            name=sname, role=role, base="LHR",
            career_start=date(2015, 1, 1),
            day_rate=random.randint(300, 700),
            holds=holds, trainings=scheduled,
        )

    tasks = {}
    for i in range(n_tasks):
        tname = f"Task_{i}"
        start = random_date(date(2025, 6, 1), date(2025, 12, 1))
        end = start + timedelta(days=random.randint(1, 14))
        required = random.sample(qual_names, min(quals_per_task, n_quals))
        min_staff = random.randint(1, max(1, n_staff // 20))

        tasks[tname] = Task(
            name=tname, description=f"Generated task {i}",
            type="base_maintenance", aircraft="B737", location="LHR",
            window=TimeWindow(start=start, end=end),
            requires=Requirements(qualifications=required, role="certifying", min_staff=min_staff),
            prefer="least_flexible_first",
        )

    return ForesightModel(qualifications=qualifications, trainings=trainings, staff=staff, tasks=tasks)


def generate_aero_small(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff):
    """Generate .aero source text for small scenarios to benchmark the parser."""
    random.seed(42)
    lines = []
    qual_names = [f"Qual_{i}" for i in range(n_quals)]
    training_names = [f"Training_{i}" for i in range(n_quals)]

    for name in qual_names:
        lines.append(f'qualification {name} {{')
        lines.append(f'    category: licence')
        lines.append(f'    validity: {random.choice([6, 12, 24])} months')
        lines.append(f'    recency: {random.choice([30, 90, 180])} days')
        lines.append(f'    renewal: training')
        lines.append(f'    prerequisites: []')
        lines.append(f'    min_experience: none')
        lines.append(f'}}')

    for i, name in enumerate(training_names):
        lines.append(f'training {name} {{')
        lines.append(f'    renews: {qual_names[i % n_quals]}')
        lines.append(f'    duration: 3 days')
        lines.append(f'    type: continuation')
        lines.append(f'    location: LHR')
        lines.append(f'    capacity: 10')
        lines.append(f'    cost: 3000')
        lines.append(f'}}')

    for i in range(n_staff):
        lines.append(f'staff Staff_{i} {{')
        lines.append(f'    role: certifying')
        lines.append(f'    base: LHR')
        lines.append(f'    career_start: 2015-01-01')
        lines.append(f'    day_rate: 400')
        for q in random.sample(qual_names, min(quals_per_staff, n_quals)):
            issued = random_date(date(2022, 1, 1), date(2024, 6, 1))
            last_used = random_date(issued, date(2025, 1, 1))
            lines.append(f'    holds {q} {{')
            lines.append(f'        issued: {issued}')
            lines.append(f'        last_used: {last_used}')
            lines.append(f'    }}')
        lines.append(f'}}')

    for i in range(n_tasks):
        start = random_date(date(2025, 6, 1), date(2025, 12, 1))
        end = start + timedelta(days=random.randint(1, 7))
        required = random.sample(qual_names, min(quals_per_task, n_quals))
        lines.append(f'task Task_{i} {{')
        lines.append(f'    description: "Task {i}"')
        lines.append(f'    type: base_maintenance')
        lines.append(f'    aircraft: B737')
        lines.append(f'    location: LHR')
        lines.append(f'    window {{')
        lines.append(f'        start: {start}')
        lines.append(f'        end: {end}')
        lines.append(f'    }}')
        lines.append(f'    requires {{')
        for q in required:
            lines.append(f'        qualification: {q}')
        lines.append(f'        role: certifying')
        lines.append(f'        min_staff: 1')
        lines.append(f'    }}')
        lines.append(f'    prefer: least_flexible_first')
        lines.append(f'}}')

    return '\n'.join(lines)


def bench_parse(label, n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff):
    src = generate_aero_small(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)
    t0 = time.perf_counter()
    model = parse_foresight(src)
    elapsed = time.perf_counter() - t0
    print(f"  {label:30s}  parse={elapsed:7.3f}s  (src={len(src):,} chars)", flush=True)
    return model


def bench_validate(label, n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff):
    model = build_model(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)
    tracemalloc.start()
    t0 = time.perf_counter()
    violations = validate(model)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"  {label:30s}  validate={elapsed:7.3f}s  "
          f"violations={len(violations):6d}  "
          f"mem={peak / 1024 / 1024:6.1f}MB", flush=True)


def main():
    print("Foresight Scaling Benchmark")
    print()

    # --- parser scaling ---
    print("PARSER (Earley, from .aero source)")
    print("-" * 70)
    parse_scenarios = [
        ("4 staff, 3 tasks",        4, 4,   3, 3, 3),
        ("20 staff, 10 tasks",      6, 20, 10, 3, 4),
        ("50 staff, 15 tasks",      6, 50, 15, 3, 4),
        ("100 staff, 20 tasks",     8, 100, 20, 4, 5),
        ("200 staff, 30 tasks",     8, 200, 30, 4, 5),
    ]
    for label, *args in parse_scenarios:
        bench_parse(label, *args)

    print()

    # --- validator scaling ---
    print("VALIDATOR (from model objects, parser bypassed)")
    print("-" * 70)
    validate_scenarios = [
        # label                      quals  staff  tasks  q/task  q/staff
        ("4 staff, 3 tasks",           4,      4,     3,     3,      3),
        ("50 staff, 10 tasks",         6,     50,    10,     3,      4),
        ("200 staff, 30 tasks",        8,    200,    30,     4,      5),
        ("500 staff, 50 tasks",       10,    500,    50,     4,      6),
        ("1k staff, 100 tasks",       12,   1000,   100,     5,      7),
        ("2k staff, 200 tasks",       15,   2000,   200,     5,      8),
        ("5k staff, 500 tasks",       20,   5000,   500,     6,     10),
        ("10k staff, 1k tasks",       20,  10000,  1000,     6,     10),
    ]
    for label, *args in validate_scenarios:
        bench_validate(label, *args)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
