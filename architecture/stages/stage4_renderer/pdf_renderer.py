"""ReportLab-based multi-page PDF renderer for floor plan documentation."""

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)

from utils.logger import get_logger

_logger = get_logger("pdf_renderer")

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle(
    "Title",
    parent=_STYLES["Title"],
    fontSize=22,
    spaceAfter=12,
    textColor=colors.HexColor("#1A237E"),
)
_HEADING_STYLE = ParagraphStyle(
    "Heading",
    parent=_STYLES["Heading2"],
    fontSize=14,
    spaceBefore=10,
    spaceAfter=6,
    textColor=colors.HexColor("#283593"),
)
_BODY_STYLE = ParagraphStyle(
    "Body",
    parent=_STYLES["Normal"],
    fontSize=9,
    leading=13,
)


class PDFRenderer:
    """Generates a professional multi-page PDF document for the approved floor plan."""

    def render(
        self,
        svg_path: Path,
        site_schema: dict,
        buildable_zone: dict,
        floor_plan: dict,
        quality_scores: dict,
        output_path: Path,
    ) -> Path:
        """Generates a 6-page PDF document.

        Pages:
            1. Cover — project title, Plan ID, district, date
            2. Buildable zone site summary
            3. Floor plan reference (SVG path placeholder)
            4. Quality score breakdown table
            5. Room schedule table
            6. User requirements and design notes

        Args:
            svg_path: Path to the rendered SVG file from SVGRenderer.
            site_schema: Stage 1 output.
            buildable_zone: Stage 2 output.
            floor_plan: Approved floor plan dict.
            quality_scores: Output from LayoutScorer.
            output_path: Destination path for the PDF file.

        Returns:
            Path: Path to the written PDF file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )

        plan_id = site_schema.get("plan_id", "PLAN-UNKNOWN")
        district = site_schema.get("district", "N/A")
        today = date.today().isoformat()
        rooms: list[dict] = floor_plan.get("rooms", [])

        story = []

        # --- Page 1: Cover ---
        story.append(Spacer(1, 3 * cm))
        story.append(Paragraph("Residential Floor Plan Report", _TITLE_STYLE))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A237E")))
        story.append(Spacer(1, 0.5 * cm))
        cover_data = [
            ["Project", "R26-IT-117 — AI-Based Architectural Planning"],
            ["Component", "Component 01 — SLIIT"],
            ["Plan ID", plan_id],
            ["District", district],
            ["Area (sqm)", f"{site_schema.get('area_sqm', 'N/A')} m²"],
            ["Generated", today],
            ["Layout", floor_plan.get("layout_label", "N/A").title()],
            ["Finish Grade", floor_plan.get("budget_tier", "medium").title()],
        ]
        cover_table = Table(cover_data, colWidths=[5 * cm, 11 * cm])
        cover_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EAF6")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(cover_table)
        story.append(PageBreak())

        # --- Page 2: Buildable Zone Summary ---
        story.append(Paragraph("Buildable Zone Analysis", _HEADING_STYLE))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))
        bz_data = [
            ["Parameter", "Value"],
            ["Max Footprint", f"{buildable_zone.get('max_footprint_sqm', 0):.2f} m²"],
            ["Max Total Built Area", f"{buildable_zone.get('max_total_built_sqm', 0):.2f} m²"],
            ["Recommended Floors", str(buildable_zone.get("recommended_floors", "N/A"))],
            ["Coverage Achieved", f"{buildable_zone.get('coverage_achieved', 0) * 100:.1f}%"],
            ["Front Setback", f"{buildable_zone.get('setback_margins', {}).get('front', 0):.1f} m"],
            ["Rear Setback", f"{buildable_zone.get('setback_margins', {}).get('rear', 0):.1f} m"],
            ["Side Setback", f"{buildable_zone.get('setback_margins', {}).get('side', 0):.1f} m"],
        ]
        bz_table = Table(bz_data, colWidths=[8 * cm, 8 * cm])
        bz_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(bz_table)
        story.append(PageBreak())

        # --- Page 3: Floor Plan Reference ---
        story.append(Paragraph("Floor Plan", _HEADING_STYLE))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))
        story.append(
            Paragraph(
                f"SVG floor plan file: <b>{svg_path}</b>",
                _BODY_STYLE,
            )
        )
        story.append(Spacer(1, 0.5 * cm))
        story.append(
            Paragraph(
                "The floor plan SVG has been rendered and saved separately. "
                "Refer to the SVG file for the scaled drawing.",
                _BODY_STYLE,
            )
        )
        # TODO Sprint 11: embed SVG pages using svglib.renderPDF
        story.append(PageBreak())

        # --- Page 4: Quality Score Breakdown ---
        story.append(Paragraph("Quality Score Analysis", _HEADING_STYLE))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))
        score_data = [["Dimension", "Score", "Rating"]]
        for key, label in [
            ("space_utilisation", "Space Utilisation"),
            ("natural_light", "Natural Light"),
            ("adjacency_quality", "Adjacency Quality"),
            ("ventilation_potential", "Ventilation Potential"),
            ("overall", "Overall Score"),
        ]:
            val = quality_scores.get(key, 0.0)
            rating = "Excellent" if val >= 0.8 else "Good" if val >= 0.6 else "Fair" if val >= 0.4 else "Poor"
            score_data.append([label, f"{val:.2f} / 1.00", rating])

        score_table = Table(score_data, colWidths=[7 * cm, 5 * cm, 4 * cm])
        score_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EAF6")),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(score_table)
        story.append(PageBreak())

        # --- Page 5: Room Schedule ---
        story.append(Paragraph("Room Schedule", _HEADING_STYLE))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))
        room_data = [["Room Name", "Area (m²)", "Floor", "Window Orientation"]]
        for room in rooms:
            room_data.append(
                [
                    room.get("name", "").replace("_", " ").title(),
                    f"{room.get('area_sqm', 0):.1f}",
                    str(room.get("floor", 1)),
                    room.get("window_orientation", "N/A"),
                ]
            )
        room_data.append(
            ["TOTAL", f"{sum(r.get('area_sqm', 0) for r in rooms):.1f}", "", ""]
        )
        room_table = Table(room_data, colWidths=[6 * cm, 4 * cm, 3 * cm, 4 * cm])
        room_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F5F5F5")]),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EAF6")),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(room_table)
        story.append(PageBreak())

        # --- Page 6: Requirements Summary & Design Notes ---
        story.append(Paragraph("Design Notes & Requirements Summary", _HEADING_STYLE))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))
        notes = floor_plan.get("space_notes", "No additional design notes.")
        story.append(Paragraph(f"<b>Space Notes:</b> {notes}", _BODY_STYLE))
        story.append(Spacer(1, 0.4 * cm))
        coastal_note = (
            "This site is in a coastal district. Stricter BCR (0.40) and NBC coastal "
            "setbacks apply. Pile foundations recommended."
            if site_schema.get("is_coastal")
            else "Standard inland setbacks and foundation type apply."
        )
        story.append(Paragraph(f"<b>Site Notes:</b> {coastal_note}", _BODY_STYLE))
        story.append(Spacer(1, 0.4 * cm))
        story.append(
            Paragraph(
                "<i>This document was generated by Component 01 of Project R26-IT-117 "
                "at SLIIT. It is a computational planning aid and must be reviewed by a "
                "licensed architect and structural engineer before construction.</i>",
                _BODY_STYLE,
            )
        )

        doc.build(story)
        _logger.info("PDF rendered: %s (%d pages)", output_path, 6)
        return output_path
