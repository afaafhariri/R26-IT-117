"""
Regression tests for homeowner-facing phase status derivation.

Guards the bug where every phase of every project displayed as "complete"
purely because its planned end date had passed - even with zero recorded
progress - which made the dashboard contradict itself (all phases complete,
yet SPI CRITICAL).
"""

from datetime import date

from monitoring.dashboard_feed import (
    STATUS_AT_RISK,
    STATUS_COMPLETED,
    STATUS_NOT_STARTED,
    STATUS_ON_TRACK,
    STATUS_OVERDUE,
    derive_phase_status,
)

TODAY = date(2026, 8, 21)
PAST = "2024-11-11"
FUTURE = "2027-01-01"


# --- The core regression: dates alone must never imply completion ---

def test_past_end_date_with_zero_progress_is_overdue_not_complete():
    assert derive_phase_status(PAST, actual_percent=0, alert_level=None, as_of=TODAY) == STATUS_OVERDUE


def test_past_end_date_with_no_progress_recorded_is_overdue_not_complete():
    assert derive_phase_status(PAST, actual_percent=None, alert_level=None, as_of=TODAY) == STATUS_OVERDUE


def test_past_end_date_with_partial_progress_is_overdue():
    assert derive_phase_status(PAST, actual_percent=45, alert_level="CRITICAL", as_of=TODAY) == STATUS_OVERDUE


def test_zero_progress_can_never_be_completed():
    for end in (PAST, FUTURE, None):
        for alert in (None, "NORMAL", "WARNING", "CRITICAL"):
            assert derive_phase_status(end, 0, alert, as_of=TODAY) != STATUS_COMPLETED
            assert derive_phase_status(end, None, alert, as_of=TODAY) != STATUS_COMPLETED


# --- Completion comes only from real recorded progress ---

def test_full_progress_is_completed_even_if_past_end_date():
    assert derive_phase_status(PAST, actual_percent=100, alert_level=None, as_of=TODAY) == STATUS_COMPLETED


def test_full_progress_is_completed_before_end_date():
    assert derive_phase_status(FUTURE, actual_percent=100, alert_level="CRITICAL", as_of=TODAY) == STATUS_COMPLETED


# --- In-window states ---

def test_no_progress_within_window_is_not_started():
    assert derive_phase_status(FUTURE, actual_percent=None, alert_level=None, as_of=TODAY) == STATUS_NOT_STARTED


def test_progress_with_healthy_spi_is_on_track():
    assert derive_phase_status(FUTURE, actual_percent=40, alert_level="NORMAL", as_of=TODAY) == STATUS_ON_TRACK


def test_progress_with_no_spi_yet_is_on_track():
    assert derive_phase_status(FUTURE, actual_percent=40, alert_level=None, as_of=TODAY) == STATUS_ON_TRACK


def test_progress_with_warning_spi_is_at_risk():
    assert derive_phase_status(FUTURE, actual_percent=40, alert_level="WARNING", as_of=TODAY) == STATUS_AT_RISK


def test_progress_with_critical_spi_is_at_risk():
    assert derive_phase_status(FUTURE, actual_percent=40, alert_level="CRITICAL", as_of=TODAY) == STATUS_AT_RISK


def test_missing_planned_end_does_not_crash():
    assert derive_phase_status(None, actual_percent=10, alert_level="NORMAL", as_of=TODAY) == STATUS_ON_TRACK
