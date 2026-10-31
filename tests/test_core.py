"""Unit tests for preprocessing, explanation, threshold policy, serving models and brief generation."""
import json

import numpy as np
import pandas as pd
import pytest

from src.config import BUNDLE_DIR, FEATURES
from src.detect.features import MissingColumns, Preprocessor, raw_matrix, signed_log, strip_columns
from src.detect.models import LinearModel, NumpyMLP
from src.eval.detection import binary_metrics, choose_threshold
from src.explain.zscore import BenignBaseline

RNG = np.random.default_rng(0)


def frame(n=50):
    return pd.DataFrame(RNG.lognormal(3, 2, size=(n, len(FEATURES))), columns=[" " + f for f in FEATURES])


def test_strip_columns_handles_cicflowmeter_padding():
    df = strip_columns(frame())
    assert list(df.columns) == FEATURES


def test_missing_columns_are_reported_by_name():
    df = strip_columns(frame()).drop(columns=["Flow Duration", "SYN Flag Count"])
    with pytest.raises(MissingColumns) as e:
        raw_matrix(df)
    assert set(e.value.missing) == {"Flow Duration", "SYN Flag Count"}


def test_inf_becomes_nan_and_is_imputed_with_train_medians():
    df = strip_columns(frame())
    df.iloc[0, 5] = np.inf
    X = raw_matrix(df)
    assert np.isnan(X[0, 5])
    pre = Preprocessor().fit(X[1:])
    Z = pre.transform(X)
    assert np.isfinite(Z).all()
    # the imputed cell equals the transform of the training median
    expected = (signed_log(np.array([pre.medians[5]])) - pre.mean[5]) / pre.scale[5]
    assert Z[0, 5] == pytest.approx(expected[0], rel=1e-5)


def test_signed_log_keeps_sign_of_negative_flow_rates():
    assert signed_log(np.array([-1000.0]))[0] < 0
    assert signed_log(np.array([0.0]))[0] == 0


def test_preprocessor_roundtrip_through_json():
    X = raw_matrix(strip_columns(frame()))
    pre = Preprocessor().fit(X)
    pre2 = Preprocessor.from_dict(json.loads(json.dumps(pre.to_dict())))
    np.testing.assert_allclose(pre.transform(X), pre2.transform(X))


def test_zscore_top_k_ranks_by_absolute_deviation():
    Zb = RNG.normal(0, 1, size=(500, len(FEATURES)))
    base = BenignBaseline.fit(Zb, np.abs(Zb) * 10)
    row = np.zeros(len(FEATURES)); row[3] = -9.0; row[7] = 5.0; row[1] = 2.0
    top = base.top_k(row, np.ones(len(FEATURES)), k=3)
    assert [t["feature"] for t in top] == [FEATURES[3], FEATURES[7], FEATURES[1]]
    assert top[0]["direction"] == "below" and top[1]["direction"] == "above"


def test_threshold_respects_target_fpr_on_validation():
    y = np.r_[np.zeros(5000), np.ones(1000)].astype(int)
    p = np.r_[RNG.beta(2, 8, 5000), RNG.beta(8, 2, 1000)]
    op = choose_threshold(y, p, target_fpr=0.01)
    assert op["val_fpr"] <= 0.01
    m = binary_metrics(y, p, op["threshold"])
    assert m["fpr"] <= 0.0101
    c = m["confusion"]
    assert c["tp"] + c["fn"] == 1000 and c["tn"] + c["fp"] == 5000


def test_linear_model_matches_logistic_formula():
    lm = LinearModel([1.0, -2.0], 0.5)
    Z = np.array([[0.0, 0.0], [1.0, 1.0]])
    np.testing.assert_allclose(lm.predict_proba(Z), 1 / (1 + np.exp(-np.array([0.5, -0.5]))))


@pytest.mark.skipif(not (BUNDLE_DIR / "dnn.keras").exists(), reason="model bundle not trained")
def test_numpy_dnn_matches_keras_exactly():
    from tensorflow import keras
    model = keras.models.load_model(BUNDLE_DIR / "dnn.keras")
    mlp = NumpyMLP(dict(np.load(BUNDLE_DIR / "dnn.npz")))
    Z = RNG.normal(0, 2, size=(2048, len(FEATURES))).astype(np.float32)
    np.testing.assert_allclose(mlp.predict_proba(Z), model.predict(Z, verbose=0).ravel(), atol=1e-5)


# ---------------------------------------------------------------- advisory
FACTS = {"record_id": "test.csv#7", "model_name": "DNN (64-32)", "score": 0.97, "threshold": 0.69,
         "deviations": [{"feature": f, "value": 10.0 * i, "z": 5.0 - i, "direction": "above",
                         "benign_median": 1.0} for i, f in enumerate(FEATURES[:5])]}


class FakeProvider:
    name, label, model = "fake", "Fake", "fake-1"

    def __init__(self, outputs):
        self.outputs = list(outputs)

    def status(self):
        return {"available": True, "detail": "ok"}

    def stream(self, prompt):
        yield self.outputs.pop(0)


GOOD = json.dumps({"summary": "s", "hypothesis": {"family": "DoS", "technique_ids": ["T1499", "T1046", "T9999"],
                                                    "reasoning": "r", "confidence_note": "c"},
                   "impact": "i", "actions": ["a1", "a2", "a3"], "limitations": "l"})


def test_brief_numbers_come_from_detector_not_llm():
    from src.advisory.generate import generate
    ev = generate(FACTS, providers=[FakeProvider([GOOD])])
    assert ev["meta"]["provider"] == "fake"
    assert [d["z"] for d in ev["brief"]["why_flagged"]] == [d["z"] for d in FACTS["deviations"]]
    # technique IDs outside the family's A.3 mapping are stripped
    assert ev["brief"]["hypothesis"]["technique_ids"] == ["T1499"]


def test_invalid_json_is_retried_once_then_succeeds():
    from src.advisory.generate import generate_stream
    events = list(generate_stream(FACTS, providers=[FakeProvider(["not json", GOOD])]))
    assert any(e["type"] == "retry" for e in events)
    assert events[-1]["meta"]["provider"] == "fake"


def test_two_invalid_outputs_fall_back_to_playbook():
    from src.advisory.generate import generate
    ev = generate(FACTS, providers=[FakeProvider(["{}", "{bad"])])
    assert ev["meta"]["provider"] == "playbook"
    assert ev["brief"]["actions"]


def test_offline_playbook_works_with_no_providers_and_family_hint():
    from src.advisory.generate import generate
    ev = generate(FACTS, family_hint="Brute Force", providers=[])
    assert ev["meta"]["provider"] == "playbook"
    assert ev["brief"]["hypothesis"]["family"] == "Brute Force"
    assert ev["brief"]["hypothesis"]["technique_ids"] == ["T1110"]


def test_unreachable_ollama_falls_back(monkeypatch):
    from src.advisory.generate import generate
    from src.advisory.providers import OllamaProvider
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")  # nothing listens here
    ev = generate(FACTS, providers=[OllamaProvider()])
    assert ev["meta"]["provider"] == "playbook"
    assert any("ollama" in r for r in ev["meta"]["fallback_reasons"])


def test_prompt_contains_only_detector_facts():
    from src.advisory.prompts import build_prompt
    p = build_prompt(FACTS)
    assert "0.9700" in p and FEATURES[0] in p and "Do not invent IP addresses" in p
