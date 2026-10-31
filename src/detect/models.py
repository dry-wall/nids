"""Detector definitions (training) and their light-weight serving forms.

Serving never imports TensorFlow: the DNN's weights are exported to .npz and run as four numpy
matmuls, and Logistic Regression is just a weight vector. A unit test checks numpy == Keras.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

MODEL_NAMES = {"lr": "Logistic Regression", "rf": "Random Forest", "dnn": "DNN (64-32)"}


def make_lr(seed: int) -> LogisticRegression:
    return LogisticRegression(class_weight="balanced", max_iter=2000, random_state=seed)


def make_rf(seed: int) -> RandomForestClassifier:
    # Depth/leaf limits keep the bundle small enough to load in the API in ~1 s.
    return RandomForestClassifier(n_estimators=100, max_depth=22, min_samples_leaf=2,
                                  max_samples=0.5, class_weight="balanced_subsample",
                                  n_jobs=-1, random_state=seed)


def train_dnn(Xtr, ytr, Xva, yva, seed: int, epochs: int = 15, batch: int = 512, verbose: int = 2):
    """Dense 64 -> Dropout 0.3 -> Dense 32 -> sigmoid, class-weighted BCE, early stop on val loss."""
    import tensorflow as tf
    from tensorflow import keras

    keras.utils.set_random_seed(seed)
    tf.config.experimental.enable_op_determinism()
    model = keras.Sequential([
        keras.layers.Input((Xtr.shape[1],)),
        keras.layers.Dense(64, activation="relu"),
        keras.layers.Dropout(0.3),
        keras.layers.Dense(32, activation="relu"),
        keras.layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(keras.optimizers.Adam(1e-3), "binary_crossentropy")
    n, n1 = len(ytr), int(ytr.sum())
    cw = {0: n / (2 * (n - n1)), 1: n / (2 * n1)}
    stop = keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)
    hist = model.fit(Xtr, ytr, validation_data=(Xva, yva), epochs=epochs, batch_size=batch,
                     class_weight=cw, callbacks=[stop], verbose=verbose, shuffle=True)
    return model, {"epochs_run": len(hist.history["loss"]),
                   "best_epoch": int(np.argmin(hist.history["val_loss"])) + 1,
                   "loss": [round(float(v), 5) for v in hist.history["loss"]],
                   "val_loss": [round(float(v), 5) for v in hist.history["val_loss"]]}


def keras_to_arrays(model) -> dict:
    dense = [l for l in model.layers if l.get_weights()]
    out = {}
    for i, layer in enumerate(dense):
        w, b = layer.get_weights()
        out[f"W{i}"], out[f"b{i}"] = w.astype(np.float32), b.astype(np.float32)
    return out


class NumpyMLP:
    """ReLU hidden layers, sigmoid output; dropout is identity at inference."""

    def __init__(self, arrays: dict):
        n = len([k for k in arrays if k.startswith("W")])
        self.layers = [(arrays[f"W{i}"], arrays[f"b{i}"]) for i in range(n)]

    def predict_proba(self, Z: np.ndarray) -> np.ndarray:
        h = Z.astype(np.float32)
        for i, (W, b) in enumerate(self.layers):
            h = h @ W + b
            if i < len(self.layers) - 1:
                np.maximum(h, 0, out=h)
        return (1.0 / (1.0 + np.exp(-np.clip(h[:, 0], -60, 60)))).astype(np.float64)


class LinearModel:
    def __init__(self, coef, intercept):
        self.coef = np.asarray(coef, dtype=np.float64)
        self.intercept = float(intercept)

    def predict_proba(self, Z: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(Z @ self.coef + self.intercept, -60, 60)))


class SklearnProba:
    def __init__(self, est):
        self.est = est

    def predict_proba(self, Z: np.ndarray) -> np.ndarray:
        return self.est.predict_proba(Z)[:, 1]
