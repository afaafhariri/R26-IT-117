"""
train.py — Trains the Component 04 delay-prediction models.

Produces the three artefacts that pipeline/delay_model.py loads at runtime:

    models/xgboost_classifier.json   delay risk  (multi-class)
    models/xgboost_regressor.json    delay days  (regression)
    models/label_encoders.pkl        fitted LabelEncoders

Run from performance/:

    python train.py

Ported from research/notebooks/delay_model.ipynb. The plotting and manual
sample-prediction cells were exploratory and are not reproduced here; the
modelling steps are unchanged.
"""

import os
import pickle

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from skopt import BayesSearchCV
from skopt.space import Integer, Real
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_score,
    train_test_split,
)
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier, XGBRegressor

# Feature order is owned by the serving code — importing it here means a
# reordering there can never silently desync the trained model.
from pipeline.delay_model import FEATURES

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

TARGET_CLASS = "delay_risk"
TARGET_REG   = "delay_days"

# Columns that need label encoding. The remaining features are already numeric.
CATEGORICAL = [
    "phase_group",
    "sub_phase",
    "district",
    "province",
    "delay_category",
]

RANDOM_STATE = 42

# ── CSV resolution ────────────────────────────────────────────────────────────
# Mirrors rag/embedder.py::_resolve_csv_path. Duplicated rather than imported
# because embedder pulls in sentence-transformers (and torch) at import time,
# which training does not need.
_LOCAL_CSV    = os.path.join(BASE_DIR, "data", "delay_data.csv")
_RESEARCH_CSV = os.path.join(
    BASE_DIR, "..", "research", "datasets", "delay-cases", "delay_data.csv"
)


def resolve_csv_path() -> str:
    configured = os.getenv("DELAY_CASES_CSV_PATH")
    if configured:
        configured_abs = os.path.abspath(configured)
        if os.path.exists(configured_abs):
            return configured_abs
        raise FileNotFoundError(
            f"DELAY_CASES_CSV_PATH is set but file not found: {configured_abs}"
        )
    if os.path.exists(_LOCAL_CSV):
        return _LOCAL_CSV
    if os.path.exists(_RESEARCH_CSV):
        return _RESEARCH_CSV
    raise FileNotFoundError(
        f"CSV not found. Checked: {os.path.abspath(_LOCAL_CSV)} "
        f"and {os.path.abspath(_RESEARCH_CSV)}"
    )


# ── Steps ─────────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    path = resolve_csv_path()
    df = pd.read_csv(path)
    print(f"Loaded {path}")
    print(f"  shape: {df.shape}")
    df = df.dropna(subset=FEATURES + [TARGET_CLASS, TARGET_REG])
    print(f"  after dropna: {df.shape}")
    print(f"  risk distribution:\n{df[TARGET_CLASS].value_counts().to_string()}")
    return df


def encode(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Label-encode the categorical columns and the class target."""
    encoders = {}
    for col in CATEGORICAL + [TARGET_CLASS]:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        encoders[col] = le
        print(f"  {col}: {len(le.classes_)} classes")
    return df, encoders


def tune_classifier(X, y) -> dict:
    """Bayesian hyperparameter search, as in the original notebook."""
    search_space = {
        "n_estimators":     Integer(100, 500),
        "max_depth":        Integer(3, 10),
        "learning_rate":    Real(0.01, 0.3),
        "subsample":        Real(0.6, 1.0),
        "colsample_bytree": Real(0.6, 1.0),
        "min_child_weight": Integer(1, 10),
    }
    search = BayesSearchCV(
        XGBClassifier(eval_metric="mlogloss", random_state=RANDOM_STATE),
        search_spaces=search_space,
        n_iter=8,
        cv=5,
        scoring="f1_weighted",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=1,
    )
    search.fit(X, y)
    print(f"  best CV F1: {search.best_score_:.4f}")
    print(f"  best params: {dict(search.best_params_)}")
    return dict(search.best_params_)


def main() -> None:
    print("\n[1/7] Loading data")
    df = load_data()

    print("\n[2/7] Encoding categoricals")
    df, encoders = encode(df)

    print("\n[3/7] Train/test split")
    X, y_class, y_reg = df[FEATURES], df[TARGET_CLASS], df[TARGET_REG]
    X_tr, X_te, yc_tr, yc_te, yr_tr, yr_te = train_test_split(
        X, y_class, y_reg,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y_class,
    )
    print(f"  train {X_tr.shape}  test {X_te.shape}")

    print("\n[4/7] SMOTE oversampling")
    X_sm, y_sm = SMOTE(random_state=RANDOM_STATE).fit_resample(X_tr, yc_tr)
    print(f"  {X_tr.shape} -> {X_sm.shape}")

    print("\n[5/7] Tuning and training the classifier")
    best_params = tune_classifier(X_sm, y_sm)
    classifier = XGBClassifier(
        **best_params, eval_metric="mlogloss", random_state=RANDOM_STATE
    )
    classifier.fit(X_sm, y_sm)

    y_pred = classifier.predict(X_te)
    print(f"  accuracy: {accuracy_score(yc_te, y_pred):.4f}")
    print(f"  F1 (weighted): {f1_score(yc_te, y_pred, average='weighted'):.4f}")
    print(classification_report(
        yc_te, y_pred, target_names=encoders[TARGET_CLASS].classes_
    ))

    cv = cross_val_score(
        classifier, X_sm, y_sm,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE),
        scoring="f1_weighted",
    )
    print(f"  5-fold CV F1: {cv.mean():.4f} (+/- {cv.std():.4f})")

    print("\n[6/7] Training the regressor")
    regressor = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RANDOM_STATE,
    )
    regressor.fit(X_tr, yr_tr)
    yr_pred = regressor.predict(X_te)
    print(f"  MAE:  {mean_absolute_error(yr_te, yr_pred):.2f} days")
    print(f"  RMSE: {np.sqrt(mean_squared_error(yr_te, yr_pred)):.2f} days")

    print("\n[7/7] Saving artefacts")
    os.makedirs(MODELS_DIR, exist_ok=True)
    classifier.save_model(os.path.join(MODELS_DIR, "xgboost_classifier.json"))
    regressor.save_model(os.path.join(MODELS_DIR, "xgboost_regressor.json"))
    with open(os.path.join(MODELS_DIR, "label_encoders.pkl"), "wb") as f:
        pickle.dump(encoders, f)
    for name in ("xgboost_classifier.json", "xgboost_regressor.json",
                 "label_encoders.pkl"):
        print(f"  wrote models/{name}")

    print("\nDone. Build the RAG index next:")
    print("  python -c \"from rag.embedder import generate_rag_documents;"
          " generate_rag_documents()\"")
    print("  python -c \"from rag.faiss_index import build_index; build_index()\"")


if __name__ == "__main__":
    main()
