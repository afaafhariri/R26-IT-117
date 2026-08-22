"""
XSS regression guard for the frontend.

The frontend renders server-supplied strings (validation errors echoing user
input, RAG case text, phase names originating from POST /schedule). Building
that markup with `innerHTML = `...${value}...`` turns any of those into an
injection point. These tests fail the build if that pattern comes back.

Static/lint-style checks: there is no JS test runner in this project, so this
runs in pytest instead of adding a whole frontend toolchain.
"""

import os
import re

import pytest

FRONTEND = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
    "index.html",
)


def _frontend_source() -> str:
    if not os.path.exists(FRONTEND):
        # The Docker build context is ./performance, so frontend/ is not
        # present inside the container image - skip rather than fail there.
        pytest.skip("frontend/index.html not available in this context")
    with open(FRONTEND, "r", encoding="utf-8") as f:
        return f.read()


def test_no_interpolated_innerhtml_assignments():
    """
    Flags `x.innerHTML = `...${...}...`` - a template literal containing an
    interpolation assigned to innerHTML. Static strings are fine (e.g.
    clearing with innerHTML = "").
    """
    src = _frontend_source()
    offenders = re.findall(r"\.innerHTML\s*=\s*`[^`]*\$\{[^`]*`", src, re.DOTALL)
    assert not offenders, (
        f"{len(offenders)} interpolated innerHTML assignment(s) found - use "
        "textContent / createElement for server-supplied data instead:\n"
        + "\n---\n".join(o[:180] for o in offenders)
    )


def test_no_innerhtml_concatenation_with_variables():
    """Flags `x.innerHTML = "..." + something` string concatenation."""
    src = _frontend_source()
    offenders = re.findall(r"\.innerHTML\s*=\s*[\"'][^\"']*[\"']\s*\+", src)
    assert not offenders, f"innerHTML built by concatenation: {offenders}"


def test_escape_helper_is_defined():
    """A shared text-escaping/DOM helper should exist and be used."""
    src = _frontend_source()
    assert "function setText" in src or "function escapeHtml" in src, (
        "Expected a shared safe-text helper (setText/escapeHtml) in the frontend."
    )
