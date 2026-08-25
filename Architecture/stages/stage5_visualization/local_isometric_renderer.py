"""Local, cost-free isometric 3D dollhouse floor plan renderer using Pillow.

Draws an extruded, roofless "dollhouse" view directly from solved room
layout data — same rationale as local_blueprint_renderer: general-purpose
text-to-image models don't reliably produce accurate technical drawings from
a short prompt, so we compute this deterministically from real coordinates
instead. No external API calls, no cost.
"""

from __future__ import annotations

import base64
import io
import math
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

from models.schemas import Room
from utils.logger import get_logger

_logger = get_logger("local_isometric_renderer")

_COS30 = math.cos(math.radians(30))
_SIN30 = math.sin(math.radians(30))

_WALL_HEIGHT_FT = 9.0

_ROOM_COLOURS: dict[str, tuple[int, int, int]] = {
    "living": (174, 214, 241),
    "dining": (241, 148, 138),
    "kitchen": (169, 223, 191),
    "bedroom": (250, 215, 160),
    "master_bedroom": (249, 231, 159),
    "bathroom": (210, 180, 222),
    "garage": (191, 201, 202),
    "home_office": (163, 228, 215),
    "prayer_room": (245, 203, 167),
    "kids_playroom": (245, 183, 177),
    "library": (200, 180, 230),
    "gym": (240, 128, 128),
    "default": (245, 245, 245),
}


def _room_colour(name: str) -> tuple[int, int, int]:
    key = name.lower().replace(" ", "_")
    if key in _ROOM_COLOURS:
        return _ROOM_COLOURS[key]
    for k, v in _ROOM_COLOURS.items():
        if key.startswith(k):
            return v
    return _ROOM_COLOURS["default"]


def _shade(colour: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in colour)


def _iso(x: float, y: float, z: float) -> tuple[float, float]:
    """Projects a 3D world point (x, y, z) — z is height — to 2D isometric screen space."""
    screen_x = (x - y) * _COS30
    screen_y = (x + y) * _SIN30 - z
    return screen_x, screen_y


def _load_fonts() -> tuple[ImageFont.ImageFont, ImageFont.ImageFont]:
    try:
        return ImageFont.truetype("arial.ttf", 20), ImageFont.truetype("arial.ttf", 11)
    except Exception:
        default = ImageFont.load_default()
        return default, default


def render_isometric_png(rooms: list[Room], total_built_area_sqft: float, layout_label: str) -> str:
    """Renders an isometric 3D dollhouse view (roof removed) from solved room layout data.

    Args:
        rooms: Solved room layout (position_x/y and width_ft/length_ft share
            one coordinate system, same as the 2D blueprint renderer).
        total_built_area_sqft: Total built area across all rooms.
        layout_label: Variant name (conservative/balanced/creative) for the title.

    Returns:
        str: Base64-encoded PNG (no ``data:`` URI prefix). Empty string if
            there are no rooms to draw.
    """
    if not rooms:
        return ""

    # Only the ground floor is rendered — upper floors would occlude it in a dollhouse view.
    floor_rooms = [r for r in rooms if (r.floor or 1) == 1] or rooms

    iso_points: list[tuple[float, float]] = []
    for r in floor_rooms:
        for x in (r.position_x, r.position_x + r.width_ft):
            for y in (r.position_y, r.position_y + r.length_ft):
                iso_points.append(_iso(x, y, 0))
                iso_points.append(_iso(x, y, _WALL_HEIGHT_FT))

    xs = [p[0] for p in iso_points]
    ys = [p[1] for p in iso_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = (max_x - min_x) or 1
    range_y = (max_y - min_y) or 1

    margin = 60
    canvas_w = 900
    canvas_h = int((range_y / range_x) * (canvas_w - margin * 2)) + margin * 2 + 40
    scale = (canvas_w - margin * 2) / range_x

    def to_screen(x: float, y: float, z: float) -> tuple[float, float]:
        sx, sy = _iso(x, y, z)
        return (
            margin + (sx - min_x) * scale,
            margin + 40 + (sy - min_y) * scale,
        )

    img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font_title, font_room = _load_fonts()

    draw.text(
        (margin, 10),
        f"{layout_label.title()} Layout — 3D View — {total_built_area_sqft:.0f} sqft",
        fill=(26, 35, 126), font=font_title,
    )

    # Draw back-to-front (by x+y, isometric painter's algorithm) so nearer rooms overlap farther ones.
    for r in sorted(floor_rooms, key=lambda r: r.position_x + r.position_y, reverse=True):
        x0, y0 = r.position_x, r.position_y
        x1, y1 = r.position_x + r.width_ft, r.position_y + r.length_ft
        colour = _room_colour(r.name)

        floor_poly = [
            to_screen(x0, y0, 0), to_screen(x1, y0, 0),
            to_screen(x1, y1, 0), to_screen(x0, y1, 0),
        ]
        # Back walls only (north + west) — keeps the interior visible, dollhouse-style.
        north_wall = [
            to_screen(x0, y0, 0), to_screen(x1, y0, 0),
            to_screen(x1, y0, _WALL_HEIGHT_FT), to_screen(x0, y0, _WALL_HEIGHT_FT),
        ]
        west_wall = [
            to_screen(x0, y0, 0), to_screen(x0, y1, 0),
            to_screen(x0, y1, _WALL_HEIGHT_FT), to_screen(x0, y0, _WALL_HEIGHT_FT),
        ]

        draw.polygon(west_wall, fill=_shade(colour, 0.75), outline=(20, 20, 20))
        draw.polygon(north_wall, fill=_shade(colour, 0.9), outline=(20, 20, 20))
        draw.polygon(floor_poly, fill=_shade(colour, 1.1), outline=(20, 20, 20))

        label_x, label_y = to_screen((x0 + x1) / 2, (y0 + y1) / 2, 0)
        name_text = r.name.replace("_", " ").title()
        draw.text((label_x, label_y), name_text, fill=(20, 20, 20), font=font_room, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    _logger.info(
        "Local isometric PNG rendered: %d room(s), %d bytes base64",
        len(floor_rooms), len(encoded),
    )
    return encoded
