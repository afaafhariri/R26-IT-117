"""SVG floor plan renderer using svgwrite."""

from datetime import date
from pathlib import Path

import svgwrite

from utils.logger import get_logger

_logger = get_logger("svg_renderer")

_ROOM_COLOURS: dict[str, str] = {
    "living_room":    "#E8F4FD",
    "bedroom":        "#FEF9E7",
    "master_bedroom": "#FEF9E7",
    "kitchen":        "#EAFAF1",
    "bathroom":       "#EBF5FB",
    "dining":         "#F9EBEA",
    "garage":         "#F2F3F4",
    "default":        "#FDFEFE",
}

_SCALE_FACTOR = 500  # 1 normalised unit = 500 SVG units
_CANVAS_W = 840      # A4 landscape width in px (297mm at 96 dpi ~1122, scaled down)
_CANVAS_H = 595
_MARGIN = 40


def _room_colour(name: str) -> str:
    key = name.lower().replace(" ", "_")
    for k, v in _ROOM_COLOURS.items():
        if key.startswith(k):
            return v
    return _ROOM_COLOURS["default"]


class SVGRenderer:
    """Renders an approved floor plan as a scaled SVG diagram."""

    def render(
        self,
        floor_plan: dict,
        buildable_zone: dict,
        output_path: Path,
    ) -> Path:
        """Renders the floor plan as an SVG file.

        Args:
            floor_plan: Approved floor plan dict with rooms list.
            buildable_zone: Stage 2 output for scale reference.
            output_path: Path where the SVG file will be written.

        Returns:
            Path: Path to the written SVG file.

        Output SVG includes:
            - Scaled room rectangles colour-coded by room type
            - Room name and area labels centred in each room
            - North arrow in top-right corner
            - Scale bar at bottom
            - Title block with Plan ID, date, finish grade
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rooms: list[dict] = floor_plan.get("rooms", [])
        plan_id = floor_plan.get("plan_id", "PLAN-UNKNOWN")
        finish_grade = floor_plan.get("budget_tier", "medium")

        # Normalise drawing area
        draw_w = _CANVAS_W - 2 * _MARGIN
        draw_h = _CANVAS_H - 80  # reserve 80px for title block

        dwg = svgwrite.Drawing(
            str(output_path),
            size=(f"{_CANVAS_W}px", f"{_CANVAS_H}px"),
        )
        dwg.add(dwg.rect(insert=(0, 0), size=("100%", "100%"), fill="white"))

        # Border
        dwg.add(
            dwg.rect(
                insert=(_MARGIN, _MARGIN),
                size=(draw_w, draw_h - _MARGIN),
                fill="none",
                stroke="#333",
                stroke_width=1,
            )
        )

        # Rooms
        for room in rooms:
            x = _MARGIN + room.get("x_norm", 0) * draw_w
            y = _MARGIN + room.get("y_norm", 0) * (draw_h - _MARGIN)
            w = room.get("width_norm", 0.1) * draw_w
            h = room.get("height_norm", 0.1) * (draw_h - _MARGIN)
            fill = _room_colour(room.get("name", ""))

            dwg.add(
                dwg.rect(
                    insert=(x, y),
                    size=(w, h),
                    fill=fill,
                    stroke="#555",
                    stroke_width=1.5,
                )
            )

            # Room name label
            cx, cy = x + w / 2, y + h / 2
            dwg.add(
                dwg.text(
                    room.get("name", "").replace("_", " ").title(),
                    insert=(cx, cy - 6),
                    text_anchor="middle",
                    font_size="9px",
                    font_family="Arial, sans-serif",
                    fill="#222",
                )
            )
            # Area sub-label
            area = room.get("area_sqm", 0)
            dwg.add(
                dwg.text(
                    f"{area:.1f} m²",
                    insert=(cx, cy + 8),
                    text_anchor="middle",
                    font_size="8px",
                    font_family="Arial, sans-serif",
                    fill="#555",
                )
            )

        # North arrow (top-right)
        _add_north_arrow(dwg, _CANVAS_W - _MARGIN - 30, _MARGIN + 30)

        # Scale bar
        _add_scale_bar(dwg, _MARGIN, _CANVAS_H - 55, draw_w)

        # Title block
        _add_title_block(dwg, _MARGIN, _CANVAS_H - 40, draw_w, plan_id, finish_grade)

        dwg.save()
        _logger.info("SVG rendered: %s (%d rooms)", output_path, len(rooms))
        # TODO Sprint 10: add door swing arcs and window break symbols
        return output_path


def _add_north_arrow(dwg: svgwrite.Drawing, cx: float, cy: float) -> None:
    r = 18
    dwg.add(dwg.circle(center=(cx, cy), r=r, fill="none", stroke="#333", stroke_width=1))
    dwg.add(dwg.line(start=(cx, cy + r - 4), end=(cx, cy - r + 4), stroke="#333", stroke_width=1.5))
    dwg.add(dwg.polygon(
        points=[(cx - 5, cy - 4), (cx + 5, cy - 4), (cx, cy - r + 4)],
        fill="#333",
    ))
    dwg.add(dwg.text("N", insert=(cx, cy + r + 12), text_anchor="middle",
                     font_size="10px", font_family="Arial", font_weight="bold", fill="#333"))


def _add_scale_bar(dwg: svgwrite.Drawing, x: float, y: float, width: float) -> None:
    bar_w = min(150, width * 0.2)
    segment = bar_w / 5
    for i in range(5):
        fill = "#333" if i % 2 == 0 else "white"
        dwg.add(dwg.rect(insert=(x + i * segment, y), size=(segment, 8),
                         fill=fill, stroke="#333", stroke_width=0.5))
    dwg.add(dwg.text("0", insert=(x, y + 20), font_size="8px", font_family="Arial", fill="#555"))
    dwg.add(dwg.text("5 m", insert=(x + bar_w, y + 20), font_size="8px",
                     font_family="Arial", fill="#555"))


def _add_title_block(
    dwg: svgwrite.Drawing,
    x: float,
    y: float,
    width: float,
    plan_id: str,
    finish_grade: str,
) -> None:
    dwg.add(dwg.rect(insert=(x, y), size=(width, 30), fill="#F0F0F0",
                     stroke="#333", stroke_width=0.5))
    today = date.today().isoformat()
    label = (
        f"Plan: {plan_id}   |   Date: {today}   |   Finish: {finish_grade.title()}   |   "
        "Component 01 — R26-IT-117 SLIIT"
    )
    dwg.add(dwg.text(label, insert=(x + 10, y + 19), font_size="8px",
                     font_family="Arial", fill="#333"))
