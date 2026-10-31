"""Ingest NIST SP 800-61 Rev. 3 (April 2025).

Sections 1-2 are prose and are split by numbered heading. Section 3 is the CSF 2.0 Community
Profile table; it is split per CSF element (e.g. "RS.MI-02") so each recommendation is retrievable.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

from src.kb.chunk import chunk

SOURCE = "NIST SP 800-61 Rev. 3"
URL = "https://doi.org/10.6028/NIST.SP.800-61r3"
FIRST_PAGE, LAST_PAGE = 9, 42           # body text; references and glossary are excluded
FUNCTIONS = {"GV": "Govern", "ID": "Identify", "PR": "Protect", "DE": "Detect", "RS": "Respond", "RC": "Recover"}
HEADER = re.compile(r"^(NIST SP 800-61r3|April 2025|CSF Element CSF Element Description|\d{1,3}$)")
HEADING = re.compile(r"^(\d)(?:\.(\d))?\.\s+([A-Z][A-Za-z0-9 ,.\-]+)$")
CSF_ID = re.compile(r"^([A-Z]{2}\.[A-Z]{2}(?:-\d{2})?)\b(.*)$")


def _lines(path: Path) -> list[str]:
    reader = PdfReader(str(path))
    out = []
    for i in range(FIRST_PAGE, LAST_PAGE + 1):
        for raw in reader.pages[i].extract_text().split("\n"):
            line = raw.replace("�", "'").replace("’", "'").strip()
            if line and not HEADER.match(line):
                out.append(line)
    return out


def ingest(path: Path) -> tuple[list[dict], dict]:
    blocks, cur = [], None
    section = "1"
    for line in _lines(path):
        h = HEADING.match(line)
        if h and len(line) < 90:
            section = h.group(1) + (f".{h.group(2)}" if h.group(2) else "")
            cur = {"section": section, "title": h.group(3).strip(), "csf": None, "lines": []}
            blocks.append(cur)
            continue
        m = CSF_ID.match(line) if section.startswith("3") else None
        if m and m.group(1)[:2] in FUNCTIONS:
            cur = {"section": section, "title": m.group(2).strip(" ()") or m.group(1), "csf": m.group(1),
                   "lines": [m.group(2).strip()]}
            blocks.append(cur)
            continue
        if cur is None:
            cur = {"section": section, "title": "Introduction", "csf": None, "lines": []}
            blocks.append(cur)
        cur["lines"].append(line)

    chunks = []
    for b in blocks:
        text = " ".join(b["lines"]).strip()
        if len(text.split()) < 8:
            continue
        if b["csf"]:
            fn = FUNCTIONS[b["csf"][:2]]
            title = f"{b['csf']} ({fn}) {' '.join(text.split()[:10])}"
            base = f"nist-800-61r3:{b['section']}:{b['csf']}"
            sec = f"{b['section']} {b['csf']}"
        else:
            title = f"§{b['section']} {b['title']}"
            base = f"nist-800-61r3:{b['section']}"
            sec = b["section"]
        chunks += chunk(text, base, {"source": SOURCE, "technique_id": None, "title": title, "section": sec,
                                     "doc_type": "csf-element" if b["csf"] else "guidance", "tactics": [],
                                     "url": URL, "csf_function": FUNCTIONS.get((b["csf"] or "")[:2])})
    # chunk IDs must be unique even if a CSF element ID appears twice
    seen = Counter()
    for c in chunks:
        cid = c["chunk_id"]
        if seen[cid]:
            c["chunk_id"] = f"{cid}~{seen[cid]}"
        seen[cid] += 1
    return chunks, {"pages": f"{FIRST_PAGE + 1}-{LAST_PAGE + 1}"}
