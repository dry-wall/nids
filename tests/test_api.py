"""End-to-end API tests against the real bundle and a held-out demo sample (LLM forced offline)."""
import io
import json

import pytest

from src.config import BUNDLE_DIR, SAMPLES_DIR

pytestmark = pytest.mark.skipif(not (BUNDLE_DIR / "manifest.json").exists() or not (SAMPLES_DIR / "samples.json").exists(),
                                reason="run training and make_samples first")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["LLM_PROVIDERS"] = ""          # no LLM: exercises the offline path deterministically
    from fastapi.testclient import TestClient
    from backend.app import main
    from backend.app.store import Store
    main.store = Store(tmp_path_factory.mktemp("db") / "test.db")
    return TestClient(main.app)


@pytest.fixture(scope="module")
def analysis(client):
    r = client.post("/api/samples/demo_mixed_2k.csv/detect?model=dnn")
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["llm_chain"][-1]["name"] == "playbook"


def test_detect_summary_is_consistent(analysis):
    a = analysis
    assert a["total"] == a["flagged"] + a["benign"]
    assert sum(a["bands"].values()) == a["flagged"]
    assert sum(b["flagged"] for b in a["timeline"]) == a["flagged"]
    gt = a["ground_truth"]["confusion"]
    assert gt["tp"] + gt["fp"] == a["flagged"]


def test_detections_paging_and_record_detail(client, analysis):
    d = client.get(f"/api/analyses/{analysis['id']}/detections?size=5").json()
    assert d["total"] == analysis["flagged"] and len(d["rows"]) == 5
    scores = [r["score"] for r in d["rows"]]
    assert scores == sorted(scores, reverse=True)
    rec = client.get(f"/api/analyses/{analysis['id']}/records/{d['rows'][0]['record']}").json()
    assert rec["flagged"] and len(rec["deviations"]) == 5 and len(rec["models"]) == 3
    assert client.get(f"/api/analyses/{analysis['id']}/records/999999").status_code == 404


def test_brief_stream_and_decision_audit(client, analysis):
    rec = client.get(f"/api/analyses/{analysis['id']}/detections?size=1").json()["rows"][0]["record"]
    r = client.post(f"/api/analyses/{analysis['id']}/records/{rec}/brief", json={"family_hint": "DoS"})
    events = [json.loads(l) for l in r.text.strip().splitlines()]
    done = events[-1]
    assert done["type"] == "done" and done["meta"]["provider"] == "playbook" and done["brief_id"]
    r = client.post("/api/decisions", json={"analysis_id": analysis["id"], "record_id": rec, "brief_id": done["brief_id"],
                                            "status": "approved", "analyst": "pytest", "notes": "ok"})
    assert r.status_code == 200
    audit = client.get("/api/audit").json()
    assert audit["decisions"][0]["analyst"] == "pytest" and audit["briefs"][0]["provider"] == "playbook"
    hist = client.get(f"/api/analyses/{analysis['id']}/records/{rec}").json()["history"]
    assert hist["decisions"][0]["status"] == "approved"


def test_upload_validation(client):
    bad = client.post("/api/detect", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert bad.status_code == 422 and "Flow Duration" in bad.json()["error"]["missing"]
    wrong = client.post("/api/detect", files={"file": ("x.txt", io.BytesIO(b"a"), "text/plain")})
    assert wrong.status_code == 415
    assert client.post("/api/decisions", json={"analysis_id": "x", "record_id": 1, "status": "maybe",
                                               "analyst": "a"}).status_code == 422


def test_unlabelled_upload_works(client):
    csv = (SAMPLES_DIR / "demo_mixed_2k.csv").read_text(encoding="latin-1").splitlines()
    header = csv[0].split(",")
    li = [h.strip() for h in header].index("Label")
    stripped = "\n".join(",".join(c for i, c in enumerate(l.split(",")) if i != li) for l in csv[:300])
    r = client.post("/api/detect?model=rf", files={"file": ("nolabel.csv", io.BytesIO(stripped.encode()), "text/csv")})
    assert r.status_code == 200 and r.json()["ground_truth"] is None


def test_kb_search(client):
    r = client.get("/api/kb/search?q=ssh password guessing&k=5").json()
    assert r["results"] and any((c.get("technique_id") or "").startswith("T1110") for c in r["results"])
