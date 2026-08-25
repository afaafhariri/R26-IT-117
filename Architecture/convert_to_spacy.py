"""
convert_to_spacy.py — Converts reviewed NER annotations to spaCy training format.

Reads all JSON files from data/ocr_results/ and builds a spaCy .spacy binary
training file from plans that have been corrected (ner_corrected is not None)
OR have good auto values (district and area both detected and area < 5000).

Run from Architecture/:
    python convert_to_spacy.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ocr_results"
TRAIN_DIR  = Path(__file__).resolve().parent.parent / "data" / "spacy_training"
TRAIN_DIR.mkdir(parents=True, exist_ok=True)


def _best_ner(record: dict) -> dict:
    return record["ner_corrected"] if record.get("ner_corrected") else record["ner_auto"]


def _is_usable(record: dict) -> bool:
    if record["token_count"] == 0:
        return False
    ner = _best_ner(record)
    has_district = ner.get("district") is not None
    has_area     = ner.get("area_sqm") is not None and 0 < ner["area_sqm"] < 5000
    return has_district or has_area


def _find_span_safe(text: str, value: str, min_len: int = 3) -> tuple[int, int] | None:
    """Finds a character span — only accepts matches of min_len or more characters."""
    val = str(value).strip()
    if len(val) < min_len:
        return None
    m = re.search(re.escape(val), text, re.IGNORECASE)
    if not m:
        return None
    start, end = m.start(), m.end()
    # Reject if matched text has leading/trailing whitespace
    if text[start:end] != text[start:end].strip():
        return None
    return start, end


def _build_entities(text: str, ner: dict) -> list[tuple[int, int, str]]:
    """Builds (start, end, label) entity spans. Only safe, non-overlapping spans."""
    candidates = []

    # DISTRICT — look for "DISTRICT NAME DISTRICT" pattern first, else just name
    district = ner.get("district")
    if district:
        m = re.search(
            rf"\b{re.escape(district)}\b\s*DISTRICT", text, re.IGNORECASE
        )
        if not m:
            m = re.search(rf"\b{re.escape(district)}\b", text, re.IGNORECASE)
        if m:
            candidates.append((m.start(), m.end(), "DISTRICT"))

    # PLAN_NO — look for plan number after "PLAN No" keyword
    plan_no = ner.get("plan_number")
    if plan_no and len(str(plan_no)) >= 3:
        m = re.search(
            rf"PLAN\s*No[.:]\s*({re.escape(str(plan_no))})", text, re.IGNORECASE
        )
        if m:
            candidates.append((m.start(1), m.end(1), "PLAN_NO"))

    # AREA — look for number with unit near extent/area/containing keyword
    area_sqm = ner.get("area_sqm")
    if area_sqm and 0 < area_sqm < 5000:
        m = re.search(
            r"(?:extent|area|containing)[^0-9]{0,40}"
            r"(\d+(?:\.\d+)?)\s*(Square\s+metre|Hectare|Ha\b|sq\.?\s*m(?:etre)?s?)"
            r"|=\s*(\d+(?:\.\d+)?)\s*(Square\s+metre|sq\.?\s*m(?:etre)?s?)",
            text, re.IGNORECASE,
        )
        if m:
            candidates.append((m.start(), m.end(), "AREA"))

    # SURVEYOR — only if long enough and clearly after a keyword
    surveyor = ner.get("surveyor")
    if surveyor and len(str(surveyor)) >= 5:
        span = _find_span_safe(text, surveyor, min_len=5)
        if span:
            candidates.append((*span, "SURVEYOR"))

    # LICENCE — only digits/alphanumeric, min 5 chars
    licence = ner.get("licence_number")
    if licence and len(str(licence)) >= 5:
        m = re.search(
            rf"Lic(?:ence|ense)?\s*No[.]?\s*({re.escape(str(licence))})",
            text, re.IGNORECASE,
        )
        if m:
            candidates.append((m.start(1), m.end(1), "LICENCE"))

    # Remove overlapping spans — keep longest
    candidates.sort(key=lambda x: x[1] - x[0], reverse=True)
    final = []
    for start, end, label in candidates:
        overlap = any(s < end and start < e for s, e, _ in final)
        if not overlap:
            # Final whitespace check
            if text[start:end].strip() == text[start:end]:
                final.append((start, end, label))

    return final


def main() -> None:
    try:
        import spacy
        from spacy.tokens import DocBin
        from spacy.util import filter_spans
    except ImportError:
        print("spaCy not found. Run: pip install spacy")
        sys.exit(1)

    records = []
    for path in sorted(OUTPUT_DIR.glob("*.json")):
        if path.name == "_summary.json":
            continue
        records.append(json.loads(path.read_text(encoding="utf-8")))

    usable = [r for r in records if _is_usable(r)]
    print(f"Total records : {len(records)}")
    print(f"Usable records: {len(usable)}")

    nlp     = spacy.blank("en")
    doc_bin = DocBin()
    skipped = 0

    for record in usable:
        text = record["raw_text"]
        if not text.strip():
            skipped += 1
            continue

        ner      = _best_ner(record)
        entities = _build_entities(text, ner)

        doc  = nlp.make_doc(text)
        ents = []
        for start, end, label in entities:
            span = doc.char_span(start, end, label=label, alignment_mode="contract")
            if span is not None and len(span.text.strip()) > 0:
                ents.append(span)

        # filter_spans removes any remaining overlaps (keeps longest)
        doc.ents = filter_spans(ents)
        doc_bin.add(doc)

    out_path = TRAIN_DIR / "train.spacy"
    doc_bin.to_disk(str(out_path))

    print(f"Skipped       : {skipped}")
    print(f"Training docs : {len(usable) - skipped}")
    print(f"Saved to      : {out_path}")
    print(f"\nNext step: run  python train_ner.py")


if __name__ == "__main__":
    main()
