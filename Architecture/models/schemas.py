"""Pydantic data contracts for all stages of the C01 pipeline."""

from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Stage 1 — Document Intelligence output
# ---------------------------------------------------------------------------

class CadastralData(BaseModel):
    land_area_perches: float
    land_area_sqft: float
    district: str
    road_access_type: str                        # "main road" | "lane" | "private road"
    gps_coordinates: list[tuple[float, float]]
    sld99_coordinates: list[tuple[float, float]]
    plot_boundary_polygon: list[tuple[float, float]]
    orientation: str                             # "North-facing" | "South-facing" | etc.
    raw_ocr_text: str
    extracted_entities: dict


# ---------------------------------------------------------------------------
# Stage 2 — Regulatory Compliance output
# ---------------------------------------------------------------------------

class BuildableZone(BaseModel):
    buildable_polygon: list[tuple[float, float]]
    buildable_area_sqft: float
    bcr_value: float
    front_setback_ft: float
    rear_setback_ft: float
    side_setbacks_ft: list[float]
    constraints_summary: str


# ---------------------------------------------------------------------------
# Stage 3 — Floor Plan Generation output
# ---------------------------------------------------------------------------

class Room(BaseModel):
    name: str
    width_ft: float
    length_ft: float
    area_sqft: float
    position_x: float
    position_y: float
    adjacencies: list[str]
    has_window: bool
    has_door: bool


class FloorPlanScores(BaseModel):
    space_utilisation: float     # 0–10
    natural_light: float         # 0–10
    adjacency: float             # 0–10
    ventilation: float           # 0–10
    overall: float               # weighted average


class FloorPlanAlternative(BaseModel):
    variant: str                 # "conservative" | "balanced" | "creative"
    temperature_used: float
    rooms: list[Room]
    total_built_area_sqft: float
    scores: FloorPlanScores
    validation_passed: bool
    description: str


# ---------------------------------------------------------------------------
# Stage 5 — Visualization Assets output
# ---------------------------------------------------------------------------

class ShoppingItem(BaseModel):
    name: str
    description: str
    price_range_lkr: str
    category: str                # "furniture" | "lighting" | "flooring" | "fixtures" | "decor"


class VisualizationAssets(BaseModel):
    exterior_image_base64: str
    interior_image_base64: str
    blueprint_2d_image_base64: str
    floorplan_3d_image_base64: str
    blueprint_2d_description: str
    floorplan_3d_description: str
    walkthrough_script: str
    shopping_list: list[ShoppingItem]
    video_url: str | None
    video_skipped_reason: str | None


# ---------------------------------------------------------------------------
# Stage 6 — Full Design Package output
# ---------------------------------------------------------------------------

class StageLogEntry(BaseModel):
    stage: str
    message: str
    timestamp: str


class FullDesignPackage(BaseModel):
    job_id: str
    cadastral_data: CadastralData
    buildable_zone: BuildableZone
    selected_plan: FloorPlanAlternative
    svg_floor_plan_url: str
    pdf_report_url: str
    building_schema_json: dict
    visualization_assets: VisualizationAssets
    generation_stages_log: list[StageLogEntry]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class SelectPlanRequest(BaseModel):
    job_id: str
    selected_variant: str        # "conservative" | "balanced" | "creative"


# ---------------------------------------------------------------------------
# Progress / polling
# ---------------------------------------------------------------------------

class GenerationStatus(BaseModel):
    job_id: str
    current_stage: str
    messages: list[str]
    is_complete: bool
    error: str | None = None
