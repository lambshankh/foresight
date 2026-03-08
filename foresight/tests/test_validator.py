"""Tests for the temporal validation engine."""

from datetime import date
from pathlib import Path

from foresight.parser import parse_file
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
