"""Temporal validation engine. Checks staff compliance against task windows."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .models import Duration, ForesightModel


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
            return date(d.year + dur.value, d.month, 28)  # Feb 29 edge case

    raise ValueError(f"Unknown duration unit: {dur.unit!r}")


@dataclass
class Violation:
    kind: str           # "missing" | "expired" | "expires_during_task" | "not_recent" | "insufficient_staff"
    task: str
    staff: Optional[str]
    qualification: Optional[str]
    detail: str
    on_date: Optional[date] = None


def _most_recent_renewal(qual_name, staff, model, before):
    qual = model.qualifications.get(qual_name)
    best = None
    for entry in staff.trainings:
        training = model.trainings.get(entry.training)
        if training and training.renews == qual_name:
            # DD25: renewal type matching
            if qual and qual.renewal == "retest" and training.type != "retest":
                continue
            if entry.scheduled and entry.scheduled <= before:
                if best is None or entry.scheduled > best:
                    best = entry.scheduled
    return best


def _effective_issued(qual_name, staff, model, before):
    held = next((h for h in staff.holds if h.qualification == qual_name), None)
    if held is None:
        return None
    renewal = _most_recent_renewal(qual_name, staff, model, before)
    if renewal and (held.issued is None or renewal > held.issued):
        return renewal
    return held.issued


def _effective_last_used(qual_name, staff, model, before):
    # training completion counts as "use" for recency purposes
    held = next((h for h in staff.holds if h.qualification == qual_name), None)
    if held is None:
        return None
    renewal = _most_recent_renewal(qual_name, staff, model, before)
    candidates = [d for d in (held.last_used, renewal) if d is not None]
    return max(candidates) if candidates else None


def _check_staff_for_task(staff, task, model):
    violations = []
    window_start = task.window.start
    window_end   = task.window.end

    for qual_name in task.requires.qualifications:
        qual = model.qualifications.get(qual_name)
        held = next((h for h in staff.holds if h.qualification == qual_name), None)

        if held is None:
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

        issued = _effective_issued(qual_name, staff, model, window_start)
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

        last_used = _effective_last_used(qual_name, staff, model, window_start)
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
        if qual is not None:
            for prereq_name in qual.prerequisites:
                prereq_qual = model.qualifications.get(prereq_name)
                prereq_held = next((h for h in staff.holds if h.qualification == prereq_name), None)
                if prereq_held is None:
                    violations.append(Violation(
                        kind="prerequisite_expired",
                        task=task.name,
                        staff=staff.name,
                        qualification=qual_name,
                        detail=f"{staff.name}'s {qual_name} depends on {prereq_name} which they do not hold",
                    ))
                elif prereq_qual and prereq_qual.validity:
                    prereq_issued = _effective_issued(prereq_name, staff, model, window_start)
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
        if qual is not None and qual.min_experience and staff.career_start:
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


def validate(model: ForesightModel) -> list[Violation]:
    """Run compliance checks across all tasks. Returns every violation found."""
    all_violations = []

    for task in model.tasks.values():
        if not task.window or not task.requires:
            continue

        eligible = 0
        for staff in model.staff.values():
            if task.requires.role and staff.role != task.requires.role:
                continue
            is_ok, violations = _check_staff_for_task(staff, task, model)
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
