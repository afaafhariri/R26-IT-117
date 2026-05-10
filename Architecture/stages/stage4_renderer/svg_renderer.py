"""SVG floor plan renderer using svgwrite."""

from datetime import date
from math import sqrt
from pathlib import Path

import svgwrite

from utils.logger import get_logger

_logger = get_logger("svg_renderer")

_ROOM_COLOURS: dict[str, str] = {
    "living":         "#AED6F1",  # sky blue
    "living_room":    "#AED6F1",
    "family":         "#AED6F1",
    "lounge":         "#AED6F1",
    "dining":         "#F1948A",  # coral
    "bedroom":        "#FAD7A0",  # peach
    "master_bedroom": "#F9E79F",  # yellow
    "kitchen":        "#A9DFBF",  # green
    "bathroom":       "#D2B4DE",  # lavender
    "toilet":         "#D2B4DE",
    "garage":         "#BFC9CA",  # grey
    "verandah":       "#D5D8DC",
    "balcony":        "#D5D8DC",
    "terrace":        "#D5D8DC",
    "stair":          "#E5E7E9",
    "staircase":      "#E5E7E9",
    "default":        "#FDFEFE",
}

_CANVAS_W = 1400
_CANVAS_H = 870
_MARGIN    = 55
_TITLE_H   = 38
_HEADER_H  = 32
_DIM_OFFSET = 30
_WALL_W     = 4


def _room_colour(name: str) -> str:
    key = name.lower().replace(" ", "_").replace("/", "_")
    # Exact match first, then startswith, then substring — prevents
    # "bedroom" matching inside "master_bedroom"
    if key in _ROOM_COLOURS:
        return _ROOM_COLOURS[key]
    for k, v in _ROOM_COLOURS.items():
        if key.startswith(k):
            return v
    for k, v in _ROOM_COLOURS.items():
        if k in key:
            return v
    return _ROOM_COLOURS["default"]


def _is_stair(name: str) -> bool:
    return "stair" in name.lower().replace(" ", "")


def _is_outdoor(name: str) -> bool:
    n = name.lower().replace(" ", "_")
    return any(x in n for x in ("balcony", "verandah", "terrace", "porch"))


def _door_wall(orient: str) -> str:
    return {"north": "south", "south": "north", "east": "west", "west": "east"}.get(
        orient.lower().split("|")[0].strip(), "south"
    )


class SVGRenderer:
    """Renders an approved floor plan as a scaled SVG diagram."""

    def render(
        self,
        floor_plan: dict,
        buildable_zone: dict,
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rooms: list[dict] = floor_plan.get("rooms", [])
        plan_id      = floor_plan.get("plan_id", "PLAN-UNKNOWN")
        layout_label = floor_plan.get("layout_label", "")
        finish_grade = floor_plan.get("budget_tier", "medium")

        footprint   = buildable_zone.get("max_footprint_sqm", 120.0)
        real_side_m = sqrt(footprint)

        floors: dict[int, list[dict]] = {}
        for room in rooms:
            f = room.get("floor", 1)
            floors.setdefault(f, []).append(room)

        floor_numbers = sorted(floors.keys())
        num_floors    = len(floor_numbers)

        dwg = svgwrite.Drawing(str(output_path), size=(f"{_CANVAS_W}px", f"{_CANVAS_H}px"))

        # ── Background ────────────────────────────────────────────────────────
        dwg.add(dwg.rect(insert=(0, 0), size=("100%", "100%"), fill="#F4F6F7"))

        # ── Header bar ───────────────────────────────────────────────────────
        dwg.add(dwg.rect(insert=(0, 0), size=(_CANVAS_W, _HEADER_H), fill="#1A237E"))
        dwg.add(dwg.text(
            f"R26-IT-117  |  Plan: {plan_id}  |  Layout: {layout_label.title()}  |  Date: {date.today().isoformat()}",
            insert=(14, 22),
            font_size="12px", font_family="Arial, sans-serif",
            font_weight="bold", fill="white",
        ))

        # ── North arrow ───────────────────────────────────────────────────────
        _add_north_arrow(dwg, _CANVAS_W - 105, _HEADER_H + 68)

        draw_top    = _HEADER_H + _MARGIN
        draw_bottom = _CANVAS_H - _TITLE_H - 24
        draw_h      = draw_bottom - draw_top

        dim_pad = 32
        _RIGHT_RESERVE = 90  # space for north arrow
        panel_w = (_CANVAS_W - _MARGIN * (num_floors + 1) - dim_pad * num_floors - _RIGHT_RESERVE) // num_floors

        for idx, floor_num in enumerate(floor_numbers):
            floor_rooms = floors[floor_num]
            panel_x = _MARGIN + dim_pad + idx * (panel_w + _MARGIN + dim_pad)
            panel_y = draw_top

            floor_label = "Ground Floor" if floor_num == 1 else f"Floor {floor_num}"

            dwg.add(dwg.text(
                floor_label,
                insert=(panel_x + panel_w / 2, panel_y + 20),
                text_anchor="middle",
                font_size="14px", font_family="Arial, sans-serif",
                font_weight="bold", fill="#1A237E",
            ))

            room_top = panel_y + 28
            room_h   = draw_h - 28

            # Outer wall (thick border)
            dwg.add(dwg.rect(
                insert=(panel_x, room_top), size=(panel_w, room_h),
                fill="white", stroke="#1A1A1A", stroke_width=_WALL_W + 2,
            ))

            for room in floor_rooms:
                rx = panel_x + room.get("x_norm", 0) * panel_w
                ry = room_top  + room.get("y_norm", 0) * room_h
                rw = max(room.get("width_norm",  0.1) * panel_w, 24)
                rh = max(room.get("height_norm", 0.1) * room_h,  24)
                rname  = room.get("name", "")
                orient = room.get("window_orientation", "south")
                fill   = _room_colour(rname)

                # Room rectangle with thick walls
                dwg.add(dwg.rect(
                    insert=(rx, ry), size=(rw, rh),
                    fill=fill, stroke="#1A1A1A", stroke_width=_WALL_W,
                ))

                # Outdoor hatching
                if _is_outdoor(rname):
                    _add_hatching(dwg, rx, ry, rw, rh)

                # Staircase or door + furniture
                if _is_stair(rname):
                    _add_staircase_pattern(dwg, rx, ry, rw, rh)
                else:
                    _add_door_arc(dwg, rx, ry, rw, rh, _door_wall(orient))
                    _add_furniture(dwg, rx, ry, rw, rh, rname)

                # Room name + area label
                cx = rx + rw / 2
                cy = ry + rh / 2
                name_text = rname.replace("_", " ").title()
                area      = room.get("area_sqm", 0)

                dwg.add(dwg.text(
                    name_text,
                    insert=(cx, cy - 6),
                    text_anchor="middle",
                    font_size="10px", font_family="Arial, sans-serif",
                    font_weight="bold", fill="#1A1A1A",
                ))
                dwg.add(dwg.text(
                    f"{area:.1f} m²",
                    insert=(cx, cy + 8),
                    text_anchor="middle",
                    font_size="9px", font_family="Arial, sans-serif",
                    fill="#555555",
                ))

                # Window indicator
                _add_window_indicator(dwg, rx, ry, rw, rh, orient)

                # Dimension lines
                w_m = room.get("width_norm",  0) * real_side_m
                h_m = room.get("height_norm", 0) * real_side_m
                _add_dim_width(dwg, rx, ry, rw, w_m)
                _add_dim_height(dwg, rx, ry, rh, h_m)

        # ── Legend ────────────────────────────────────────────────────────────
        _add_legend(dwg, _MARGIN, draw_bottom + 4)

        # ── Scale bar ─────────────────────────────────────────────────────────
        _add_scale_bar(dwg, _CANVAS_W - 220, draw_bottom + 4, real_side_m)

        # ── Title block ───────────────────────────────────────────────────────
        _add_title_block(
            dwg, _MARGIN, _CANVAS_H - _TITLE_H,
            _CANVAS_W - 2 * _MARGIN,
            plan_id, finish_grade,
        )

        dwg.save()
        _logger.info("SVG rendered: %s (%d rooms, %d floors)", output_path, len(rooms), num_floors)
        return output_path


# ── Furniture helpers ─────────────────────────────────────────────────────────

def _add_furniture(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float, name: str) -> None:
    if rw < 32 or rh < 32:
        return
    n = name.lower().replace(" ", "_")
    if any(x in n for x in ("bedroom", "master")):
        _furniture_bedroom(dwg, rx, ry, rw, rh)
    elif any(x in n for x in ("living", "lounge", "family")):
        _furniture_living(dwg, rx, ry, rw, rh)
    elif "kitchen" in n:
        _furniture_kitchen(dwg, rx, ry, rw, rh)
    elif any(x in n for x in ("bathroom", "toilet", "wc")):
        _furniture_bathroom(dwg, rx, ry, rw, rh)
    elif "dining" in n:
        _furniture_dining(dwg, rx, ry, rw, rh)
    elif "garage" in n:
        _furniture_garage(dwg, rx, ry, rw, rh)


def _furniture_bedroom(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    bw = min(rw * 0.55, rh * 0.6, 72)
    bh = min(rw * 0.65, rh * 0.65, 82)
    bx = rx + (rw - bw) / 2
    by = ry + (rh - bh) / 2
    dwg.add(dwg.rect(insert=(bx, by), size=(bw, bh),
                     fill="white", stroke="#888", stroke_width=1))
    # Headboard
    dwg.add(dwg.rect(insert=(bx, by), size=(bw, bh * 0.18),
                     fill="#cccccc", stroke="#888", stroke_width=0.8))
    # Pillows
    pw, ph = bw * 0.38, bh * 0.16
    dwg.add(dwg.rect(insert=(bx + bw * 0.05, by + bh * 0.04), size=(pw, ph),
                     fill="#eeeeee", stroke="#aaa", stroke_width=0.5, rx=2))
    dwg.add(dwg.rect(insert=(bx + bw * 0.55, by + bh * 0.04), size=(pw, ph),
                     fill="#eeeeee", stroke="#aaa", stroke_width=0.5, rx=2))


def _furniture_living(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    sw = min(rw * 0.70, 90)
    sh = min(rh * 0.22, 22)
    sx = rx + (rw - sw) / 2
    sy = ry + rh * 0.62
    dwg.add(dwg.rect(insert=(sx, sy), size=(sw, sh),
                     fill="white", stroke="#888", stroke_width=1))
    aw = sw * 0.10
    dwg.add(dwg.rect(insert=(sx, sy), size=(aw, sh),
                     fill="#dddddd", stroke="#888", stroke_width=0.7))
    dwg.add(dwg.rect(insert=(sx + sw - aw, sy), size=(aw, sh),
                     fill="#dddddd", stroke="#888", stroke_width=0.7))
    # Coffee table
    tw, th = sw * 0.38, sh * 0.75
    dwg.add(dwg.rect(insert=(rx + (rw - tw) / 2, sy - th - 5), size=(tw, th),
                     fill="white", stroke="#888", stroke_width=0.8))


def _furniture_kitchen(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    cw = rw * 0.82
    ch = min(rh * 0.22, 18)
    cx = rx + rw * 0.09
    cy = ry + rh - ch - 3
    dwg.add(dwg.rect(insert=(cx, cy), size=(cw, ch),
                     fill="#dddddd", stroke="#888", stroke_width=0.8))
    # Sink
    sr = min(ch * 0.38, 7)
    dwg.add(dwg.circle(center=(cx + cw * 0.18, cy + ch / 2), r=sr,
                       fill="white", stroke="#888", stroke_width=0.8))
    # Burners
    for boff in (0.52, 0.65, 0.78):
        dwg.add(dwg.circle(center=(cx + cw * boff, cy + ch / 2), r=sr * 0.7,
                           fill="none", stroke="#888", stroke_width=0.7))


def _furniture_bathroom(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    tr = min(min(rw, rh) * 0.22, 16)
    tcx, tcy = rx + rw * 0.72, ry + rh * 0.30
    # Toilet bowl
    dwg.add(dwg.ellipse(center=(tcx, tcy), r=(tr * 0.75, tr),
                        fill="white", stroke="#888", stroke_width=1))
    # Cistern
    dwg.add(dwg.ellipse(center=(tcx, tcy - tr * 0.65), r=(tr * 0.55, tr * 0.28),
                        fill="#dddddd", stroke="#888", stroke_width=0.7))
    # Sink
    sw, sh = min(rw * 0.36, 28), min(rh * 0.24, 20)
    dwg.add(dwg.rect(insert=(rx + rw * 0.12, ry + rh * 0.15), size=(sw, sh),
                     fill="white", stroke="#888", stroke_width=0.8, rx=3))


def _furniture_dining(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    tw = min(rw * 0.50, 60)
    th = min(rh * 0.45, 50)
    tx = rx + (rw - tw) / 2
    ty = ry + (rh - th) / 2
    dwg.add(dwg.rect(insert=(tx, ty), size=(tw, th),
                     fill="white", stroke="#888", stroke_width=1))
    cw, ch = min(tw * 0.22, 12), min(th * 0.20, 10)
    for cxoff in (0.15, 0.55):
        dwg.add(dwg.rect(insert=(tx + tw * cxoff, ty - ch - 2), size=(cw, ch),
                         fill="#dddddd", stroke="#888", stroke_width=0.5))
        dwg.add(dwg.rect(insert=(tx + tw * cxoff, ty + th + 2), size=(cw, ch),
                         fill="#dddddd", stroke="#888", stroke_width=0.5))
    for cyoff in (0.20, 0.65):
        dwg.add(dwg.rect(insert=(tx - cw - 2, ty + th * cyoff), size=(cw, ch),
                         fill="#dddddd", stroke="#888", stroke_width=0.5))
        dwg.add(dwg.rect(insert=(tx + tw + 2, ty + th * cyoff), size=(cw, ch),
                         fill="#dddddd", stroke="#888", stroke_width=0.5))


def _furniture_garage(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    cw = min(rw * 0.70, 80)
    ch = min(rh * 0.55, 55)
    cx = rx + (rw - cw) / 2
    cy = ry + (rh - ch) / 2
    dwg.add(dwg.rect(insert=(cx, cy), size=(cw, ch),
                     fill="#e0e0e0", stroke="#888", stroke_width=1, rx=6))
    dwg.add(dwg.line(start=(cx + cw * 0.2, cy + ch * 0.12),
                     end=(cx + cw * 0.8, cy + ch * 0.12), stroke="#aaa", stroke_width=0.8))
    dwg.add(dwg.line(start=(cx + cw * 0.2, cy + ch * 0.85),
                     end=(cx + cw * 0.8, cy + ch * 0.85), stroke="#aaa", stroke_width=0.8))


# ── Staircase ─────────────────────────────────────────────────────────────────

def _add_staircase_pattern(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    n_steps = max(5, int(rh / 10))
    step_h  = rh / n_steps
    for i in range(1, n_steps):
        y = ry + i * step_h
        dwg.add(dwg.line(start=(rx + 3, y), end=(rx + rw - 3, y),
                         stroke="#555", stroke_width=0.9))
    mx = rx + rw / 2
    dwg.add(dwg.line(start=(mx, ry + rh - 14), end=(mx, ry + 16),
                     stroke="#333", stroke_width=1.5))
    dwg.add(dwg.polygon(points=[(mx - 5, ry + 22), (mx + 5, ry + 22), (mx, ry + 12)],
                        fill="#333"))
    dwg.add(dwg.text("UP", insert=(mx + 8, ry + 20),
                     font_size="7px", font_family="Arial", fill="#333"))


# ── Door arc ──────────────────────────────────────────────────────────────────

def _add_door_arc(
    dwg: svgwrite.Drawing,
    rx: float, ry: float, rw: float, rh: float, wall: str,
) -> None:
    arc_r = max(min(rw * 0.27, rh * 0.27, 24), 10)
    s, sw = "#333", 0.9

    if wall == "south":
        hx, hy = rx, ry + rh
        dwg.add(dwg.line(start=(hx, hy), end=(hx + arc_r, hy), stroke=s, stroke_width=sw))
        dwg.add(dwg.path(
            d=f"M {hx+arc_r:.1f},{hy:.1f} A {arc_r:.1f},{arc_r:.1f} 0 0,0 {hx:.1f},{hy-arc_r:.1f}",
            fill="none", stroke=s, stroke_width=sw,
        ))
    elif wall == "north":
        hx, hy = rx, ry
        dwg.add(dwg.line(start=(hx, hy), end=(hx + arc_r, hy), stroke=s, stroke_width=sw))
        dwg.add(dwg.path(
            d=f"M {hx+arc_r:.1f},{hy:.1f} A {arc_r:.1f},{arc_r:.1f} 0 0,1 {hx:.1f},{hy+arc_r:.1f}",
            fill="none", stroke=s, stroke_width=sw,
        ))
    elif wall == "west":
        hx, hy = rx, ry
        dwg.add(dwg.line(start=(hx, hy), end=(hx, hy + arc_r), stroke=s, stroke_width=sw))
        dwg.add(dwg.path(
            d=f"M {hx:.1f},{hy+arc_r:.1f} A {arc_r:.1f},{arc_r:.1f} 0 0,1 {hx+arc_r:.1f},{hy:.1f}",
            fill="none", stroke=s, stroke_width=sw,
        ))
    elif wall == "east":
        hx, hy = rx + rw, ry
        dwg.add(dwg.line(start=(hx, hy), end=(hx, hy + arc_r), stroke=s, stroke_width=sw))
        dwg.add(dwg.path(
            d=f"M {hx:.1f},{hy+arc_r:.1f} A {arc_r:.1f},{arc_r:.1f} 0 0,0 {hx-arc_r:.1f},{hy:.1f}",
            fill="none", stroke=s, stroke_width=sw,
        ))


# ── Hatching (outdoor areas) ──────────────────────────────────────────────────

def _add_hatching(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, rh: float) -> None:
    spacing = 10
    n = int((rw + rh) / spacing) + 2
    for i in range(n):
        offset = i * spacing
        x1 = rx + min(offset, rw)
        y1 = ry + max(0.0, offset - rw)
        x2 = rx + max(0.0, offset - rh)
        y2 = ry + min(offset, rh)
        if abs(x1 - x2) > 0.5 or abs(y1 - y2) > 0.5:
            dwg.add(dwg.line(start=(x1, y1), end=(x2, y2),
                             stroke="#bbbbbb", stroke_width=0.6))


# ── Window indicator ──────────────────────────────────────────────────────────

def _add_window_indicator(
    dwg: svgwrite.Drawing,
    rx: float, ry: float, rw: float, rh: float, orient: str,
) -> None:
    orient = orient.lower().split("|")[0].strip()
    bar_len = min(rw * 0.35, 28)
    bar_h   = min(rh * 0.35, 28)
    t = 4
    color = "#00ACC1"
    if orient == "north":
        dwg.add(dwg.rect(insert=(rx + rw / 2 - bar_len / 2, ry), size=(bar_len, t), fill=color))
    elif orient == "south":
        dwg.add(dwg.rect(insert=(rx + rw / 2 - bar_len / 2, ry + rh - t), size=(bar_len, t), fill=color))
    elif orient == "east":
        dwg.add(dwg.rect(insert=(rx + rw - t, ry + rh / 2 - bar_h / 2), size=(t, bar_h), fill=color))
    elif orient == "west":
        dwg.add(dwg.rect(insert=(rx, ry + rh / 2 - bar_h / 2), size=(t, bar_h), fill=color))


# ── Dimension lines ───────────────────────────────────────────────────────────

def _add_dim_width(dwg: svgwrite.Drawing, rx: float, ry: float, rw: float, w_m: float) -> None:
    y = ry - _DIM_OFFSET
    dwg.add(dwg.line(start=(rx, ry - 4), end=(rx, y + 4), stroke="#888", stroke_width=0.7))
    dwg.add(dwg.line(start=(rx + rw, ry - 4), end=(rx + rw, y + 4), stroke="#888", stroke_width=0.7))
    dwg.add(dwg.line(start=(rx, y), end=(rx + rw, y), stroke="#E74C3C", stroke_width=1))
    dwg.add(dwg.polygon(points=[(rx, y), (rx + 5, y - 3), (rx + 5, y + 3)], fill="#E74C3C"))
    dwg.add(dwg.polygon(points=[(rx + rw, y), (rx + rw - 5, y - 3), (rx + rw - 5, y + 3)], fill="#E74C3C"))
    dwg.add(dwg.text(
        f"{w_m:.1f} m", insert=(rx + rw / 2, y - 3),
        text_anchor="middle",
        font_size="8px", font_family="Arial", fill="#C0392B", font_weight="bold",
    ))


def _add_dim_height(dwg: svgwrite.Drawing, rx: float, ry: float, rh: float, h_m: float) -> None:
    x = rx - _DIM_OFFSET
    dwg.add(dwg.line(start=(rx - 4, ry), end=(x + 4, ry), stroke="#888", stroke_width=0.7))
    dwg.add(dwg.line(start=(rx - 4, ry + rh), end=(x + 4, ry + rh), stroke="#888", stroke_width=0.7))
    dwg.add(dwg.line(start=(x, ry), end=(x, ry + rh), stroke="#2980B9", stroke_width=1))
    dwg.add(dwg.polygon(points=[(x, ry), (x - 3, ry + 5), (x + 3, ry + 5)], fill="#2980B9"))
    dwg.add(dwg.polygon(points=[(x, ry + rh), (x - 3, ry + rh - 5), (x + 3, ry + rh - 5)], fill="#2980B9"))
    txt = dwg.text(
        f"{h_m:.1f} m", insert=(x - 3, ry + rh / 2),
        text_anchor="middle",
        font_size="8px", font_family="Arial", fill="#1F618D", font_weight="bold",
    )
    txt.rotate(-90, center=(x - 3, ry + rh / 2))
    dwg.add(txt)


# ── North arrow ───────────────────────────────────────────────────────────────

def _add_north_arrow(dwg: svgwrite.Drawing, cx: float, cy: float) -> None:
    r = 26
    # White background halo so arrow is visible against any room colour
    dwg.add(dwg.circle(center=(cx, cy), r=r + 4, fill="white", stroke="none"))
    dwg.add(dwg.circle(center=(cx, cy), r=r, fill="#F4F6F7", stroke="#1A237E", stroke_width=1.8))
    # Filled north half (dark)
    dwg.add(dwg.polygon(
        points=[(cx, cy - r + 3), (cx - 6, cy), (cx + 6, cy)],
        fill="#1A237E",
    ))
    # South half (white)
    dwg.add(dwg.polygon(
        points=[(cx, cy + r - 3), (cx - 6, cy), (cx + 6, cy)],
        fill="white", stroke="#1A237E", stroke_width=0.8,
    ))
    # Centre dot
    dwg.add(dwg.circle(center=(cx, cy), r=2.5, fill="#1A237E"))
    # "N" label above the circle
    dwg.add(dwg.text("N", insert=(cx, cy - r - 6), text_anchor="middle",
                     font_size="14px", font_family="Arial", font_weight="bold", fill="#1A237E"))


# ── Scale bar ─────────────────────────────────────────────────────────────────

def _add_scale_bar(dwg: svgwrite.Drawing, x: float, y: float, real_side_m: float) -> None:
    bar_w, segments = 100, 4
    seg_w = bar_w / segments
    seg_m = real_side_m / segments
    for i in range(segments):
        fill = "#2C3E50" if i % 2 == 0 else "white"
        dwg.add(dwg.rect(insert=(x + i * seg_w, y), size=(seg_w, 7),
                         fill=fill, stroke="#2C3E50", stroke_width=0.7))
    dwg.add(dwg.text("0", insert=(x - 2, y + 17), font_size="8px", font_family="Arial", fill="#555"))
    dwg.add(dwg.text(f"{real_side_m:.1f} m", insert=(x + bar_w + 3, y + 17),
                     font_size="8px", font_family="Arial", fill="#555"))
    dwg.add(dwg.text("Scale bar", insert=(x + bar_w / 2, y - 2),
                     text_anchor="middle", font_size="7px", font_family="Arial", fill="#888"))


# ── Legend ────────────────────────────────────────────────────────────────────

def _add_legend(dwg: svgwrite.Drawing, x: float, y: float) -> None:
    items = [
        ("Living / Dining", "#AED6F1"),
        ("Bedroom",         "#FAD7A0"),
        ("Master Bedroom",  "#F9E79F"),
        ("Kitchen",         "#A9DFBF"),
        ("Bathroom",        "#D2B4DE"),
        ("Other",           "#BFC9CA"),
    ]
    dwg.add(dwg.text("Legend:", insert=(x, y + 10),
                     font_size="8px", font_family="Arial", font_weight="bold", fill="#333"))
    for i, (label, color) in enumerate(items):
        lx = x + 52 + i * 90
        dwg.add(dwg.rect(insert=(lx, y + 1), size=(12, 12), fill=color,
                         stroke="#555", stroke_width=0.6))
        dwg.add(dwg.text(label, insert=(lx + 15, y + 11),
                         font_size="8px", font_family="Arial", fill="#444"))
    wx = x + 52 + len(items) * 90
    dwg.add(dwg.rect(insert=(wx, y + 4), size=(20, 4), fill="#00ACC1"))
    dwg.add(dwg.text("Window", insert=(wx + 24, y + 11),
                     font_size="8px", font_family="Arial", fill="#444"))


# ── Title block ───────────────────────────────────────────────────────────────

def _add_title_block(
    dwg: svgwrite.Drawing,
    x: float, y: float, width: float,
    plan_id: str, finish_grade: str,
) -> None:
    dwg.add(dwg.rect(insert=(x, y), size=(width, _TITLE_H),
                     fill="#EBF5FB", stroke="#2C3E50", stroke_width=0.7))
    dwg.add(dwg.line(start=(x, y), end=(x + width, y), stroke="#1A237E", stroke_width=2))
    label = (
        f"Plan ID: {plan_id}   |   Finish Grade: {finish_grade.title()}   |   "
        "Component 01 — AI-Based Architectural Planning   |   Project R26-IT-117 SLIIT"
    )
    dwg.add(dwg.text(label, insert=(x + 10, y + 24),
                     font_size="10px", font_family="Arial", fill="#1A237E", font_weight="bold"))
