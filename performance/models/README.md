# Model Artefacts — Component 03

Place trained model files here before running the service.

| File | Description |
|---|---|
| `delay_xgboost.json` | XGBoost 3-class delay-risk classifier (low / medium / high). Train via `scripts/train_xgboost.py` (TODO). |
| `lstm_weights.h5` | Keras LSTM regressor for predicted delay days. Train via `scripts/train_lstm.py` (TODO). |

## Training notes

- XGBoost: fit on labelled historical progress records with columns matching `XGB_FEATURES` in `pipeline/delay_model.py`.
- LSTM: sequence length = 10 time steps, input features defined in `LSTM_SEQUENCE_FEATURES`.
- Save with `model.save_model("models/delay_xgboost.json")` and `model.save("models/lstm_weights.h5")` respectively.
- The service performs lazy loading — models are read from disk on the first prediction call.
