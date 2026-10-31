"""Fixed-section prompt. Only the detector's own facts go in; the model is told not to invent any."""

SYSTEM = """You are a SOC analysis assistant that drafts short incident briefs for a human analyst.
You never decide or take action; the analyst approves or rejects your draft.
Respond ONLY with a JSON object matching the given schema. Be concise and specific."""

USER = """A binary machine-learning network intrusion detector flagged one network flow.

FACTS (the only facts you may use):
- Record: {record_id}
- Detector: {model_name}; output score {score:.4f} (uncalibrated; decision threshold {threshold:.4f})
- The detector is binary (benign vs attack). It does NOT name the attack type.
- Top-5 features furthest from the benign baseline (z = standard deviations from benign mean):
{deviations}
{analyst_hint}
Write the brief:
- "summary": 1-2 plain sentences on what this traffic did, citing the most unusual values. Do not mention
  the detector, machine learning, models or scores, and do not start with "A" or "This flow was flagged".
- "hypothesis.family": the attack family most consistent with these deviations, chosen from the enum.
  Use "Unknown" if the evidence does not clearly point to one family. This is a hypothesis, not a classification.
- "hypothesis.technique_ids": only for the chosen family, from the allowed list; else empty.
- "hypothesis.reasoning": one sentence linking specific deviations above to the family.
- "hypothesis.confidence_note": state that the score is uncalibrated and the family is a hypothesis.
- "impact": what could happen if this is real (possible impact, not observed fact).
- "actions": 3-6 concrete defensive investigation or containment steps, imperative voice. Tie at least
  two steps to the specific deviating features above (e.g. what to check given an unusual packet size).
- "limitations": what is unknown and what the analyst should verify.

RULES: Do not invent IP addresses, hostnames, users, ports, CVEs, malware names or tools.
Do not claim certainty. Defensive guidance only. Under 220 words in total."""

FEATURE_HINTS = {
    "Flow Duration": "microseconds",
    "Flow Bytes/s": "bytes per second",
    "Flow Packets/s": "packets per second",
}


def format_deviations(devs: list[dict]) -> str:
    lines = []
    for d in devs:
        unit = FEATURE_HINTS.get(d["feature"])
        value = f"{d['value']} {unit}" if unit else f"{d['value']}"
        lines.append(f"  * {d['feature']}: {value} (z = {d['z']:+.1f}, {d['direction']} benign; "
                     f"benign median {d.get('benign_median')})")
    return "\n".join(lines)


def build_prompt(facts: dict, family_hint: str | None = None) -> str:
    hint = ""
    if family_hint and family_hint != "Unknown":
        hint = f"- Analyst note: the analyst asked you to evaluate the hypothesis '{family_hint}'.\n"
    return USER.format(record_id=facts["record_id"], model_name=facts["model_name"],
                       score=facts["score"], threshold=facts["threshold"],
                       deviations=format_deviations(facts["deviations"]), analyst_hint=hint)
