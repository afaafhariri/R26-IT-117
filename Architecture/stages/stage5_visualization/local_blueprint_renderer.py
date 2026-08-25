"""Local, cost-free 2D floor plan blueprint renderer using Pillow.

Draws a top-down blueprint directly from the solved room layout data instead
of relying on an AI image model, which doesn't reliably draw accurate
technical drawings from a prompt. No external API calls, no cost, always
correct.
"""

from __future__ import annotations

import base64
import io
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

from models.schemas import Room
from utils.logger import get_logger

_logger = get_logger("local_blueprint_renderer")

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


def _load_fonts() -> tuple[ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    try:
        return (
            ImageFont.truetype("arial.ttf", 20),
            ImageFont.truetype("arial.ttf", 13),
            ImageFont.truetype("arial.ttf", 11),
        )
    except Exception:
        default = ImageFont.load_default()
        return default, default, default


def render_blueprint_png(rooms: list[Room], total_built_area_sqft: float, layout_label: str) -> str:
    """Renders a top-down 2D floor plan PNG directly from solved room layout data.

    Args:
        rooms: Solved room layout (position_x/y and width_ft/length_ft share
            one coordinate system, same as FloorPlanCard's mini layout).
        total_built_area_sqft: Total built area across all rooms.
        layout_label: Variant name (conservative/balanced/creative) for the title.

    Returns:
        str: Base64-encoded PNG (no ``data:`` URI prefix), matching the format
            the frontend expects for ``blueprint_2d_image_base64``. Empty
            string if there are no rooms to draw.
    """
    if not rooms:
        return ""

    by_floor: dict[int, list[Room]] = defaultdict(list)
    for r in rooms:
        by_floor[r.floor or 1].append(r)

    floor_numbers = sorted(by_floor)
    panel_w, panel_h = 700, 700
    margin = 40
    canvas_w = panel_w * len(floor_numbers) + margin * (len(floor_numbers) + 1)
    canvas_h = panel_h + margin * 2 + 60

    img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font_title, font_room, font_small = _load_fonts()

    draw.text(
        (margin, 10),
        f"{layout_label.title()} Layout — Total Built Area: {total_built_area_sqft:.0f} sqft",
        fill=(26, 35, 126), font=font_title,
    )

    for idx, floor_num in enumerate(floor_numbers):
        floor_rooms = by_floor[floor_num]
        panel_x = margin + idx * (panel_w + margin)
        panel_y = margin + 40

        xs = [r.position_x for r in floor_rooms] + [r.position_x + r.width_ft for r in floor_rooms]
        ys = [r.position_y for r in floor_rooms] + [r.position_y + r.length_ft for r in floor_rooms]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        range_x = (max_x - min_x) or 1
        range_y = (max_y - min_y) or 1

        pad = 20
        draw_w, draw_h = panel_w - pad * 2, panel_h - pad * 2

        floor_label = "Ground Floor" if floor_num == 1 else f"Floor {floor_num}"
        draw.text((panel_x + panel_w / 2, panel_y - 15), floor_label, fill=(26, 35, 126), font=font_room, anchor="mm")

        draw.rectangle(
            [panel_x, panel_y, panel_x + panel_w, panel_y + panel_h],
            outline=(20, 20, 20), width=2,
        )

        for room in floor_rooms:
            rx = panel_x + pad + (room.position_x - min_x) / range_x * draw_w
            ry = panel_y + pad + (room.position_y - min_y) / range_y * draw_h
            rw = max(room.width_ft / range_x * draw_w, 20)
            rh = max(room.length_ft / range_y * draw_h, 20)

            colour = _room_colour(room.name)
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=colour, outline=(20, 20, 20), width=2)

            name_text = room.name.replace("_", " ").title()
            area_text = f"{room.area_sqft:.0f} sqft"
            draw.text((rx + rw / 2, ry + rh / 2 - 8), name_text, fill=(20, 20, 20), font=font_room, anchor="mm")
            draw.text((rx + rw / 2, ry + rh / 2 + 8), area_text, fill=(80, 80, 80), font=font_small, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    _logger.info(
        "Local blueprint PNG rendered: %d floor(s), %d bytes base64",
        len(floor_numbers), len(encoded),
    )
    return encoded
