# nids.

A supervised detector scores CIC-IDS2017 network flows. Each alert is explained against the benign
baseline, a **local** language model drafts a short JSON advisory brief from the detector's facts only,
and an analyst approves or rejects it. Every brief, prompt and decision is stored in an audit trail.
Everything runs offline.

## Run it

```powershell
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:3b          # local LLM (optional - the offline playbook is the fallback)
python run.py                   # http://127.0.0.1:8000  (builds the UI on first run)
```

| Command | What it does |
|---|---|
| `python run.py` | Serve API + dashboard (one process) |
| `python run.py reproduce` | Regenerate **every** number, table and figure from the raw CSVs |
| `python run.py test` | 29 unit, API and regression tests (LLM forced offline) |
| `python run.py dev` | Backend with reload + Vite dev server on :5173 |

The five-minute evaluation walkthrough, with the offline fallback, is in [docs/DEMO.md](docs/DEMO.md).

**Data.** A fresh clone runs straight away: the trained models, the knowledge-base index and two
held-out demo samples are committed. To retrain or regenerate everything, put the eight CIC-IDS2017
*MachineLearningCVE* CSVs in `data/raw/cic-ids2017/` and run `python run.py reproduce`. It also
downloads the KB sources (MITRE ATT&CK STIX, NIST SP 800-61r3) and builds the 50k-flow sample.

## Phase-1 results (held-out test split, mean ± std over seeds 42/43/44)

Threshold chosen on the **validation** split: maximise F1 subject to benign FPR ≤ 1 %. Test touched once.

| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | FPR |
|---|---|---|---|---|---|---|
| Logistic Regression | 0.9400 | 0.7401 | 0.8282 | 0.9485 | 0.8914 | 1.03 % |
| Random Forest | **0.9938** ± 0.0004 | **0.9849** ± 0.0003 | **0.9894** ± 0.0001 | **0.9998** | **0.9993** | **0.13 %** |
| DNN 64-32 (report model) | 0.9841 ± 0.0004 | 0.9798 ± 0.0011 | 0.9819 ± 0.0007 | 0.9995 | 0.9982 | 0.34 % |

**Leakage check (temporal split).** Train on Mon–Wed, test on Thu–Fri, so every test attack family is
unseen. F1 drops to LR 0.748, RF 0.289, DNN 0.613. The random-split scores measure recognition of
*known* families. Zero-day detection is Phase-2 work (benign-only autoencoder).

**Cleaning.** 2,830,743 raw flows → 1,830,365 after removing 308,381 exact duplicates and 691,997
duplicates in the 12-feature model space (de-duplication happens before splitting). 99 % of PortScan
rows are the same 12-feature vector.

**Knowledge base.** 2,375 chunks (706 ATT&CK techniques + mitigations, 146 NIST 800-61r3 chunks).
TF-IDF Recall@5 = 0.90, MRR = 0.714 on 20 labelled queries (BM25: 0.85 / 0.732).

**Local LLM.** qwen2.5:3b on an RTX 3050 Ti (4 GB): ~80 tok/s, brief p50 ≈ 4.5 s, first token ≈ 0.8 s,
21/21 schema-valid outputs in the benchmark.

All tables and figures: `artifacts/tables/*.md|csv`, `artifacts/figures/*.png`, `artifacts/metrics.json`.

## What is built (Phase 1) and what is honest about it

| Stage | Phase 1 |
|---|---|
| Ingestion | CSV upload (≤ 300 MB) with schema check that names missing columns; padded CICFlowMeter headers handled |
| Preprocessing | Train-median imputation → signed log → standardise; fitted state stored as JSON |
| Detection | LR / RF / DNN, all served; the DNN runs as numpy matmuls (tested equal to Keras) |
| Calibration | **None.** Scores are labelled *uncalibrated*; bands are margins above the threshold, not severity |
| Explanation | Top-5 \|z\| vs benign training baseline (not causal; SHAP in Phase 2) |
| Knowledge base | ATT&CK + NIST ingested and chunked with stable IDs; TF-IDF prototype; shown as reference only |
| Advisory | Fixed-section JSON brief; local Ollama → optional Gemini → deterministic playbook; invalid JSON retried once; technique IDs restricted to the A.3 mapping; numbers in the brief are copied from the detector, never from the LLM |
| Human in the loop | Edit → approve / reject, stored with analyst, notes and final brief; nothing is blocked automatically |
| Interface | React dashboard with light and dark themes: Analyze, Alerts, Models, Knowledge, Audit, System |

The file's `Label` column is shown only as a dashed **GT** badge and in "evaluation only" panels.
It is never passed to the detector or the LLM. The detector is binary, so naming the attack family
is a *hypothesis* proposed by the LLM, or chosen by the analyst. A multi-class model replaces this in Phase 2.

## Layout

```
src/data       clean.py (dedupe, data card) · split.py (seeded) · make_samples.py (test split only)
src/detect     features.py · models.py · train.py
src/explain    zscore.py
src/kb         ingest_attack.py · ingest_nist.py · chunk.py · index.py · build.py
src/advisory   schema.py · prompts.py · providers.py · generate.py · playbooks/
src/eval       detection.py · retrieval.py · figures.py
backend/app    FastAPI (main.py) · detector.py · store.py (SQLite audit)
frontend       React + Vite + Tailwind (fonts bundled for offline use)
artifacts      model_bundle/ · metrics.json · data_card.json · tables/ · figures/ · kb/
```

## Configuration (`backend/.env`, copied from `.env.example`)

`LLM_PROVIDERS=ollama` (add `gemini` plus `GEMINI_API_KEY` for the optional cloud tier) ·
`OLLAMA_MODEL=qwen2.5:3b` · `MAX_UPLOAD_MB=300` · `CORS_ORIGINS`. Never commit `.env`.
