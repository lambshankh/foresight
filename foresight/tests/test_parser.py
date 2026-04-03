from pathlib import Path
import pytest
from foresight.parser import parse_file, parse_foresight, ForesightError
from foresight.models import (
    Qualification, Training, Staff, Task, Duration, ForesightModel,
)

_EXAMPLE = Path(__file__).parent.parent / "examples" / "example.aero"


def _load():
    return parse_file(str(_EXAMPLE))


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


_MINIMAL_QUAL = """\
qualification TestQual {
    category: licence
    validity: 12 months
    renewal: training
    prerequisites: []
}
"""


def test_syntax_error_raises_foresight_error():
    with pytest.raises(ForesightError) as exc_info:
        parse_foresight("qualification Bad {{{")
    assert exc_info.value.line is not None
    assert "expected" in str(exc_info.value) or "unexpected" in str(exc_info.value)

def test_syntax_error_includes_line_number():
    bad = "qualification X {\n    category: licence\n    !!!\n}"
    with pytest.raises(ForesightError) as exc_info:
        parse_foresight(bad)
    assert exc_info.value.line is not None


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
        parse_foresight(dsl)

def test_training_renews_undefined_qualification():
    dsl = _MINIMAL_QUAL + """
training SomeCourse {
    renews: NoSuchQual
}
"""
    with pytest.raises(ForesightError, match="renews qualification 'NoSuchQual'.*not defined"):
        parse_foresight(dsl)

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
        parse_foresight(dsl)

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
        parse_foresight(dsl)

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
        parse_foresight(dsl)

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
        parse_foresight(dsl)

def test_valid_file_passes_semantic_checks():
    model = _load()
    assert len(model.qualifications) > 0


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
        parse_foresight(dsl)


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


def test_subsumption_block_parses():
    dsl = _TWO_QUALS + "subsumption {\n    B1 subsumes A1\n}\n"
    model = parse_foresight(dsl)
    assert "B1" in model.subsumptions
    assert "A1" in model.subsumptions["B1"]


def test_multiple_rules_in_one_block():
    dsl = _THREE_QUALS + """\
qualification A2 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
qualification A3 {
    category: licence
    validity: 60 months
    renewal: training
    prerequisites: []
}
subsumption {
    B1 subsumes A1
    C1 subsumes A2
    C1 subsumes A3
}
"""
    model = parse_foresight(dsl)
    assert model.subsumptions["B1"] == {"A1"}
    assert model.subsumptions["C1"] == {"A2", "A3"}


def test_multiple_subsumption_blocks_merge():
    dsl = _THREE_QUALS + """\
subsumption {
    B1 subsumes A1
}
subsumption {
    C1 subsumes B1
}
"""
    model = parse_foresight(dsl)
    assert "A1" in model.subsumptions.get("B1", set())
    assert "B1" in model.subsumptions.get("C1", set())


def test_no_subsumption_block_defaults_empty():
    model = parse_foresight(_MINIMAL_QUAL)
    assert model.subsumptions == {}


def test_subsumption_undefined_subsuming_qual():
    dsl = _TWO_QUALS + "subsumption {\n    GhostQual subsumes A1\n}\n"
    with pytest.raises(ForesightError, match="'GhostQual'.*not a defined qualification"):
        parse_foresight(dsl)


def test_subsumption_undefined_subsumed_qual():
    dsl = _TWO_QUALS + "subsumption {\n    B1 subsumes GhostTarget\n}\n"
    with pytest.raises(ForesightError, match="'GhostTarget'.*not a defined qualification"):
        parse_foresight(dsl)


def test_circular_subsumption_two_nodes():
    dsl = _TWO_QUALS + """\
subsumption {
    A1 subsumes B1
    B1 subsumes A1
}
"""
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        parse_foresight(dsl)


def test_circular_subsumption_three_nodes():
    dsl = _THREE_QUALS + """\
subsumption {
    A1 subsumes B1
    B1 subsumes C1
    C1 subsumes A1
}
"""
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        parse_foresight(dsl)


def test_self_subsumption():
    dsl = _TWO_QUALS + "subsumption {\n    A1 subsumes A1\n}\n"
    with pytest.raises(ForesightError, match="circular subsumption chain"):
        parse_foresight(dsl)


def test_example_still_parses():
    model = _load()
    assert "EASA_Part66_B1" in model.subsumptions
    assert "EASA_Part66_A1" in model.subsumptions["EASA_Part66_B1"]


from foresight.parser import _format_lark_error
from lark.exceptions import UnexpectedToken, UnexpectedCharacters


def test_format_lark_error_unexpected_token_branch():
    class FakeUnexpectedToken(UnexpectedToken):
        def __init__(self): pass

    exc = FakeUnexpectedToken()
    exc.line = 3
    exc.column = 8
    exc.expected = frozenset({"IDENT", "NUMBER"})
    exc.token = "'keyword'"
    msg, line, col = _format_lark_error(exc)
    assert line == 3
    assert col == 8
    assert "expected" in msg


def test_format_lark_error_unexpected_token_empty_expected():
    class FakeUnexpectedToken(UnexpectedToken):
        def __init__(self): pass

    exc = FakeUnexpectedToken()
    exc.line = 5
    exc.column = 2
    exc.expected = frozenset()
    exc.token = None  # no token → "end of input"
    msg, line, col = _format_lark_error(exc)
    assert "end of input" in msg
    assert "unknown" in msg


def test_format_lark_error_unexpected_chars_empty_allowed():
    class FakeUnexpectedChars(UnexpectedCharacters):
        def __init__(self): pass

    exc = FakeUnexpectedChars()
    exc.line = 2
    exc.column = 5
    exc.char = "@"
    exc.allowed = frozenset()  # empty → hits the "unexpected" branch
    msg, line, col = _format_lark_error(exc)
    assert "unexpected" in msg
    assert line == 2


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
        print(f"    type:     {t.type}")

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