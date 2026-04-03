import io
from pathlib import Path

from fastapi.testclient import TestClient

from foresight.api import app

client = TestClient(app)
_EXAMPLE = Path(__file__).parent.parent / "examples" / "example.aero"


def _post_dsl(dsl: str):
    return client.post(
        "/validate",
        files={"file": ("test.aero", io.BytesIO(dsl.encode()), "text/plain")},
    )


def _post_example():
    with open(_EXAMPLE, "rb") as f:
        return client.post("/validate", files={"file": ("example.aero", f, "text/plain")})


def test_validate_returns_200():
    assert _post_example().status_code == 200


def test_validate_response_keys():
    data = _post_example().json()
    for key in ("tasks", "staff", "violations", "overview"):
        assert key in data


def test_validate_overview_keys():
    overview = _post_example().json()["overview"]
    for key in ("total_tasks", "covered", "at_risk", "total_staff", "total_violations", "by_kind"):
        assert key in overview


def test_validate_example_has_violations():
    data = _post_example().json()
    assert data["overview"]["total_violations"] > 0


def test_validate_task_keys():
    task = _post_example().json()["tasks"][0]
    for key in ("name", "window", "status", "eligible", "violations", "min_staff"):
        assert key in task


def test_validate_staff_keys():
    s = _post_example().json()["staff"][0]
    for key in ("name", "role", "tasks_eligible", "violation_count"):
        assert key in s


def test_validate_violation_on_date_type():
    # Violations with on_date=None should serialise as null, not crash
    violations = _post_example().json()["violations"]
    for v in violations:
        assert v["on_date"] is None or isinstance(v["on_date"], str)


def test_validate_at_risk_before_covered():
    tasks = _post_example().json()["tasks"]
    statuses = [t["status"] for t in tasks]
    seen_covered = False
    for s in statuses:
        if s == "covered":
            seen_covered = True
        if seen_covered:
            assert s == "covered", "at-risk task appeared after a covered task"


def test_validate_parse_error_returns_400():
    resp = _post_dsl("this is not valid DSL !!!")
    assert resp.status_code == 400
    assert "Parse error" in resp.json()["detail"]


_TWO_STAFF_DSL = """\
qualification Q {{
    category: licence
    validity: 24 months
    renewal: training
    prerequisites: []
}}
staff Alpha {{
    role: certifying
    holds Q {{
        issued: 2024-01-01
    }}
}}
staff Beta {{
    role: certifying
    holds Q {{
        issued: 2024-09-01
    }}
}}
task T {{
    type: base_maintenance
    window {{
        start: 2025-06-01
        end: 2025-06-05
    }}
    requires {{
        qualification: Q
        min_staff: 1
    }}
    prefer: {prefer}
}}
"""


def _eligible(prefer: str) -> list[str]:
    resp = _post_dsl(_TWO_STAFF_DSL.format(prefer=prefer))
    assert resp.status_code == 200
    task = next(t for t in resp.json()["tasks"] if t["name"] == "T")
    return task["eligible"]


def test_prefer_latest_expiry_first():
    # Beta expires 2026-09-01, Alpha expires 2026-01-01 → Beta first
    assert _eligible("latest_expiry_first")[0] == "Beta"


def test_prefer_earliest_expiry_first():
    # Alpha expires 2026-01-01 → Alpha first
    assert _eligible("earliest_expiry_first")[0] == "Alpha"


def test_prefer_none_returns_all_eligible():
    dsl = """\
qualification Q {
    category: licence
    validity: 24 months
    renewal: training
    prerequisites: []
}
staff Alice {
    role: certifying
    holds Q {
        issued: 2024-01-01
    }
}
staff Bob {
    role: certifying
    holds Q {
        issued: 2024-01-01
    }
}
task T {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-05
    }
    requires {
        qualification: Q
        min_staff: 1
    }
}
"""
    resp = _post_dsl(dsl)
    assert resp.status_code == 200
    task = next(t for t in resp.json()["tasks"] if t["name"] == "T")
    assert len(task["eligible"]) == 2


def test_min_expiry_qual_no_validity_skipped():
    # qual has no validity → _min_expiry skips it and returns None → fallback sort key used
    dsl = """\
qualification Q {
    category: licence
    renewal: training
    prerequisites: []
}
staff Alpha {
    role: certifying
    holds Q {
        issued: 2024-01-01
    }
}
staff Beta {
    role: certifying
    holds Q {
        issued: 2024-09-01
    }
}
task T {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-05
    }
    requires {
        qualification: Q
        min_staff: 1
    }
    prefer: latest_expiry_first
}
"""
    resp = _post_dsl(dsl)
    assert resp.status_code == 200
    task = next(t for t in resp.json()["tasks"] if t["name"] == "T")
    assert len(task["eligible"]) == 2


def test_min_expiry_no_issued_skipped():
    # holds block with no issued → effective_issued returns None → _min_expiry skips
    dsl = """\
qualification Q {
    category: licence
    validity: 24 months
    renewal: training
    prerequisites: []
}
staff Alpha {
    role: certifying
    holds Q {
        last_used: 2025-01-01
    }
}
task T {
    type: base_maintenance
    window {
        start: 2025-06-01
        end: 2025-06-05
    }
    requires {
        qualification: Q
        min_staff: 1
    }
    prefer: earliest_expiry_first
}
"""
    resp = _post_dsl(dsl)
    assert resp.status_code == 200
    task = next(t for t in resp.json()["tasks"] if t["name"] == "T")
    assert "Alpha" in task["eligible"]


def test_example_covers_least_flexible_first():
    # B737_CCheck_LHR uses least_flexible_first
    tasks = _post_example().json()["tasks"]
    ccheck = next(t for t in tasks if t["name"] == "B737_CCheck_LHR")
    assert ccheck["prefer"] == "least_flexible_first"


def test_example_covers_most_experience_first():
    tasks = _post_example().json()["tasks"]
    linecheck = next(t for t in tasks if t["name"] == "B737_LineCheck_LGW")
    assert linecheck["prefer"] == "most_experience_first"


def test_example_covers_lowest_cost_first():
    tasks = _post_example().json()["tasks"]
    engine = next(t for t in tasks if t["name"] == "B737_EngineChange_LHR")
    assert engine["prefer"] == "lowest_cost_first"


def test_task_without_window_not_in_response():
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
    resp = _post_dsl(dsl)
    assert resp.status_code == 200
    task_names = [t["name"] for t in resp.json()["tasks"]]
    assert "NoWindow" not in task_names
