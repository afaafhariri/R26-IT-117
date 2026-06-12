def calculate_spi(planned_percent: float, actual_percent: float) -> float:
    if planned_percent == 0:
        return 0.0
    return round(actual_percent / planned_percent, 4)


def get_alert_level(spi: float) -> str:
    if spi > 0.85:
        return "NORMAL"
    elif spi > 0.70:
        return "WARNING"
    else:
        return "CRITICAL"
