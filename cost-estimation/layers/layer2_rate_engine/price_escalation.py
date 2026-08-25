"""Price escalation model — projects base rates forward to a target date.

Current implementation is a simple linear monthly escalation.
TODO: Replace the stub with a trained XGBoost time-series model that incorporates
      CCPI (Construction Cost Price Index) and material-specific inflation trends.
"""

import logging
from datetime import date, datetime
from typing import Union

logger = logging.getLogger(__name__)

# Default monthly escalation rate (0.8% per month ≈ ~9.6% per annum)
DEFAULT_MONTHLY_RATE: float = 0.008


def _parse_date(value: Union[str, date, datetime]) -> date:
    """Convert a string or datetime to a date object."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


class PriceEscalationModel:
    """Projects a base unit rate to a future date using monthly escalation.

    Args:
        monthly_rate: Fraction increase per month (default 0.008).
    """

    def __init__(self, monthly_rate: float = DEFAULT_MONTHLY_RATE) -> None:
        self.monthly_rate = monthly_rate

    def predict_escalation(
        self,
        base_rate: float,
        base_date: Union[str, date, datetime],
        target_date: Union[str, date, datetime],
    ) -> float:
        """Project base_rate forward to target_date.

        Args:
            base_rate: Rate in LKR at base_date.
            base_date: Date the base rate is valid from.
            target_date: Date to project the rate to.

        Returns:
            Escalated rate in LKR (never less than base_rate).

        TODO: Replace linear model with XGBoost trained on CCPI time-series data.
        """
        bd = _parse_date(base_date)
        td = _parse_date(target_date)

        if td <= bd:
            return round(base_rate, 2)

        # Fractional months between dates
        months = (td.year - bd.year) * 12 + (td.month - bd.month)
        months += (td.day - bd.day) / 30.0

        escalated = base_rate * (1.0 + self.monthly_rate * months)
        logger.debug(
            "Escalation: base=%.2f months=%.1f rate=%.4f -> %.2f",
            base_rate, months, self.monthly_rate, escalated,
        )
        return round(escalated, 2)

    def escalation_factor(
        self,
        base_date: Union[str, date, datetime],
        target_date: Union[str, date, datetime],
    ) -> float:
        """Return the multiplier alone without applying it to a rate.

        Useful for displaying percentage increase in the cost report.
        """
        bd = _parse_date(base_date)
        td = _parse_date(target_date)
        if td <= bd:
            return 1.0
        months = (td.year - bd.year) * 12 + (td.month - bd.month)
        months += (td.day - bd.day) / 30.0
        return round(1.0 + self.monthly_rate * months, 6)
