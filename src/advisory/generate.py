"""P1.7 - brief generation: LLM chain with JSON validation, one retry, then the local playbook.

generate_stream(facts) yields events:
  {"type": "provider", "provider": ..., "label": ...}     a provider attempt starts
  {"type": "token", "text": ...}                          streamed raw model output
  {"type": "retry" | "fallback", "reason": ...}
  {"type": "done", "brief": {...}, "meta": {...}}         always the last event
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

from pydantic import ValidationError

from src.advisory.prompts import build_prompt
from src.advisory.providers import ProviderError, configured_chain
from src.advisory.schema import TECHNIQUES_OF_FAMILY, Brief

PLAYBOOKS = json.loads((Path(__file__).parent / "playbooks" / "playbooks.json").read_text())


def _brief_from_llm(raw: str, facts: dict) -> Brief:
    data = json.loads(raw)
    hyp = data.get("hypothesis", {})
    fam = hyp.get("family", "Unknown")
    # keep only technique IDs that belong to the hypothesised family (A.3 mapping)
    hyp["technique_ids"] = [t for t in hyp.get("technique_ids", []) if t in TECHNIQUES_OF_FAMILY.get(fam, [])]
    return Brief(
        record_id=str(facts["record_id"]),
        summary=data["summary"],
        why_flagged=[{"feature": d["feature"], "value": d["value"], "z": d["z"]} for d in facts["deviations"]],
        hypothesis=hyp,
        impact=data["impact"],
        actions=[{"step": a if isinstance(a, str) else a.get("step", ""), "citations": []}
                 for a in data["actions"] if a],
        limitations=data["limitations"],
    )


def playbook_brief(facts: dict, family: str | None) -> Brief:
    fam = family if family in PLAYBOOKS else "Unknown"
    pb = PLAYBOOKS[fam]
    top = ", ".join(f"{d['feature']} (z {d['z']:+.1f})" for d in facts["deviations"][:3])
    return Brief(
        record_id=str(facts["record_id"]),
        summary=f"{pb['summary']} Strongest deviations from benign traffic: {top}.",
        why_flagged=[{"feature": d["feature"], "value": d["value"], "z": d["z"]} for d in facts["deviations"]],
        hypothesis={
            "family": fam, "technique_ids": pb["technique_ids"],
            "reasoning": ("Family chosen by the analyst for the local playbook." if family and family != "Unknown"
                          else "No family selected; the generic triage playbook is used."),
            "confidence_note": (f"Detector score {facts['score']:.4f} is uncalibrated; the family is a "
                                f"hypothesis, not a classifier output."),
        },
        impact=pb["impact"],
        actions=[{"step": s, "citations": []} for s in pb["actions"]],
        limitations=("Generated offline from a fixed local playbook, not tailored by a language model. "
                     "The detector is binary and does not identify the attack family; verify against "
                     "host and network logs before acting."),
    )


def generate_stream(facts: dict, family_hint: str | None = None,
                    providers: list | None = None) -> Iterator[dict]:
    prompt = build_prompt(facts, family_hint)
    t0 = time.perf_counter()
    attempts, reasons = [], []
    for prov in (configured_chain() if providers is None else providers):
        st = prov.status()
        if not st["available"]:
            reasons.append(f"{prov.name}: {st['detail']}")
            continue
        for attempt in (1, 2):  # reject-and-retry once on invalid JSON, then move on
            yield {"type": "provider", "provider": prov.name, "label": prov.label,
                   "model": getattr(prov, "model", None), "attempt": attempt}
            buf, t_first = [], None
            try:
                for chunk in prov.stream(prompt):
                    if t_first is None:
                        t_first = time.perf_counter()
                    buf.append(chunk)
                    yield {"type": "token", "text": chunk}
                raw = "".join(buf)
                brief = _brief_from_llm(raw, facts)
                attempts.append({"provider": prov.name, "attempt": attempt, "ok": True})
                yield _done(brief, prov.name, prov.label, getattr(prov, "model", None), prompt, raw, t0,
                            t_first, attempts, reasons)
                return
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
                attempts.append({"provider": prov.name, "attempt": attempt, "ok": False,
                                 "error": f"invalid output: {type(e).__name__}"})
                if attempt == 1:
                    yield {"type": "retry", "reason": "output did not match the brief schema"}
                    continue
                reasons.append(f"{prov.name}: invalid output twice")
            except ProviderError as e:
                attempts.append({"provider": prov.name, "attempt": attempt, "ok": False, "error": str(e)})
                reasons.append(str(e))
                break
        yield {"type": "fallback", "reason": "; ".join(reasons) or "no provider available"}
    brief = playbook_brief(facts, family_hint)
    yield _done(brief, "playbook", "Local playbook", None, prompt, None, t0, None, attempts, reasons)


def _done(brief, provider, label, model, prompt, raw, t0, t_first, attempts, reasons) -> dict:
    now = time.perf_counter()
    return {"type": "done", "brief": brief.model_dump(), "meta": {
        "provider": provider, "label": label, "model": model,
        "latency_ms": round((now - t0) * 1000), "first_token_ms": round((t_first - t0) * 1000) if t_first else None,
        "attempts": attempts, "fallback_reasons": reasons, "prompt": prompt, "raw_response": raw,
    }}


def generate(facts: dict, family_hint: str | None = None, providers: list | None = None) -> dict:
    """Blocking convenience wrapper; returns the final 'done' event."""
    ev = None
    for ev in generate_stream(facts, family_hint, providers):
        pass
    return ev
