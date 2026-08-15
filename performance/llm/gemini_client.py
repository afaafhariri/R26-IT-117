import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

_model = None


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        _model = genai.GenerativeModel("gemini-2.0-flash")
    return _model


def _build_prompt(
    phase_group: str,
    sub_phase: str,
    district: str,
    province: str,
    spi_alert: str,
    delay_risk: str,
    delay_days: int,
    similar_cases: list[dict],
) -> str:
    case_lines = []
    for c in similar_cases:
        case_lines.append(
            f"- Cause: {c.get('cause_of_delay', '')}\n"
            f"  Action: {c.get('corrective_action_taken', '')}\n"
            f"  Status: {c.get('construction_status', '')}"
        )

    cases_text = "\n".join(case_lines) if case_lines else "- No similar cases available"
    return f"""You are an expert advisor for Sri Lankan coastal residential construction projects.

Current project context:
- Location: {district}, {province}
- Phase: {phase_group} / {sub_phase}
- SPI alert level: {spi_alert}
- ML delay risk level: {delay_risk}
- Estimated delay days: {delay_days}

Top similar historical cases:
{cases_text}

Respond in exactly this format:
EXPLANATION:
<plain language explanation in 2-4 sentences>

CORRECTIVE ACTIONS:
- <specific action 1>
- <specific action 2>
- <specific action 3>
- <optional action 4>
- <optional action 5>
"""


def _parse_actions(text: str) -> list[str]:
    actions = []
    in_actions = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("CORRECTIVE ACTIONS"):
            in_actions = True
            continue
        if upper.startswith("EXPLANATION"):
            in_actions = False
            continue
        if in_actions and line.startswith("-"):
            actions.append(line[1:].strip())
    return actions[:5]


def _parse_explanation(text: str) -> str:
    lines = []
    in_explanation = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("EXPLANATION"):
            in_explanation = True
            continue
        if upper.startswith("CORRECTIVE ACTIONS"):
            break
        if in_explanation:
            lines.append(line)
    return " ".join(lines).strip()


def generate_recommendations(
    phase_group: str,
    sub_phase: str,
    district: str,
    province: str,
    spi_alert: str,
    delay_risk: str,
    delay_days: int,
    similar_cases: list[dict],
) -> dict:
    try:
        model = _get_model()
        prompt = _build_prompt(
            phase_group,
            sub_phase,
            district,
            province,
            spi_alert,
            delay_risk,
            delay_days,
            similar_cases,
        )
        response = model.generate_content(prompt)
        text = response.text.strip()

        explanation = _parse_explanation(text)
        actions = _parse_actions(text)
        if not explanation:
            explanation = "Delay risk has increased based on SPI trend and contextual factors."
        if not actions:
            actions = [
                "Prioritize critical path tasks and update the weekly execution sequence.",
                "Secure near-term labour and material commitments with daily follow-up.",
                "Escalate blockers immediately to avoid compounding schedule slippage.",
            ]

        return {
            "explanation": explanation,
            "corrective_actions": actions,
            "raw_text": text,
        }
    except Exception as exc:
        return {
            "explanation": "Unable to generate detailed recommendation due to LLM error.",
            "corrective_actions": [
                "Review site bottlenecks and refresh the 2-week lookahead plan.",
                "Stabilize labour/material availability for critical path tasks.",
                "Track daily recovery against the updated micro-schedule.",
            ],
            "error": str(exc),
        }
