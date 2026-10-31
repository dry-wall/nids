"""SQLite audit trail: every analysis, every generated brief (with prompt + raw response), every decision."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY, file_name TEXT, rows INTEGER, flagged INTEGER, model TEXT,
  threshold REAL, bundle_version TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS briefs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id TEXT, record_id INTEGER, provider TEXT,
  model TEXT, family_hint TEXT, prompt TEXT, raw_response TEXT, brief_json TEXT, latency_ms INTEGER,
  first_token_ms INTEGER, fallback_reasons TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id TEXT, record_id INTEGER, brief_id INTEGER,
  status TEXT, analyst TEXT, notes TEXT, final_brief_json TEXT, edited INTEGER, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_briefs_rec ON briefs(analysis_id, record_id);
CREATE INDEX IF NOT EXISTS ix_dec_rec ON decisions(analysis_id, record_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def add_analysis(self, a: dict):
        self._exec("INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?,?,?)",
                   (a["id"], a["file_name"], a["rows"], a["flagged"], a["model"], a["threshold"],
                    a["bundle_version"], now()))

    def has_analysis(self, aid) -> bool:
        return bool(self._all("SELECT 1 FROM analyses WHERE id=?", (aid,)))

    def add_brief(self, analysis_id, record_id, family_hint, ev) -> int:
        m = ev["meta"]
        return self._exec(
            "INSERT INTO briefs (analysis_id, record_id, provider, model, family_hint, prompt, raw_response,"
            " brief_json, latency_ms, first_token_ms, fallback_reasons, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (analysis_id, record_id, m["provider"], m.get("model"), family_hint, m["prompt"], m.get("raw_response"),
             json.dumps(ev["brief"]), m["latency_ms"], m.get("first_token_ms"), json.dumps(m["fallback_reasons"]), now()))

    def add_decision(self, d: dict) -> int:
        return self._exec(
            "INSERT INTO decisions (analysis_id, record_id, brief_id, status, analyst, notes, final_brief_json,"
            " edited, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (d["analysis_id"], d["record_id"], d.get("brief_id"), d["status"], d["analyst"], d.get("notes", ""),
             json.dumps(d.get("final_brief")) if d.get("final_brief") else None, int(bool(d.get("edited"))), now()))

    def record_history(self, analysis_id, record_id) -> dict:
        briefs = self._all("SELECT * FROM briefs WHERE analysis_id=? AND record_id=? ORDER BY id DESC",
                           (analysis_id, record_id))
        decisions = self._all("SELECT * FROM decisions WHERE analysis_id=? AND record_id=? ORDER BY id DESC",
                              (analysis_id, record_id))
        for b in briefs:
            b["brief"] = json.loads(b.pop("brief_json"))
            b["fallback_reasons"] = json.loads(b["fallback_reasons"] or "[]")
        for d in decisions:
            d["final_brief"] = json.loads(d.pop("final_brief_json")) if d.get("final_brief_json") else None
        return {"briefs": briefs, "decisions": decisions}

    def decisions_for(self, analysis_id) -> dict[int, str]:
        rows = self._all("SELECT record_id, status FROM decisions WHERE analysis_id=? ORDER BY id", (analysis_id,))
        return {r["record_id"]: r["status"] for r in rows}  # latest wins

    def audit(self, limit=200) -> dict:
        decisions = self._all(
            "SELECT d.id, d.analysis_id, d.record_id, d.brief_id, d.status, d.analyst, d.notes, d.edited, d.created_at,"
            " a.file_name, b.provider FROM decisions d LEFT JOIN analyses a ON a.id=d.analysis_id"
            " LEFT JOIN briefs b ON b.id=d.brief_id ORDER BY d.id DESC LIMIT ?", (limit,))
        briefs = self._all(
            "SELECT b.id, b.analysis_id, b.record_id, b.provider, b.model, b.family_hint, b.latency_ms,"
            " b.first_token_ms, b.fallback_reasons, b.created_at, a.file_name FROM briefs b"
            " LEFT JOIN analyses a ON a.id=b.analysis_id ORDER BY b.id DESC LIMIT ?", (limit,))
        analyses = self._all("SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,))
        return {"decisions": decisions, "briefs": briefs, "analyses": analyses}

    def brief(self, brief_id) -> dict | None:
        rows = self._all("SELECT * FROM briefs WHERE id=?", (brief_id,))
        if not rows:
            return None
        b = rows[0]
        b["brief"] = json.loads(b.pop("brief_json"))
        return b

    def latency_stats(self) -> list[dict]:
        out = []
        for prov in [r["provider"] for r in self._all("SELECT DISTINCT provider FROM briefs")]:
            v = sorted(r["latency_ms"] for r in self._all("SELECT latency_ms FROM briefs WHERE provider=?", (prov,)))
            ft = sorted(r["first_token_ms"] for r in self._all(
                "SELECT first_token_ms FROM briefs WHERE provider=? AND first_token_ms IS NOT NULL", (prov,)))
            pct = lambda a, q: a[min(len(a) - 1, int(round(q * (len(a) - 1))))] if a else None  # noqa: E731
            out.append({"provider": prov, "n": len(v), "p50_ms": pct(v, .5), "p95_ms": pct(v, .95),
                        "first_token_p50_ms": pct(ft, .5)})
        return out
