"""Word-window chunking with metadata and stable IDs (source:section:index)."""
from __future__ import annotations

import re

CHUNK_WORDS, OVERLAP_WORDS = 300, 50


def clean_text(s: str) -> str:
    s = re.sub(r"\(Citation:[^)]*\)", "", s or "")          # ATT&CK inline citations
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", s)  # markdown links -> text
    s = re.sub(r"<code>|</code>", "", s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", s)).strip()


def chunk(text: str, base_id: str, meta: dict) -> list[dict]:
    words = clean_text(text).split()
    if not words:
        return []
    out, start, i = [], 0, 0
    while True:
        piece = words[start:start + CHUNK_WORDS]
        out.append({"chunk_id": f"{base_id}:{i}", "text": " ".join(piece), "n_words": len(piece), **meta})
        if start + CHUNK_WORDS >= len(words):
            return out
        start += CHUNK_WORDS - OVERLAP_WORDS
        i += 1
