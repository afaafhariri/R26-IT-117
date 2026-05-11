"""
LSTM Training Script — Total Project Duration Prediction
Project : AI-Driven Construction Planner — Component 04: Timeline Prediction
Student : Hanfi A.M.M | IT22074454 | SLIIT
"""

import os
import sys
import pickle
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Suppress TensorFlow info / warning noise ──────────────────────────────────
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import (
    EarlyStopping, ReduceLROnPlateau, Callback,
)
from tensorflow.keras.optimizers import Adam

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_PATH     = os.path.join(BASE_DIR, 'data', 'construction_projects.csv')
ENCODERS_PATH = os.path.join(BASE_DIR, 'models', 'encoders.pkl')
MODEL_PATH    = os.path.join(BASE_DIR, 'models', 'lstm_total_model.h5')
SCALER_PATH   = os.path.join(BASE_DIR, 'models', 'lstm_scaler.pkl')
OUTPUT_DIR    = os.path.join(BASE_DIR, 'output')
PLOT_PATH     = os.path.join(OUTPUT_DIR, 'lstm_training_plot.png')

os.makedirs(os.path.join(BASE_DIR, 'models'), exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Column definitions ────────────────────────────────────────────────────────
PHASE_COLS = [
    'preconstruction_weeks', 'siteprep_weeks', 'foundation_weeks',
    'structure_weeks',       'envelope_weeks', 'mep_weeks',
    'finishes_weeks',        'external_weeks',
]
N_TIMESTEPS = len(PHASE_COLS)   # 8
TARGET_COL  = 'total_weeks'

# Raw input features expected in the CSV (after encoding)
RAW_FEATURES = [
    'built_up_area_sqft', 'num_floors', 'num_rooms', 'num_bathrooms',
    'total_cost_lkr',     'labor_hours_total', 'material_cost_lkr',
    'contractor_experience_years', 'start_month', 'num_workers', 'had_delays',
]

# Categorical columns: (csv_name, encoded_col_name, fallback_index)
CAT_COLS = [
    ('district',          'district_enc', 0),
    ('construction_type', 'type_enc',     0),
    ('soil_type',         'soil_enc',     0),
]

# ── Hyper-parameters ──────────────────────────────────────────────────────────
LSTM_UNITS_1  = 128
LSTM_UNITS_2  = 64
DENSE_UNITS   = 32
DROPOUT_LSTM  = 0.2
DROPOUT_DENSE = 0.1
LEARNING_RATE = 0.001
EPOCHS        = 100
BATCH_SIZE    = 32
VAL_SPLIT     = 0.2
TEST_SIZE     = 0.2
ES_PATIENCE   = 15
LR_PATIENCE   = 8
LR_FACTOR     = 0.5
SEED          = 42

tf.random.set_seed(SEED)
np.random.seed(SEED)


# ─────────────────────────────────────────────────────────────────────────────
#  Custom callback: print every 10 epochs
# ─────────────────────────────────────────────────────────────────────────────
class PrintEvery10(Callback):
    def __init__(self, total_epochs):
        super().__init__()
        self.total_epochs = total_epochs

    def on_epoch_end(self, epoch, logs=None):
        if (epoch + 1) % 10 == 0 or epoch == 0:
            lr = float(self.model.optimizer.learning_rate)
            print(
                f'  Epoch {epoch + 1:3d}/{self.total_epochs}'
                f'  loss: {logs["loss"]:.4f}'
                f'  val_loss: {logs["val_loss"]:.4f}'
                f'  lr: {lr:.6f}'
            )


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: safe division
# ─────────────────────────────────────────────────────────────────────────────
def safe_div(a: pd.Series, b: pd.Series, fallback: float = 0.0) -> pd.Series:
    return np.where(b > 0, a / b, fallback).astype(float)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — Load dataset
# ─────────────────────────────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    print(f'\n[1/7] Loading dataset ...')
    if not os.path.exists(DATA_PATH):
        print(f'  ERROR: {DATA_PATH} not found.')
        print('  Run:  python data/generate_dataset.py  then  python train.py  first.')
        sys.exit(1)

    df = pd.read_csv(DATA_PATH)
    print(f'  Loaded {len(df)} rows x {df.shape[1]} columns')

    # Create total_weeks if absent
    if TARGET_COL not in df.columns:
        missing = [c for c in PHASE_COLS if c not in df.columns]
        if missing:
            print(f'  ERROR: Missing phase columns: {missing}')
            sys.exit(1)
        df[TARGET_COL] = df[PHASE_COLS].sum(axis=1)
        print(f'  Created {TARGET_COL} = sum of 8 phase columns')

    print(f'  {TARGET_COL} — mean: {df[TARGET_COL].mean():.1f}w  '
          f'min: {df[TARGET_COL].min():.1f}w  max: {df[TARGET_COL].max():.1f}w')
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 — Encode categoricals
# ─────────────────────────────────────────────────────────────────────────────
def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    print('\n[2/7] Encoding categorical features ...')
    encoders = {}

    if os.path.exists(ENCODERS_PATH):
        with open(ENCODERS_PATH, 'rb') as fh:
            encoders = pickle.load(fh)
        print(f'  Loaded encoders.pkl  (keys: {list(encoders.keys())})')
    else:
        print(f'  encoders.pkl not found — using pandas factorize as fallback')

    for csv_col, enc_col, _ in CAT_COLS:
        # Already present with expected name → nothing to do
        if enc_col in df.columns:
            continue

        # Try alternate names that existing train.py might have used
        alt_names = [f'{csv_col}_enc', f'{csv_col}Enc', enc_col]
        found_alt = next((a for a in alt_names if a in df.columns), None)
        if found_alt:
            df[enc_col] = df[found_alt].values
            continue

        # Encode from string column
        if csv_col in df.columns:
            if csv_col in encoders:
                le = encoders[csv_col]
                # Handle unseen labels gracefully
                known = set(le.classes_)
                df[csv_col] = df[csv_col].astype(str).apply(
                    lambda x: x if x in known else le.classes_[0]
                )
                df[enc_col] = le.transform(df[csv_col])
            else:
                df[enc_col] = pd.factorize(df[csv_col])[0]
            print(f'  Encoded  {csv_col} -> {enc_col}')
        else:
            df[enc_col] = 0
            print(f'  Column {csv_col} not found — using 0 for {enc_col}')

    return df


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 — Feature engineering
# ─────────────────────────────────────────────────────────────────────────────
def engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    print('\n[3/7] Engineering features ...')

    area   = df['built_up_area_sqft']
    floors = df['num_floors'].clip(1)
    rooms  = df['num_rooms']
    baths  = df['num_bathrooms']
    cost   = df['total_cost_lkr'].clip(1)
    mat    = df['material_cost_lkr']
    labor  = df['labor_hours_total']
    wrk    = df['num_workers']
    exp    = df['contractor_experience_years']
    month  = df['start_month']

    df['area_per_floor']    = safe_div(area,  floors)
    df['cost_per_sqft']     = safe_div(cost,  area)
    df['labor_per_sqft']    = safe_div(labor, area)
    df['rooms_per_floor']   = safe_div(rooms, floors)
    df['bath_per_floor']    = safe_div(baths, floors)
    df['complexity_score']  = (
        0.4 * (area  / max(area.max(), 1))  +
        0.4 * (floors / max(floors.max(), 1)) +
        0.2 * (rooms  / max(rooms.max(), 1))
    )
    df['resource_density']  = safe_div(wrk, area / 1000.0)
    df['experience_factor'] = np.log1p(exp)
    df['is_monsoon']        = month.isin([5, 6, 7, 8, 9, 10]).astype(int)
    df['cost_ratio']        = safe_div(mat,  cost)
    df['worker_per_floor']  = safe_div(wrk,  floors)

    engineered = [
        'area_per_floor', 'cost_per_sqft', 'labor_per_sqft',
        'rooms_per_floor', 'bath_per_floor', 'complexity_score',
        'resource_density', 'experience_factor', 'is_monsoon',
        'cost_ratio', 'worker_per_floor',
    ]
    enc_cols = [enc for _, enc, _ in CAT_COLS]

    # Build the final global feature list (only columns that exist)
    global_features = [
        c for c in RAW_FEATURES + enc_cols + engineered
        if c in df.columns
    ]

    print(f'  Global features: {len(global_features)}')
    print(f'  Engineered:      {len(engineered)} new columns')
    return df, global_features


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 — Build LSTM sequences
# ─────────────────────────────────────────────────────────────────────────────
def build_sequences(
    df: pd.DataFrame, global_features: list[str]
) -> tuple[np.ndarray, np.ndarray, dict]:
    print('\n[4/7] Building LSTM sequences ...')

    N  = len(df)
    G  = len(global_features)
    nf = 1 + G  # phase duration + global features at each timestep

    # Scale phase columns (one scaler for all 8 phases)
    phase_scaler  = StandardScaler()
    global_scaler = StandardScaler()
    target_scaler = StandardScaler()

    phase_vals  = phase_scaler.fit_transform(df[PHASE_COLS].values)       # (N, 8)
    global_vals = global_scaler.fit_transform(df[global_features].values) # (N, G)
    y_scaled    = target_scaler.fit_transform(
        df[[TARGET_COL]].values
    ).ravel().astype(np.float32)                                           # (N,)

    # Shape: (N, 8 timesteps, 1+G features)
    # Timestep t = [phase_t_normalized, global_feature_0, ..., global_feature_G]
    X = np.zeros((N, N_TIMESTEPS, nf), dtype=np.float32)
    for t in range(N_TIMESTEPS):
        X[:, t, 0]  = phase_vals[:, t]
        X[:, t, 1:] = global_vals

    print(f'  X shape : {X.shape}  (samples, timesteps, features)')
    print(f'  y shape : {y_scaled.shape}  (scaled {TARGET_COL})')

    scaler_bundle = {
        'phase_scaler':    phase_scaler,
        'global_scaler':   global_scaler,
        'target_scaler':   target_scaler,
        'global_features': global_features,
        'phase_cols':      PHASE_COLS,
        'n_timesteps':     N_TIMESTEPS,
        'n_features':      nf,
    }
    return X, y_scaled, scaler_bundle


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 — Build LSTM model
# ─────────────────────────────────────────────────────────────────────────────
def build_model(n_timesteps: int, n_features: int) -> Sequential:
    print('\n[5/7] Building LSTM architecture ...')

    model = Sequential(
        [
            LSTM(
                LSTM_UNITS_1,
                input_shape=(n_timesteps, n_features),
                return_sequences=True,
                dropout=DROPOUT_LSTM,
                recurrent_dropout=0.0,  # 0 keeps CuDNN compatibility
                name='lstm_1',
            ),
            LSTM(
                LSTM_UNITS_2,
                return_sequences=False,
                dropout=DROPOUT_LSTM,
                recurrent_dropout=0.0,
                name='lstm_2',
            ),
            Dense(DENSE_UNITS, activation='relu', name='dense_1'),
            Dropout(DROPOUT_DENSE, name='dropout_1'),
            Dense(1, name='output'),
        ],
        name='lstm_total_duration',
    )

    model.compile(
        optimizer=Adam(learning_rate=LEARNING_RATE),
        loss='mean_squared_error',
        metrics=['mae'],
    )

    print()
    model.summary()
    total_params = model.count_params()
    print(f'\n  Total trainable parameters: {total_params:,}')
    print(f'  Input shape : ({n_timesteps}, {n_features})')
    print(f'  LSTM-1      : {LSTM_UNITS_1} units  return_sequences=True  dropout={DROPOUT_LSTM}')
    print(f'  LSTM-2      : {LSTM_UNITS_2} units  return_sequences=False dropout={DROPOUT_LSTM}')
    print(f'  Dense       : {DENSE_UNITS} units  ReLU')
    print(f'  Dropout     : {DROPOUT_DENSE}')
    print(f'  Output      : 1 unit  (total_weeks)')
    return model


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 6 — Train
# ─────────────────────────────────────────────────────────────────────────────
def train_model(model, X_train, y_train):
    print('\n[6/7] Training LSTM ...')
    print(f'  Epochs        : {EPOCHS}')
    print(f'  Batch size    : {BATCH_SIZE}')
    print(f'  Val split     : {VAL_SPLIT}')
    print(f'  Early stop    : patience={ES_PATIENCE}')
    print(f'  ReduceLR      : patience={LR_PATIENCE}  factor={LR_FACTOR}')
    print(f'  GPU available : {len(tf.config.list_physical_devices("GPU")) > 0}')
    print()

    callbacks = [
        EarlyStopping(
            monitor='val_loss',
            patience=ES_PATIENCE,
            restore_best_weights=True,
            verbose=0,
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=LR_FACTOR,
            patience=LR_PATIENCE,
            min_lr=1e-6,
            verbose=0,
        ),
        PrintEvery10(total_epochs=EPOCHS),
    ]

    history = model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=VAL_SPLIT,
        callbacks=callbacks,
        verbose=0,
        shuffle=True,
    )

    actual_epochs = len(history.history['loss'])
    print(f'\n  Done. Ran {actual_epochs} epoch(s) '
          f'(early-stop patience={ES_PATIENCE}).')
    return history


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 7 — Evaluate + save
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_and_save(model, history, X_test, y_test, scaler_bundle):
    print('\n[7/7] Evaluating on test set ...')
    target_scaler = scaler_bundle['target_scaler']

    y_pred_scaled = model.predict(X_test, verbose=0).ravel()
    y_pred        = target_scaler.inverse_transform(
        y_pred_scaled.reshape(-1, 1)
    ).ravel()
    y_true        = target_scaler.inverse_transform(
        y_test.reshape(-1, 1)
    ).ravel()

    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    mape = float(
        np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1e-8))) * 100
    )
    r2   = float(r2_score(y_true, y_pred))

    # ── Save model ────────────────────────────────────────────────────────────
    model.save(MODEL_PATH)
    print(f'\n  Model saved  : {MODEL_PATH}')

    # ── Save scaler bundle ────────────────────────────────────────────────────
    with open(SCALER_PATH, 'wb') as fh:
        pickle.dump(scaler_bundle, fh)
    print(f'  Scaler saved : {SCALER_PATH}')

    # ── Training history plot ─────────────────────────────────────────────────
    epochs_axis = range(1, len(history.history['loss']) + 1)
    fig, ax     = plt.subplots(figsize=(10, 5))

    ax.plot(epochs_axis, history.history['loss'],
            'b-', lw=2, label='Training Loss')
    ax.plot(epochs_axis, history.history['val_loss'],
            'r--', lw=2, label='Validation Loss')

    best_epoch = int(np.argmin(history.history['val_loss'])) + 1
    best_val   = min(history.history['val_loss'])
    ax.axvline(best_epoch, color='green', linestyle=':', lw=1.5,
               label=f'Best epoch {best_epoch} (val_loss={best_val:.4f})')

    ax.set_xlabel('Epoch', fontsize=12)
    ax.set_ylabel('Loss (MSE)', fontsize=12)
    ax.set_title(
        'LSTM Training History — Total Duration Prediction\n'
        'AI-Driven Construction Planner  |  Hanfi A.M.M  |  IT22074454  |  SLIIT',
        fontsize=11, fontweight='bold',
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  Plot saved   : {PLOT_PATH}')

    # ── Final summary ─────────────────────────────────────────────────────────
    mape_ok = 'OK' if mape < 15.0 else f'FAIL ({mape:.1f}%)'
    rmse_ok = 'OK' if rmse < 2.0  else f'FAIL ({rmse:.2f}w)'
    r2_ok   = 'OK' if r2   > 0.85 else f'FAIL ({r2:.3f})'

    print()
    print('=' * 55)
    print('  LSTM Model Results:')
    print(f'  RMSE: {rmse:.2f} weeks')
    print(f'  MAE:  {mae:.2f} weeks')
    print(f'  MAPE: {mape:.1f}%')
    print(f'  R2:   {r2:.3f}')
    print()
    print(f'  Target Check:  MAPE < 15% [{mape_ok}]'
          f'  RMSE < 2w [{rmse_ok}]  R2 > 0.85 [{r2_ok}]')
    print('=' * 55)
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print('=' * 55)
    print('  LSTM TRAINING — AI-Driven Construction Planner')
    print('  Student : Hanfi A.M.M | IT22074454 | SLIIT')
    print(f'  TF      : {tf.__version__}')
    print(f'  GPUs    : {tf.config.list_physical_devices("GPU")}')
    print('=' * 55)

    # Steps 1-3: data preparation
    df                    = load_data()
    df                    = encode_categoricals(df)
    df, global_features   = engineer_features(df)

    # Step 4: sequence building + scalers
    X, y, scaler_bundle   = build_sequences(df, global_features)

    # Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=SEED
    )
    print(f'\n  Train samples : {X_train.shape[0]}')
    print(f'  Test  samples : {X_test.shape[0]}')

    # Steps 5-7: build, train, evaluate
    n_timesteps = X.shape[1]
    n_features  = X.shape[2]
    model       = build_model(n_timesteps, n_features)
    history     = train_model(model, X_train, y_train)
    evaluate_and_save(model, history, X_test, y_test, scaler_bundle)


if __name__ == '__main__':
    main()
