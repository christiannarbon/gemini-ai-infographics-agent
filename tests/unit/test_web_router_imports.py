"""Tests that web router modules can be imported independently in a fresh interpreter without circular import errors."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "web.routers.auth",
        "web.routers.pages",
        "web.routers.summaries",
        "web.routers.infographics",
        "web.routers.jobs",
    ],
)
def test_router_isolated_import(module_name: str) -> None:
    # We must run import in a subprocess since importing web.main first would resolve the cycle in-process.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Failed to import {module_name} in isolation.\n"
        f"Stdout:\n{result.stdout}\n"
        f"Stderr:\n{result.stderr}"
    )
