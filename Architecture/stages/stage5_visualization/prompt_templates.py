"""Prompt factory functions for Stage 5 Gemini calls.

Every function accepts real data parameters extracted from Stage 1–4 outputs
and returns a fully-formatted string ready to send to the relevant Gemini model.
No placeholder or hardcoded values appear inside the returned strings.
"""

from __future__ import annotations

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
    return (
        f"Photorealistic architectural exterior rendering of a modern Sri Lankan residential house "
        f"located in {district} district, Sri Lanka. The house is {facing}-facing with the main "
        f"entrance visible from a {road_access_type}. Total built area is {total_built_area_sqft:.0f} "
        f"square feet on a {land_area_sqft:.0f} square foot plot with {buildable_area_sqft:.0f} sqft "
        f"buildable zone. The house has {floors} floor(s). Rendered in golden hour light, late afternoon. "
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


def blueprint_2d_prompt(
    rooms: list[Room],
    total_built_area_sqft: float,
) -> str:
    room_lines = "\n".join(
        f"  - {r.name}: {r.width_ft:.0f}ft × {r.length_ft:.0f}ft ({r.area_sqft:.0f} sqft)"
        for r in rooms
    )
    layout_lines = _room_layout_lines(rooms)
    return (
        f"Highly detailed real-world 2D architectural floor plan drawing, exactly as produced by a "
        f"licensed Sri Lankan architect. White paper background. Black ink. Total built area: "
        f"{total_built_area_sqft:.0f} square feet. Rooms: {room_lines}\n\n"
        f"EXACT LAYOUT — draw rooms in these precise positions, do not rearrange them:\n"
        f"{layout_lines}\n\n"
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
        f"TITLE BLOCK: Bottom of drawing shows plot size in feet (e.g. PLOT: 40x60 ft). "
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
        f"Re-render this EXACT SAME image with photorealistic materials and lighting: keep the "
        f"identical isometric camera angle, identical room positions, identical wall layout, identical "
        f"proportions shown in the reference. Do not change the perspective, do not change the layout, "
        f"do not rotate the view, do not crop or reframe. Only enhance realism: warm oak wood floor "
        f"texture, cream painted walls with real texture, realistic furniture matching each room type "
        f"(bed and wardrobe in bedrooms, sofa and coffee table in living room, dining table and chairs "
        f"in dining room, kitchen counter with cabinets in kitchen, toilet and sink in bathroom), soft "
        f"realistic ambient lighting with shadows.\n\n"
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
