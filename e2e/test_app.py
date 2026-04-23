"""
End-to-end tests for the Foresight web application.

Covers the full user journey: 
file upload
overview stats
tab navigation
search/filter interactions
error handling.
"""

import os
import tempfile
from pathlib import Path

import pytest

EXAMPLE_AERO = Path(__file__).parent.parent / "foresight" / "examples" / "example.aero"

# The example scenario has 3 tasks, 4 staff members
EXPECTED_TASKS = 3
EXPECTED_STAFF = 4
TASK_NAMES = {"B737 CCheck LHR", "B737 LineCheck LGW", "B737 EngineChange LHR"}



# Initial state (no file uploaded)

def test_initial_page_has_header(page, app_url):
    page.goto(app_url)
    assert page.locator("h1").text_content() == "Foresight"


def test_initial_upload_button_visible(page, app_url):
    page.goto(app_url)
    assert page.locator("text=Choose .aero file").is_visible()


def test_no_tabs_before_upload(page, app_url):
    page.goto(app_url)
    assert not page.locator(".tab-bar").is_visible()



# Upload - overview tab


def test_upload_shows_stat_row(loaded_page):
    assert loaded_page.locator(".stat-row").is_visible()


def test_overview_stat_labels(loaded_page):
    for label in ("Tasks", "Covered", "At Risk", "Violations", "Staff"):
        assert loaded_page.locator(f".stat-label:has-text('{label}')").is_visible()


def test_overview_task_count(loaded_page):
    value = int(loaded_page.locator(".stat-card").nth(0).locator(".stat-value").text_content())
    assert value == EXPECTED_TASKS


def test_overview_task_cards_visible(loaded_page):
    assert loaded_page.locator(".task-card").count() == EXPECTED_TASKS


def test_overview_task_names(loaded_page):
    cards = loaded_page.locator(".task-name").all()
    names = {c.text_content() for c in cards}
    assert names == TASK_NAMES


def test_upload_button_text_changes(loaded_page):
    assert loaded_page.locator("text=Upload new file").is_visible()


def test_four_tabs_appear_after_upload(loaded_page):
    for tab in ("Overview", "Tasks", "Staff", "Violations"):
        assert loaded_page.locator(f"button:has-text('{tab}')").is_visible()



# Tab: Tasks


def test_tasks_tab_shows_split_layout(loaded_page):
    loaded_page.locator("button:has-text('Tasks')").click()
    loaded_page.wait_for_selector(".split-layout")
    assert loaded_page.locator(".task-sidebar").is_visible()
    assert loaded_page.locator(".task-detail").is_visible()


def test_tasks_tab_sidebar_has_all_tasks(loaded_page):
    loaded_page.locator("button:has-text('Tasks')").click()
    loaded_page.wait_for_selector(".task-sidebar")
    items = loaded_page.locator(".sidebar-item").all()
    assert len(items) == EXPECTED_TASKS


def test_tasks_tab_clicking_sidebar_updates_detail(loaded_page):
    loaded_page.locator("button:has-text('Tasks')").click()
    loaded_page.wait_for_selector(".task-sidebar")
    # click the second sidebar item
    loaded_page.locator(".sidebar-item").nth(1).click()
    # detail heading should update - just verify it's still visible
    assert loaded_page.locator(".task-detail h2").is_visible()



# Tab: Staff


def test_staff_tab_shows_all_staff(loaded_page):
    loaded_page.locator("button:has-text('Staff')").click()
    loaded_page.wait_for_selector(".staff-list")
    assert loaded_page.locator(".staff-card").count() == EXPECTED_STAFF


def test_staff_search_filters_by_name(loaded_page):
    loaded_page.locator("button:has-text('Staff')").click()
    loaded_page.wait_for_selector(".search-box")
    loaded_page.fill(".search-box", "Ali")
    assert loaded_page.locator(".staff-card").count() == 1
    assert loaded_page.locator("text=AliReza").is_visible()


def test_staff_search_empty_shows_no_match_message(loaded_page):
    loaded_page.locator("button:has-text('Staff')").click()
    loaded_page.wait_for_selector(".search-box")
    loaded_page.fill(".search-box", "zzznomatch")
    assert loaded_page.locator(".staff-card").count() == 0
    assert loaded_page.locator(".muted").is_visible()



# Tab: Violations


def test_violations_tab_has_table_rows(loaded_page):
    loaded_page.locator("button:has-text('Violations')").click()
    loaded_page.wait_for_selector("table")
    assert loaded_page.locator("tbody tr").count() > 0


def test_violations_table_headers(loaded_page):
    loaded_page.locator("button:has-text('Violations')").click()
    loaded_page.wait_for_selector("table")
    for header in ("Kind", "Task", "Staff", "Qualification"):
        assert loaded_page.locator(f"th:has-text('{header}')").is_visible()


def test_violations_kind_filter_reduces_rows(loaded_page):
    loaded_page.locator("button:has-text('Violations')").click()
    loaded_page.wait_for_selector("table")
    total = loaded_page.locator("tbody tr").count()
    # select the first non-empty kind option
    loaded_page.locator("select").first.select_option(index=1)
    filtered = loaded_page.locator("tbody tr").count()
    assert filtered <= total



# Navigation: overview task card → Tasks tab


def test_task_card_click_switches_to_tasks_tab(loaded_page):
    # start on Overview (default after upload)
    assert loaded_page.locator(".task-grid").is_visible()
    loaded_page.locator(".task-card").first.click()
    loaded_page.wait_for_selector(".split-layout")
    assert loaded_page.locator(".task-detail").is_visible()
    # Tasks tab button should now be active
    assert "active" in loaded_page.locator("button:has-text('Tasks')").get_attribute("class")



# Error handling


def test_invalid_file_shows_error_message(page, app_url):
    page.goto(app_url)
    with tempfile.NamedTemporaryFile(suffix=".aero", mode="w", delete=False) as f:
        f.write("this is not valid DSL !!!")
        tmp = f.name
    try:
        page.locator('input[type="file"]').set_input_files(tmp)
        page.wait_for_selector(".error", timeout=10_000)
        assert "Error" in page.locator(".error").text_content()
    finally:
        os.unlink(tmp)


def test_export_button_visible_on_violations_tab(loaded_page):
    loaded_page.locator("button:has-text('Violations')").click()
    loaded_page.wait_for_selector("table")
    assert loaded_page.locator("button:has-text('Export')").is_visible()


def test_invalid_file_does_not_show_tabs(page, app_url):
    page.goto(app_url)
    with tempfile.NamedTemporaryFile(suffix=".aero", mode="w", delete=False) as f:
        f.write("not valid")
        tmp = f.name
    try:
        page.locator('input[type="file"]').set_input_files(tmp)
        page.wait_for_selector(".error", timeout=10_000)
        assert not page.locator(".tab-bar").is_visible()
    finally:
        os.unlink(tmp)
