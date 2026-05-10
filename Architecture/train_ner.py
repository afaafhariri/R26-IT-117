"""
train_ner.py — Fine-tunes spaCy NER on annotated Sri Lankan cadastral plans.

Uses the .spacy training file produced by convert_to_spacy.py.
Fine-tunes en_core_web_sm and saves the model to models/ner_cadastral/.

Run from Architecture/:
    python train_ner.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TRAIN_FILE  = Path(__file__).resolve().parent.parent / "data" / "spacy_training" / "train.spacy"
MODEL_DIR   = Path(__file__).resolve().parent / "models" / "ner_cadastral"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

N_ITER      = 60
DROP_RATE   = 0.2
EVAL_SPLIT  = 0.15   # 15% held out for evaluation


def main() -> None:
    try:
        import spacy
        from spacy.tokens import DocBin
        from spacy.training import Example
    except ImportError:
        print("spaCy not found. Run: pip install spacy")
        sys.exit(1)

    if not TRAIN_FILE.exists():
        print(f"Training file not found: {TRAIN_FILE}")
        print("Run convert_to_spacy.py first.")
        sys.exit(1)

    # Load training docs
    nlp_blank = spacy.blank("en")
    doc_bin   = DocBin().from_disk(str(TRAIN_FILE))
    all_docs  = list(doc_bin.get_docs(nlp_blank.vocab))

    if len(all_docs) < 5:
        print(f"Only {len(all_docs)} training docs — need at least 5. Review more plans first.")
        sys.exit(1)

    random.shuffle(all_docs)
    split      = max(1, int(len(all_docs) * EVAL_SPLIT))
    eval_docs  = all_docs[:split]
    train_docs = all_docs[split:]

    print(f"Training docs : {len(train_docs)}")
    print(f"Eval docs     : {len(eval_docs)}")
    print(f"Iterations    : {N_ITER}")
    print(f"Loading base model en_core_web_sm ...\n")

    # Load base model and get/create NER pipe
    nlp = spacy.load("en_core_web_sm")
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    # Add custom cadastral labels
    for label in ("PLAN_NO", "DISTRICT", "AREA", "LOT_NO", "SURVEYOR", "LICENCE"):
        ner.add_label(label)

    # Build Example objects
    def make_examples(docs, nlp_model):
        examples = []
        for doc in docs:
            pred = nlp_model.make_doc(doc.text)
            examples.append(Example(pred, doc))
        return examples

    # Disable pipes we are not training
    other_pipes = [p for p in nlp.pipe_names if p != "ner"]

    print("Starting training...\n")
    best_f = 0.0

    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.resume_training()

        for i in range(1, N_ITER + 1):
            random.shuffle(train_docs)
            examples = make_examples(train_docs, nlp)
            losses   = {}
            nlp.update(examples, drop=DROP_RATE, sgd=optimizer, losses=losses)

            # Evaluate every 5 iterations
            if i % 5 == 0 or i == N_ITER:
                eval_examples = make_examples(eval_docs, nlp)
                scores = nlp.evaluate(eval_examples)
                f      = scores.get("ents_f", 0.0)
                p      = scores.get("ents_p", 0.0)
                r      = scores.get("ents_r", 0.0)
                print(
                    f"  Iter {i:>3}/{N_ITER}  loss={losses.get('ner', 0):.2f}  "
                    f"P={p:.3f}  R={r:.3f}  F={f:.3f}"
                )
                if f > best_f:
                    best_f = f
                    nlp.to_disk(str(MODEL_DIR))
                    print(f"           ↑ Best model saved (F={f:.3f})")
            else:
                print(f"  Iter {i:>3}/{N_ITER}  loss={losses.get('ner', 0):.2f}")

    print(f"\n{'='*60}")
    print(f"Training complete. Best F-score: {best_f:.3f}")
    print(f"Model saved to: {MODEL_DIR}")
    print(f"\nNext step: run  python update_ner_parser.py")
    print(f"Or manually update ner_parser.py to load: {MODEL_DIR}")


if __name__ == "__main__":
    main()
