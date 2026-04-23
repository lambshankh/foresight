"""
scale_bench.py — Token-scale benchmark for Foresight.

Measures parse and validate performance across scenarios sized by approximate
token count (chars // 4), scaling from ~1 k up to ~100 k tokens.

Parser benchmarks stop at ~50 k tokens; the Earley parser is cubic in the
worst case and becomes the bottleneck well before 100 k tokens. Validator
benchmarks go to 100 k tokens by bypassing the parser and building model
objects directly.

Usage:
    python scale_bench.py            # full suite
    python scale_bench.py --parse    # parser section only
    python scale_bench.py --validate # validator section only
"""

import argparse
import random
import sys
import time
import tracemalloc
from datetime import date, timedelta

from foresight.parser import parse_foresight
from foresight.validator import validate
from foresight.models import (
    Duration, Qualification, Training, HoldsRecord, ScheduledTraining,
    Staff, TimeWindow, Requirements, Task, ForesightModel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def token_estimate(text: str) -> int:
    """Rough token count: 1 token ≈ 4 characters (industry-standard heuristic)."""
    return len(text) // 4


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(1, delta)))


# ---------------------------------------------------------------------------
# Source-text generator (for parser benchmarks)
# ---------------------------------------------------------------------------

def generate_aero(n_quals: int, n_staff: int, n_tasks: int,
                  quals_per_task: int, quals_per_staff: int) -> str:
    """Generate .aero source text for a scenario of the given dimensions."""
    random.seed(42)
    lines: list[str] = []
    qual_names = [f"Qual_{i}" for i in range(n_quals)]
    training_names = [f"Training_{i}" for i in range(n_quals)]

    for name in qual_names:
        lines += [
            f"qualification {name} {{",
            f"    category: licence",
            f"    validity: {random.choice([6, 12, 24])} months",
            f"    recency: {random.choice([30, 90, 180])} days",
            f"    renewal: training",
            f"    prerequisites: []",
            f"    min_experience: none",
            f"}}",
        ]

    for i, name in enumerate(training_names):
        lines += [
            f"training {name} {{",
            f"    renews: {qual_names[i % n_quals]}",
            f"    type: continuation",
            f"}}",
        ]

    for i in range(n_staff):
        held = random.sample(qual_names, min(quals_per_staff, n_quals))
        lines += [
            f"staff Staff_{i} {{",
            f"    role: certifying",
            f"    base: LHR",
            f"    career_start: 2015-01-01",
            f"    day_rate: 400",
        ]
        for q in held:
            issued = random_date(date(2022, 1, 1), date(2024, 6, 1))
            last_used = random_date(issued, date(2025, 1, 1))
            lines += [
                f"    holds {q} {{",
                f"        issued: {issued}",
                f"        last_used: {last_used}",
                f"    }}",
            ]
        lines.append("}")

    for i in range(n_tasks):
        start = random_date(date(2025, 6, 1), date(2025, 12, 1))
        end = start + timedelta(days=random.randint(1, 7))
        required = random.sample(qual_names, min(quals_per_task, n_quals))
        lines += [
            f'task Task_{i} {{',
            f'    description: "Task {i}"',
            f'    type: base_maintenance',
            f'    aircraft: B737',
            f'    location: LHR',
            f'    window {{',
            f'        start: {start}',
            f'        end: {end}',
            f'    }}',
            f'    requires {{',
        ]
        for q in required:
            lines.append(f"        qualification: {q}")
        lines += [
            f"        role: certifying",
            f"        min_staff: 1",
            f"    }}",
            f"    prefer: least_flexible_first",
            f"}}",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Model builder (for validator benchmarks — parser bypassed)
# ---------------------------------------------------------------------------

def build_model(n_quals: int, n_staff: int, n_tasks: int,
                quals_per_task: int, quals_per_staff: int) -> ForesightModel:
    """Build a ForesightModel directly, bypassing the parser."""
    random.seed(42)
    qual_names = [f"Qual_{i}" for i in range(n_quals)]
    training_names = [f"Training_{i}" for i in range(n_quals)]

    qualifications = {
        name: Qualification(
            name=name,
            category="licence",
            validity=Duration(random.choice([6, 12, 24, 36, 60]), "months"),
            recency=Duration(random.choice([30, 60, 90, 180]), "days"),
            renewal="training",
        )
        for name in qual_names
    }

    trainings = {
        name: Training(name=name, renews=qual_names[i % n_quals], type="continuation")
        for i, name in enumerate(training_names)
    }

    staff: dict[str, Staff] = {}
    for i in range(n_staff):
        sname = f"Staff_{i}"
        held_quals = random.sample(qual_names, min(quals_per_staff, n_quals))
        holds = [
            HoldsRecord(
                qualification=q,
                issued=(iss := random_date(date(2021, 1, 1), date(2024, 12, 1))),
                last_used=random_date(iss, date(2025, 5, 1)),
            )
            for q in held_quals
        ]
        scheduled = []
        if random.random() < 0.4:
            tr = random.choice(training_names)
            sched = random_date(date(2025, 3, 1), date(2025, 9, 1))
            scheduled.append(ScheduledTraining(training=tr, scheduled=sched))

        staff[sname] = Staff(
            name=sname,
            role="certifying" if random.random() < 0.7 else "non_certifying",
            base="LHR",
            career_start=date(2015, 1, 1),
            day_rate=random.randint(300, 700),
            holds=holds,
            trainings=scheduled,
        )

    tasks: dict[str, Task] = {}
    for i in range(n_tasks):
        tname = f"Task_{i}"
        start = random_date(date(2025, 6, 1), date(2025, 12, 1))
        tasks[tname] = Task(
            name=tname,
            description=f"Generated task {i}",
            type="base_maintenance",
            aircraft="B737",
            location="LHR",
            window=TimeWindow(start=start, end=start + timedelta(days=random.randint(1, 14))),
            requires=Requirements(
                qualifications=random.sample(qual_names, min(quals_per_task, n_quals)),
                role="certifying",
                min_staff=random.randint(1, max(1, n_staff // 20)),
            ),
            prefer="least_flexible_first",
        )

    return ForesightModel(
        qualifications=qualifications, trainings=trainings, staff=staff, tasks=tasks
    )


def source_token_count(n_quals: int, n_staff: int, n_tasks: int,
                       quals_per_task: int, quals_per_staff: int) -> int:
    """Generate the .aero source text and return the actual token count."""
    src = generate_aero(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)
    return token_estimate(src)


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------

HEADER_WIDTH = 80


def _bar(label: str, char: str = "-") -> str:
    return f"{label}\n{char * HEADER_WIDTH}"


def bench_parse(label: str, n_quals: int, n_staff: int, n_tasks: int,
                quals_per_task: int, quals_per_staff: int) -> None:
    src = generate_aero(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)
    tokens = token_estimate(src)

    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        _model = parse_foresight(src)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(
            f"  {label:<32s}  ~{tokens:>6,} tok  parse={elapsed:7.3f}s"
            f"  mem={peak / 1024 / 1024:5.1f} MB",
            flush=True,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        tracemalloc.stop()
        print(
            f"  {label:<32s}  ~{tokens:>6,} tok  parse={elapsed:7.3f}s"
            f"  ERROR: {exc}",
            flush=True,
        )


def bench_validate(label: str, n_quals: int, n_staff: int, n_tasks: int,
                   quals_per_task: int, quals_per_staff: int) -> None:
    tokens = source_token_count(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)
    model = build_model(n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff)

    tracemalloc.start()
    t0 = time.perf_counter()
    violations = validate(model)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(
        f"  {label:<32s}  ~{tokens:>6,} tok  validate={elapsed:7.3f}s"
        f"  violations={len(violations):6,}  mem={peak / 1024 / 1024:5.1f} MB",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Scenario tables
# ---------------------------------------------------------------------------

# Target token sizes (approximate) and the scenario parameters that produce them.
# Columns: label, n_quals, n_staff, n_tasks, quals_per_task, quals_per_staff
PARSE_SCENARIOS = [
    # label                          quals  staff  tasks  q/task  q/staff  (~tokens)
    ("~1 k tok  (10 staff,  5 tasks)",    5,    10,    5,    3,    3),   # ~1 k
    ("~2 k tok  (25 staff, 10 tasks)",    6,    25,   10,    3,    3),   # ~2 k
    ("~5 k tok  (60 staff, 15 tasks)",    8,    60,   15,    4,    4),   # ~5 k
    ("~10 k tok (120 staff, 25 tasks)",  10,   120,   25,    4,    5),   # ~10 k
    ("~25 k tok (300 staff, 50 tasks)",  12,   300,   50,    4,    5),   # ~25 k
    ("~50 k tok (600 staff, 80 tasks)",  15,   600,   80,    5,    6),   # ~50 k
]

VALIDATE_SCENARIOS = [
    # label                              quals  staff   tasks  q/task  q/staff
    # Actual token counts measured from generated source text.
    ("~1 k tok  ( 10 staff,   5 tasks)",   5,     10,     5,     3,     3),  # ~1.5 k
    ("~5 k tok  ( 45 staff,  12 tasks)",   7,     45,    12,     3,     4),  # ~5 k
    ("~10 k tok ( 85 staff,  18 tasks)",   9,     85,    18,     4,     5),  # ~10 k
    ("~25 k tok (200 staff,  35 tasks)",  11,    200,    35,     4,     5),  # ~25 k
    ("~50 k tok (400 staff,  55 tasks)",  13,    400,    55,     5,     6),  # ~50 k
    ("~75 k tok (600 staff,  75 tasks)",  15,    600,    75,     5,     6),  # ~75 k
    ("~100k tok (800 staff,  95 tasks)",  17,    800,    95,     5,     7),  # ~100 k
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Foresight token-scale benchmark")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--parse", action="store_true", help="Parser section only")
    group.add_argument("--validate", action="store_true", help="Validator section only")
    args = parser.parse_args()

    run_parse = args.parse or not args.validate
    run_validate = args.validate or not args.parse

    print("Foresight Token-Scale Benchmark")
    print(f"Token estimate: chars // 4  |  date: 2026-04-20")
    print("=" * HEADER_WIDTH)
    print()

    if run_parse:
        print(_bar("PARSER  (Earley, from .aero source — capped at ~50 k tokens)"))
        print(f"  {'Scenario':<32s}  {'Tokens':>9}  {'Time':>12}  {'Memory':>10}")
        print(f"  {'-'*32}  {'-'*9}  {'-'*12}  {'-'*10}")
        for label, *scenario_args in PARSE_SCENARIOS:
            bench_parse(label, *scenario_args)
        print()

    if run_validate:
        print(_bar("VALIDATOR  (model objects, parser bypassed — up to ~100 k tokens)"))
        print(f"  {'Scenario':<32s}  {'Tokens':>9}  {'Time':>15}  {'Violations':>10}  {'Memory':>10}")
        print(f"  {'-'*32}  {'-'*9}  {'-'*15}  {'-'*10}  {'-'*10}")
        for label, *scenario_args in VALIDATE_SCENARIOS:
            bench_validate(label, *scenario_args)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
