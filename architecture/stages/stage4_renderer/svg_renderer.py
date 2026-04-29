"""
svg_renderer.py — SVG floor plan drawing renderer using svgwrite.

Converts a floor plan JSON (room polygons + metadata) to an SVG drawing
and returns it as a base64-encoded string for API transport.
"""

import base64
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Drawing scale: pixels per metre
_PX_PER_METRE = 30
_MARGIN_PX = 40
_ROOM_FILL = "#F5F0E8"
_ROOM_STROKE = "#333333"
_LABEL_FONT_SIZE = 10
_STROKE_WIDTH = 1.5


class SVGRenderer:
    """Renders a floor plan dict to an SVG drawing."""

    def render(self, floor_plan: dict) -> str:
        """
        Convert a floor plan to a base64-encoded SVG string.

        Args:
            floor_plan: Floor plan dict with a 'rooms' list, each room having
                        a 'polygon', 'name', 'floor', and 'area_sqm'.

        Returns:
            Base64-encoded SVG string (UTF-8).

        Raises:
            RuntimeError: If SVG generation fails.
        """
        try:
            import svgwrite  # type: ignore
        except ImportError:
            logger.warning("svgwrite not available — returning stub SVG.")
            return self._stub_svg_b64()

        try:
            rooms = floor_plan.get("rooms", [])
            width_px, height_px = self._compute_canvas(rooms)

            dwg = svgwrite.Drawing(
                size=(f"{width_px}px", f"{height_px}px"),
                profile="full",
            )
            dwg.add(dwg.rect(insert=(0, 0), size=("100%", "100%"), fill="white"))

            # Group rooms by floor
            floors = sorted({r.get("floor", 1) for r in rooms})
            for floor_num in floors:
                floor_rooms = [r for r in rooms if r.get("floor", 1) == floor_num]
                grp = dwg.add(dwg.g(id=f"floor_{floor_num}"))
                for room in floor_rooms:
                    self._draw_room(dwg, grp, room)

            # Title block
            plan_id = floor_plan.get("floor_plan_id", "unknown")
            dwg.add(
                dwg.text(
                    f"Floor Plan — {plan_id}",
                    insert=(_MARGIN_PX, _MARGIN_PX - 10),
                    font_size=12,
                    font_family="Arial",
                    fill="#000000",
                )
            )

            svg_string = dwg.tostring()
            return base64.b64encode(svg_string.encode("utf-8")).decode("utf-8")

        except Exception as exc:
            logger.exception("SVG rendering failed")
            raise RuntimeError(f"SVG rendering error: {exc}") from exc

    def _draw_room(self, dwg: Any, group: Any, room: dict) -> None:
        """Draw a single room polygon with label."""
        import svgwrite  # type: ignore

        raw_polygon = room.get("polygon", [])
        if len(raw_polygon) < 3:
            return

        scaled = [
            (pt[0] * _PX_PER_METRE + _MARGIN_PX, pt[1] * _PX_PER_METRE + _MARGIN_PX)
            for pt in raw_polygon
        ]

        group.add(
            dwg.polygon(
                points=scaled,
                fill=_ROOM_FILL,
                stroke=_ROOM_STROKE,
                stroke_width=_STROKE_WIDTH,
            )
        )

        # Centroid label
        cx = sum(pt[0] for pt in scaled) / len(scaled)
        cy = sum(pt[1] for pt in scaled) / len(scaled)
        label = f"{room.get('name', '?')} ({room.get('area_sqm', 0):.0f}m²)"
        group.add(
            dwg.text(
                label,
                insert=(cx, cy),
                text_anchor="middle",
                dominant_baseline="central",
                font_size=_LABEL_FONT_SIZE,
                font_family="Arial",
                fill="#222222",
            )
        )

    @staticmethod
    def _compute_canvas(rooms: list[dict]) -> tuple[int, int]:
        """Compute the required canvas size from all room polygon extents."""
        all_x: list[float] = []
        all_y: list[float] = []
        for room in rooms:
            for pt in room.get("polygon", []):
                all_x.append(pt[0])
                all_y.append(pt[1])

        if not all_x:
            return (600, 500)

        width = int(max(all_x) * _PX_PER_METRE) + 2 * _MARGIN_PX + 20
        height = int(max(all_y) * _PX_PER_METRE) + 2 * _MARGIN_PX + 20
        return (max(width, 200), max(height, 200))

    @staticmethod
    def _stub_svg_b64() -> str:
        """Return a minimal placeholder SVG when svgwrite is unavailable."""
        stub = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">'
            '<rect width="300" height="200" fill="white" stroke="black"/>'
            '<text x="150" y="100" text-anchor="middle" font-family="Arial" font-size="14">'
            "Floor Plan Placeholder</text>"
            "</svg>"
        )
        return base64.b64encode(stub.encode("utf-8")).decode("utf-8")
