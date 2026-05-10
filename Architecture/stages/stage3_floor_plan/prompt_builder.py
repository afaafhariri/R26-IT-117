"""Structured LLM prompt builder for Gemini floor plan generation."""

from utils.logger import get_logger

_logger = get_logger("prompt_builder")

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
6. Rooms on different floors do NOT need to avoid each other.
7. width_norm and height_norm must each be between 0.05 and 0.90.
8. Total area of all rooms must be <= max_total_built_sqm."""

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
        orientation = buildable_zone.get("orientation", {})
        entrance_side = orientation.get("entrance_side", "south")

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

        layout_rules = _LAYOUT_RULES_TEMPLATE.format(
            x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max
        )

        rag_context = "\n---\n".join(retrieved_plans) if retrieved_plans else "No precedents available."

        prompt = "\n\n".join(
            [
                f"ROLE:\n{_SYSTEM_ROLE}",
                f"DESIGN PRECEDENTS AND STANDARDS:\n{rag_context}",
                (
                    "SITE CONSTRAINTS:\n"
                    f"- Buildable footprint: {buildable_zone.get('max_footprint_sqm', 0):.1f} sqm\n"
                    f"- Maximum total built area: {buildable_zone.get('max_total_built_sqm', 0):.1f} sqm\n"
                    f"- Buildable zone (normalised coords): "
                    f"x=[{x_min}, {x_max}], y=[{y_min}, {y_max}]\n"
                    f"- Number of floors: {user_requirements.get('floors', 1)}\n"
                    f"- Building orientation: entrance facing {entrance_side}\n"
                    f"- District: {user_requirements.get('district', 'unspecified')}\n"
                    f"- Coastal site: {user_requirements.get('is_coastal', False)}"
                ),
                (
                    "USER REQUIREMENTS:\n"
                    f"- Room types required: {', '.join(user_requirements.get('room_types', []))}\n"
                    f"- Garage: {'Yes' if user_requirements.get('garage') else 'No'}\n"
                    f"- Finish grade: {user_requirements.get('budget_tier', 'medium')}\n"
                    f"- Architectural style: {user_requirements.get('style', 'modern')}"
                ),
                f"LAYOUT RULES:\n{layout_rules}",
                f"OUTPUT FORMAT:\n{_OUTPUT_FORMAT}",
            ]
        )

        _logger.info(
            "Prompt built: %d chars, %d RAG passages",
            len(prompt),
            len(retrieved_plans),
        )
        return prompt
