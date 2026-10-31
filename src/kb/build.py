"""P1.8 - build the knowledge base: ingest ATT&CK + NIST, chunk, index (TF-IDF), evaluate retrieval.

Usage: python -m src.kb.build
Needs: data/raw/kb/enterprise-attack.json and data/raw/kb/NIST.SP.800-61r3.pdf (python run.py fetch-kb)
"""
import json
from collections import Counter

from src.config import KB_DIR, ROOT
from src.kb import ingest_attack, ingest_nist
from src.kb.index import TfidfIndex

RAW = ROOT / "data" / "raw" / "kb"


def main():
    a_chunks, a_info = ingest_attack.ingest(RAW / "enterprise-attack.json")
    n_chunks, n_info = ingest_nist.ingest(RAW / "NIST.SP.800-61r3.pdf")
    chunks = a_chunks + n_chunks
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "chunk IDs must be unique"
    idx = TfidfIndex(chunks).build()
    idx.save(KB_DIR)
    stats = {
        "chunks": len(chunks),
        "by_source": dict(Counter(c["source"] for c in chunks)),
        "by_doc_type": dict(Counter(c["doc_type"] for c in chunks)),
        "attack": a_info, "nist": n_info,
        "vocabulary": len(idx.vectorizer.vocabulary_),
        "chunking": "300-word windows, 50-word overlap; IDs source:section:index",
    }
    (KB_DIR / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))

    from src.eval.retrieval import evaluate
    evaluate(idx)


if __name__ == "__main__":
    main()
