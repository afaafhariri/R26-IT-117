"""Generates PP1_Panel_Preparation_v2.pdf using ReportLab."""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUTPUT = r"C:\Users\Asus\Desktop\Project\R26-IT-117\PP1_Panel_Preparation_v2.pdf"

DARK_BLUE  = colors.HexColor("#1a3a5c")
MID_BLUE   = colors.HexColor("#2d6a9f")
LIGHT_BLUE = colors.HexColor("#dce9f5")
ACCENT     = colors.HexColor("#e8a020")
LIGHT_GREY = colors.HexColor("#f5f5f5")
MID_GREY   = colors.HexColor("#888888")

def build_styles():
    base = getSampleStyleSheet()
    styles = {}
    styles["title"] = ParagraphStyle("title", fontSize=22, textColor=DARK_BLUE,
        fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4)
    styles["subtitle"] = ParagraphStyle("subtitle", fontSize=11, textColor=MID_BLUE,
        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=2)
    styles["meta"] = ParagraphStyle("meta", fontSize=9, textColor=MID_GREY,
        fontName="Helvetica", alignment=TA_CENTER, spaceAfter=14)
    styles["h1"] = ParagraphStyle("h1", fontSize=13, textColor=colors.white,
        fontName="Helvetica-Bold", spaceAfter=6, spaceBefore=14,
        leftIndent=8, backColor=DARK_BLUE, borderPad=5)
    styles["h2"] = ParagraphStyle("h2", fontSize=11, textColor=DARK_BLUE,
        fontName="Helvetica-Bold", spaceAfter=4, spaceBefore=8,
        leftIndent=0, borderPad=3)
    styles["body"] = ParagraphStyle("body", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=3, leading=14)
    styles["bullet"] = ParagraphStyle("bullet", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=2, leading=14, leftIndent=16,
        bulletIndent=6, bulletText="•")
    styles["q"] = ParagraphStyle("q", fontSize=10, textColor=DARK_BLUE,
        fontName="Helvetica-Bold", spaceAfter=2, spaceBefore=8,
        backColor=LIGHT_BLUE, borderPad=4, leftIndent=6)
    styles["a"] = ParagraphStyle("a", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=4, leading=14, leftIndent=10)
    styles["abul"] = ParagraphStyle("abul", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=2, leading=13, leftIndent=24,
        bulletIndent=14, bulletText="•")
    styles["num"] = ParagraphStyle("num", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=2, leading=13, leftIndent=24)
    styles["kv"] = ParagraphStyle("kv", fontSize=9.5, textColor=colors.black,
        fontName="Helvetica", spaceAfter=2, leading=13)
    styles["highlight"] = ParagraphStyle("highlight", fontSize=10, textColor=DARK_BLUE,
        fontName="Helvetica-Bold", spaceAfter=2, leading=14, leftIndent=8)
    return styles

def section_heading(text, styles):
    return Paragraph(text, styles["h1"])

def sub_heading(text, styles):
    return Paragraph(text, styles["h2"])

def body(text, styles):
    return Paragraph(text, styles["body"])

def bullet(text, styles):
    return Paragraph(text, styles["bullet"])

def make_table(headers, rows, col_widths=None):
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  DARK_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  9),
        ("BOTTOMPADDING",(0, 0), (-1, 0),  6),
        ("TOPPADDING",   (0, 0), (-1, 0),  6),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),  [colors.white, LIGHT_GREY]),
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t

def build_story(styles):
    W = A4[0] - 4*cm
    story = []

    # ── Cover block ──────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("PP1 PANEL PREPARATION GUIDE", styles["title"]))
    story.append(Paragraph("Project R26-IT-117 &mdash; AI-Based Architectural Planning Model", styles["subtitle"]))
    story.append(Paragraph("Component 01 &mdash; Architectural Planning API", styles["subtitle"]))
    story.append(Paragraph("Student: Shazni (IT22131256) &nbsp;|&nbsp; University: SLIIT &nbsp;|&nbsp; Date: May 11, 2026", styles["meta"]))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=10))

    # ── Section 1 ────────────────────────────────────────────────
    story.append(section_heading("1. PROJECT OVERVIEW", styles))
    story.append(body("<b>What it does:</b> Takes a Sri Lankan cadastral (survey) plan as input and automatically "
                      "generates 3 floor plan alternatives as SVG/PDF output, following NBC Sri Lanka building regulations.", styles))
    story.append(body("<b>Input:</b> Cadastral plan (PDF/JPG/PNG), user requirements (rooms, floors, style, budget)", styles))
    story.append(body("<b>Output:</b> 3 floor plan alternatives (SVG + PDF), Building Schema JSON for Component 02", styles))

    # ── Section 2 ────────────────────────────────────────────────
    story.append(section_heading("2. THE 4-STAGE PIPELINE", styles))

    stages = [
        ("Stage 1 — Cadastral Plan Extraction", "POST /api/v1/extract", "Synchronous",
         ["Uploads a cadastral plan image or PDF",
          "EasyOCR reads all text from the plan",
          "OpenCV detects the plot boundary polygon",
          "spaCy fine-tuned NER extracts: plan number, district, area, scale, surveyor, road access, coordinates (F=0.857, trained on 69 real SL plans)",
          "pyproj converts SLD99 survey coordinates to WGS84 GPS",
          "Output: validated Site Schema JSON"]),
        ("Stage 2 — Buildable Zone Calculation", "POST /api/v1/buildable-zone", "Synchronous",
         ["Applies NBC Sri Lanka setbacks (front/rear/side margins)",
          "Applies BCR (Building Coverage Ratio) based on district and coastal flag",
          "Shapely computes the legal buildable polygon",
          "Output: buildable polygon, max footprint sqm, recommended floors, orientation"]),
        ("Stage 3 — AI Floor Plan Generation", "POST /api/v1/generate-floor-plan", "Async (Celery)",
         ["RAG retrieves 5 similar Sri Lankan house designs from Supabase pgvector (131 entries)",
          "PromptBuilder constructs structured prompt with site constraints and RAG context",
          "Gemini 2.5 Flash generates 3 alternatives at temperatures 0.4 / 0.7 / 1.0",
          "Strip-packing layout solver eliminates room overlaps — all plans return is_valid=true",
          "Validator checks geometric violations, Scorer rates each plan on 4 dimensions",
          "Returns task_id immediately — poll GET /api/v1/floor-plan-status/{task_id}"]),
        ("Stage 4 — Render SVG/PDF", "POST /api/v1/render", "Synchronous",
         ["SVGRenderer draws floor plan with thick walls, door arcs, furniture symbols, staircase pattern, dimension lines, north arrow, title block",
          "PDFRenderer generates 6-page professional report (ReportLab)",
          "SchemaSerialiser validates Building Schema and POSTs to Component 02",
          "Output: SVG file + PDF file + Building Schema JSON"]),
    ]
    for name, endpoint, mode, bullets in stages:
        story.append(KeepTogether([
            sub_heading(f"{name}  |  {endpoint}  |  {mode}", styles),
            *[bullet(b, styles) for b in bullets],
            Spacer(1, 4),
        ]))

    # ── Section 3 ────────────────────────────────────────────────
    story.append(section_heading("3. MODELS &amp; TECHNOLOGIES", styles))
    tech_rows = [
        ["EasyOCR (CRAFT + CRNN)", "Stage 1", "Reads text from cadastral plan images"],
        ["PyTorch CNN (ResNet-based)", "Stage 1", "Classifies cadastral vs non-cadastral plans"],
        ["OpenCV (Canny + contours)", "Stage 1", "Detects plot boundary polygon"],
        ["spaCy fine-tuned NER", "Stage 1", "Custom NER trained on 69 real SL plans, F=0.857"],
        ["pyproj (EPSG:5234 to 4326)", "Stage 1", "Converts SLD99 to WGS84 GPS coordinates"],
        ["Shapely", "Stage 2", "Geometric polygon operations"],
        ["NBC Rule Engine (custom)", "Stage 2", "Sri Lanka National Building Code setbacks"],
        ["all-MiniLM-L6-v2 (SentenceTransformer)", "Stage 3", "384-dim embeddings for RAG vector search"],
        ["Supabase pgvector", "Stage 3", "Cloud vector database — 131 floor plan entries"],
        ["Gemini 2.5 Flash (Google)", "Stage 3", "LLM — generates 3 floor plan alternatives"],
        ["layout_solver.py (strip packing)", "Stage 3", "Post-processing solver eliminates room overlaps"],
        ["svgwrite", "Stage 4", "Draws SVG with walls, doors, furniture, staircase"],
        ["ReportLab", "Stage 4", "Generates 6-page professional PDF report"],
        ["jsonschema", "Stage 4", "Validates Building Schema JSON"],
        ["FastAPI", "API", "REST API framework"],
        ["Celery + Redis", "Stage 3", "Async task queue for Gemini generation"],
        ["Docker", "Infra", "Containerisation for deployment"],
    ]
    story.append(make_table(["Model / Library", "Stage", "Purpose"], tech_rows,
                             col_widths=[5.5*cm, 2.2*cm, 9.3*cm]))

    # ── Section 4 ────────────────────────────────────────────────
    story.append(section_heading("4. DATASET &amp; DATA COLLECTION", styles))
    ds_rows = [
        ["EasyOCR", "Pre-trained multilingual model (ICDAR, SynthText)", "Ready"],
        ["CNN Classifier", "Collecting 100+ SL cadastral plans from licensed surveyors", "In progress"],
        ["NER Parser", "Fine-tuned on 69 real SL cadastral plans + 41 synthetic", "F=0.857 — completed"],
        ["RAG Knowledge Base", "121 CVC FPP floor plan images via Gemini Vision + 10 original", "131 entries in Supabase"],
        ["Gemini 2.5 Flash", "Google pre-trained LLM", "Ready — API integrated"],
    ]
    story.append(make_table(["Component", "Dataset", "Status"], ds_rows,
                             col_widths=[3.5*cm, 10*cm, 3.5*cm]))
    story.append(Spacer(1, 6))
    story.append(sub_heading("CNN Classifier — 5 Classes", styles))
    for cls, desc in [
        ("surveyor_plan", "Standard licensed surveyor cadastral plan"),
        ("municipal_plan", "Municipal council subdivision plan"),
        ("uda_plan", "Urban Development Authority plan"),
        ("low_quality", "Scan too poor for reliable extraction"),
        ("non_cadastral", "Not a cadastral plan — reject"),
    ]:
        story.append(bullet(f"<b>{cls}</b> — {desc}", styles))

    # ── Section 5 ────────────────────────────────────────────────
    story.append(section_heading("5. ACCURACY &amp; PERFORMANCE METRICS", styles))
    met_rows = [
        ["EasyOCR", "Text recognition on printed cadastral plans", "85–95%"],
        ["CNN Classifier", "5-class classification accuracy", "Pending — expected 90%+"],
        ["NER Parser (fine-tuned)", "F-score on held-out eval set", "0.857 (P=0.941, R=0.787)"],
        ["Coordinate Conversion", "SLD99 to WGS84", "Mathematically exact (EPSG:5234)"],
        ["RAG Retriever", "Passages retrieved per query", "5 passages, cosine similarity"],
        ["Floor Plan Validity", "is_valid=true rate after layout solver", "100% (3/3 alternatives)"],
        ["Floor Plan Scorer", "Quality dimensions", "4: space utilisation, natural light, adjacency, ventilation"],
        ["Celery Task", "End-to-end generation time", "60–170 seconds"],
        ["Test Suite", "Unit + integration tests", "31/31 passing"],
    ]
    story.append(make_table(["Component", "Metric", "Value"], met_rows,
                             col_widths=[4.5*cm, 8*cm, 4.5*cm]))

    # ── Section 6 ────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(section_heading("6. PANEL QUESTIONS &amp; ANSWERS", styles))

    qas = [
        ("What AI/ML processes are in your system?",
         None,
         ["1. Computer Vision — OpenCV edge detection for boundary polygon",
          "2. Deep Learning OCR — EasyOCR CRAFT+CRNN neural network",
          "3. CNN Classification — ResNet-based cadastral plan classifier",
          "4. NLP/NER — Fine-tuned Named Entity Recognition (F=0.857)",
          "5. RAG — vector similarity search combined with LLM generation",
          "6. LLM Prompting — Gemini 2.5 Flash with structured prompt engineering",
          "7. Geometric Validation + Solver — Shapely polygon intersection + strip-packing layout solver"]),
        ("You use pre-trained models — is that allowed?",
         "Yes. We use pre-trained models as a base and extend them for the Sri Lankan domain. "
         "EasyOCR is extended with Sri Lankan cadastral text patterns. spaCy base model is fine-tuned on 69 real "
         "Sri Lankan cadastral plans achieving F=0.857. CNN classifier is being fine-tuned on 100+ real plans "
         "currently being collected from licensed surveyors. Gemini is prompted with Sri Lankan NBC regulations "
         "and RAG context from 131 local house design entries.",
         []),
        ("What dataset did you use?",
         None,
         ["1. EasyOCR — pre-trained, no dataset needed",
          "2. CNN — collecting 100+ SL cadastral plans from licensed surveyors (father and colleagues)",
          "3. NER — fine-tuned on 69 real cadastral plans from Ampara district surveyors + 41 synthetic. F=0.857.",
          "4. RAG — 131 entries: 10 original SL coastal descriptions + 121 CVC FPP floor plans via Gemini Vision"]),
        ("What is your accuracy?",
         "EasyOCR: 85–95% on printed cadastral text. NER fine-tuned model: F=0.857 (P=0.941, R=0.787) on real "
         "cadastral plans. Coordinate conversion: mathematically exact. CNN: fine-tuning in progress, expected 90%+. "
         "Floor plan validity: 100% after layout solver. 31/31 unit tests passing.",
         []),
        ("Why did you use RAG?",
         "RAG gives Gemini real Sri Lankan house design context. Without RAG, Gemini generates generic Western-style "
         "floor plans. With RAG, it generates designs suited for Sri Lankan climate — cross-ventilation, shade, coastal "
         "pile foundations, verandahs. We built our RAG store from 121 real floor plan images (CVC FPP dataset) "
         "analysed by Gemini Vision, giving 131 total entries in Supabase pgvector. RAG retrieves the 5 most similar "
         "designs using cosine similarity on 384-dimensional sentence embeddings.",
         []),
        ("Why 3 temperature values for Gemini?",
         "Temperature controls creativity in LLM output:",
         ["0.4 (Conservative) — low randomness, strictly follows NBC constraints",
          "0.7 (Balanced) — moderate creativity, balances rules and innovation",
          "1.0 (Creative) — high randomness, more innovative designs",
          "This gives the user 3 real alternatives to choose from."]),
        ("Why Celery and Redis?",
         "Gemini takes 60–170 seconds to generate 3 floor plans. A synchronous HTTP request would time out. "
         "Celery runs the generation as a background task, the user gets a task_id immediately and polls "
         "/floor-plan-status/{task_id} for the result. Redis is the message broker and result backend.",
         []),
        ("Why Supabase instead of a local vector database?",
         "Supabase pgvector is cloud-hosted PostgreSQL with vector extension — no local ChromaDB to manage or deploy. "
         "Works from anywhere, persistent storage, and integrates with standard SQL for structured queries alongside vector search.",
         []),
        ("What is SLD99 and why do you convert it?",
         "SLD99 (EPSG:5234) is Sri Lanka's official local coordinate system used by all licensed surveyors. "
         "GPS uses WGS84 (EPSG:4326). We convert so the plot location can be displayed on Google Maps and used "
         "by other system components. pyproj handles the mathematical transformation. "
         "Example: SLD99 E=319950, N=231025 converts to GPS lat=7.280069, lon=81.859983 (Ampara district).",
         []),
        ("What NBC regulations do you follow?",
         "NBC = National Building Code of Sri Lanka.",
         ["Front setback: 3m (national road), 2m (provincial), 1.5m (local), 1m (lane)",
          "Rear setback: 1.5m minimum",
          "Side setback: 1m minimum",
          "BCR: Colombo 0.60, Coastal districts 0.40 (stricter), Other districts 0.50",
          "Coastal sites require pile foundations"]),
        ("How does your component connect to other components?",
         "Input: Receives cadastral plan upload from frontend (Component 04). "
         "Output: Sends Building Schema JSON to Component 02 (cost estimation) via HTTP POST to /estimate endpoint. "
         "If Component 02 is unavailable, Stage 4 logs a warning and continues — the render is never blocked by C02 availability.",
         []),
        ("What are the limitations?",
         None,
         ["1. CNN fine-tuning in progress — collecting real Sri Lankan cadastral plans",
          "2. Room overlap issue resolved via strip-packing layout solver — all plans now return is_valid=true",
          "3. Currently tested primarily on Ampara district data — expanding to all 25 districts",
          "4. Generation takes 60–170 seconds due to 3 Gemini API calls"]),
    ]

    for q, ans, buls in qas:
        items = [Paragraph(f"Q: {q}", styles["q"])]
        if ans:
            items.append(Paragraph(ans, styles["a"]))
        for b in buls:
            items.append(Paragraph(b, styles["abul"]))
        items.append(Spacer(1, 2))
        story.append(KeepTogether(items))

    # ── Section 7 ────────────────────────────────────────────────
    story.append(section_heading("7. NBC SRI LANKA QUICK REFERENCE", styles))
    nbc_rows = [
        ["National Road / Main Road", "3.0m", "1.5m", "1.0m"],
        ["Provincial Road",            "2.0m", "1.5m", "1.0m"],
        ["Local Road",                 "1.5m", "1.5m", "1.0m"],
        ["Lane / Private Road",        "1.0m", "1.5m", "1.0m"],
    ]
    story.append(make_table(["Road Type", "Front Setback", "Rear Setback", "Side Setback"],
                             nbc_rows, col_widths=[5*cm, 3*cm, 3*cm, 3*cm]))
    story.append(Spacer(1, 8))
    bcr_rows = [
        ["Colombo (urban)",             "0.60", "60% of land can be built"],
        ["Other Districts (standard)",  "0.50", "50% of land can be built"],
        ["Coastal Districts (Ampara, Galle, etc.)", "0.40", "40% of land — stricter"],
    ]
    story.append(sub_heading("Building Coverage Ratio (BCR)", styles))
    story.append(make_table(["District Type", "BCR", "Meaning"],
                             bcr_rows, col_widths=[6*cm, 2.5*cm, 8.5*cm]))
    story.append(Spacer(1, 8))
    story.append(sub_heading("Foundation Type Rules", styles))
    for rule in ["Coastal site — Pile foundation",
                 "Large plot (area > 500 sqm) — Raft foundation",
                 "Standard plot — Strip foundation"]:
        story.append(bullet(rule, styles))

    # ── Section 8 ────────────────────────────────────────────────
    story.append(section_heading("8. API ENDPOINTS", styles))
    ep_rows = [
        ["POST", "/api/v1/extract",                    "Stage 1 — Upload cadastral plan, get Site Schema"],
        ["POST", "/api/v1/buildable-zone",             "Stage 2 — Compute buildable polygon"],
        ["POST", "/api/v1/generate-floor-plan",        "Stage 3 — Dispatch async floor plan generation"],
        ["GET",  "/api/v1/floor-plan-status/{task_id}","Stage 3 — Poll for generation result"],
        ["POST", "/api/v1/render",                     "Stage 4 — Render SVG + PDF + Building Schema"],
        ["GET",  "/api/v1/download/{filename}",        "Download rendered SVG or PDF file"],
        ["GET",  "/api/v1/health",                     "Health check"],
    ]
    story.append(make_table(["Method", "Endpoint", "Description"],
                             ep_rows, col_widths=[1.5*cm, 7*cm, 8.5*cm]))
    story.append(Spacer(1, 8))
    story.append(sub_heading("Infrastructure", styles))
    for item in ["API Server: FastAPI + Uvicorn (port 8001)",
                 "Task Queue: Celery 5.4 + Redis",
                 "Vector DB: Supabase pgvector (131 entries)",
                 "LLM: Gemini 2.5 Flash (Google AI Studio)",
                 "Container: Docker"]:
        story.append(bullet(item, styles))

    # ── Section 9 ────────────────────────────────────────────────
    story.append(section_heading("9. DEMO FLOW FOR PANEL", styles))
    demo_steps = [
        "GET /api/v1/health — verify status:ok, component:C01",
        "POST /api/v1/extract with cadastral plan image — get Site Schema JSON (plan_id, district, area_sqm, GPS coords)",
        "POST /api/v1/buildable-zone — get buildable polygon, max footprint, setback margins",
        "POST /api/v1/generate-floor-plan — get task_id immediately (async dispatch)",
        "GET /api/v1/floor-plan-status/{task_id} — poll until DONE — 3 alternatives: conservative, balanced, creative — all is_valid=true",
        "POST /api/v1/render with chosen plan — get SVG + PDF + Building Schema JSON",
        "Open SVG file — show floor plan with thick walls, door arcs, furniture symbols, room labels, north arrow, title block",
    ]
    for i, step in enumerate(demo_steps, 1):
        story.append(Paragraph(f"<b>Step {i}</b> — {step}", styles["num"]))

    # ── Key Numbers ──────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=6))
    story.append(Paragraph("KEY NUMBERS TO REMEMBER", styles["h2"]))
    key_nums = [
        "131 RAG entries in Supabase (10 original + 121 from CVC FPP dataset)",
        "69 real cadastral plans for NER training + 41 synthetic = 110 total",
        "NER F=0.857, Precision=0.941, Recall=0.787",
        "3 floor plan alternatives per generation (conservative / balanced / creative)",
        "100% validity rate after strip-packing layout solver",
        "31/31 unit tests passing",
        "60–170 seconds generation time",
        "7 AI/ML processes in the system",
    ]
    for n in key_nums:
        story.append(Paragraph(f"<b>✓</b>  {n}", styles["highlight"]))

    return story


def main():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
        title="PP1 Panel Preparation Guide",
        author="Shazni IT22131256",
    )
    styles = build_styles()
    story  = build_story(styles)
    doc.build(story)
    print(f"PDF written to: {OUTPUT}")


if __name__ == "__main__":
    main()
