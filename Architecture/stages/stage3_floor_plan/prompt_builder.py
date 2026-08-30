"""Structured LLM prompt builder for Gemini floor plan generation."""

import math

from utils.logger import get_logger

_logger = get_logger("prompt_builder")

# Minimum room areas (sqm). This is the single source of truth used for both
# generation (this file, layout_solver.py) and validation (validator.py) — the
# two used to keep separate, disagreeing copies, which meant plans that were
# generated to satisfy this table could still fail validation against a
# stricter, unsynced one. Keep frontend/src/views/LandDataReviewView.tsx's
# ROOM_SQM_MIN in sync with these values manually (JS/Python can't share an
# import) if you change them here.
#
# living_room / dining_room / bedroom / kitchen: from Sri Lanka's UDA Planning
# & Building Regulations (Gazette 392/9, 1986) — "general room" minimum 90 sqft
# (8.4 sqm) covers living/dining/ordinary bedrooms; kitchen has its own 60 sqft
# (5.6 sqm) minimum; "at least one bedroom" must be 120 sqft (11.2 sqm), used
# here for master_bedroom. bathroom is lower-confidence — sources disagreed
# between ~1.5 sqm and ~3.25 sqm for the same clause; used the less extreme
# figure. garage/home_office/prayer_room/library/maids_room/kids_playroom/gym/
# home_theatre aren't covered by this 1986 regulation at all (it predates
# these room types) — those remain practical minimums, not a cited regulation.
_MIN_ROOM_SQM: dict[str, float] = {
    "living_room": 8.4,
    "master_bedroom": 11.2,
    "bedroom": 8.4,
    "kitchen": 5.6,
    "bathroom": 3.3,
    "dining_room": 8.4,
    "home_office": 5.0,
    "prayer_room": 5.0,
    "library": 5.0,
    "maids_room": 5.0,
    "kids_playroom": 8.0,
    "gym": 12.0,
    "home_theatre": 12.0,
    "garage": 14.0,
    # A compact switchback residential staircase (~1m run per flight, small
    # mid-landing) fits in roughly this footprint. Not a cited regulation —
    # a practical minimum, same as the other non-UDA-covered room types.
    # This size is fixed and reused identically on every floor by
    # layout_solver.py — see solve_overlaps — since a staircase must occupy
    # the same physical footprint on each floor it connects.
    "staircase": 4.0,
}

# Realistic maximum room areas — rooms won't grow beyond these even on large plots
_MAX_ROOM_SQM: dict[str, float] = {
    "living_room": 45.0,
    "master_bedroom": 28.0,
    "bedroom": 20.0,
    "kitchen": 22.0,
    "bathroom": 10.0,
    "dining_room": 28.0,
    "home_office": 18.0,
    "prayer_room": 12.0,
    "library": 22.0,
    "maids_room": 14.0,
    "kids_playroom": 22.0,
    "gym": 35.0,
    "home_theatre": 35.0,
    "garage": 38.0,
    # Fixed, not a real ceiling — layout_solver.py always uses exactly
    # _MIN_ROOM_SQM["staircase"], never scaling it up like other rooms.
    "staircase": 4.0,
}


def _compute_target_sizes(room_types: list[str], total_budget_sqm: float) -> dict[str, float]:
    """Scale room sizes proportionally to fill available budget, capped at realistic maxima.

    No artificial scale cap — rooms grow until they hit their individual maximum.
    Any remaining budget after capping is redistributed proportionally to uncapped rooms.
    """
    min_total = sum(_MIN_ROOM_SQM.get(rt, 8.0) for rt in room_types)
    if min_total <= 0:
        return {rt: _MIN_ROOM_SQM.get(rt, 8.0) for rt in room_types}

    scale = total_budget_sqm / min_total
    targets: dict[str, float] = {}
    for rt in room_types:
        min_sqm = _MIN_ROOM_SQM.get(rt, 8.0)
        max_sqm = _MAX_ROOM_SQM.get(rt, min_sqm * 4)
        targets[rt] = round(min(min_sqm * scale, max_sqm), 1)
    return targets


def _format_min_sizes() -> str:
    """Builds the MINIMUM ROOM SIZES prompt text directly from _MIN_ROOM_SQM,
    grouping room types that share the same minimum onto one line — so the
    prompt Gemini reads can never drift out of sync with the table generation
    and validation actually enforce (this used to be a separately hand-typed
    list here that fell out of sync the moment _MIN_ROOM_SQM changed)."""
    by_value: dict[float, list[str]] = {}
    for rt, sqm in _MIN_ROOM_SQM.items():
        by_value.setdefault(sqm, []).append(rt)
    lines = [
        f"   - {' / '.join(by_value[sqm])}: minimum {sqm:g} sqm"
        for sqm in sorted(by_value, reverse=True)
    ]
    return "\n".join(lines)

# Lower index = higher priority (must keep)
_ROOM_PRIORITY: list[str] = [
    "master_bedroom", "bedroom", "living_room", "kitchen",
    "bathroom", "dining_room", "prayer_room", "home_office",
    "library", "maids_room", "kids_playroom", "gym", "home_theatre", "garage",
]


def _budget_check(room_types: list[str], max_total_sqm: float) -> tuple[list[str], list[str]]:
    """Returns (rooms_to_include, rooms_to_drop) based on area budget.

    Sorts requested rooms by priority and greedily adds until budget is exhausted.
    Rooms that cannot fit at NBC minimum size are returned as rooms_to_drop.
    """
    def _priority(rt: str) -> int:
        base = rt.split("_")[0]
        for i, p in enumerate(_ROOM_PRIORITY):
            if rt == p or rt.startswith(p.split("_")[0]):
                return i
        return len(_ROOM_PRIORITY)

    sorted_rooms = sorted(room_types, key=_priority)
    include: list[str] = []
    total = 0.0
    for rt in sorted_rooms:
        min_sqm = _MIN_ROOM_SQM.get(rt, 8.0)
        if total + min_sqm <= max_total_sqm + 0.5:  # 0.5 sqm tolerance
            include.append(rt)
            total += min_sqm
        # else: over budget — skip this room
    drop = [rt for rt in room_types if rt not in include]
    return include, drop


# Which rooms belong on which floor (for explicit per-room assignment)
_FLOOR1_ROOMS = {
    "living_room", "dining_room", "kitchen", "garage",
    "bathroom", "home_office", "prayer_room", "maids_room",
    "staircase",
}
_FLOOR2_ROOMS = {
    "master_bedroom", "bedroom", "library", "gym",
    "home_theatre", "kids_playroom",
}


def _assign_floors(room_types: list[str], floors: int) -> list[tuple[str, int]]:
    """Returns [(room_type, floor_number), ...] for each room in room_types.

    When floors == 1 everything goes to floor 1.
    When floors >= 2 the explicit floor map is used; a bathroom next to a
    bedroom group goes to floor 2, all others default to floor 1.
    """
    if floors < 2:
        return [(rt, 1) for rt in room_types]

    # Count bedrooms to decide whether to split bathroom assignments
    bed_count = sum(1 for rt in room_types if "bedroom" in rt)
    bath_count = sum(1 for rt in room_types if "bathroom" in rt)
    # Assign 1st bathroom to floor 1 (guest), remainder to floor 2 (ensuite)
    bath_seen = 0
    result: list[tuple[str, int]] = []
    for rt in room_types:
        if rt in _FLOOR2_ROOMS:
            result.append((rt, 2))
        elif rt == "bathroom":
            bath_seen += 1
            if bath_seen == 1 and bath_count > 1:
                result.append((rt, 1))  # first bathroom = guest on floor 1
            else:
                result.append((rt, 2))  # rest go to floor 2
        else:
            result.append((rt, 1))
    return result

# Maps entrance_side to which edge of the normalised (x=east, y=south)
# coordinate space the living_room should hug — see _LAYOUT_RULES_TEMPLATE
# rule 11. Text is filled in with the actual x/y bounds at build() time.
_ENTRANCE_EDGE_HINT: dict[str, str] = {
    "north": "with a low y_norm, close to y_norm = {y_min} (the north edge)",
    "south": "with a high y_norm + height_norm, close to {y_max} (the south edge)",
    "east": "with a high x_norm + width_norm, close to {x_max} (the east edge)",
    "west": "with a low x_norm, close to x_norm = {x_min} (the west edge)",
}


def parse_entrance_side(orientation: str) -> str:
    """Extracts north/south/east/west from an orientation string like
    "South-facing" (CadastralData.orientation's format). Shared between the
    LLM prompt (this file) and layout_solver.py's packer, which also needs
    the real entrance side to bias where living_room ends up — a prompt
    instruction alone isn't enough, since the packer recomputes every room's
    position itself and would otherwise ignore it entirely."""
    side = str(orientation or "South-facing").replace("-facing", "").strip().lower()
    return side if side in _ENTRANCE_EDGE_HINT else "south"

_SYSTEM_ROLE = (
    "You are a licensed Sri Lankan residential architect with 15 years of experience "
    "designing single and double storey detached dwellings for the Sri Lankan climate "
    "(6°N latitude, tropical, high humidity). You follow NBC Sri Lanka regulations and "
    "UDA guidelines. You optimise for natural cross-ventilation, shade, and spatial efficiency."
)

_LAYOUT_RULES_TEMPLATE = """LAYOUT RULES — YOU MUST FOLLOW ALL OF THESE EXACTLY:
1. All rooms on the SAME floor must have NON-OVERLAPPING rectangles. Two rooms overlap if their (x_norm, y_norm, width_norm, height_norm) rectangles share any area. This is a hard constraint.
2. Use a ROW-BASED grid layout per floor:
   - Row 1: public/living spaces (living room, dining, kitchen) placed left to right.
   - Row 2: private spaces (bedrooms, bathrooms) placed left to right below Row 1.
   - Row 3 (if needed): utility/garage below Row 2.
3. ALL rooms must be placed INSIDE the buildable zone: x_norm >= {x_min}, y_norm >= {y_min}.
4. x_norm + width_norm MUST be <= {x_max} for every room.
5. y_norm + height_norm MUST be <= {y_max} for every room.
6. Rooms on different floors do NOT need to avoid each other — they share the same footprint.
7. width_norm and height_norm must each be between 0.05 and 0.90.
8. Total area of all rooms must be <= max_total_built_sqm.
9. FLOOR DISTRIBUTION — when floors >= 2, you MUST distribute rooms across floors:
   - Floor 1 (ground): living room, dining room, kitchen, garage, guest bathroom, home_office, prayer_room, maids_room, staircase
   - Floor 2 (upper): master bedroom, all other bedrooms, ensuite bathrooms, library, gym, kids_playroom, home_theatre
   - Each room's "floor" field in the JSON must be set to 1 or 2 accordingly.
   - Do NOT put all rooms on floor 1 when floors=2. Upper floor rooms reuse the same x_norm/y_norm footprint.
10. MINIMUM ROOM SIZES — never generate a room smaller than these:
{min_sizes_list}
   If the total area budget cannot fit all rooms at minimum sizes, REMOVE lower-priority rooms rather than shrinking rooms below minimums.
   Priority order: bedrooms > living_room > kitchen > bathrooms > dining_room > special_rooms > garage.
11. ENTRANCE-AWARE PLACEMENT — MANDATORY:
   The main entrance is on the {entrance_side} side of the plot. The living_room MUST be
   positioned {entrance_edge_hint} — a person walking in the front door must reach the
   living room immediately, not after passing through other rooms. Do NOT place living_room
   in the corner or edge farthest from the entrance; that is not how a real house is entered.
12. STAIRCASE — when floors >= 2, a room named "staircase" is included in the required room
   list. Its exact position and size are fixed by the system after generation and will be
   placed to physically connect floor 1 and floor 2, so treat it like any other floor-1 room
   for layout purposes (give it a position that does not overlap others) — your specific
   coordinates for it will be overridden, but every other room's position must still make
   sense as if the staircase occupies real space near the entrance/public zone."""

_OUTPUT_FORMAT = """Respond ONLY with a valid JSON object. No markdown fences, no explanation. Use this exact schema:
{
  "layout_name": "string",
  "rooms": [
    {
      "name": "string",
      "area_sqm": 0.0,
      "floor": 1,
      "x_norm": 0.0,
      "y_norm": 0.0,
      "width_norm": 0.0,
      "height_norm": 0.0,
      "window_orientation": "north|south|east|west",
      "adjacencies": ["room_name"]
    }
  ],
  "total_area_sqm": 0.0,
  "space_notes": "string"
}"""


class PromptBuilder:
    """Constructs a 4-part structured LLM prompt for Sri Lankan residential
    floor plan generation.
    """

    def build(
        self,
        buildable_zone: dict,
        user_requirements: dict,
        retrieved_plans: list[str],
    ) -> str:
        """Assembles a complete structured prompt ready for the Gemini API.

        Args:
            buildable_zone: Stage 2 output with dimensions, orientation, max area.
            user_requirements: Room types, floors, budget_tier, style, etc.
            retrieved_plans: RAG context passages from RAGRetriever.

        Returns:
            str: Complete structured prompt.
        """
        # user_requirements["orientation"] carries the plan's real entrance side
        # (e.g. "South-facing", from OrientationSolver via cadastral.py) —
        # buildable_zone has no "orientation" key at all, so reading it from
        # there (the previous approach) silently always fell back to "south"
        # regardless of the actual plot.
        entrance_side = parse_entrance_side(user_requirements.get("orientation"))

        # Derive axis-aligned bounds from the buildable polygon so the LLM
        # knows exactly which coordinate range is valid for room placement.
        polygon = buildable_zone.get("buildable_polygon", [])
        if polygon:
            xs = [pt[0] for pt in polygon]
            ys = [pt[1] for pt in polygon]
            x_min, x_max = round(min(xs), 2), round(max(xs), 2)
            y_min, y_max = round(min(ys), 2), round(max(ys), 2)
        else:
            x_min, y_min, x_max, y_max = 0.0, 0.0, 1.0, 1.0

        entrance_edge_hint = _ENTRANCE_EDGE_HINT[entrance_side].format(
            x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max
        )
        layout_rules = _LAYOUT_RULES_TEMPLATE.format(
            x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max,
            min_sizes_list=_format_min_sizes(),
            entrance_side=entrance_side,
            entrance_edge_hint=entrance_edge_hint,
        )

        rag_context = "\n---\n".join(retrieved_plans) if retrieved_plans else "No precedents available."

        # Budget check: can all requested rooms fit at NBC minimum sizes?
        max_total_sqm = float(buildable_zone.get("max_total_built_sqm", 0))
        room_types_req: list[str] = user_requirements.get("room_types", [])
        floors_req: int = int(user_requirements.get("floors", 1))
        rooms_ok, rooms_drop = _budget_check(room_types_req, max_total_sqm)

        # Assign explicit floor numbers to every room
        room_floor_assignments = _assign_floors(rooms_ok, floors_req)
        floor1_rooms = [rt for rt, f in room_floor_assignments if f == 1]
        floor2_rooms = [rt for rt, f in room_floor_assignments if f == 2]

        budget_note = ""
        if rooms_drop:
            _logger.warning(
                "Budget %g sqm too small for all rooms — dropping: %s",
                max_total_sqm, rooms_drop,
            )
            budget_note = (
                f"\nBUDGET CONSTRAINT — CRITICAL:\n"
                f"Total budget is {max_total_sqm:.1f} sqm. The requested rooms require more "
                f"space than available at NBC minimum sizes.\n"
                f"YOU MUST include ONLY these rooms (in order of priority):\n"
                f"  INCLUDE: {', '.join(rooms_ok)}\n"
                f"  DROP (omit entirely): {', '.join(rooms_drop)}\n"
                f"Do NOT include the dropped rooms. Do NOT shrink rooms below NBC minimums. "
                f"Use the full budget on fewer, properly-sized rooms."
            )

        # Build explicit floor assignment note for multi-floor plans
        floor_assignment_note = ""
        if floors_req >= 2 and floor2_rooms:
            floor_assignment_note = (
                f"\nFLOOR ASSIGNMENT — MANDATORY (floors={floors_req}):\n"
                f"  Floor 1 rooms (set \"floor\": 1): {', '.join(floor1_rooms)}\n"
                f"  Floor 2 rooms (set \"floor\": 2): {', '.join(floor2_rooms)}\n"
                f"Every room in the JSON MUST have the correct \"floor\" value from the list above.\n"
                f"DO NOT put all rooms on floor 1. Floor 2 rooms MUST have \"floor\": 2."
            )

        # Compute the real-world meter equivalent of 1 normalized unit, accounting
        # for the layout solver's zone remapping.  The solver multiplies every
        # width_norm by zone_w and every height_norm by zone_h before the display
        # layer converts to feet.  So Gemini must pre-compensate:
        #   effective_width_norm  = room_width_m  / (zone_side_m × zone_w)
        #   effective_height_norm = room_height_m / (zone_side_m × zone_h)
        footprint_sqm = float(buildable_zone.get("max_footprint_sqm", 100))
        zone_side_m = math.sqrt(footprint_sqm) if footprint_sqm > 0 else 10.0
        zone_w = round(x_max - x_min, 4) or 0.6
        zone_h = round(y_max - y_min, 4) or 0.7

        def _nw(meters: float) -> str:
            return f"{meters / (zone_side_m * zone_w):.3f}"

        def _nh(meters: float) -> str:
            return f"{meters / (zone_side_m * zone_h):.3f}"

        # Compute recommended target sizes scaled to available budget
        target_sizes = _compute_target_sizes(rooms_ok, max_total_sqm)

        def _target_w(rt: str) -> float:
            sqm = target_sizes.get(rt, _MIN_ROOM_SQM.get(rt, 8.0))
            return math.sqrt(sqm * 1.2)  # assume w:h ≈ 1.2:1

        def _target_h(rt: str) -> float:
            sqm = target_sizes.get(rt, _MIN_ROOM_SQM.get(rt, 8.0))
            return math.sqrt(sqm / 1.2)

        target_lines = "\n".join(
            f"  {rt}: target {target_sizes[rt]:.1f} sqm "
            f"(width_norm≈{_nw(_target_w(rt))}, height_norm≈{_nh(_target_h(rt))})"
            for rt in rooms_ok
        )

        size_guide = (
            f"COORDINATE SYSTEM — CRITICAL:\n"
            f"- Buildable footprint ≈ {zone_side_m:.1f}m × {zone_side_m:.1f}m "
            f"({footprint_sqm:.1f} sqm).\n"
            f"- The usable zone spans x=[{x_min},{x_max}] (width={zone_w}) and "
            f"y=[{y_min},{y_max}] (height={zone_h}) in normalised coordinates.\n"
            f"- FORMULA: width_norm = room_width_m / ({zone_side_m:.1f} × {zone_w}) = "
            f"room_width_m / {zone_side_m * zone_w:.2f}\n"
            f"           height_norm = room_height_m / ({zone_side_m:.1f} × {zone_h}) = "
            f"room_height_m / {zone_side_m * zone_h:.2f}\n"
            f"- TARGET ROOM SIZES — size each room to these recommended values:\n"
            f"{target_lines}\n"
            f"- These are TARGETS, not minimums. Generate rooms at these sizes — "
            f"do NOT default to NBC minimums when the budget allows larger rooms.\n"
            f"- Target total built area: {sum(target_sizes.values()):.1f} sqm. "
            f"Your total_area_sqm in the JSON should be close to this value."
        )

        prompt_sections = [
            f"ROLE:\n{_SYSTEM_ROLE}",
            f"DESIGN PRECEDENTS AND STANDARDS:\n{rag_context}",
            (
                "SITE CONSTRAINTS:\n"
                f"- Buildable footprint: {footprint_sqm:.1f} sqm "
                f"(approx {zone_side_m:.1f}m × {zone_side_m:.1f}m)\n"
                f"- Maximum total built area: {buildable_zone.get('max_total_built_sqm', 0):.1f} sqm\n"
                f"- Buildable zone (normalised coords): "
                f"x=[{x_min}, {x_max}], y=[{y_min}, {y_max}]\n"
                f"- Number of floors: {floors_req}\n"
                f"- Building orientation: entrance facing {entrance_side}\n"
                f"- District: {user_requirements.get('district', 'unspecified')}\n"
                f"- Coastal site: {user_requirements.get('is_coastal', False)}"
                + budget_note
                + floor_assignment_note
            ),
            (
                "USER REQUIREMENTS:\n"
                f"- Room types required: {', '.join(rooms_ok)}\n"
                f"- Garage: {'Yes' if user_requirements.get('garage') and 'garage' in rooms_ok else 'No'}\n"
                f"- Finish grade: {user_requirements.get('budget_tier', 'medium')}\n"
                f"- Architectural style: {user_requirements.get('style', 'modern')}\n"
                + (
                    f"- Outdoor features to accommodate: "
                    f"{', '.join(user_requirements.get('outdoor_features', []))}\n"
                    if user_requirements.get('outdoor_features') else ""
                )
                + (
                    f"- Additional client notes: {user_requirements.get('additional_notes')}\n"
                    if user_requirements.get('additional_notes', '').strip() else ""
                )
            ),
            size_guide,
            f"LAYOUT RULES:\n{layout_rules}",
            f"OUTPUT FORMAT:\n{_OUTPUT_FORMAT}",
        ]

        prompt = "\n\n".join(prompt_sections)

        _logger.info(
            "Prompt built: %d chars, %d RAG passages",
            len(prompt),
            len(retrieved_plans),
        )
        return prompt
