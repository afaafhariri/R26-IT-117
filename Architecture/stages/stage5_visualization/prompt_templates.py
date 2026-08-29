"""Prompt factory functions for Stage 5 Gemini calls.

Every function accepts real data parameters extracted from Stage 1–4 outputs
and returns a fully-formatted string ready to send to the relevant Gemini model.
No placeholder or hardcoded values appear inside the returned strings.
"""

from __future__ import annotations

import math

from models.schemas import Room, ShoppingItem


# ---------------------------------------------------------------------------
# Image prompts — sent to imagen-4.0-generate-001
# ---------------------------------------------------------------------------

def exterior_prompt(
    district: str,
    land_area_sqft: float,
    orientation: str,
    road_access_type: str,
    total_built_area_sqft: float,
    buildable_area_sqft: float,
    floors: int,
) -> str:
    facing = orientation.replace("-facing", "").lower()
    if floors >= 2:
        floor_instruction = (
            f"CRITICAL — {floors}-STOREY HOUSE: this must clearly be a {floors}-storey house, NOT a "
            f"single-storey bungalow. Show a full upper floor with its own row of windows and wall "
            f"height for {floors} levels stacked on top of each other, plus a visible staircase, "
            f"balcony, or upper-floor terrace. A single-storey result is wrong no matter what."
        )
    else:
        floor_instruction = (
            "This is a single-storey (one floor, bungalow-style) house — do not add an upper floor."
        )
    return (
        f"Photorealistic architectural exterior rendering of a modern Sri Lankan residential house "
        f"located in {district} district, Sri Lanka. The house is {facing}-facing with the main "
        f"entrance visible from a {road_access_type}. Total built area is {total_built_area_sqft:.0f} "
        f"square feet on a {land_area_sqft:.0f} square foot plot with {buildable_area_sqft:.0f} sqft "
        f"buildable zone. {floor_instruction} Rendered in golden hour light, late afternoon. "
        f"Tropical Sri Lankan garden surroundings with palm trees, bougainvillea and frangipani. "
        f"Cream or white rendered walls, terracotta or clay roof tiles, wooden window frames. "
        f"Wide driveway from the {road_access_type}. Professional architectural photography, "
        f"35mm lens, sharp focus, high dynamic range."
    )


def interior_prompt(
    living_room_width: float,
    living_room_length: float,
    adjacencies: list[str],
    orientation: str,
) -> str:
    adj_str = ", ".join(adjacencies) if adjacencies else "dining area"
    facing = orientation.replace("-facing", "").lower()
    return (
        f"Photorealistic interior render of a Sri Lankan residential living and dining area. "
        f"Room dimensions: {living_room_width:.0f} feet wide by {living_room_length:.0f} feet long. "
        f"The room is adjacent to: {adj_str}. Large windows face {facing} bringing in natural light. "
        f"Warm Sri Lankan design sensibility: cream walls, dark teak wood furniture, rattan accents, "
        f"terracotta floor tiles, ceiling fan, tropical house plants. Open-plan layout with visible "
        f"connection to adjacent spaces. Professional interior photography, wide-angle lens, "
        f"warm morning light flooding through windows, high resolution."
    )


def _room_layout_lines(rooms: list[Room]) -> str:
    """Describes each room's exact position and adjacencies from the solved layout.

    position_x/position_y/width_ft/length_ft come from the same coordinate
    system used everywhere else in the app (layout solver output) — this is
    the single source of truth for where each room actually sits, so the
    generated image reproduces the real solved layout instead of inventing
    its own arrangement.
    """
    by_floor: dict[int, list[Room]] = {}
    for r in rooms:
        by_floor.setdefault(r.floor or 1, []).append(r)

    sections = []
    for floor_num in sorted(by_floor):
        lines = []
        for r in by_floor[floor_num]:
            x1, y1 = r.position_x, r.position_y
            x2, y2 = r.position_x + r.width_ft, r.position_y + r.length_ft
            adj = ", ".join(r.adjacencies) if r.adjacencies else "none"
            lines.append(
                f"  - {r.name}: occupies the rectangle from ({x1:.0f}ft, {y1:.0f}ft) to "
                f"({x2:.0f}ft, {y2:.0f}ft), measured from the north-west corner of the floor "
                f"(x = east, y = south). Adjacent to: {adj}."
            )
        label = "Ground floor" if floor_num == 1 else f"Floor {floor_num}"
        sections.append(f"{label} layout:\n" + "\n".join(lines))
    return "\n\n".join(sections)


def _plot_outline_lines(plot_polygon: list[tuple[float, float]], land_area_sqft: float) -> str:
    """Describes the plot's true boundary shape in feet, corner by corner, so
    the drawing can show the plot's actual outline — often an irregular
    quadrilateral on a real cadastral plan, not a plain rectangle — instead
    of inventing a generic rectangular garden border, which is all Gemini
    could do without this (it was never told the real shape at all before).

    Coordinates use the same square-footprint approximation used everywhere
    else in this pipeline (dim_ft = sqrt(area)) — this is a relative-shape
    description good enough for an AI image prompt, not a survey-grade
    coordinate transform.
    """
    if not plot_polygon or len(plot_polygon) < 3:
        return ""
    dim_ft = math.sqrt(land_area_sqft) if land_area_sqft > 0 else 30.0
    xs = [p[0] for p in plot_polygon]
    ys = [p[1] for p in plot_polygon]
    x_min, y_min = min(xs), min(ys)
    return " → ".join(
        f"({(x - x_min) * dim_ft:.0f}ft, {(y - y_min) * dim_ft:.0f}ft)"
        for x, y in plot_polygon
    )


def blueprint_2d_prompt(
    rooms: list[Room],
    total_built_area_sqft: float,
    plot_area_sqft: float,
    plot_polygon: list[tuple[float, float]] | None = None,
) -> str:
    room_lines = "\n".join(
        f"  - {r.name}: {r.width_ft:.0f}ft × {r.length_ft:.0f}ft ({r.area_sqft:.0f} sqft)"
        for r in rooms
    )
    layout_lines = _room_layout_lines(rooms)
    labels_list = ", ".join(f'"{r.name.replace("_", " ").title()}"' for r in rooms)
    outline = _plot_outline_lines(plot_polygon or [], plot_area_sqft)
    plot_outline_section = (
        f"PLOT OUTLINE — CRITICAL: the plot boundary is this exact shape, walked corner to corner "
        f"in feet from a reference corner: {outline}. Draw the plot line as this real polygon, "
        f"NOT a plain rectangle — real cadastral plots are often irregular. The building footprint "
        f"sits inside this boundary; any area inside the boundary but outside the building is "
        f"garden, driveway, or margin space. Do not straighten the plot's corners into 90° angles.\n\n"
        if outline else ""
    )
    return (
        f"Highly detailed real-world 2D architectural floor plan drawing, exactly as produced by a "
        f"licensed Sri Lankan architect. White paper background. Black ink. Total built area: "
        f"{total_built_area_sqft:.0f} square feet. Rooms: {room_lines}\n\n"
        f"EXACT LAYOUT — draw rooms in these precise positions, do not rearrange them:\n"
        f"{layout_lines}\n\n"
        f"{plot_outline_section}"
        f"CRITICAL — DRAW EVERY ROOM: all {len(rooms)} rooms listed above must appear on the drawing, "
        f"exactly these labels: {labels_list}. Do not omit any room, do not merge two rooms into one, "
        f"do not substitute a different room in its place. A room missing from the drawing is wrong "
        f"no matter how crowded the plan looks — shrink the drawing scale before you drop a room.\n\n"
        f"WALLS: Exterior walls are thick with diagonal hatch fill (like real architectural drawings). "
        f"Interior partition walls are thinner solid black lines. "
        f"DOORS: Each room has a door shown as a thin quarter-circle arc swing symbol. "
        f"WINDOWS: Shown as three parallel lines on exterior walls. "
        f"FURNITURE: Each room contains accurate top-down furniture symbols — living room has sofa, "
        f"armchair and coffee table; dining room has rectangular dining table with chairs around it; "
        f"kitchen has L-shaped counter with sink symbol and stove burner circles; bedrooms have "
        f"rectangular bed with pillows and wardrobe; bathrooms have toilet, vanity sink and bathtub "
        f"or shower. Furniture drawn in thin black lines, realistic top-view architectural symbols. "
        f"LANDSCAPING: Outside the building footprint — circular tree symbols (ring with cross) placed "
        f"around the perimeter, a garden area labelled GARDEN, straight driveway lines from road. "
        f"DIMENSIONS: Exterior dimension lines with arrows and measurements in feet along all four sides. "
        f"ANNOTATIONS: Room name labels centred in each space in clean uppercase text, area in sqft "
        f"shown below each label in smaller text. "
        f"TITLE BLOCK: Bottom of drawing shows the real plot area — \"PLOT AREA: {plot_area_sqft:.0f} SQFT\". "
        f"Use this exact figure, not an invented width x height — the plot is not necessarily rectangular. "
        f"NORTH ARROW: Standard architectural north arrow symbol in top-right corner. "
        f"OVERALL STYLE: Clean, crisp, professional. Looks exactly like a real architect-drawn "
        f"floor plan you would submit to a Sri Lankan municipal council for approval. "
        f"White background, black lines only, no colour, no shading, no dark backgrounds."
    )


def floorplan_3d_prompt(rooms: list[Room]) -> str:
    """Text-only 3D prompt — fallback for when no 2D blueprint image is available
    to condition on. Includes the exact layout so it's still as consistent as
    possible without a reference image."""
    room_names = ", ".join(r.name for r in rooms)
    layout_lines = _room_layout_lines(rooms)
    return (
        f"3D dollhouse perspective floor plan. Bird's eye isometric view with the roof removed to "
        f"reveal the interior layout. Rooms: {room_names}.\n\n"
        f"EXACT LAYOUT — position rooms according to these precise coordinates, do not invent a "
        f"different arrangement:\n{layout_lines}\n\n"
        f"Cream painted walls, warm oak wood floor "
        f"texture throughout, each room has minimal furniture silhouettes appropriate to the room type "
        f"(bed and wardrobe in bedroom, sofa and coffee table in living room, dining table and chairs "
        f"in dining room, kitchen counter in kitchen, toilet and sink in bathroom). Soft ambient "
        f"lighting from above. Clean architectural illustration style, slight drop shadow on walls, "
        f"room labels in clean sans-serif font."
    )


def floorplan_3d_from_blueprint_prompt(rooms: list[Room]) -> str:
    """3D prompt used together with a locally-rendered plain isometric diagram
    (local_isometric_renderer output) as a reference image — that reference
    already has the correct camera angle AND correct room layout (it's drawn
    directly from the solved coordinates), so this just asks Gemini to
    re-render it with photorealistic materials without changing the
    composition. This is far more reliable than asking Gemini to invent a
    3D camera angle from a flat 2D blueprint — it kept just recoloring the
    flat image instead of actually tilting the perspective.
    """
    room_names = ", ".join(r.name for r in rooms)
    labels_list = ", ".join(f'"{r.name.replace("_", " ").title()}"' for r in rooms)
    return (
        f"The attached image is a plain 3D isometric dollhouse floor plan diagram with the correct "
        f"camera angle and correct room layout already — rooms: {room_names}.\n\n"
        f"Re-render this EXACT SAME image with warm, lightly realistic materials and shading — clean "
        f"and uncluttered, but not flat, bare, or sketch-like either. Keep the identical isometric "
        f"camera angle, identical room positions, identical wall layout, identical proportions shown "
        f"in the reference. Do not change the perspective, do not change the layout, do not rotate the "
        f"view, do not crop or reframe.\n"
        f"MATERIALS — ONE uniform warm wall color across every room (do not vary wall color per room), "
        f"a light natural wood floor with visible grain texture throughout. Keep materials natural and "
        f"understated — no bright per-room color accents, no busy patterns.\n"
        f"FURNITURE — the essential pieces that identify each room type, plus one or two natural extras "
        f"for warmth, not a fully furnished/styled room: a bed with a simple headboard and one nightstand "
        f"in bedrooms, a sofa and a coffee table in living room, a dining table with chairs in dining "
        f"room, a counter and a few cabinets in kitchen, a toilet and sink in bathroom, a car in garage. "
        f"Skip wall art, layered rugs, and small decor clutter — keep each room readable at a glance.\n"
        f"LIGHTING — soft natural daylight with gentle, subtle shadows for a sense of depth. Not flat "
        f"and not dramatic — no harsh glossy reflections, no heavy golden-hour glow.\n\n"
        f"CRITICAL — NO ROOF: the reference image has NO roof, and your output must also have NO roof, "
        f"on every room, with no exceptions. Do not add a roof, ceiling, attic, or any structure above "
        f"the wall tops anywhere in the image, even partially, even over just one or two rooms. This is "
        f"a cutaway dollhouse view seen from directly above the open top of the walls — the interior of "
        f"every single room must be visible from this angle, exactly like the flat-topped reference "
        f"image. Do not invent or add any element that is not present in the reference image.\n\n"
        f"Label every single room with its name in clean sans-serif font — all {len(rooms)} rooms must "
        f"be labeled, exactly these labels: {labels_list}. Do not omit any room's label, do not "
        f"duplicate any label."
    )


# ---------------------------------------------------------------------------
# Text prompts — sent to gemini-2.5-flash
# ---------------------------------------------------------------------------

def walkthrough_script_prompt(
    district: str,
    land_area_perches: float,
    orientation: str,
    road_access_type: str,
    rooms: list[Room],
    total_built_area_sqft: float,
    bcr_value: float,
) -> str:
    room_lines = "\n".join(
        f"- {r.name}: {r.width_ft:.0f}ft × {r.length_ft:.0f}ft"
        for r in rooms
    )
    bcr_pct = bcr_value * 100
    return (
        f"Write a professional Sri Lankan real estate agent room-by-room narration for a "
        f"{land_area_perches:.1f}-perch ({total_built_area_sqft:.0f} sqft built) residential property "
        f"in {district} district, Sri Lanka. The property is {orientation} with access from a "
        f"{road_access_type}. Building coverage ratio is {bcr_pct:.0f}%.\n\n"
        f"Rooms:\n{room_lines}\n\n"
        f"Write the narration in 250–350 words. Tone: warm, aspirational, conversational. "
        f"Walk through each room in a natural flow (entrance → living → dining → kitchen → bedrooms → "
        f"bathrooms). Mention specific room dimensions naturally in the narration. Reference Sri Lankan "
        f"lifestyle — morning light, cross-ventilation, garden views. Suitable for text-to-speech. "
        f"Do not include any headers, bullet points or markdown — plain flowing prose only."
    )


def shopping_list_prompt(rooms: list[Room]) -> str:
    room_names = ", ".join(r.name for r in rooms)
    return (
        f"You are a Sri Lankan interior design consultant. Recommend exactly 5 furniture or material "
        f"items for a new home with these rooms: {room_names}.\n\n"
        f"Return a JSON array with exactly 5 objects. Each object must have these exact keys:\n"
        f'  "name": string — product name\n'
        f'  "description": string — 1-sentence description\n'
        f'  "price_range_lkr": string — price range in Sri Lankan Rupees (e.g. "LKR 45,000 – 85,000")\n'
        f'  "category": string — one of: furniture | lighting | flooring | fixtures | decor\n\n'
        f"Rules: prices must be realistic LKR amounts for Sri Lanka (not USD). "
        f"Cover at least 3 different categories. Return raw JSON array only, no markdown, no explanation."
    )
