"""P1.5 - FastAPI backend.  Run:  uvicorn backend.app.main:app --port 8000   (from the repo root)"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import ARTIFACTS, FEATURES, KB_DIR, ROOT, SAMPLES_DIR

load_dotenv(ROOT / "backend" / ".env")

from backend.app.detector import DetectorService  # noqa: E402
from backend.app.store import Store  # noqa: E402
from src.advisory.generate import generate_stream  # noqa: E402
from src.advisory.providers import configured_chain  # noqa: E402
from src.advisory.schema import FAMILIES, TECHNIQUES_OF_FAMILY  # noqa: E402
from src.detect.features import MissingColumns  # noqa: E402
from src.kb.index import TfidfIndex  # noqa: E402

MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "300"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")]


def _warm_llm():
    for p in configured_chain():
        try:
            if p.status()["available"]:
                p.warm()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_warm_llm, daemon=True).start()  # load the local model before the first draft
    yield


app = FastAPI(title="nids.", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])

svc = DetectorService()                       # model + scaler + baseline loaded once
store = Store(ROOT / "backend" / "data" / "nids.db")
kb = TfidfIndex.load(KB_DIR) if (KB_DIR / "tfidf.joblib").exists() else None
STARTED = time.time()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _analysis(aid: str):
    a = svc.get(aid)
    if a is None:
        raise HTTPException(404, "Analysis not found or expired. Re-run the detection.")
    return a


# ---------------------------------------------------------------- system
@app.get("/api/health")
def health():
    chain = [{"name": p.name, "label": p.label, **p.status()} for p in configured_chain()]
    chain.append({"name": "playbook", "label": "Local playbook", "available": True, "detail": "always available"})
    return {"status": "ok", "uptime_s": round(time.time() - STARTED),
            "bundle": svc.bundle.manifest, "kb_chunks": len(kb.chunks) if kb else 0,
            "llm_chain": chain, "brief_latency": store.latency_stats(),
            "limits": {"max_upload_mb": MAX_UPLOAD_MB}, "features": FEATURES}


@app.get("/api/metrics")
def metrics():
    m = _json(ARTIFACTS / "metrics.json")
    if m is None:
        raise HTTPException(404, "Run `python -m src.detect.train` first.")
    return m


@app.get("/api/data-card")
def data_card():
    return _json(ARTIFACTS / "data_card.json") or {}


# ---------------------------------------------------------------- detection
def _detect(df: pd.DataFrame, name: str, model: str, t_parse_ms: float):
    if df.empty:
        raise HTTPException(422, "The CSV has no rows.")
    try:
        a = svc.analyze(df, name, model, t_parse_ms)
    except MissingColumns as e:
        raise HTTPException(422, {"message": "The CSV is missing required CICFlowMeter feature columns.",
                                  "missing": e.missing, "required": FEATURES})
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.add_analysis({"id": a.id, "file_name": name, "rows": a.n, "flagged": len(a.flagged), "model": model,
                        "threshold": a.threshold, "bundle_version": svc.bundle.manifest["version"]})
    return a.summary


def _parse_and_detect(raw: bytes, name: str, model: str):
    t0 = time.perf_counter()
    try:
        df = pd.read_csv(io.BytesIO(raw), low_memory=False, encoding="latin-1")
    except Exception:
        raise HTTPException(400, "Could not parse the file as CSV.")
    return _detect(df, name, model, (time.perf_counter() - t0) * 1000)


@app.post("/api/detect")
async def detect(file: UploadFile = File(...), model: str = Query(None)):
    model = model or svc.bundle.default
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(415, "Upload a .csv file in CICFlowMeter format.")
    # read in chunks so an oversized upload is refused without holding all of it in memory
    limit, chunks, size = int(MAX_UPLOAD_MB * 1024 * 1024), [], 0
    while chunk := await file.read(1 << 20):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds the {MAX_UPLOAD_MB:.0f} MB upload limit.")
        chunks.append(chunk)
    # parsing and scoring are CPU-bound: keep them off the event loop so other requests stay responsive
    return await run_in_threadpool(_parse_and_detect, b"".join(chunks), file.filename, model)


@app.get("/api/samples")
def samples():
    return [s for s in (_json(SAMPLES_DIR / "samples.json") or []) if (SAMPLES_DIR / s["name"]).exists()]


@app.get("/api/samples/{name}/download")
def sample_download(name: str):
    path = (SAMPLES_DIR / name).resolve()
    if path.parent != SAMPLES_DIR.resolve() or path.suffix != ".csv" or not path.exists():
        raise HTTPException(404, "Unknown sample")
    return FileResponse(path, filename=name, media_type="text/csv")


@app.post("/api/samples/{name}/detect")
def sample_detect(name: str, model: str = Query(None)):
    path = (SAMPLES_DIR / name).resolve()
    if path.parent != SAMPLES_DIR.resolve() or path.suffix != ".csv" or not path.exists():
        raise HTTPException(404, "Unknown sample")
    t0 = time.perf_counter()
    df = pd.read_csv(path, low_memory=False, encoding="latin-1")
    return _detect(df, name, model or svc.bundle.default, (time.perf_counter() - t0) * 1000)


@app.get("/api/analyses/{aid}")
def analysis(aid: str):
    return _analysis(aid).summary


@app.get("/api/analyses/{aid}/detections")
def detections(aid: str, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500),
               band: str | None = None, label: str | None = None, q: str | None = None,
               sort: Literal["score", "record"] = "score"):
    a = _analysis(aid)
    return svc.detections(a, page, size, band, label, q, sort, store.decisions_for(aid))


@app.get("/api/analyses/{aid}/records/{rec}")
def record(aid: str, rec: int):
    a = _analysis(aid)
    try:
        out = svc.record(a, rec)
    except IndexError:
        raise HTTPException(404, f"Record {rec} is outside 1..{a.n}")
    out["history"] = store.record_history(aid, rec)
    return out


# ---------------------------------------------------------------- advisory brief
class BriefIn(BaseModel):
    family_hint: str | None = None
    playbook_only: bool = False


@app.post("/api/analyses/{aid}/records/{rec}/brief")
def brief(aid: str, rec: int, body: BriefIn):
    a = _analysis(aid)
    if body.family_hint and body.family_hint not in FAMILIES:
        raise HTTPException(422, f"family_hint must be one of {FAMILIES}")
    try:
        facts = svc.facts(a, rec)
    except IndexError:
        raise HTTPException(404, "Record not found")

    def stream():
        for ev in generate_stream(facts, body.family_hint, providers=[] if body.playbook_only else None):
            if ev["type"] == "done":
                ev["brief_id"] = store.add_brief(aid, rec, body.family_hint, ev)
                ev["meta"] = {k: v for k, v in ev["meta"].items() if k not in ("raw_response",)}
            yield json.dumps(ev) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/api/briefs/{brief_id}")
def get_brief(brief_id: int):
    b = store.brief(brief_id)
    if not b:
        raise HTTPException(404, "Brief not found")
    return b


# ---------------------------------------------------------------- analyst decisions (human in the loop)
class DecisionIn(BaseModel):
    analysis_id: str
    record_id: int
    brief_id: int | None = None
    status: Literal["approved", "rejected"]
    analyst: str = Field(min_length=1, max_length=60)
    notes: str = Field("", max_length=2000)
    final_brief: dict | None = None
    edited: bool = False


@app.post("/api/decisions")
def decide(d: DecisionIn):
    a = svc.get(d.analysis_id)
    if a is None and not store.has_analysis(d.analysis_id):
        raise HTTPException(404, "Unknown analysis")
    if a is not None and not 1 <= d.record_id <= a.n:
        raise HTTPException(422, f"Record {d.record_id} is outside 1..{a.n}")
    if d.brief_id is not None:
        b = store.brief(d.brief_id)
        if not b or b["analysis_id"] != d.analysis_id or b["record_id"] != d.record_id:
            raise HTTPException(422, "The draft does not belong to this record.")
    did = store.add_decision(d.model_dump())
    return {"id": did, "status": d.status}


@app.get("/api/audit")
def audit(limit: int = Query(200, ge=1, le=1000)):
    return store.audit(limit)


# ---------------------------------------------------------------- knowledge base
@app.get("/api/kb/stats")
def kb_stats():
    return {"stats": _json(KB_DIR / "stats.json"), "eval": _json(KB_DIR / "retrieval_eval.json"),
            "families": {f: TECHNIQUES_OF_FAMILY[f] for f in FAMILIES}}


@app.get("/api/kb/search")
def kb_search(q: str = Query(..., min_length=2, max_length=300), k: int = Query(8, ge=1, le=30),
              technique: str | None = None, source: str | None = None):
    if kb is None:
        raise HTTPException(503, "Knowledge base not built. Run `python -m src.kb.build`.")
    t0 = time.perf_counter()
    res = kb.search(q, k, technique, source)
    return {"query": q, "results": res, "ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.get("/api/kb/related")
def kb_related(family: str, q: str = ""):
    """Reference material for an analyst - shown beside the brief, NOT fed to the Phase-1 generator."""
    if kb is None:
        return {"results": []}
    techs = TECHNIQUES_OF_FAMILY.get(family, [])
    out = []
    for t in techs:
        out += kb.search(f"{family} {q} mitigation detection", 3, technique=t)
    out += kb.search(f"{family} {q} incident response containment", 2, source="NIST SP 800-61 Rev. 3")
    return {"family": family, "techniques": techs, "results": out}


# ---------------------------------------------------------------- static frontend (production build)
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, f"No API route /{path}")
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")


@app.exception_handler(RequestValidationError)
def validation_error(_, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x not in ("body", "query", "path"))
    msg = f"{where}: {first.get('msg', 'invalid input')}" if where else first.get("msg", "Invalid input.")
    return JSONResponse(status_code=422, content={"error": {"message": msg}})


@app.exception_handler(HTTPException)
def http_error(_, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})
