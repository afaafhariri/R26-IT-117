"""Pydantic data contracts for all stages of the C01 pipeline."""

from __future__ import annotations

from typing import Optional

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
    buildable_area_sqm: float = 0.0
    max_footprint_sqm: float = 0.0
    max_total_built_sqm: float = 0.0
    max_floors: int = 1
    bcr_value: float = 1.0
    front_setback_ft: float = 0.0
    rear_setback_ft: float = 0.0
    side_setbacks_ft: list[float] = []
    constraints_summary: str


# ---------------------------------------------------------------------------
# Stage 3 — Floor Plan Generation output
# ---------------------------------------------------------------------------

class Room(BaseModel):
    name: str
    floor: int = 1
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
    violations: list[str] = []   # reasons validation_passed is False; empty when True
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
    blueprint_2d_description: str
    floorplan_3d_image_base64: str
    floorplan_3d_description: str
    walkthrough_script: str
    shopping_list: list[ShoppingItem]


class VideoAsset(BaseModel):
    video_base64: Optional[str] = None
    skipped: bool
    skip_reason: Optional[str] = None
    minutes_until_available: Optional[int] = None


# ---------------------------------------------------------------------------
# Full Design Package output
# ---------------------------------------------------------------------------

class FullDesignPackage(BaseModel):
    job_id: str
    cadastral_data: CadastralData
    buildable_zone: BuildableZone
    selected_plan: FloorPlanAlternative
    building_schema_json: dict
    visualization_assets: VisualizationAssets
    video: Optional[VideoAsset] = None


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
