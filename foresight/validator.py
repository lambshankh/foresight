from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .models import Duration, ForesightError, ForesightModel


def add_duration(d: date, dur: Duration) -> date:
    if dur.unit == "days":
        return d + timedelta(days=dur.value)

    if dur.unit == "months":
        total = d.month - 1 + dur.value
        year  = d.year + total // 12
        month = total % 12 + 1
        day   = min(d.day, monthrange(year, month)[1])
        return date(year, month, day)

    if dur.unit == "years":
        try:
            return d.replace(year=d.year + dur.value)
        except ValueError:
            return date(d.year + dur.value, d.month, 28) # feb 29 edge case

    raise ValueError(f"Unknown duration unit: {dur.unit!r}")


@dataclass
class Violation:
    kind: str           # "missing" | "expired" | "expires_during_task"
                        # "not_recent" | "recency_lapses_during_task"
                        # "no_recency_evidence" | "prerequisite_missing" | "prerequisite_expired"
                        # "insufficient_experience" | "insufficient_staff"
    task: str
    staff: Optional[str]
    qualification: Optional[str]
    detail: str
    on_date: Optional[date] = None


def check_references(model: ForesightModel) -> None:
    """Validate referential integrity of a ForesightModel.

    Checks that all names used in the model (qualification references,
    training references, prerequisite chains, subsumption rules, task
    windows) resolve to defined entities and contain no cycles.

    Raises ForesightError if any violations are found.
    """
    errors = []
    qual_names = set(model.qualifications)
    training_names = set(model.trainings)

    for q in model.qualifications.values():
        for p in q.prerequisites:
            if p not in qual_names:
                errors.append(
                    f"qualification '{q.name}': prerequisite '{p}' is not defined")

    completed: set[str] = set()

    def _prereq_cycle(name, path):
        if name in path:
            errors.append("circular prerequisite chain: " + " -> ".join(list(path) + [name]))
            return True
        if name in completed or name not in qual_names:
            return False
        path.add(name)
        for p in model.qualifications[name].prerequisites:
            if _prereq_cycle(p, path):
                return True
        path.discard(name)
        completed.add(name)
        return False

    for name in qual_names:
        _prereq_cycle(name, set())

    for t in model.trainings.values():
        if t.renews and t.renews not in qual_names:
            errors.append(
                f"training '{t.name}': renews qualification '{t.renews}' which is not defined")

    for s in model.staff.values():
        for h in s.holds:
            if h.qualification not in qual_names:
                errors.append(
                    f"staff '{s.name}': holds qualification '{h.qualification}' which is not defined")
        for st in s.trainings:
            if st.training not in training_names:
                errors.append(
                    f"staff '{s.name}': scheduled training '{st.training}' is not defined")

    for t in model.tasks.values():
        if t.requires:
            for qn in t.requires.qualifications:
                if qn not in qual_names:
                    errors.append(
                        f"task '{t.name}': requires qualification '{qn}' which is not defined")
        if t.window and t.window.start > t.window.end:
            errors.append(
                f"task '{t.name}': window start {t.window.start} is after end {t.window.end}")

    for subsuming, subsumed_set in model.subsumptions.items():
        if subsuming not in qual_names:
            errors.append(f"subsumption: '{subsuming}' is not a defined qualification")
        for subsumed in subsumed_set:
            if subsumed not in qual_names:
                errors.append(
                    f"subsumption: '{subsumed}' (subsumed by '{subsuming}') is not a defined qualification")

    sub_completed: set[str] = set()

    def _sub_cycle(name, path):
        if name in path:
            errors.append("circular subsumption chain: " + " -> ".join(list(path) + [name]))
            return True
        if name in sub_completed or name not in model.subsumptions:
            return False
        path.add(name)
        for target in model.subsumptions[name]:
            if _sub_cycle(target, path):
                return True
        path.discard(name)
        sub_completed.add(name)
        return False

    for name in list(model.subsumptions):
        _sub_cycle(name, set())

    if errors:
        raise ForesightError("Semantic errors:\n  " + "\n  ".join(errors))


def most_recent_renewal(qual_name, staff, model, before):
    qual = model.qualifications.get(qual_name)
    best = None
    for entry in staff.trainings:
        training = model.trainings.get(entry.training)
        if training and training.renews == qual_name:
            if qual and qual.renewal and training.type:
                expected = "retest" if qual.renewal == "retest" else "continuation"
                if training.type != expected:
                    continue
            if entry.scheduled and entry.scheduled <= before:
                if best is None or entry.scheduled > best:
                    best = entry.scheduled
    return best


def effective_issued(qual_name, staff, model, before):
    held = next((h for h in staff.holds if h.qualification == qual_name), None)
    if held is None:
        return None
    renewal = most_recent_renewal(qual_name, staff, model, before)
    if renewal and (held.issued is None or renewal > held.issued):
        return renewal
    return held.issued


def effective_last_used(qual_name, staff, model, before):
    held = next((h for h in staff.holds if h.qualification == qual_name), None)
    if held is None:
        return None
    renewal = most_recent_renewal(qual_name, staff, model, before)
    candidates = [d for d in (held.last_used, renewal) if d is not None]
    return max(candidates) if candidates else None


def _subsumption_closure(model: ForesightModel) -> dict[str, set[str]]:
    cache: dict[str, set[str]] = {}

    def _reach(name, visiting=None):
        if name in cache:
            return cache[name]
        if visiting is None:
            visiting = set()
        if name in visiting:
            return set()
        visiting.add(name)
        result = {name}
        for target in model.subsumptions.get(name, set()):
            result |= _reach(target, visiting)
        cache[name] = result
        return result

    for q in model.qualifications:
        _reach(q)
    return cache


def _check_staff_for_task(staff, task, model, subsumption_closure):
    violations = []
    window_start = task.window.start
    window_end   = task.window.end

    for qual_name in task.requires.qualifications:
        qual = model.qualifications.get(qual_name)
        held = next((h for h in staff.holds if h.qualification == qual_name), None)

        if held is None:
            subsuming = next(
                (h for h in staff.holds
                 if qual_name in subsumption_closure.get(h.qualification, set())),
                None
            )
            if subsuming is None:
                violations.append(Violation(
                    kind="missing",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name} does not hold {qual_name}",
                ))
            continue

        if qual is None:
            continue

        issued = effective_issued(qual_name, staff, model, window_start)
        if qual.validity and issued:
            expiry = add_duration(issued, qual.validity)
            if expiry < window_start:
                violations.append(Violation(
                    kind="expired",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name}'s {qual_name} expired on {expiry}",
                    on_date=expiry,
                ))
            elif expiry < window_end:
                violations.append(Violation(
                    kind="expires_during_task",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name}'s {qual_name} expires on {expiry}, before the task ends on {window_end}",
                    on_date=expiry,
                ))

        last_used = effective_last_used(qual_name, staff, model, window_start)
        if qual.recency and last_used is None:
            # DD22: no recency evidence
            violations.append(Violation(
                kind="no_recency_evidence",
                task=task.name,
                staff=staff.name,
                qualification=qual_name,
                detail=f"{staff.name}'s {qual_name} requires recency evidence but has no last_used date",
            ))
        elif qual.recency and last_used:
            recency_expiry = add_duration(last_used, qual.recency)
            if recency_expiry < window_start:
                violations.append(Violation(
                    kind="not_recent",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name}'s {qual_name} recency lapsed on {recency_expiry} (last used {last_used})",
                    on_date=recency_expiry,
                ))
            elif recency_expiry < window_end:
                violations.append(Violation(
                    kind="recency_lapses_during_task",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name}'s {qual_name} recency lapses on {recency_expiry}, before the task ends on {window_end}",
                    on_date=recency_expiry,
                ))

        # DD23: prerequisite enforcement
        for prereq_name in qual.prerequisites:
            prereq_qual = model.qualifications.get(prereq_name)
            prereq_held = next((h for h in staff.holds if h.qualification == prereq_name), None)
            if prereq_held is None:
                violations.append(Violation(
                    kind="prerequisite_missing",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name}'s {qual_name} depends on {prereq_name} which they do not hold",
                ))
            elif prereq_qual and prereq_qual.validity:
                prereq_issued = effective_issued(prereq_name, staff, model, window_start)
                if prereq_issued:
                    prereq_expiry = add_duration(prereq_issued, prereq_qual.validity)
                    if prereq_expiry < window_start:
                        violations.append(Violation(
                            kind="prerequisite_expired",
                            task=task.name,
                            staff=staff.name,
                            qualification=qual_name,
                            detail=f"{staff.name}'s {qual_name} depends on {prereq_name} which expired on {prereq_expiry}",
                            on_date=prereq_expiry,
                        ))

        # DD24: minimum experience
        if qual.min_experience and staff.career_start:
            experience_met = add_duration(staff.career_start, qual.min_experience)
            if experience_met > window_start:
                violations.append(Violation(
                    kind="insufficient_experience",
                    task=task.name,
                    staff=staff.name,
                    qualification=qual_name,
                    detail=f"{staff.name} won't meet {qual_name}'s {qual.min_experience.value} {qual.min_experience.unit} experience requirement until {experience_met}",
                    on_date=experience_met,
                ))

    return len(violations) == 0, violations


def min_expiry(staff, task, model):
    """Return the earliest expiry date across all required qualifications for a staff member."""
    earliest = None
    for qual_name in task.requires.qualifications:
        qual = model.qualifications.get(qual_name)
        if qual is None or qual.validity is None:
            continue
        issued = effective_issued(qual_name, staff, model, task.window.start)
        if issued is None:
            continue
        expiry = add_duration(issued, qual.validity)
        if earliest is None or expiry < earliest:
            earliest = expiry
    return earliest


def rank_eligible(eligible_staff, task, model, eligibility_counts):
    """Sort eligible staff according to the task's prefer strategy."""
    prefer = task.prefer
    if prefer is None:
        return eligible_staff

    if prefer == "least_flexible_first":
        return sorted(eligible_staff, key=lambda s: eligibility_counts.get(s.name, 0))
    if prefer == "most_experience_first":
        return sorted(eligible_staff, key=lambda s: s.career_start or date.max)
    if prefer == "lowest_cost_first":
        return sorted(eligible_staff, key=lambda s: s.day_rate if s.day_rate is not None else float("inf"))
    if prefer == "latest_expiry_first":
        return sorted(eligible_staff, key=lambda s: min_expiry(s, task, model) or date.min, reverse=True)
    if prefer == "earliest_expiry_first":
        return sorted(eligible_staff, key=lambda s: min_expiry(s, task, model) or date.max)
    return eligible_staff


def validate(model: ForesightModel) -> list[Violation]:
    all_violations = []
    closure = _subsumption_closure(model)

    for task in model.tasks.values():
        if not task.window or not task.requires:
            continue

        eligible = 0
        for staff in model.staff.values():
            if task.requires.role and staff.role != task.requires.role:
                continue
            is_ok, violations = _check_staff_for_task(staff, task, model, closure)
            all_violations.extend(violations)
            if is_ok:
                eligible += 1

        needed = task.requires.min_staff or 1
        if eligible < needed:
            all_violations.append(Violation(
                kind="insufficient_staff",
                task=task.name,
                staff=None,
                qualification=None,
                detail=f"Task needs {needed} eligible certifying staff but only {eligible} qualify",
            ))

    return all_violations
