"""
prompt_builder.py — Constructs the structured LLM prompt for floor plan generation.

Builds a 4-part prompt:
  Part 1: System role
  Part 2: RAG context (retrieved examples)
  Part 3: Site constraints (dimensions, orientation, setbacks)
  Part 4: User requirements (rooms, finish grade, style)
"""

import json
import logging

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Assembles a structured LLM prompt from site data, RAG context, and user requirements."""

    def build(
        self,
        buildable_zone: dict,
        user_requirements: dict,
        retrieved_plans: list[dict],
    ) -> str:
        """
        Construct the full LLM prompt string.

        Args:
            buildable_zone:    Stage 2 output with polygon, area, floors, orientation.
            user_requirements: User input (rooms, style, finish_grade, special_req).
            retrieved_plans:   RAG retriever output (similar floor plan examples).

        Returns:
            Multi-part prompt string ready for the LLM API.
        """
        parts = [
            self._part1_system_role(),
            self._part2_rag_context(retrieved_plans),
            self._part3_site_constraints(buildable_zone),
            self._part4_user_requirements(user_requirements),
            self._output_format_instruction(),
        ]
        return "\n\n".join(parts)

    # ── Part 1 — System role ──────────────────────────────────────────────

    @staticmethod
    def _part1_system_role() -> str:
        return (
            "## ROLE\n"
            "You are a licensed Sri Lankan residential architect with 20 years of experience "
            "designing homes that comply with the Urban Development Authority (UDA) regulations "
            "and the National Building Code (NBC) of Sri Lanka.\n"
            "You deeply understand tropical climate design, local material availability, "
            "Sinhala and Tamil spatial traditions, and the practical needs of Sri Lankan families.\n"
            "Your floor plans prioritise natural light, cross-ventilation, privacy hierarchy, "
            "and cost-effective construction."
        )

    # ── Part 2 — RAG context ──────────────────────────────────────────────

    @staticmethod
    def _part2_rag_context(retrieved_plans: list[dict]) -> str:
        if not retrieved_plans:
            return "## REFERENCE PLANS\nNo similar plans found in knowledge base."

        lines = ["## REFERENCE PLANS", "The following similar approved plans may inspire your design:"]
        for i, plan in enumerate(retrieved_plans, start=1):
            meta = plan.get("metadata", {})
            doc = plan.get("document", "")
            lines.append(
                f"\n### Reference {i} "
                f"(Style: {meta.get('style', 'N/A')}, "
                f"Floors: {meta.get('floors', 'N/A')}, "
                f"Area: {meta.get('area_sqm', 'N/A')} m²)\n{doc}"
            )
        return "\n".join(lines)

    # ── Part 3 — Site constraints ─────────────────────────────────────────

    @staticmethod
    def _part3_site_constraints(buildable_zone: dict) -> str:
        polygon = buildable_zone.get("buildable_polygon", [])
        area = buildable_zone.get("buildable_area_sqm", "unknown")
        max_area = buildable_zone.get("max_area_sqm", "unknown")
        floors = buildable_zone.get("recommended_floors", 2)
        orientation = buildable_zone.get("optimal_orientation", {})
        setbacks = buildable_zone.get("setbacks_applied", {})

        orient_deg = orientation.get("recommended_building_deg", "unknown") if orientation else "unknown"
        orient_score = orientation.get("solar_efficiency_score", "N/A") if orientation else "N/A"

        polygon_str = json.dumps(polygon[:6]) + ("..." if len(polygon) > 6 else "")

        return (
            "## SITE CONSTRAINTS\n"
            f"- Buildable polygon (metres): {polygon_str}\n"
            f"- Buildable area: {area} m²\n"
            f"- Maximum ground floor area (coverage limit): {max_area} m²\n"
            f"- Recommended floors: {floors}\n"
            f"- Optimal building orientation: {orient_deg}° "
            f"(solar efficiency score: {orient_score})\n"
            f"- Applied setbacks — "
            f"front: {setbacks.get('front', 'N/A')} m, "
            f"rear: {setbacks.get('rear', 'N/A')} m, "
            f"side: {setbacks.get('side', 'N/A')} m\n"
            "- All room polygons MUST fit entirely within the buildable polygon.\n"
            "- Do not exceed the maximum ground floor area."
        )

    # ── Part 4 — User requirements ────────────────────────────────────────

    @staticmethod
    def _part4_user_requirements(user_requirements: dict) -> str:
        rooms = user_requirements.get("rooms", [])
        style = user_requirements.get("style", "modern")
        finish_grade = user_requirements.get("finish_grade", "standard")
        num_floors = user_requirements.get("num_floors", 2)
        special = user_requirements.get("special_requirements", "none")

        room_list = "\n".join(f"  - {r}" for r in rooms) if rooms else "  - Not specified"

        return (
            "## USER REQUIREMENTS\n"
            f"- Architectural style: {style}\n"
            f"- Finish grade: {finish_grade} (budget / standard / premium / luxury)\n"
            f"- Number of floors: {num_floors}\n"
            f"- Required rooms:\n{room_list}\n"
            f"- Special requirements: {special}"
        )

    # ── Output format ─────────────────────────────────────────────────────

    @staticmethod
    def _output_format_instruction() -> str:
        return (
            "## OUTPUT FORMAT\n"
            "Return ONLY a valid JSON object with the following structure. "
            "Do not include any explanation text outside the JSON.\n\n"
            "```json\n"
            "{\n"
            '  "floor_plan_id": "<uuid>",\n'
            '  "style": "<style>",\n'
            '  "total_floors": <int>,\n'
            '  "rooms": [\n'
            "    {\n"
            '      "name": "<room name>",\n'
            '      "floor": <int>,\n'
            '      "polygon": [[x,y], ...],\n'  # coordinates in metres
            '      "area_sqm": <float>,\n'
            '      "has_window": <bool>,\n'
            '      "has_door": <bool>,\n'
            '      "adjacencies": ["<room name>", ...]\n'
            "    }\n"
            "  ],\n"
            '  "circulation": { "corridors": [...], "staircases": [...] },\n'
            '  "roof_type": "<flat|gable|hip|lean-to>",\n'
            '  "foundation_type": "<strip|raft|pad>"\n'
            "}\n"
            "```"
        )
