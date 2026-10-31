"""Ingest MITRE ATT&CK Enterprise (STIX 2.1 bundle from github.com/mitre/cti).

One document per technique description, per technique detection note (when present) and per
technique-specific mitigation relationship. Revoked and deprecated objects are skipped.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.kb.chunk import chunk

SOURCE = "MITRE ATT&CK Enterprise"


def _ext(obj):
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id"), ref.get("url")
    return None, None


def ingest(path: Path) -> tuple[list[dict], dict]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    objs = bundle["objects"]
    live = [o for o in objs if not o.get("revoked") and not o.get("x_mitre_deprecated")]
    by_id = {o["id"]: o for o in live}
    version = next((o.get("x_mitre_version") for o in objs if o.get("type") == "x-mitre-collection"), None)

    chunks, techniques = [], {}
    for o in live:
        if o.get("type") != "attack-pattern":
            continue
        tid, url = _ext(o)
        if not tid:
            continue
        tactics = [p["phase_name"] for p in o.get("kill_chain_phases", [])]
        techniques[tid] = {"id": tid, "name": o["name"], "tactics": tactics, "url": url,
                           "stix_id": o["id"], "is_sub": bool(o.get("x_mitre_is_subtechnique"))}
        meta = {"source": SOURCE, "technique_id": tid, "title": f"{tid} {o['name']}",
                "tactics": tactics, "url": url}
        chunks += chunk(o.get("description", ""), f"attack:{tid}:description",
                        {**meta, "section": "description", "doc_type": "technique"})
        if o.get("x_mitre_detection"):
            chunks += chunk(o["x_mitre_detection"], f"attack:{tid}:detection",
                            {**meta, "section": "detection", "doc_type": "detection"})

    stix_to_tid = {v["stix_id"]: k for k, v in techniques.items()}
    for r in live:
        if r.get("type") != "relationship" or r.get("relationship_type") != "mitigates":
            continue
        tid, coa = stix_to_tid.get(r.get("target_ref")), by_id.get(r.get("source_ref"))
        if not tid or not coa or not r.get("description"):
            continue
        mid, murl = _ext(coa)
        t = techniques[tid]
        chunks += chunk(f"{coa['name']}: {r['description']}", f"attack:{tid}:mitigation-{mid}",
                        {"source": SOURCE, "technique_id": tid, "title": f"{tid} {t['name']} - mitigation {mid} {coa['name']}",
                         "tactics": t["tactics"], "url": murl or t["url"], "section": f"mitigation {mid}",
                         "doc_type": "mitigation"})
    return chunks, {"version": version, "techniques": len(techniques)}
