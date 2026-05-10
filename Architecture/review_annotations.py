"""
review_annotations.py — Interactive CLI review of auto-extracted NER annotations.

Only shows plans where something is wrong:
  - district not detected
  - area not detected
  - area clearly wrong (> 5000 sqm or == 0)
  - (skips plans with 0 tokens — unusable for training)

Run from Architecture/:
    python review_annotations.py
"""

import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ocr_results"

_DISTRICTS = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo",
    "Galle", "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy",
    "Kegalle", "Kilinochchi", "Kurunegala", "Mannar", "Matale",
    "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya", "Polonnaruwa",
    "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya",
]

_COASTAL = {
    "Ampara", "Trincomalee", "Batticaloa", "Jaffna", "Kilinochchi",
    "Mannar", "Galle", "Matara", "Hambantota", "Puttalam",
    "Colombo", "Gampaha", "Kalutara",
}


def _is_wrong(record: dict) -> bool:
    if record["token_count"] == 0:
        return False   # unusable — skip silently
    ner = record["ner_auto"]
    if ner["district"] is None:
        return True
    if ner["area_sqm"] is None:
        return True
    if ner["area_sqm"] == 0.0:
        return True
    if ner["area_sqm"] > 5000:
        return True
    return False


def _load_records() -> list[dict]:
    records = []
    for path in sorted(OUTPUT_DIR.glob("*.json")):
        if path.name == "_summary.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = str(path)
        records.append(data)
    return records


def _save(record: dict) -> None:
    path = Path(record.pop("_path"))
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def _ask(prompt: str, default: str = "") -> str:
    val = input(prompt).strip()
    return val if val else default


def main() -> None:
    records = _load_records()
    wrong   = [r for r in records if _is_wrong(r)]

    if not wrong:
        print("Nothing to review — all plans look correct!")
        return

    print(f"\nFound {len(wrong)} plans needing review (out of {len(records)} total).")
    print("Press Enter to skip a field (keep existing value).")
    print("Type 'skip' to skip the whole plan.")
    print("Type 'quit' to save and exit.\n")
    print("=" * 60)

    reviewed = 0
    for i, record in enumerate(wrong, 1):
        ner  = record["ner_auto"]
        text = record["raw_text"][:600].replace("\n", " ")

        print(f"\n[{i}/{len(wrong)}]  {record['filename']}")
        print(f"  Tokens : {record['token_count']}")
        print(f"  Text   : {text}...")
        print(f"  Auto   : district={ner['district']}  area_sqm={ner['area_sqm']}  "
              f"scale={ner.get('scale')}  lot={ner.get('lot_number')}")
        print()

        action = _ask("  Action [Enter=review / skip / quit]: ").lower()
        if action == "quit":
            print("Saving and exiting...")
            break
        if action == "skip":
            continue

        corrected = dict(ner)   # start from auto values

        # District
        current_d = ner["district"] or "?"
        d = _ask(f"  District [{current_d}]: ")
        if d:
            # match case-insensitively
            match = next((x for x in _DISTRICTS if x.lower() == d.lower()), d.title())
            corrected["district"]   = match
            corrected["is_coastal"] = match in _COASTAL

        # Area
        current_a = str(ner["area_sqm"]) if ner["area_sqm"] is not None else "?"
        a = _ask(f"  Area sqm [{current_a}] (enter raw number, e.g. 127.5): ")
        if a:
            try:
                corrected["area_sqm"] = float(a)
            except ValueError:
                print("  Invalid number — keeping original.")

        # Plan number
        current_p = ner.get("plan_number") or "?"
        p = _ask(f"  Plan number [{current_p}]: ")
        if p:
            corrected["plan_number"] = p

        # Scale
        current_s = str(ner.get("scale")) if ner.get("scale") else "?"
        s = _ask(f"  Scale [{current_s}] (e.g. 500): ")
        if s:
            try:
                corrected["scale"] = int(s)
            except ValueError:
                print("  Invalid number — keeping original.")

        record["ner_corrected"] = corrected
        record.pop("_path", None)
        path = Path(OUTPUT_DIR / record["filename"].replace(".pdf", ".json"))
        record["_path"] = str(path)
        _save(record)
        reviewed += 1
        print(f"  Saved ✓")

    print(f"\n{'='*60}")
    print(f"Review complete. {reviewed} plans corrected.")
    print(f"Next step: run  python convert_to_spacy.py")


if __name__ == "__main__":
    main()
