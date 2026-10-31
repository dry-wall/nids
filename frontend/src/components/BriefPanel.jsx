import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ExternalLink } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../state.jsx";
import { Button, Dot, Tag, Tile } from "./ui.jsx";
import { FAMILY_COLORS, familyOf, fmtMs } from "../lib/format.js";

const FAMILIES = ["DoS", "DDoS", "PortScan", "Brute Force", "Web Attack", "Bot", "Infiltration"];

const writer = (m) => (!m ? "" : m.provider === "playbook" ? "the offline playbook" : m.model || m.label);

/** Pull the summary out of a partially streamed JSON object so it can be shown while it is written. */
function partialSummary(raw) {
  const m = raw.match(/"summary"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (!m) return "";
  try { return JSON.parse(`"${m[1].replace(/\\$/, "")}"`); } catch { return m[1]; }
}

function Section({ title, children }) {
  return (
    <div className="border-t border-line pt-3">
      <h3 className="mb-1 text-[13px] font-semibold">{title}</h3>
      {children}
    </div>
  );
}

function Related({ family, deviations }) {
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(null);
  useEffect(() => {
    if (!family || family === "Unknown") { setRes(null); return; }
    api.kbRelated(family, deviations.slice(0, 2).map((d) => d.feature).join(" ")).then(setRes).catch(() => setRes(null));
  }, [family]); // eslint-disable-line
  if (!res?.results?.length) return null;
  return (
    <Tile title="Related reading" sub="MITRE ATT&CK and NIST SP 800-61, for reference. Not used to write the draft." >
      <ul>
        {res.results.map((c) => (
          <li key={c.chunk_id} className="border-t border-line first:border-0">
            <button onClick={() => setOpen(open === c.chunk_id ? null : c.chunk_id)} className="flex w-full items-center gap-2.5 py-2 text-left">
              <Dot color={c.source.startsWith("MITRE") ? "var(--color-red)" : "var(--color-blue)"} />
              <span className="min-w-0 flex-1 truncate text-[13px]">{c.title}</span>
              <span className="text-[12px] text-faint">{c.source.startsWith("MITRE") ? "ATT&CK" : "NIST"}</span>
            </button>
            {open === c.chunk_id && (
              <div className="pb-3 text-[13px] leading-relaxed text-muted">
                {c.text}
                {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="mt-1.5 flex items-center gap-1 hover:underline">Open source <ExternalLink size={11} /></a>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Tile>
  );
}

export default function BriefPanel({ rec, analysisId, onDecided, historyNode }) {
  const { analyst, setAnalyst } = useApp();
  const latest = rec.history.briefs[0];
  const [hint, setHint] = useState("");
  const [phase, setPhase] = useState(latest ? "done" : "idle");
  const [raw, setRaw] = useState("");
  const [provider, setProvider] = useState(null);
  const [brief, setBrief] = useState(latest?.brief ?? null);
  const [meta, setMeta] = useState(latest ? { provider: latest.provider, model: latest.model, latency_ms: latest.latency_ms, fallback_reasons: latest.fallback_reasons } : null);
  const [briefId, setBriefId] = useState(latest?.id ?? null);
  const [elapsed, setElapsed] = useState(0);
  const [err, setErr] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [name, setName] = useState(analyst);           // local, so the buttons enable as soon as a name is typed
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(null);
  const [saved, setSaved] = useState(null);
  const [prompt, setPrompt] = useState(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const abortRef = useRef(null);
  const t0 = useRef(0);

  useEffect(() => () => abortRef.current?.(), []);
  useEffect(() => setName(analyst), [analyst]);
  useEffect(() => {
    if (phase !== "writing") return;
    const t = setInterval(() => setElapsed(performance.now() - t0.current), 100);
    return () => clearInterval(t);
  }, [phase]);

  const generate = (offline = false) => {
    abortRef.current?.();
    setPhase("writing"); setRaw(""); setErr(null); setEditing(false); setPrompt(null); setShowPrompt(false); setSaved(null);
    setProvider(offline ? { provider: "playbook" } : null);
    t0.current = performance.now(); setElapsed(0);
    abortRef.current = api.streamBrief(analysisId, rec.record, { family_hint: hint || null, playbook_only: offline },
      (ev) => {
        if (ev.type === "provider") { setProvider(ev); setRaw(""); }
        else if (ev.type === "token") setRaw((s) => s + ev.text);
        else if (ev.type === "done") { setBrief(ev.brief); setMeta(ev.meta); setBriefId(ev.brief_id); setPrompt(ev.meta.prompt); setPhase("done"); }
      },
      (e) => { setErr(e.message); setPhase(brief ? "done" : "idle"); });
  };

  const decide = async (status) => {
    const who = name.trim();
    if (!who) return;
    setSaving(status); setErr(null);
    try {
      const final = editing ? draft : brief;
      await api.decide({ analysis_id: analysisId, record_id: rec.record, brief_id: briefId, status, analyst: who, notes, final_brief: final, edited: editing });
      setAnalyst(who);
      if (editing) setBrief(draft);
      setEditing(false); setNotes(""); setSaved(status);
      onDecided?.();
    } catch (e) { setErr(e.message); } finally { setSaving(null); }
  };

  const togglePrompt = async () => {
    if (!prompt && briefId) { try { setPrompt((await api.brief(briefId)).prompt); } catch {} }
    setShowPrompt((s) => !s);
  };

  const view = editing ? draft : brief;
  const fam = view?.hypothesis?.family;
  const label = familyOf(rec.ground_truth);
  const set = (k, v) => setDraft({ ...draft, [k]: v });
  const done = phase === "done" && view;

  return (
    <>
      <Tile title="Advisory" sub="Drafted from this flow's score and five largest deviations. You make the call." className="md:col-span-12"
        aside={<>
          <select value={hint} onChange={(e) => setHint(e.target.value)} disabled={phase === "writing"} className="select !py-1 text-[12.5px]" aria-label="Attack type to consider">
            <option value="">Any attack type</option>
            {FAMILIES.map((f) => <option key={f} value={f}>Consider {f}</option>)}
          </select>
          {phase === "writing"
            ? <Button size="sm" variant="raised" onClick={() => { abortRef.current?.(); setPhase(brief ? "done" : "idle"); }}>Stop</Button>
            : <Button size="sm" variant="primary" onClick={() => generate(false)}>{brief ? "Write again" : "Write draft"}</Button>}
        </>}>

        {phase === "idle" && !brief && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-raised px-4 py-3.5">
            <p className="max-w-xl text-[13.5px] text-muted">A language model on this machine writes the draft from the score and the deviations only. It is told not to invent addresses, CVEs or malware names.</p>
            <Button size="sm" variant="raised" onClick={() => generate(true)}>Use offline playbook</Button>
          </div>
        )}

        {err && <div className="mb-2 text-[13.5px] text-red">{err}</div>}

        {phase === "writing" && (
          <div className="rounded-xl bg-raised px-4 py-3.5">
            <div className="flex justify-between text-[12.5px] text-muted">
              <span>{provider ? `Writing with ${writer(provider) || provider.label}` : "Starting"}</span>
              <span className="num">{(elapsed / 1000).toFixed(1)} s</span>
            </div>
            <div className="progress-line mt-2" />
            <p className="mt-3 min-h-[2.8em] text-[15px] leading-relaxed">{partialSummary(raw)}</p>
          </div>
        )}

        {done && (
          <>
            {meta?.provider === "playbook" && meta?.fallback_reasons?.length > 0 && (
              <div className="mb-3 rounded-lg bg-orange-soft px-3 py-2 text-[13px] text-orange">The local model was unavailable, so the offline playbook wrote this draft.</div>
            )}
            {editing
              ? <textarea className="input min-h-[70px] text-[15px]" value={draft.summary} onChange={(e) => set("summary", e.target.value)} />
              : <p className="text-[16px] leading-relaxed">{view.summary}</p>}
            <div className="mt-3 grid gap-x-8 gap-y-3 md:grid-cols-2">
              <div className="space-y-3">
                <Section title="Likely attack type">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Tag><Dot color={FAMILY_COLORS[fam]} className="!h-1.5 !w-1.5" />{fam === "Unknown" ? "Not clear from this flow" : fam}</Tag>
                    {view.hypothesis.technique_ids.map((t) => <a key={t} href={`https://attack.mitre.org/techniques/${t}/`} target="_blank" rel="noreferrer" className="text-[13px] hover:underline">{t}</a>)}
                    {label && label !== "Benign" && fam !== "Unknown" && <span className="text-[12px] text-faint">{label === fam ? "matches the file label" : `file label says ${label}`}</span>}
                    {label === "Benign" && <Tag tone="orange">file label says benign</Tag>}
                  </div>
                  {view.hypothesis.reasoning && <p className="mt-1.5 text-[13px] text-muted">{view.hypothesis.reasoning}</p>}
                </Section>
                <Section title="Possible impact">
                  {editing ? <textarea className="input min-h-[60px]" value={draft.impact} onChange={(e) => set("impact", e.target.value)} /> : <p className="text-[13.5px] leading-relaxed">{view.impact}</p>}
                </Section>
                <Section title="What to verify">
                  {editing ? <textarea className="input min-h-[60px]" value={draft.limitations} onChange={(e) => set("limitations", e.target.value)} /> : <p className="text-[13.5px] leading-relaxed text-muted">{view.limitations}</p>}
                </Section>
              </div>
              <Section title="Steps to take">
                <ol className="space-y-1.5">
                  {view.actions.map((a, i) => (
                    <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed">
                      <span className="num w-4 shrink-0 text-right text-faint">{i + 1}.</span>
                      {editing ? (
                        <span className="flex flex-1 gap-2">
                          <input className="input !py-1" value={a.step} onChange={(e) => { const x = [...draft.actions]; x[i] = { ...x[i], step: e.target.value }; set("actions", x); }} />
                          <button className="text-[12.5px] text-red" onClick={() => set("actions", draft.actions.filter((_, j) => j !== i))}>Remove</button>
                        </span>
                      ) : <span>{a.step}</span>}
                    </li>
                  ))}
                </ol>
                {editing && <button className="mt-2 text-[13px] text-link hover:underline" onClick={() => set("actions", [...draft.actions, { step: "", citations: [] }])}>Add a step</button>}
              </Section>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-2.5 text-[12.5px] text-muted">
              <span>Written by {writer(meta)}{meta?.latency_ms != null && ` in ${fmtMs(meta.latency_ms)}`}.</span>
              <button onClick={togglePrompt} className="text-link hover:underline">{showPrompt ? "Hide prompt" : "Show prompt"}</button>
              <button onClick={() => generate(true)} className="text-link hover:underline">Use offline playbook</button>
            </div>
            {showPrompt && prompt && <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-raised p-4 font-mono text-[11.5px] leading-relaxed text-muted">{prompt}</pre>}
          </>
        )}
      </Tile>

      {done && (
        <section className="tile flex flex-wrap items-center gap-2 p-3 md:col-span-12">
          <span className="px-2 text-[14px] font-semibold">Your decision</span>
          <input className="input !w-40 !py-[5px] text-[13px]" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Your name" />
          <input className="input !py-[5px] text-[13px] sm:!w-auto sm:flex-1" placeholder="Note (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Note" />
          {editing
            ? <Button size="sm" variant="plain" onClick={() => setEditing(false)}>Discard edits</Button>
            : <Button size="sm" variant="plain" onClick={() => { setDraft(JSON.parse(JSON.stringify(brief))); setEditing(true); setSaved(null); }}>Edit draft</Button>}
          <Button size="sm" variant="reject" loading={saving === "rejected"} disabled={!name.trim()} onClick={() => decide("rejected")}>Reject</Button>
          <Button size="sm" variant="approve" loading={saving === "approved"} disabled={!name.trim()} onClick={() => decide("approved")}>{editing ? "Approve edited" : "Approve"}</Button>
          {saved && <span className={clsx("w-full px-2 text-[12.5px]", saved === "approved" ? "text-green" : "text-red")}>{saved === "approved" ? "Approved" : "Rejected"} by {analyst}. Saved to the audit log.</span>}
        </section>
      )}

      <div className="grid gap-3 empty:hidden md:col-span-12 md:auto-cols-fr md:grid-flow-col">
        {done && <Related family={hint || fam} deviations={rec.deviations} />}
        {historyNode}
      </div>
    </>
  );
}
