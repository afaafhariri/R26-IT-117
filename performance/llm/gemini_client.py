import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ── Configure Gemini ──────────────────────────────────────────────────────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
_model = None


def _get_model():
    global _model
    if _model is None:
        _model = genai.GenerativeModel("gemini-1.5-flash")
    return _model


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    phase_group:   str,
    sub_phase:     str,
    district:      str,
    province:      str,
    alert_level:   str,
    delay_risk:    str,
    delay_days:    int,
    similar_cases: list[dict],
) -> str:

    cases_text = ""
    for c in similar_cases:
        cases_text += f"\n---\n{c['summary']}\n"

    return f"""You are an expert construction project advisor specializing in Sri Lankan residential construction.

A construction project has triggered a {alert_level} schedule alert.

PROJECT CONTEXT:
- Location     : {district}, {province}
- Phase        : {phase_group} / {sub_phase}
- Predicted Risk: {delay_risk}
- Estimated Delay: {delay_days} days

SIMILAR HISTORICAL CASES FROM SRI LANKA:
{cases_text}

Based on the project context and the similar historical cases above, provide a concise advisory response with exactly these three sections:

1. LIKELY CAUSES
List the most probable causes of this delay based on the location, phase, and similar cases.

2. CORRECTIVE ACTIONS
List specific, actionable steps the project manager should take immediately.

3. RECOVERY ESTIMATE
Estimate how many days could be recovered if corrective actions are taken promptly.

Keep each section to 3-4 bullet points. Be specific to the Sri Lankan construction context."""


# ── Main function ─────────────────────────────────────────────────────────────

def generate_recommendations(
    phase_group:   str,
    sub_phase:     str,
    district:      str,
    province:      str,
    alert_level:   str,
    delay_risk:    str,
    delay_days:    int,
    similar_cases: list[dict],
) -> dict:
    """
    Call Gemini with project context + RAG cases.

    Returns:
        {
            "likely_causes":      "...",
            "corrective_actions": "...",
            "recovery_estimate":  "..."
        }
    """
    try:
        model  = _get_model()
        prompt = _build_prompt(
            phase_group, sub_phase, district, province,
            alert_level, delay_risk, delay_days, similar_cases
        )

        response = model.generate_content(prompt)
        text     = response.text.strip()

        # ── Parse the 3 sections from Gemini's response ───────────────────────
        likely_causes      = _extract_section(text, "LIKELY CAUSES",      "CORRECTIVE ACTIONS")
        corrective_actions = _extract_section(text, "CORRECTIVE ACTIONS",  "RECOVERY ESTIMATE")
        recovery_estimate  = _extract_section(text, "RECOVERY ESTIMATE",   None)

        return {
            "likely_causes":      likely_causes.strip(),
            "corrective_actions": corrective_actions.strip(),
            "recovery_estimate":  recovery_estimate.strip(),
        }

    except Exception as e:
        return {
            "likely_causes":      None,
            "corrective_actions": None,
            "recovery_estimate":  None,
            "error":              str(e),
        }


def _extract_section(text: str, start_heading: str, end_heading: str | None) -> str:
    """Extract content between two headings in Gemini's response."""
    try:
        start_idx = text.upper().find(start_heading.upper())
        if start_idx == -1:
            return ""
        # skip past the heading line
        start_idx = text.find("\n", start_idx) + 1

        if end_heading:
            end_idx = text.upper().find(end_heading.upper(), start_idx)
            return text[start_idx:end_idx].strip() if end_idx != -1 else text[start_idx:].strip()
        else:
            return text[start_idx:].strip()
    except Exception:
        return ""
