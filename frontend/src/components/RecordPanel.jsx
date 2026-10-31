import { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "../api.js";
import BriefPanel from "./BriefPanel.jsx";
import { Dot, Tag, Tile } from "./ui.jsx";
import { BAND, FAMILY_COLORS, FEATURE_UNITS, MODEL_COLORS, MODEL_LABEL, familyOf, fmtNum, fmtScore, timeAgo } from "../lib/format.js";

function Deviation({ d, max }) {
  const w = Math.min(50, (50 * Math.abs(d.z)) / max);
  const unit = FEATURE_UNITS[d.feature];
  const up = d.z > 0;
  return (
    <div className="grid grid-cols-[minmax(0,1.2fr)_minmax(90px,1fr)_46px] items-center gap-3 border-t border-line py-2 first:border-0">
      <div className="min-w-0">
        <div className="truncate text-[13.5px]">{d.feature}</div>
        <div className="num truncate text-[12px] text-muted">{fmtNum(d.value)}{unit && ` ${unit}`}, normally {fmtNum(d.benign_median)}</div>
      </div>
      <div className="relative h-3">
        <div className="absolute inset-y-0 left-1/2 w-px bg-line" />
        <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full" style={{ background: up ? "var(--color-red)" : "var(--color-blue)", ...(up ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }) }} />
      </div>
      <div className="num text-right text-[13px] font-medium" style={{ color: up ? "var(--color-red)" : "var(--color-blue)" }}>{up ? "+" : "−"}{Math.abs(d.z).toFixed(1)}σ</div>
    </div>
  );
}

export default function RecordPanel({ analysisId, record, onDecided }) {
  const [rec, setRec] = useState(null);
  const [err, setErr] = useState(null);
  const [all, setAll] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setErr(null);
    api.record(analysisId, record).then(setRec).catch(setErr);
  }, [analysisId, record, tick]);

  if (err) return <div className="tile p-5 text-red">{err.message}</div>;
  if (!rec) return <div className="grid gap-3"><div className="tile h-32 animate-pulse" /><div className="tile h-64 animate-pulse" /></div>;

  const maxZ = Math.max(...rec.deviations.map((d) => Math.abs(d.z)), 3);
  const fam = familyOf(rec.ground_truth);
  const history = [
    ...rec.history.decisions.map((d) => ({ ...d, kind: "decision" })),
    ...rec.history.briefs.map((b) => ({ ...b, kind: "brief" })),
  ].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

  return (
    <div className="appear grid gap-3 md:grid-cols-12">
      <section className="tile grid gap-5 p-5 md:col-span-12 md:grid-cols-[1fr_1.3fr]">
        <div>
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="num text-[24px] font-semibold tracking-[-0.02em]">Record {rec.record}</h2>
            <div className="num text-[28px] font-semibold leading-none tracking-[-0.02em]" style={{ color: rec.flagged ? "var(--color-red)" : undefined }}>{fmtScore(rec.score)}</div>
          </div>
          <div className="num mt-0.5 text-right text-[12px] text-muted">score, threshold {rec.threshold.toFixed(3)}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {rec.flagged ? <Tag tone={rec.band === "strong" ? "red" : rec.band === "moderate" ? "orange" : "gray"}>Flagged, {BAND[rec.band].label.toLowerCase()} margin</Tag> : <Tag tone="green">Not flagged</Tag>}
            {rec.ground_truth && <Tag title="From the uploaded file. Never used by the model."><Dot color={FAMILY_COLORS[fam]} className="!h-1.5 !w-1.5" />File label {rec.ground_truth}</Tag>}
          </div>
        </div>
        <div>
          <div className="mb-2 text-[12.5px] text-muted">What each model says</div>
          <div className="space-y-2">
            {rec.models.map((m) => (
              <div key={m.key} className="grid grid-cols-[150px_1fr_52px_56px] items-center gap-2.5 text-[13px]">
                <span className={clsx("flex items-center gap-1.5", !m.active && "text-muted")}><Dot color={MODEL_COLORS[m.key]} />{MODEL_LABEL[m.key]}</span>
                <div className="relative h-1.5 rounded-full bg-hair">
                  <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(1, m.score * 100)}%`, background: MODEL_COLORS[m.key] }} />
                  <div className="absolute -top-1 h-3.5 w-px bg-ink" style={{ left: `${m.threshold * 100}%` }} title={`Threshold ${m.threshold.toFixed(3)}`} />
                </div>
                <span className="num text-right">{fmtScore(m.score)}</span>
                <span className={clsx("text-right text-[12px]", m.flagged ? "text-red" : "text-green")}>{m.flagged ? "Flagged" : "Passed"}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Tile title="Why it was flagged" sub="Distance from normal traffic. Red is higher than usual, blue is lower." className="md:col-span-12"
        aside={<button onClick={() => setAll((s) => !s)} className="text-[13px] text-link hover:underline">{all ? "Top five" : "All 12 features"}</button>}>
        <div className={clsx(all && "md:columns-2 md:gap-8")}>
          {(all ? [...rec.features].sort((a, b) => Math.abs(b.z) - Math.abs(a.z)) : rec.deviations).map((d) => (
            <div key={d.feature} className="break-inside-avoid"><Deviation d={d} max={maxZ} /></div>
          ))}
        </div>
      </Tile>

      <BriefPanel rec={rec} analysisId={analysisId} onDecided={() => { setTick((t) => t + 1); onDecided?.(); }}
        historyNode={history.length > 0 && (
          <Tile title="History">
            <ol>
              {history.map((e) => (
                <li key={e.kind + e.id} className="flex items-start gap-2.5 border-t border-line py-2 text-[13px] first:border-0">
                  <Dot className="mt-[6px]" color={e.kind === "brief" ? "var(--color-blue)" : e.status === "approved" ? "var(--color-green)" : "var(--color-red)"} />
                  <span className="flex-1">
                    {e.kind === "brief"
                      ? <>Draft by {e.provider === "playbook" ? "the offline playbook" : e.model}, {(e.latency_ms / 1000).toFixed(1)} s</>
                      : <>{e.status === "approved" ? "Approved" : "Rejected"} by {e.analyst}{e.edited ? " after editing" : ""}{e.notes && <span className="text-muted">: {e.notes}</span>}</>}
                  </span>
                  <span className="shrink-0 text-[12px] text-faint">{timeAgo(e.created_at)}</span>
                </li>
              ))}
            </ol>
          </Tile>
        )} />
    </div>
  );
}
