"""One-command entry point.

  python run.py              serve API + dashboard on http://127.0.0.1:8000 (builds the UI if needed)
  python run.py reproduce    every number in the report: clean -> train -> samples -> KB -> figures
  python run.py test         unit + API tests
  python run.py dev          backend with auto-reload + Vite dev server on :5173
"""
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
KB_RAW = ROOT / "data" / "raw" / "kb"
KB_SOURCES = {
    "enterprise-attack.json": "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json",
    "NIST.SP.800-61r3.pdf": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf",
}


def sh(*args, cwd=ROOT, env=None):
    print(f"\n$ {' '.join(map(str, args))}", flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True, env={**os.environ, **(env or {})})


def npm(*args):
    sh("npm.cmd" if os.name == "nt" else "npm", *args, cwd=ROOT / "frontend")


def fetch_kb():
    KB_RAW.mkdir(parents=True, exist_ok=True)
    for name, url in KB_SOURCES.items():
        if not (KB_RAW / name).exists():
            print(f"downloading {name}")
            urllib.request.urlretrieve(url, KB_RAW / name)


def reproduce():
    env = {"TF_CPP_MIN_LOG_LEVEL": "2", "TF_ENABLE_ONEDNN_OPTS": "0"}
    sh(PY, "-m", "src.data.clean")
    sh(PY, "-m", "src.detect.train", env=env)
    sh(PY, "-m", "src.data.make_samples")
    fetch_kb()
    sh(PY, "-m", "src.kb.build")
    print("\nAll artefacts regenerated under artifacts/ (tables/, figures/, metrics.json, kb/).")


def ensure_ui():
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        if not (ROOT / "frontend" / "node_modules").exists():
            npm("install", "--no-audit", "--no-fund")
        npm("run", "build")


def serve():
    if not (ROOT / "artifacts" / "model_bundle" / "manifest.json").exists():
        sys.exit("No model bundle. Run:  python run.py reproduce")
    if not (ROOT / "backend" / ".env").exists():
        shutil.copy(ROOT / "backend" / ".env.example", ROOT / "backend" / ".env")
    ensure_ui()
    threading.Timer(2.5, webbrowser.open, ["http://127.0.0.1:8000"]).start()
    sh(PY, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000")


def dev():
    procs = [subprocess.Popen([PY, "-m", "uvicorn", "backend.app.main:app", "--reload", "--port", "8000"], cwd=ROOT)]
    try:
        npm("run", "dev")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    {"serve": serve, "reproduce": reproduce, "dev": dev, "fetch-kb": fetch_kb,
     "test": lambda: sh(PY, "-m", "pytest", "-q", "tests")}[cmd]()
