from datetime import date, datetime


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid date format: {value}. Expected YYYY-MM-DD.") from exc
    raise ValueError(f"Unsupported date value: {value}")


def calculate_planned_percent(planned_start, planned_end, as_of_date=None) -> float:
    start = _to_date(planned_start)
    end = _to_date(planned_end)
    as_of = _to_date(as_of_date) if as_of_date is not None else date.today()

    if end < start:
        raise ValueError("planned_end must be on or after planned_start.")

    if as_of < start:
        return 0.0
    if as_of >= end:
        return 100.0

    total_days = (end - start).days
    if total_days == 0:
        return 100.0

    elapsed_days = (as_of - start).days
    planned_percent = (elapsed_days / total_days) * 100.0
    return round(max(0.1, min(100.0, planned_percent)), 4)


def calculate_spi(planned_percent: float, actual_percent: float) -> float:
    if planned_percent is None or planned_percent <= 0:
        raise ValueError("planned_percent must be greater than 0.")
    return round(actual_percent / planned_percent, 4)


def get_alert_level(spi: float) -> str:
    if spi > 0.85:
        return "NORMAL"
    if spi > 0.70:
        return "WARNING"
    return "CRITICAL"


def calculate_spi_from_schedule(planned_start, planned_end, actual_percent, as_of_date=None) -> dict:
    try:
        actual_percent = float(actual_percent)
    except (TypeError, ValueError) as exc:
        raise ValueError("actual_percent must be a numeric value.") from exc

    if actual_percent < 0 or actual_percent > 100:
        raise ValueError("actual_percent must be between 0 and 100.")

    planned_percent = calculate_planned_percent(planned_start, planned_end, as_of_date=as_of_date)

    if planned_percent == 0.0:
        return {
            "planned_percent": 0.0,
            "actual_percent": actual_percent,
            "spi_value": 1.0,
            "alert_level": "NORMAL",
        }

    spi_value = calculate_spi(planned_percent, actual_percent)
    alert_level = get_alert_level(spi_value)
    return {
        "planned_percent": planned_percent,
        "actual_percent": actual_percent,
        "spi_value": spi_value,
        "alert_level": alert_level,
    }
