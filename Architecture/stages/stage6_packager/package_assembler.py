"""Stage 6 — assembles the FullDesignPackage from all upstream stage outputs."""

from __future__ import annotations

from datetime import datetime, timezone

from models.schemas import (
    BuildableZone,
    CadastralData,
    FloorPlanAlternative,
    FullDesignPackage,
    ShoppingItem,
    StageLogEntry,
    VisualizationAssets,
)
from utils.logger import get_logger

_logger = get_logger("package_assembler")


def _log_entry(stage: str, message: str) -> StageLogEntry:
    return StageLogEntry(
        stage=stage,
        message=message,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def assemble(
    *,
    job_id: str,
    cadastral: CadastralData,
    zone: BuildableZone,
    selected_plan: FloorPlanAlternative,
    svg_url: str,
    pdf_url: str,
    building_schema: dict,
    images: dict[str, str],           # keys: exterior, interior, blueprint_2d, floorplan_3d
    walkthrough_script: str,
    shopping_list: list[ShoppingItem],
    video_url: str | None,
    video_skipped_reason: str | None,
    stage_log: list[StageLogEntry],
) -> FullDesignPackage:
    """Assemble and return the complete FullDesignPackage."""

    viz = VisualizationAssets(
        exterior_image_base64=images["exterior"],
        interior_image_base64=images["interior"],
        blueprint_2d_image_base64=images["blueprint_2d"],
        floorplan_3d_image_base64=images["floorplan_3d"],
        blueprint_2d_description=(
            f"2D architectural blueprint of the {selected_plan.variant} floor plan. "
            f"Total built area: {selected_plan.total_built_area_sqft:.0f} sqft. "
            f"Rooms: {', '.join(r.name for r in selected_plan.rooms)}."
        ),
        floorplan_3d_description=(
            f"3D dollhouse perspective of the {selected_plan.variant} floor plan showing "
            f"interior layout with furniture silhouettes."
        ),
        walkthrough_script=walkthrough_script,
        shopping_list=shopping_list,
        video_url=video_url,
        video_skipped_reason=video_skipped_reason,
    )

    stage_log.append(_log_entry("stage6", "Full design package assembled successfully."))

    package = FullDesignPackage(
        job_id=job_id,
        cadastral_data=cadastral,
        buildable_zone=zone,
        selected_plan=selected_plan,
        svg_floor_plan_url=svg_url,
        pdf_report_url=pdf_url,
        building_schema_json=building_schema,
        visualization_assets=viz,
        generation_stages_log=stage_log,
    )

    _logger.info("Package assembled for job %s", job_id)
    return package
