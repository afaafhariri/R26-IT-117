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


def blueprint_2d_prompt(
    rooms: list[Room],
    total_built_area_sqft: float,
) -> str:
    room_lines = "\n".join(
        f"  - {r.name}: {r.width_ft:.0f}ft × {r.length_ft:.0f}ft ({r.area_sqft:.0f} sqft)"
        for r in rooms
    )
    return (
        f"Professional 2D architectural floor plan blueprint. Technical top-down drawing on a navy "
        f"blue background with white lines. Total built area: {total_built_area_sqft:.0f} square feet. "
        f"Rooms to include:\n{room_lines}\n"
        f"Drawing must show: thick exterior walls (double lines), interior partition walls, door swing "
        f"arc symbols, window triple-line symbols on exterior walls, dimension lines with measurements "
        f"in feet, room name labels centred in each space, north arrow in top-right corner, scale bar "
        f"at bottom. Clean technical drafting style, no furniture, no textures, pure blueprint aesthetic."
    )


def floorplan_3d_prompt(rooms: list[Room]) -> str:
    room_names = ", ".join(r.name for r in rooms)
    return (
        f"3D dollhouse perspective floor plan. Bird's eye isometric view with the roof removed to "
        f"reveal the interior layout. Rooms: {room_names}. Cream painted walls, warm oak wood floor "
        f"texture throughout, each room has minimal furniture silhouettes appropriate to the room type "
        f"(bed and wardrobe in bedroom, sofa and coffee table in living room, dining table and chairs "
        f"in dining room, kitchen counter in kitchen, toilet and sink in bathroom). Soft ambient "
        f"lighting from above. Clean architectural illustration style, slight drop shadow on walls, "
        f"room labels in clean sans-serif font."
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
