"""Tests for the temporal validation engine."""

from datetime import date
from pathlib import Path

from foresight.parser import parse_file, parse_foresight
from foresight.models import Duration
from foresight.validator import validate, add_duration, Violation

_EXAMPLE = Path(__file__).parent.parent / "examples" / "example.aero"


def _model():
    return parse_file(str(_EXAMPLE))


def _violations_for(violations, *, task=None, staff=None, kind=None, qualification=None):
    result = violations
    if task:          result = [v for v in result if v.task == task]
    if staff:         result = [v for v in result if v.staff == staff]
    if kind:          result = [v for v in result if v.kind == kind]
    if qualification: result = [v for v in result if v.qualification == qualification]
    return result


# add_duration

def test_add_duration_days():
    assert add_duration(date(2025, 1, 1), Duration(30, "days")) == date(2025, 1, 31)

def test_add_duration_months_no_overflow():
    assert add_duration(date(2025, 1, 15), Duration(3, "months")) == date(2025, 4, 15)

def test_add_duration_months_year_rollover():
    assert add_duration(date(2025, 11, 1), Duration(3, "months")) == date(2026, 2, 1)

def test_add_duration_months_clips_to_end_of_month():
    # Jan 31 + 1 month — Feb doesn't have 31 days
    assert add_duration(date(2025, 1, 31), Duration(1, "months")) == date(2025, 2, 28)

def test_add_duration_years():
    assert add_duration(date(2020, 6, 1), Duration(5, "years")) == date(2025, 6, 1)


# basic sanity

def test_validate_returns_list():
    violations = validate(_model())
    assert isinstance(violations, list)
    assert all(isinstance(v, Violation) for v in violations)

def test_example_has_violations():
    assert len(validate(_model())) > 0


# JohnSmith — CompanyAuth_B1 expired before B737_CCheck
# issued 2023-01-10, validity 24 months → expired 2025-01-10, task starts 2025-09-01

def test_johnsmith_companyauth_expired_for_ccheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_CCheck_LHR", staff="JohnSmith",
        kind="expired", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 1, 10)


# JohnSmith — B737_TypeRating should NOT be flagged for B737_CCheck
# B737_Recurrent scheduled 2025-08-15 (before task window) renews it

def test_johnsmith_b737_typerating_not_expired_after_renewal():
    violations = validate(_model())
    false_alarms = _violations_for(violations,
        task="B737_CCheck_LHR", staff="JohnSmith",
        kind="expired", qualification="B737_TypeRating",
    )
    assert false_alarms == []


# SarahConnor — B737_TypeRating recency lapsed for B737_LineCheck
# renewal resets recency to 2025-03-01, +90 days = lapsed 2025-05-30, task is 2025-06-10

def test_sarah_typerating_not_recent_for_linecheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_LineCheck_LGW", staff="SarahConnor",
        kind="not_recent", qualification="B737_TypeRating",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 5, 30)


# AliReza — should be the one eligible candidate for B737_LineCheck

def test_alireza_eligible_for_linecheck():
    violations = validate(_model())
    assert _violations_for(violations, task="B737_LineCheck_LGW", staff="AliReza") == []

def test_linecheck_not_understaffed():
    violations = validate(_model())
    assert _violations_for(violations, task="B737_LineCheck_LGW", kind="insufficient_staff") == []


# B737_CCheck_LHR — needs 2, nobody qualifies (John expired, Sarah missing qual, Ali stale recency)

def test_ccheck_understaffed():
    violations = validate(_model())
    matches = _violations_for(violations, task="B737_CCheck_LHR", kind="insufficient_staff")
    assert len(matches) == 1
    assert "2" in matches[0].detail


# AliReza — CompanyAuth_B1 recency lapsed just before B737_EngineChange
# last_used 2025-03-15, +6 months = lapsed 2025-09-15, task starts 2025-10-01

def test_alireza_companyauth_not_recent_for_engine_change():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_EngineChange_LHR", staff="AliReza",
        kind="not_recent", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1
    assert matches[0].on_date == date(2025, 9, 15)


# missing qualification is reported, not silently skipped

def test_sarah_missing_companyauth_for_ccheck():
    violations = validate(_model())
    matches = _violations_for(violations,
        task="B737_CCheck_LHR", staff="SarahConnor",
        kind="missing", qualification="CompanyAuth_B1",
    )
    assert len(matches) == 1


# -- phase 2: new violation kinds --

# DD22: no_recency_evidence

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
    # Alice holds Qual_A but has no last_used — recency cannot be verified
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


# DD25: renewal type matching

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
    duration: 3 days
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
    duration: 3 days
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
    # RetestCourse is type retest — matches renewal requirement
    # renewed on 2025-05-15, +12 months = valid until 2026-05-15
    model = parse_foresight(dsl)
    violations = validate(model)
    matches = _violations_for(violations, kind="expired", qualification="TypeRating")
    assert matches == []


# recency_lapses_during_task

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


# DD23: prerequisite_expired

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
    # BaseQual issued 2023-01-01, validity 12 months → expired 2024-01-01
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
    matches = _violations_for(violations, kind="prerequisite_expired", qualification="AdvancedQual")
    assert len(matches) == 1
    assert "do not hold" in matches[0].detail


# DD24: insufficient_experience

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
    # Hank started 2022-01-01, needs 5 years → meets requirement 2027-01-01
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
