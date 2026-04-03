"""
E2E test fixtures.

Starts the FastAPI API server and the Vite frontend dev server once per
test session, then provides a `loaded_page` fixture that uploads the
reference example.aero so individual tests start with data already shown.

Run:
    pytest e2e/ --headed          # visible browser
    pytest e2e/                   # headless (default)

First-time setup:
    pip install -e ".[dev]"
    playwright install chromium
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
EXAMPLE_AERO = PROJECT_ROOT / "foresight" / "examples" / "example.aero"

_PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
_NPM = "npm.cmd" if sys.platform == "win32" else "npm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_port(host: str, port: int, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"Server on {host}:{port} did not become ready within {timeout}s")


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Session-scoped server fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_server():
    """Start uvicorn on :8000 (skipped if already listening)."""
    if _port_open("localhost", 8000):
        yield "http://localhost:8000"
        return

    proc = subprocess.Popen(
        [_PYTHON, "-m", "uvicorn", "foresight.api:app", "--port", "8000"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port("localhost", 8000)
        yield "http://localhost:8000"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def frontend_server():
    """Start Vite dev server on :5173 (skipped if already listening)."""
    if _port_open("localhost", 5173):
        yield "http://localhost:5173"
        return

    proc = subprocess.Popen(
        [_NPM, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port("localhost", 5173)
        yield "http://localhost:5173"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def app_url(api_server, frontend_server):
    return frontend_server


# ---------------------------------------------------------------------------
# Page fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loaded_page(page, app_url):
    """Fresh page with example.aero already uploaded and overview visible."""
    page.goto(app_url)
    page.locator('input[type="file"]').set_input_files(str(EXAMPLE_AERO))
    page.wait_for_selector(".stat-row", timeout=10_000)
    return page
