import pytest

from pipeline.spi_calculator import (
    calculate_planned_percent,
    calculate_spi,
    calculate_spi_from_schedule,
    get_alert_level,
)


def test_spi_is_075_for_actual_45_planned_60():
    assert calculate_spi(60, 45) == 0.75


def test_warning_when_spi_075():
    assert get_alert_level(0.75) == "WARNING"


def test_critical_when_spi_065():
    assert get_alert_level(0.65) == "CRITICAL"


def test_error_when_planned_is_zero():
    with pytest.raises(ValueError):
        calculate_spi(0, 45)


def test_planned_percent_before_start_is_min_floor():
    value = calculate_planned_percent("2026-05-10", "2026-05-20", as_of_date="2026-05-09")
    assert value == 0.1


def test_planned_percent_mid_schedule():
    value = calculate_planned_percent("2026-05-10", "2026-05-20", as_of_date="2026-05-15")
    assert value == 50.0


def test_planned_percent_after_end_is_100():
    value = calculate_planned_percent("2026-05-10", "2026-05-20", as_of_date="2026-05-21")
    assert value == 100.0


def test_calculate_spi_from_schedule_returns_fields():
    result = calculate_spi_from_schedule(
        planned_start="2026-05-10",
        planned_end="2026-05-20",
        actual_percent=30,
        as_of_date="2026-05-15",
    )
    assert set(result.keys()) == {"planned_percent", "actual_percent", "spi_value", "alert_level"}


def test_invalid_date_range_raises_error():
    with pytest.raises(ValueError):
        calculate_planned_percent("2026-05-20", "2026-05-10", as_of_date="2026-05-15")
