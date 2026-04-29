"""
pdf_renderer.py — ReportLab-based PDF floor plan renderer.

Draws room polygons, labels, and a title block onto an A3 PDF page
and returns the document as a base64-encoded bytes string.
"""

import base64
import io
import logging

logger = logging.getLogger(__name__)

_PTS_PER_METRE = 28.35  # 1 metre = 28.35 points at 1:1; adjust scale below
_SCALE = 15.0            # drawing scale: points per metre on page
_MARGIN_PT = 40.0
_PAGE_WIDTH_PT = 841.89  # A3 landscape width
_PAGE_HEIGHT_PT = 595.28  # A3 landscape height


class PDFRenderer:
    """Renders a floor plan dict to a base64-encoded PDF document."""

    def render(self, floor_plan: dict) -> str:
        """
        Convert a floor plan to a base64-encoded PDF string.

        Args:
            floor_plan: Floor plan dict with a 'rooms' list and metadata.

        Returns:
            Base64-encoded PDF bytes string.

        Raises:
            RuntimeError: If PDF generation fails.
        """
        try:
            from reportlab.pdfgen import canvas as rl_canvas  # type: ignore
            from reportlab.lib import colors  # type: ignore
        except ImportError:
            logger.warning("ReportLab not available — returning stub PDF.")
            return self._stub_pdf_b64()

        try:
            buffer = io.BytesIO()
            c = rl_canvas.Canvas(
                buffer,
                pagesize=(_PAGE_WIDTH_PT, _PAGE_HEIGHT_PT),
            )

            rooms = floor_plan.get("rooms", [])
            plan_id = floor_plan.get("floor_plan_id", "unknown")
            style = floor_plan.get("style", "N/A")
            floors = floor_plan.get("total_floors", 1)

            self._draw_title_block(c, plan_id, style, floors, colors)
            self._draw_rooms(c, rooms, colors)
            self._draw_legend(c, rooms, colors)

            c.showPage()
            c.save()

            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode("utf-8")

        except Exception as exc:
            logger.exception("PDF rendering failed")
            raise RuntimeError(f"PDF rendering error: {exc}") from exc

    def _draw_title_block(
        self, c, plan_id: str, style: str, floors: int, colors
    ) -> None:
        """Draw a title block at the top of the page."""
        c.setFont("Helvetica-Bold", 14)
        c.drawString(_MARGIN_PT, _PAGE_HEIGHT_PT - _MARGIN_PT, "AI-Driven Construction Planner")
        c.setFont("Helvetica", 10)
        c.drawString(
            _MARGIN_PT,
            _PAGE_HEIGHT_PT - _MARGIN_PT - 18,
            f"Plan ID: {plan_id}   |   Style: {style}   |   Floors: {floors}",
        )
        c.setStrokeColor(colors.black)
        c.line(
            _MARGIN_PT,
            _PAGE_HEIGHT_PT - _MARGIN_PT - 25,
            _PAGE_WIDTH_PT - _MARGIN_PT,
            _PAGE_HEIGHT_PT - _MARGIN_PT - 25,
        )

    def _draw_rooms(self, c, rooms: list[dict], colors) -> None:
        """Draw all room polygons with fill, border, and label."""
        y_offset = _PAGE_HEIGHT_PT - _MARGIN_PT - 50  # start below title block

        for room in rooms:
            polygon = room.get("polygon", [])
            if len(polygon) < 3:
                continue

            scaled = [
                (
                    pt[0] * _SCALE + _MARGIN_PT,
                    y_offset - pt[1] * _SCALE,  # flip Y axis for PDF coordinate system
                )
                for pt in polygon
            ]

            # Draw filled polygon
            path = c.beginPath()
            path.moveTo(*scaled[0])
            for pt in scaled[1:]:
                path.lineTo(*pt)
            path.close()

            c.setFillColorRGB(0.96, 0.94, 0.91)  # warm off-white fill
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.75)
            c.drawPath(path, fill=1, stroke=1)

            # Label at centroid
            cx = sum(pt[0] for pt in scaled) / len(scaled)
            cy = sum(pt[1] for pt in scaled) / len(scaled)
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.black)
            label = f"{room.get('name', '?')}\n{room.get('area_sqm', 0):.1f} m²"
            c.drawCentredString(cx, cy, label.replace("\n", " "))

    def _draw_legend(self, c, rooms: list[dict], colors) -> None:
        """Draw a simple room schedule table at the bottom of the page."""
        x = _MARGIN_PT
        y = _MARGIN_PT + 10 * len(rooms) + 20

        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y, "Room Schedule")
        c.setFont("Helvetica", 7)
        y -= 12
        for room in rooms:
            line = (
                f"{room.get('name', '?')}  —  "
                f"Floor {room.get('floor', 1)}  —  "
                f"{room.get('area_sqm', 0):.1f} m²"
            )
            c.drawString(x, y, line)
            y -= 10

    @staticmethod
    def _stub_pdf_b64() -> str:
        """Minimal placeholder PDF (valid 1-byte stub for dev without ReportLab)."""
        # TODO: generate a real minimal PDF once ReportLab is installed
        stub_text = b"%PDF-1.4 placeholder — ReportLab not installed"
        return base64.b64encode(stub_text).decode("utf-8")
