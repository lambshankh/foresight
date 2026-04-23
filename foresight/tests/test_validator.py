from datetime import date
from pathlib import Path

import pytest

from foresight.parser import parse_file, parse_foresight
from foresight.models import Duration, ForesightError
from foresight.validator import check_references, validate, add_duration, Violation

_EXAMPLE = Path(__file__).parent.parent / "examples" / "example.aero"


def _model():
    return parse_file(str(_EXAMPLE))


def _violations_for(violations, *, task=None, staff=None, kind=None, qualification=None):
    result = violations
    if task: result = [v for v in result if v.task == task]
    if staff: result = [v for v in result if v.staff == staff]
    if kind: result = [v for v in result if v.kind == kind]
    if qualification: result = [v for v in result if v.qualification == qualification]
    return result


def test_add_duration_days():
    assert add_duration(date(2025, 1, 1), Duration(30, "days")) == date(2025, 1, 31)

def test_add_duration_months_no_overflow():
    assert add_duration(date(2025, 1, 15), Duration(3, "months")) == date(2025, 4, 15)

def test_add_duration_months_year_rollover():
    assert add_duration(date(2025, 11, 1), Duration(3, "months")) == date(2026, 2, 1)

def test_add_duration_months_clips_to_end_of_month():
    # Jan 31 + 1 month - Feb doesn't have 31 days
    assert add_duration(date(2025, 1, 31), Duration(1, "months")) == date(2025, 2, 28)

def test_add_duration_years():
    assert add_duration(date(2020, 6, 1), Duration(5, "years")) == date(2025, 6, 1)


def test_validate_returns_list():
    violations = validate(_model())
    assert isinstance(violations, list)
    assert all(isinstance(v, Violation) for v in violations)

def test_example_has_violations():
    assert len(validate(_model())) > 0


# JohnSmith - CompanyAuth_B1 expired before B737_CCheck
# issued 2023-01-10, validity 24 months → expired 2025-01-10, task starts 2025-09-01

def test_johnsmith_companyauth_expired_for_ccheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_CCheck_LHR", staff="JohnSmith",
        kind="expired", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 1, 10)


# JohnSmith - B737_TypeRating should NOT be flagged for B737_CCheck
# B737_TypeRating_Renewal (retest) scheduled 2025-08-15 renews it; B737_Recurrent is
# continuation-type and is rejected by DD25 (retest-only qual)

def test_johnsmith_b737_typerating_not_expired_after_renewal():
    violations = validate(_model())
    false_alarms = _violations_for(violations,
        task="B737_CCheck_LHR", staff="JohnSmith",
        kind="expired", qualification="B737_TypeRating",
    )
    assert false_alarms == []


# SarahConnor - B737_TypeRating recency lapsed for B737_LineCheck
# renewal resets recency to 2025-03-01, +90 days = lapsed 2025-05-30, task is 2025-06-10

def test_sarah_typerating_not_recent_for_linecheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_LineCheck_LGW", staff="SarahConnor",
        kind="not_recent", qualification="B737_TypeRating",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 5, 30)


# AliReza - should be the one eligible candidate for B737_LineCheck

def test_alireza_eligible_for_linecheck():
    violations = validate(_model())
    assert _violations_for(violations, task="B737_LineCheck_LGW", staff="AliReza") == []

def test_linecheck_not_understaffed():
    violations = validate(_model())
    assert _violations_for(violations, task="B737_LineCheck_LGW", kind="insufficient_staff") == []


# B737_CCheck_LHR - needs 2, nobody qualifies (John expired, Sarah missing qual, Ali stale recency)

def test_ccheck_understaffed():
    violations = validate(_model())
    matches = _violations_for(violations, task="B737_CCheck_LHR", kind="insufficient_staff")
    assert len(matches) == 1
    assert "2" in matches[0].detail


# AliReza - CompanyAuth_B1 recency lapsed just before B737_EngineChange
# last_used 2025-03-15, +6 months = lapsed 2025-09-15, task starts 2025-10-01

def test_alireza_companyauth_not_recent_for_engine_change():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_EngineChange_LHR", staff="AliReza",
        kind="not_recent", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 9, 15)


def test_sarah_missing_companyauth_for_ccheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_CCheck_LHR", staff="SarahConnor",
        kind="missing", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1


def test_no_recency_evidence():
    dsl = """\
qualification Qual_A {
    category: licence
    validity: 60 months
    recency: 90 days
    renewal: training
    prerequisites: []
}
staff Alice {
    role: certifying
    holds Qual_A {
        issued: 2025-01-01
    }
}
task CheckX {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: Qual_A
        min_staff: 1
    }
}
"""
    # Alice holds Qual_A but has no last_used - recency cannot be verified
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="no_recency_evidence", staff="Alice")
    assert len(matches) == 1
    assert "last_used" in matches[0].detail

def test_recency_evidence_present_no_flag():
    dsl = """\
qualification Qual_A {
    category: licence
    validity: 60 months
    recency: 90 days
    renewal: training
    prerequisites: []
}
staff Bob {
    role: certifying
    holds Qual_A {
        issued: 2025-01-01
        last_used: 2025-05-01
    }
}
task CheckY {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: Qual_A
        min_staff: 1
    }
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    assert _violations_for(violations, kind="no_recency_evidence") == []

def test_retest_qual_not_renewed_by_continuation():
    dsl = """\
qualification TypeRating {
    category: type_rating
    validity: 12 months
    recency: 90 days
    renewal: retest
    prerequisites: []
}
training WrongCourse {
    renews: TypeRating
    type: continuation
}
staff Carol {
    role: certifying
    holds TypeRating {
        issued: 2024-01-01
        last_used: 2025-05-01
    }
    training WrongCourse {
        scheduled: 2025-05-15
    }
}
task TaskA {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: TypeRating
        min_staff: 1
    }
}
"""
    # TypeRating requires retest renewal but WrongCourse is continuation
    # issued 2024-01-01 + 12 months = expired 2025-01-01, training ignored
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="expired", qualification="TypeRating")
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 1, 1)

def test_retest_qual_renewed_by_retest_training():
    dsl = """\
qualification TypeRating {
    category: type_rating
    validity: 12 months
    recency: 90 days
    renewal: retest
    prerequisites: []
}
training RetestCourse {
    renews: TypeRating
    type: retest
}
staff Dave {
    role: certifying
    holds TypeRating {
        issued: 2024-01-01
        last_used: 2025-05-01
    }
    training RetestCourse {
        scheduled: 2025-05-15
    }
}
task TaskB {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: TypeRating
        min_staff: 1
    }
}
"""
    # RetestCourse is type retest - matches renewal requirement
    # renewed on 2025-05-15, +12 months = valid until 2026-05-15
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="expired", qualification="TypeRating")
    assert matches == []


def test_expires_during_task():
    dsl = """\
qualification Qual_C {
    category: licence
    validity: 13 months
    renewal: training
    prerequisites: []
}
staff Frank2 {
    role: certifying
    holds Qual_C {
        issued: 2024-01-01
    }
}
task CheckW {
    type: base_maintenance
    window {
        start: 2025-01-15
        end: 2025-02-28
    }
    requires {
        qualification: Qual_C
        min_staff: 1
    }
}
"""
    # issued 2024-01-01 + 13 months = expires 2025-02-01
    # task starts 2025-01-15 (valid), ends 2025-02-28 (expires during)
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="expires_during_task", staff="Frank2")
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 2, 1)


def test_recency_lapses_during_task():
    dsl = """\
qualification Qual_B {
    category: licence
    validity: 60 months
    recency: 10 days
    renewal: training
    prerequisites: []
}
staff Eve {
    role: certifying
    holds Qual_B {
        issued: 2025-01-01
        last_used: 2025-05-25
    }
}
task CheckZ {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: Qual_B
        min_staff: 1
    }
}
"""
    # last_used 2025-05-25 + 10 days = recency expires 2025-06-04
    # task starts 2025-06-01 (ok), ends 2025-06-10 (recency lapses during)
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="recency_lapses_during_task", staff="Eve")
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 6, 4)

def test_prerequisite_expired():
    dsl = """\
qualification BaseQual {
    category: licence
    validity: 12 months
    recency: 6 months
    renewal: training
    prerequisites: []
}
qualification AdvancedQual {
    category: type_rating
    validity: 24 months
    recency: 6 months
    renewal: training
    prerequisites: [BaseQual]
}
staff Frank {
    role: certifying
    holds BaseQual {
        issued: 2023-01-01
        last_used: 2025-01-01
    }
    holds AdvancedQual {
        issued: 2024-06-01
        last_used: 2025-01-01
    }
}
task TaskC {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-15
    }
    requires {
        qualification: AdvancedQual
        min_staff: 1
    }
}
"""
    # BaseQual issued 2023-01-01, validity 12 months, expired 2024-01-01
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="prerequisite_expired", qualification="AdvancedQual")
    assert len(matches) == 1
    assert "BaseQual" in matches[0].detail
    assert matches[0].on_date == date(2024, 1, 1)

def test_prerequisite_not_held():
    dsl = """\
qualification BaseQual {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: []
}
qualification AdvancedQual {
    category: type_rating
    validity: 24 months
    renewal: training
    prerequisites: [BaseQual]
}
staff Grace {
    role: certifying
    holds AdvancedQual {
        issued: 2024-06-01
    }
}
task TaskD {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-15
    }
    requires {
        qualification: AdvancedQual
        min_staff: 1
    }
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="prerequisite_missing", qualification="AdvancedQual")
    assert len(matches) == 1
    assert "do not hold" in matches[0].detail


def test_insufficient_experience():
    dsl = """\
qualification SeniorAuth {
    category: company_authorisation
    validity: 36 months
    renewal: training
    prerequisites: []
    min_experience: 5 years
}
staff Hank {
    role: certifying
    career_start: 2022-01-01
    holds SeniorAuth {
        issued: 2024-06-01
    }
}
task TaskE {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-15
    }
    requires {
        qualification: SeniorAuth
        min_staff: 1
    }
}
"""
    # Hank started 2022-01-01, needs 5 years, meets requirement 2027-01-01
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="insufficient_experience", staff="Hank")
    assert len(matches) == 1
    assert matches[0].on_date == date(2027, 1, 1)

def test_sufficient_experience_no_violation():
    dsl = """\
qualification SeniorAuth {
    category: company_authorisation
    validity: 36 months
    renewal: training
    prerequisites: []
    min_experience: 5 years
}
staff Iris {
    role: certifying
    career_start: 2015-01-01
    holds SeniorAuth {
        issued: 2024-06-01
    }
}
task TaskF {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-15
    }
    requires {
        qualification: SeniorAuth
        min_staff: 1
    }
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    assert _violations_for(violations, kind="insufficient_experience", staff="Iris") == []


from foresight.validator import effective_issued, effective_last_used
from foresight.models import Staff, HoldsRecord, Task, Requirements, TimeWindow, ForesightModel


def test_add_duration_feb29_years_clips_to_feb28():
    # Feb 29 (leap year) + 1 year lands on non-leap, clipped to Feb 28
    assert add_duration(date(2024, 2, 29), Duration(1, "years")) == date(2025, 2, 28)


def test_add_duration_unknown_unit_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown duration unit"):
        add_duration(date(2025, 1, 1), Duration(1, "weeks"))


def test_effective_issued_returns_none_when_not_held():
    staff = Staff(name="X", role="certifying")
    model = ForesightModel()
    assert effective_issued("Q", staff, model, date(2025, 1, 1)) is None


def test_effective_last_used_returns_none_when_not_held():
    staff = Staff(name="X", role="certifying")
    model = ForesightModel()
    assert effective_last_used("Q", staff, model, date(2025, 1, 1)) is None


def test_qual_not_in_model_gracefully_skipped():
    # Staff holds a qual that task requires but it's absent from model.qualifications
    staff = Staff(
        name="Ghost",
        role="certifying",
        holds=[HoldsRecord(qualification="PhantomQual", issued=date(2024, 1, 1))],
    )
    task = Task(
        name="GhostTask",
        window=TimeWindow(start=date(2025, 6, 1), end=date(2025, 6, 5)),
        requires=Requirements(qualifications=["PhantomQual"], min_staff=1),
    )
    model = ForesightModel(staff={"Ghost": staff}, tasks={"GhostTask": task})
    violations = validate(model)
    # qual definition missing=, graceful skip, no per-staff violation
    assert [v for v in violations if v.staff == "Ghost"] == []


def test_task_without_window_produces_no_violations():
    dsl = """\
qualification Q {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: []
}
task NoWindow {
    type: base_maintenance
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    assert [v for v in violations if v.task == "NoWindow"] == []


_SUBSUMPTION_BASE = """\
qualification A1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
qualification B1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
qualification C1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
subsumption {
    B1 subsumes A1
    C1 subsumes B1
}
"""

_SUBSUMPTION_TASK = """\
task TaskX {
    type: base_maintenance
    window { start: 2026-01-01  end: 2026-01-10 }
    requires { qualification: A1  role: certifying  min_staff: 1 }
}
"""


def test_subsumption_satisfies_direct_requirement():
    # Staff holds B1; task requires A1; B1 subsumes A1, no missing violation
    dsl = _SUBSUMPTION_BASE + """\
staff StaffB {
    role: certifying
    holds B1 { issued: 2025-01-01 }
}
""" + _SUBSUMPTION_TASK
    model = parse_foresight(dsl)
    violations = validate(model)
    missing = [v for v in violations if v.kind == "missing" and v.staff == "StaffB"]
    assert missing == []


def test_subsumption_transitivity():
    # Staff holds C1; C1 subsumes B1 subsumes A1; task requires A1,  no missing
    dsl = _SUBSUMPTION_BASE + """\
staff StaffC {
    role: certifying
    holds C1 { issued: 2025-01-01 }
}
""" + _SUBSUMPTION_TASK
    model = parse_foresight(dsl)
    violations = validate(model)
    missing = [v for v in violations if v.kind == "missing" and v.staff == "StaffC"]
    assert missing == []


def test_subsumption_is_not_symmetric():
    # Staff holds A1; task requires B1; A1 does NOT subsume B1, missing
    dsl = _SUBSUMPTION_BASE + """\
staff StaffA {
    role: certifying
    holds A1 { issued: 2025-01-01 }
}
task TaskB1 {
    type: base_maintenance
    window { start: 2026-01-01  end: 2026-01-10 }
    requires { qualification: B1  role: certifying  min_staff: 1 }
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    missing = [v for v in violations if v.kind == "missing"
               and v.staff == "StaffA" and v.qualification == "B1"]
    assert len(missing) == 1


def test_no_subsuming_qual_fails():
    # Staff holds an unrelated qual; neither direct nor subsumed, missing
    dsl = _SUBSUMPTION_BASE + """\
qualification Unrelated {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
staff StaffU {
    role: certifying
    holds Unrelated { issued: 2025-01-01 }
}
""" + _SUBSUMPTION_TASK
    model = parse_foresight(dsl)
    violations = validate(model)
    missing = [v for v in violations if v.kind == "missing"
               and v.staff == "StaffU" and v.qualification == "A1"]
    assert len(missing) == 1


def test_directly_held_qual_normal_checks_still_apply():
    # Staff holds A1 directly but it is expired, normal expired violation
    dsl = _SUBSUMPTION_BASE + """\
staff StaffExpired {
    role: certifying
    holds A1 { issued: 2015-01-01 }
}
""" + _SUBSUMPTION_TASK
    model = parse_foresight(dsl)
    violations = validate(model)
    expired = [v for v in violations if v.kind == "expired"
               and v.staff == "StaffExpired" and v.qualification == "A1"]
    assert len(expired) == 1


def test_subsumption_does_not_check_absent_qual_validity():
    # Staff holds B1 (valid); task only requires A1 (not held, not directly required).
    # No validity check is triggered for A1 (it's absent); no missing either.
    dsl = _SUBSUMPTION_BASE + """\
staff StaffOK {
    role: certifying
    holds B1 { issued: 2025-01-01 }
}
""" + _SUBSUMPTION_TASK
    model = parse_foresight(dsl)
    violations = validate(model)
    a1_violations = [v for v in violations
                     if v.staff == "StaffOK" and v.qualification == "A1"]
    assert a1_violations == []



# check_references - referential integrity tests
# These tests exercise semantic constraints that are independent of temporal
# validation.  The pattern is always: parse (syntax only) then check_references.

_MINIMAL_QUAL = """\
qualification TestQual {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: []
}
"""

_TWO_QUALS = """\
qualification A1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
qualification B1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
"""

_THREE_QUALS = _TWO_QUALS + """\
qualification C1 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
"""


def _check(dsl: str) -> None:
    """Parse dsl then run check_references - helper to keep tests concise."""
    check_references(parse_foresight(dsl))


def test_check_references_passes_on_valid_model():
    _check(_MINIMAL_QUAL)  # should not raise


def test_holds_references_undefined_qualification():
    dsl = _MINIMAL_QUAL + """
staff Alice {
    role: certifying
    holds FakeQual {
        issued: 2025-01-01
    }
}
"""
    with pytest.raises(ForesightError, match="holds qualification 'FakeQual'.*not defined"):
        _check(dsl)


def test_training_renews_undefined_qualification():
    dsl = _MINIMAL_QUAL + """
training SomeCourse {
    renews: NoSuchQual
}
"""
    with pytest.raises(ForesightError, match="renews qualification 'NoSuchQual'.*not defined"):
        _check(dsl)


def test_prerequisite_references_undefined_qualification():
    dsl = """\
qualification A {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: [NonExistent]
}
"""
    with pytest.raises(ForesightError, match="prerequisite 'NonExistent'.*not defined"):
        _check(dsl)


def test_circular_prerequisites():
    dsl = """\
qualification A {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: [B]
}
qualification B {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: [A]
}
"""
    with pytest.raises(ForesightError, match="circular prerequisite"):
        _check(dsl)


def test_task_requires_undefined_qualification():
    dsl = _MINIMAL_QUAL + """
task SomeTask {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-15
    }
    requires {
        qualification: GhostQual
        min_staff: 1
    }
}
"""
    with pytest.raises(ForesightError, match="requires qualification 'GhostQual'.*not defined"):
        _check(dsl)


def test_scheduled_training_references_undefined_training():
    dsl = _MINIMAL_QUAL + """
staff Bob {
    role: certifying
    holds TestQual {
        issued: 2025-01-01
    }
    training FakeCourse {
        scheduled: 2025-07-01
    }
}
"""
    with pytest.raises(ForesightError, match="scheduled training 'FakeCourse'.*not defined"):
        _check(dsl)


def test_window_start_after_end_raises():
    dsl = """\
qualification Q {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: []
}
task BadWindow {
    type: base_maintenance
    window {
        start: 2025-06-15
        end: 2025-06-01
    }
}
"""
    with pytest.raises(ForesightError, match="window start.*after end"):
        _check(dsl)


def test_subsumption_undefined_subsuming_qual():
    dsl = _TWO_QUALS + "subsumption {\n    GhostQual subsumes A1\n}\n"
    with pytest.raises(ForesightError, match="'GhostQual'.*not a defined qualification"):
        _check(dsl)


def test_subsumption_undefined_subsumed_qual():
    dsl = _TWO_QUALS + "subsumption {\n    B1 subsumes GhostTarget\n}\n"
    with pytest.raises(ForesightError, match="'GhostTarget'.*not a defined qualification"):
        _check(dsl)


def test_circular_subsumption_two_nodes():
    dsl = _TWO_QUALS + """\
subsumption {
    A1 subsumes B1
    B1 subsumes A1
}
"""
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        _check(dsl)


def test_circular_subsumption_three_nodes():
    dsl = _THREE_QUALS + """\
subsumption {
    A1 subsumes B1
    B1 subsumes C1
    C1 subsumes A1
}
"""
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        _check(dsl)


def test_self_subsumption():
    dsl = _TWO_QUALS + "subsumption {\n    A1 subsumes A1\n}\n"
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        _check(dsl)


def test_validate_handles_circular_subsumption_gracefully():
    # Call validate() directly (not check_references) with a circular subsumption
    # model to exercise the cycle guard in _subsumption_closure._reach (line 179).
    dsl = _TWO_QUALS + """\
subsumption {
    A1 subsumes B1
    B1 subsumes A1
}
"""
    model = parse_foresight(dsl)
    violations = validate(model)
    assert isinstance(violations, list)


# rank_eligible


from foresight.validator import rank_eligible, min_expiry
from foresight.models import Qualification


def _task(prefer):
    return Task(
        name="T",
        window=TimeWindow(start=date(2026, 1, 1), end=date(2026, 1, 10)),
        requires=Requirements(qualifications=["Q"], min_staff=1),
        prefer=prefer,
    )


def test_rank_eligible_no_prefer_returns_unchanged():
    staff = [Staff(name="B", role="r"), Staff(name="A", role="r")]
    task = _task(None)
    result = rank_eligible(staff, task, ForesightModel(), {})
    assert [s.name for s in result] == ["B", "A"]


def test_rank_eligible_unknown_prefer_returns_unchanged():
    staff = [Staff(name="B", role="r"), Staff(name="A", role="r")]
    result = rank_eligible(staff, _task("unknown_strategy"), ForesightModel(), {})
    assert [s.name for s in result] == ["B", "A"]


def test_rank_least_flexible_first():
    alice = Staff(name="Alice", role="r")
    bob = Staff(name="Bob", role="r")
    # Alice eligible for 3 tasks, Bob for 1 - Bob is less flexible
    counts = {"Alice": 3, "Bob": 1}
    result = rank_eligible([alice, bob], _task("least_flexible_first"), ForesightModel(), counts)
    assert [s.name for s in result] == ["Bob", "Alice"]


def test_rank_most_experience_first():
    alice = Staff(name="Alice", role="r", career_start=date(2015, 1, 1))
    bob = Staff(name="Bob", role="r", career_start=date(2020, 1, 1))
    result = rank_eligible([bob, alice], _task("most_experience_first"), ForesightModel(), {})
    assert [s.name for s in result] == ["Alice", "Bob"]


def test_rank_most_experience_first_none_career_start_sorts_last():
    alice = Staff(name="Alice", role="r", career_start=date(2015, 1, 1))
    unknown = Staff(name="Unknown", role="r", career_start=None)
    result = rank_eligible([unknown, alice], _task("most_experience_first"), ForesightModel(), {})
    assert result[0].name == "Alice"


def test_rank_lowest_cost_first():
    alice = Staff(name="Alice", role="r", day_rate=100.0)
    bob = Staff(name="Bob", role="r", day_rate=200.0)
    result = rank_eligible([bob, alice], _task("lowest_cost_first"), ForesightModel(), {})
    assert [s.name for s in result] == ["Alice", "Bob"]


def test_rank_lowest_cost_none_sorts_last():
    alice = Staff(name="Alice", role="r", day_rate=50.0)
    bob = Staff(name="Bob", role="r", day_rate=None)
    result = rank_eligible([bob, alice], _task("lowest_cost_first"), ForesightModel(), {})
    assert result[0].name == "Alice"


def _expiry_model(alice_issued, bob_issued):
    qual = Qualification(name="Q", category="licence", validity=Duration(12, "months"))
    alice = Staff(name="Alice", role="r", holds=[HoldsRecord(qualification="Q", issued=alice_issued)])
    bob = Staff(name="Bob", role="r", holds=[HoldsRecord(qualification="Q", issued=bob_issued)])
    return ForesightModel(
        qualifications={"Q": qual},
        staff={"Alice": alice, "Bob": bob},
    ), alice, bob


def test_rank_latest_expiry_first():
    # Alice issued 2025-06-01 → expires 2026-06-01; Bob issued 2025-01-01 → expires 2026-01-01
    model, alice, bob = _expiry_model(date(2025, 6, 1), date(2025, 1, 1))
    task = _task("latest_expiry_first")
    result = rank_eligible([bob, alice], task, model, {})
    assert [s.name for s in result] == ["Alice", "Bob"]


def test_rank_earliest_expiry_first():
    model, alice, bob = _expiry_model(date(2025, 6, 1), date(2025, 1, 1))
    task = _task("earliest_expiry_first")
    result = rank_eligible([alice, bob], task, model, {})
    assert [s.name for s in result] == ["Bob", "Alice"]



# FR14: bidirectional renewal type matching


def test_training_qual_not_renewed_by_retest_course():
    dsl = """\
qualification ContQual {
    category: type_rating
    validity: 12 months
    recency: 90 days
    renewal: training
    prerequisites: []
}
training RetestCourse {
    renews: ContQual
    type: retest
}
staff Dan {
    role: certifying
    holds ContQual {
        issued: 2024-01-01
        last_used: 2025-05-01
    }
    training RetestCourse {
        scheduled: 2025-05-15
    }
}
task TaskG {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-10
    }
    requires {
        qualification: ContQual
        min_staff: 1
    }
}
"""
    # ContQual requires training-type renewal; RetestCourse is retest-type → rejected
    # issued 2024-01-01 + 12 months = expired 2025-01-01, retest course not applied
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="expired", qualification="ContQual")
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 1, 1)
