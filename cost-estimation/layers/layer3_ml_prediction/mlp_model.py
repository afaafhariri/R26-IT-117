"""Residual MLP cost prediction model built with Keras / TensorFlow 2.x.

Architecture:
  Input → Dense(256, relu) + BatchNorm + Dropout(0.3)
        → Dense(128, relu) + BatchNorm + Dropout(0.2)
        → skip connection (layer-1 output concatenated to layer-2 output)
        → Dense(64, relu)
        → Dense(1, linear)   ← predicts log(cost)

Training target is log1p(cost_lkr) to handle the wide cost range;
predictions are exponentiated back with expm1().
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_MODELS_DIR = Path(__file__).parent.parent.parent / "models"


class ResidualMLPModel:
    """Keras residual MLP for cost estimation — complements the XGBoost model."""

    def __init__(self) -> None:
        self._model = None  # keras.Model, lazy-built on first train/load
        self._scaler = None  # sklearn StandardScaler for input normalisation

    # ------------------------------------------------------------------
    # Model construction
    # ------------------------------------------------------------------

    def _build_model(self, input_dim: int):
        """Construct and compile the Keras residual model.

        Args:
            input_dim: Number of input features.

        Returns:
            Compiled keras.Model.
        """
        # Import inside method to avoid TF load time at module import
        import tensorflow as tf
        from tensorflow import keras

        inputs = keras.Input(shape=(input_dim,), name="features")

        # Layer 1
        x1 = keras.layers.Dense(256, activation="relu", name="dense_1")(inputs)
        x1 = keras.layers.BatchNormalization()(x1)
        x1 = keras.layers.Dropout(0.3)(x1)

        # Layer 2
        x2 = keras.layers.Dense(128, activation="relu", name="dense_2")(x1)
        x2 = keras.layers.BatchNormalization()(x2)
        x2 = keras.layers.Dropout(0.2)(x2)

        # Skip connection: project layer-1 output to 128 dims and add
        x1_proj = keras.layers.Dense(128, use_bias=False, name="skip_proj")(x1)
        x_skip = keras.layers.Add(name="skip_add")([x1_proj, x2])

        # Layer 3
        x3 = keras.layers.Dense(64, activation="relu", name="dense_3")(x_skip)

        # Output — linear activation for log-cost regression
        outputs = keras.layers.Dense(1, activation="linear", name="cost_log")(x3)

        model = keras.Model(inputs=inputs, outputs=outputs, name="residual_mlp")
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=1e-3),
            loss=keras.losses.Huber(delta=1.0),
            metrics=["mae"],
        )
        return model

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        epochs: int = 100,
        patience: int = 20,
    ) -> None:
        """Train the residual MLP on log-transformed cost.

        Args:
            X: Feature DataFrame (numeric, no NaNs).
            y: Series of actual costs in LKR.
            epochs: Maximum training epochs.
            patience: Early stopping patience (epochs without val_loss improvement).
        """
        from sklearn.preprocessing import StandardScaler
        import tensorflow as tf
        from tensorflow import keras

        log_y = np.log1p(y.values.astype(np.float32))

        # Normalise features
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X.values.astype(np.float32))

        self._model = self._build_model(input_dim=X_scaled.shape[1])

        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=patience,
                restore_best_weights=True,
                verbose=1,
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=patience // 2,
                verbose=1,
            ),
        ]

        logger.info("Training Residual MLP for up to %d epochs.", epochs)
        self._model.fit(
            X_scaled,
            log_y,
            epochs=epochs,
            validation_split=0.15,
            batch_size=32,
            callbacks=callbacks,
            verbose=0,
        )
        logger.info("Residual MLP training complete.")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> float:
        """Return predicted cost in LKR (exponentiated from log-space).

        Args:
            X: Single-row feature DataFrame.

        Returns:
            Predicted cost in LKR, or 0.0 if model is not loaded.
        """
        if self._model is None:
            logger.warning("MLP model not loaded — returning 0.")
            return 0.0
        X_scaled = self._scaler.transform(X.values.astype(np.float32))
        log_pred = float(self._model.predict(X_scaled, verbose=0)[0][0])
        return float(np.expm1(log_pred))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> None:
        """Save model weights (.weights.h5) and scaler to the models directory.

        Args:
            path: Directory path. Defaults to /component02/models/.
        """
        import joblib

        models_dir = Path(path) if path else _MODELS_DIR
        models_dir.mkdir(parents=True, exist_ok=True)

        if self._model:
            weights_path = models_dir / "mlp_weights.weights.h5"
            self._model.save_weights(str(weights_path))
            logger.info("MLP weights saved to %s.", weights_path)

        if self._scaler:
            scaler_path = models_dir / "mlp_scaler.pkl"
            joblib.dump(self._scaler, str(scaler_path))

    def load(self, path: Optional[str] = None) -> None:
        """Load model weights and scaler. Model architecture is rebuilt first.

        Args:
            path: Directory path. Defaults to /component02/models/.
        """
        import joblib
        from layers.layer3_ml_prediction.feature_engineer import FeatureEngineer

        models_dir = Path(path) if path else _MODELS_DIR
        weights_path = models_dir / "mlp_weights.weights.h5"
        scaler_path = models_dir / "mlp_scaler.pkl"

        input_dim = len(FeatureEngineer.feature_names())
        self._model = self._build_model(input_dim=input_dim)

        if weights_path.exists():
            self._model.load_weights(str(weights_path))
            logger.info("MLP weights loaded from %s.", weights_path)
        else:
            logger.warning("MLP weights file not found at %s.", weights_path)

        if scaler_path.exists():
            self._scaler = joblib.load(str(scaler_path))
        else:
            logger.warning("MLP scaler not found — predictions will be unscaled.")
            from sklearn.preprocessing import StandardScaler
            self._scaler = StandardScaler()

    @property
    def is_loaded(self) -> bool:
        """True if the model is ready for inference."""
        return self._model is not None
