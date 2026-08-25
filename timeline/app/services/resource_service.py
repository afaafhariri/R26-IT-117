"""Resource allocation service for planned construction phases."""

from app.models.schemas import LaborRequirements


def create_resource_allocation_plan(labor: LaborRequirements) -> dict[str, dict]:
    """Assign available labour categories and common equipment to each phase."""

    return {
        "foundation": {
            "masons": min(labor.masons, 4),
            "helpers": min(labor.helpers, 5),
            "equipment": ["concrete_mixer", "excavator"],
        },
        "structure": {
            "masons": min(labor.masons, 6),
            "helpers": min(labor.helpers, 8),
            "carpenters": min(labor.carpenters, 3),
            "equipment": ["concrete_mixer", "scaffolding"],
        },
        "roofing": {
            "masons": min(labor.masons, 3),
            "helpers": min(labor.helpers, 4),
            "carpenters": min(labor.carpenters, 2),
            "equipment": ["scaffolding"],
        },
        "electrical_plumbing": {
            "electricians": min(labor.electricians, 2),
            "plumbers": min(labor.plumbers, 2),
            "helpers": min(labor.helpers, 2),
        },
        "finishing": {
            "painters": min(labor.painters, 3),
            "helpers": min(labor.helpers, 4),
            "masons": min(labor.masons, 2),
        },
    }
