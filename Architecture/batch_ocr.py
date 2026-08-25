"""
batch_ocr.py — Batch OCR processor for cadastral survey plans.

Reads all PDFs from data/cadastral_plans/, extracts text using EasyOCR,
runs NER auto-annotation, and saves results to data/ocr_results/.

Run from Architecture/:
    python batch_ocr.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

# Add Architecture/ to sys.path so stage imports resolve correctly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

INPUT_DIR  = Path(__file__).resolve().parent / "data" / "cadastral_plans"
OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "ocr_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _pdf_to_image(pdf_path: Path, out_dir: Path) -> Path:
    import fitz
    doc  = fitz.open(str(pdf_path))
    page = doc[0]
    pix  = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img_path = out_dir / (pdf_path.stem + ".png")
    pix.save(str(img_path))
    doc.close()
    return img_path


def main() -> None:
    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {INPUT_DIR}")
        return

    print(f"Found {len(pdfs)} PDF files.")
    print("Loading EasyOCR and NER parser (first time may take ~30 seconds)...\n")

    from stages.stage1_extraction.ocr_engine import OCREngine
    from stages.stage1_extraction.ner_parser import NERParser

    ocr = OCREngine()
    ner = NERParser()

    tmp_dir = Path(tempfile.gettempdir()) / "r26_batch_ocr"
    tmp_dir.mkdir(exist_ok=True)

    errors = []

    for i, pdf_path in enumerate(pdfs, 1):
        result_path = OUTPUT_DIR / (pdf_path.stem + ".json")

        if result_path.exists():
            print(f"[{i:>3}/{len(pdfs)}] SKIP (already done): {pdf_path.name}")
            continue

        print(f"[{i:>3}/{len(pdfs)}] {pdf_path.name} ...", end=" ", flush=True)

        try:
            img_path  = _pdf_to_image(pdf_path, tmp_dir)
            ocr_out   = ocr.extract_text(img_path)
            ner_out   = ner.parse(ocr_out)

            record = {
                "filename":    pdf_path.name,
                "raw_text":    ocr_out["raw_text"],
                "token_count": len(ocr_out["tokens"]),
                "ner_auto":    ner_out,
                "ner_corrected": None,   # filled during review step
            }
            result_path.write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            d = ner_out.get("district") or "?"
            a = ner_out.get("area_sqm") or "?"
            print(f"OK  ({len(ocr_out['tokens'])} tokens | district={d} | area={a})")

            img_path.unlink(missing_ok=True)

        except Exception as exc:
            print(f"ERROR: {exc}")
            errors.append({"filename": pdf_path.name, "error": str(exc)})

    shutil.rmtree(tmp_dir, ignore_errors=True)

    processed = len(list(OUTPUT_DIR.glob("*.json")))
    print(f"\n{'='*60}")
    print(f"Done!  Processed: {processed}/{len(pdfs)}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e['filename']}: {e['error']}")
    print(f"Results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
