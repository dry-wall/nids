import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { Area, AreaChart, Bar as RBar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BadgeCheck, Microscope, ScanSearch, Sparkles } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../state.jsx";
import { Bar, Button, ChartTip, Dot, Page, Segmented, Stat, Tag, Tile } from "../components/ui.jsx";
import { BAND, FAMILY_COLORS, MODEL_COLORS, MODEL_LABEL, fmtInt, fmtLogitTick, fmtMs, fmtPct, timeAgo } from "../lib/format.js";

const SHORT = { lr: "Logistic", rf: "Forest", dnn: "Neural net" };

export function useMetrics() {
  const [m, setM] = useState(null);
  useEffect(() => { api.metrics().then(setM).catch(() => {}); }, []);
  return m;
}

function Composition({ families, total }) {
  const entries = Object.entries(families).sort((a, b) => (a[0] === "Benign" ? 1 : b[0] === "Benign" ? -1 : b[1] - a[1]));
  return (
    <div className="mt-3 flex h-2 w-full gap-px overflow-hidden rounded-full">
      {entries.map(([f, n]) => <div key={f} title={`${f}: ${fmtInt(n)}`} style={{ width: `${(100 * n) / total}%`, background: FAMILY_COLORS[f] || "var(--color-faint)" }} />)}
    </div>
  );
}

const STEPS = [
  [ScanSearch, "var(--color-blue)", "Score", "Each flow gets a score from the selected model."],
  [Microscope, "var(--color-orange)", "Explain", "Alerts list the five features furthest from normal."],
  [Sparkles, "var(--color-purple)", "Draft", "A local language model writes a short advisory."],
  [BadgeCheck, "var(--color-green)", "Decide", "You approve or reject. Everything is logged."],
];

function Launcher({ onDone }) {
  const { model, setModel, health } = useApp();
  const metrics = useMetrics();
  const [samples, setSamples] = useState([]);
  const [recent, setRecent] = useState([]);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef();

  useEffect(() => {
    api.samples().then(setSamples).catch(() => {});
    api.audit(6).then((a) => setRecent(a.analyses)).catch(() => {});
  }, []);

  const run = async (label, fn) => {
    setBusy(label); setErr(null);
    try { onDone(await fn()); } catch (e) { setErr(e); } finally { setBusy(null); }
  };
  const onFile = (f) => f && run(f.name, () => api.detectFile(f, model));
  const writer = health?.llm_chain?.find((c) => c.available && c.name !== "playbook");
  const lat = health?.brief_latency?.find((l) => l.provider !== "playbook");

  return (
    <Page title="Analyze" meta="Find suspicious flows, see why they stand out, and review a drafted advisory.">
      <div className="grid gap-3 lg:grid-cols-12">
        <section
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files?.[0]); }}
          className={clsx("tile flex flex-col p-7 transition-colors lg:col-span-8 lg:row-span-2", drag && "ring-2 ring-blue")}>
          <h2 className="text-[34px] font-semibold leading-[1.1] tracking-[-0.03em]">Analyze traffic.</h2>
          <p className="mt-2 max-w-xl text-[16px] text-muted">Drop a flow file exported by CICFlowMeter. Every flow is scored, flagged flows are explained, and you review the result.</p>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Segmented value={model} onChange={setModel}
              options={["lr", "rf", "dnn"].map((k) => ({ value: k, label: <><span className="sm:hidden">{SHORT[k]}</span><span className="hidden sm:inline">{MODEL_LABEL[k]}</span></> }))} />
            {metrics && <span className="num text-[12.5px] text-muted">F1 {metrics.models[model].summary.f1.mean.toFixed(3)}, {fmtPct(metrics.models[model].summary.fpr.mean, 2)} false alarms</span>}
          </div>
          <div className={clsx("mt-6 flex flex-1 flex-col items-start justify-center gap-4 rounded-[14px] border border-dashed px-6 py-8 sm:flex-row sm:items-center",
            drag ? "border-blue bg-blue-soft" : "border-line bg-raised")}>
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
            <div className="min-w-0 flex-1">
              <div className="text-[17px] font-semibold">{busy ? `Analyzing ${busy}` : "Drop a CSV file here"}</div>
              <div className="text-[13.5px] text-muted">Up to {health?.limits?.max_upload_mb ?? 300} MB. Column names with stray spaces are fine.</div>
              {busy && <div className="progress-line mt-3 max-w-sm" />}
            </div>
            <Button variant="primary" disabled={!!busy} onClick={() => fileRef.current?.click()}>Choose file</Button>
          </div>
          {err && (
            <div className="mt-3 text-[13.5px] text-red">
              {err.message}
              {err.detail?.missing && <div className="text-[12.5px] text-muted">Missing columns: {err.detail.missing.join(", ")}</div>}
            </div>
          )}
        </section>

        <Tile title="Detectors" sub="F1 on flows held out from training" className="lg:col-span-4">
          {metrics ? (
            <ul className="space-y-2.5">
              {["lr", "rf", "dnn"].map((k) => (
                <li key={k}>
                  <div className="flex items-center justify-between text-[13.5px]">
                    <span className="flex items-center gap-2"><Dot color={MODEL_COLORS[k]} />{MODEL_LABEL[k]}{k === model && <Tag tone="blue">selected</Tag>}</span>
                    <span className="num font-medium">{metrics.models[k].summary.f1.mean.toFixed(3)}</span>
                  </div>
                  <Bar className="mt-1" value={metrics.models[k].summary.f1.mean} color={MODEL_COLORS[k]} />
                </li>
              ))}
            </ul>
          ) : <div className="h-24" />}
        </Tile>

        <Tile title="Draft writer" sub="Runs on this machine, no internet needed" className="lg:col-span-4">
          <div className="flex items-center gap-2 text-[15px] font-medium">
            <Dot color={writer ? "var(--color-green)" : "var(--color-orange)"} />{writer ? writer.label.replace("Local · ", "") : "Offline playbook"}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div><div className="num text-[22px] font-semibold">{lat ? fmtMs(lat.p50_ms) : "≈5 s"}</div><div className="text-[12px] text-muted">typical draft</div></div>
            <div><div className="num text-[22px] font-semibold">{lat?.first_token_p50_ms ? fmtMs(lat.first_token_p50_ms) : "<1 s"}</div><div className="text-[12px] text-muted">to first words</div></div>
          </div>
          <div className="mt-3 text-[12.5px] text-muted">The offline playbook takes over if the model is unavailable.</div>
        </Tile>

        {samples.map((s) => {
          const total = Object.values(s.families).reduce((a, b) => a + b, 0);
          const attacks = Object.entries(s.families).filter(([f]) => f !== "Benign").sort((a, b) => b[1] - a[1]);
          return (
            <section key={s.name} className="tile flex flex-col p-5 lg:col-span-4">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-[16px] font-semibold">{s.title.split(" - ")[0]}</h3>
                <span className="num text-[12.5px] text-muted">{fmtInt(s.rows)} flows</span>
              </div>
              <p className="mt-1 flex-1 text-[13px] text-muted">{s.description}</p>
              <Composition families={s.families} total={total} />
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
                {attacks.slice(0, 4).map(([f, n]) => <span key={f} className="flex items-center gap-1"><Dot color={FAMILY_COLORS[f]} className="!h-1.5 !w-1.5" />{f} <span className="num text-faint">{fmtInt(n)}</span></span>)}
                {attacks.length > 4 && <span>+{attacks.length - 4} more</span>}
              </div>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-[12.5px] text-muted">{fmtPct(s.attacks / s.rows, 0)} labelled as attacks</span>
                <Button size="sm" variant="primary" loading={busy === s.name} disabled={!!busy} onClick={() => run(s.name, () => api.detectSample(s.name, model))}>Analyze</Button>
              </div>
            </section>
          );
        })}

        <Tile title="How it works" className="lg:col-span-8">
          <ol className="grid gap-4 sm:grid-cols-4">
            {STEPS.map(([Icon, color, t, d]) => (
              <li key={t}>
                <Icon size={22} strokeWidth={1.7} style={{ color }} />
                <div className="mt-2 font-semibold">{t}</div>
                <div className="text-[13px] text-muted">{d}</div>
              </li>
            ))}
          </ol>
        </Tile>

        <Tile title="Recent analyses" className="lg:col-span-4">
          {recent.length === 0 ? <p className="text-[13px] text-muted">Nothing yet. Pick a sample to start.</p> : (
            <ul>
              {recent.slice(0, 4).map((r) => (
                <li key={r.id} className="flex items-baseline justify-between gap-3 border-t border-line py-1.5 text-[13px] first:border-0">
                  <span className="min-w-0 truncate">{r.file_name}</span>
                  <span className="num shrink-0 text-muted"><span className="text-red">{fmtInt(r.flagged)}</span> flagged, {timeAgo(r.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Tile>
      </div>
    </Page>
  );
}

function ScoreChart({ hist }) {
  const { logit_edges: e, counts, threshold_logit: thr } = hist;
  const data = counts.map((c, i) => ({ x: (e[i] + e[i + 1]) / 2, c }));
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap={1}>
        <XAxis dataKey="x" type="number" domain={[-14, 14]} ticks={[-12, -6, 0, 6, 12]} tickFormatter={fmtLogitTick} axisLine={false} tickLine={false} />
        <YAxis scale="sqrt" axisLine={false} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
        <Tooltip cursor={{ fill: "var(--color-hover)" }} content={<ChartTip labelFmt={(l) => `Score ${(1 / (1 + Math.exp(-l))).toPrecision(4)}`} fmt={fmtInt} />} />
        <RBar isAnimationActive={false} dataKey="c" name="Flows" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={d.x >= thr ? "var(--color-red)" : "var(--color-chart-muted)"} />)}
        </RBar>
        <ReferenceLine x={thr} stroke="var(--color-ink)" strokeDasharray="3 3" />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TimelineChart({ data }) {
  const d = data.map((b) => ({ ...b, rate: b.total ? b.flagged / b.total : 0, label: `Records ${fmtInt(b.start)} to ${fmtInt(b.end)}` }));
  return (
    <ResponsiveContainer width="100%" height={290}>
      <AreaChart data={d} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tick={false} axisLine={false} />
        <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTip fmt={(v) => fmtPct(v)} />} />
        <Area isAnimationActive={false} type="monotone" dataKey="rate" name="Flagged" stroke="var(--color-red)" strokeWidth={1.6} fill="var(--color-red)" fillOpacity={0.1} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Results({ a, onReset }) {
  const nav = useNavigate();
  const t = a.timings;
  const gt = a.ground_truth;
  const maxFeat = Math.max(...a.top_features.map((f) => f.count), 1);
  const byLabel = gt ? gt.per_label.filter((r) => r.flagged > 0).sort((x, y) => y.flagged - x.flagged) : [];
  const maxLabel = Math.max(...byLabel.map((r) => r.flagged), 1);

  return (
    <Page title={a.file_name} meta={`${MODEL_LABEL[a.model]}, threshold ${a.threshold.toFixed(3)}, analyzed in ${fmtMs(t.total_ms)}`}
      actions={<>
        <Button size="sm" onClick={onReset}>New analysis</Button>
        <Button size="sm" variant="primary" onClick={() => nav("/alerts")}>Review {fmtInt(a.flagged)} alerts</Button>
      </>}>
      <div className="grid gap-3 lg:grid-cols-12">
        <Stat className="lg:col-span-3" label="Flows analyzed" value={fmtInt(a.total)} note={a.missing_values_imputed ? `${fmtInt(a.missing_values_imputed)} missing values filled in` : "No missing values"} />
        <Stat className="lg:col-span-3" label="Flagged" color="var(--color-red)" valueColor="var(--color-red)" value={fmtInt(a.flagged)} note={`${fmtPct(a.flag_rate)} of all flows`} />
        <Stat className="lg:col-span-3" label="Well above threshold" color={BAND.strong.color} value={fmtInt(a.bands.strong)} note={`${fmtInt(a.bands.moderate)} moderate, ${fmtInt(a.bands.marginal)} marginal`} />
        <Stat className="lg:col-span-3" label="Speed" color="var(--color-blue)" value={`${fmtInt(a.throughput_fps)}/s`} note={`Read ${fmtMs(t.parse_ms)}, scored ${fmtMs(t.inference_ms)}, explained ${fmtMs(t.explain_ms)}`} />

        <Tile title="Where alerts occur" sub="Share of flows flagged, in file order" className="lg:col-span-8"><TimelineChart data={a.timeline} /></Tile>
        <Tile title={gt ? "Flagged, by file label" : "Margin above threshold"} sub={gt ? "Labels are used for this view only" : undefined} className="lg:col-span-4">
          <ul className="space-y-2.5">
            {gt ? byLabel.slice(0, 8).map((r) => (
              <li key={r.label}>
                <div className="flex justify-between text-[13px]"><span className="flex items-center gap-2"><Dot color={FAMILY_COLORS[r.family]} />{r.label}</span><span className="num text-muted">{fmtInt(r.flagged)}</span></div>
                <Bar className="mt-1" value={r.flagged / maxLabel} color={FAMILY_COLORS[r.family]} />
              </li>
            )) : Object.entries(BAND).map(([k, b]) => (
              <li key={k}>
                <div className="flex justify-between text-[13px]"><span className="flex items-center gap-2"><Dot color={b.color} />{b.label}</span><span className="num text-muted">{fmtInt(a.bands[k])}</span></div>
                <Bar className="mt-1" value={a.flagged ? a.bands[k] / a.flagged : 0} color={b.color} />
              </li>
            ))}
          </ul>
        </Tile>

        <Tile title="Score distribution" sub="Red bars are above the threshold. Scores are not calibrated probabilities." className="lg:col-span-6"><ScoreChart hist={a.score_hist} /></Tile>
        <Tile title="What stands out" sub="How often each feature is among an alert's five largest deviations" className="lg:col-span-6">
          <ul className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
            {a.top_features.slice(0, 10).map((f) => (
              <li key={f.feature}>
                <div className="flex justify-between gap-2 text-[13px]"><span className="truncate">{f.feature}</span><span className="num text-muted">{fmtInt(f.count)}</span></div>
                <Bar className="mt-1" value={f.count / maxFeat} color="var(--color-ink)" />
              </li>
            ))}
          </ul>
        </Tile>

        {gt && (
          <Tile title="Compared with the file's labels" sub={`Never used by the model.${gt.unlabelled_rows ? ` ${fmtInt(gt.unlabelled_rows)} unlabelled rows left out.` : ""}`} className="lg:col-span-12">
            <div className="grid items-start gap-6 lg:grid-cols-[300px_220px_1fr]">
              <div className="grid grid-cols-2 gap-2">
                {[["Attacks caught", gt.confusion.tp, "bg-green-soft text-green"], ["Attacks missed", gt.confusion.fn, "bg-red-soft text-red"],
                  ["False alarms", gt.confusion.fp, "bg-orange-soft text-orange"], ["Benign passed", gt.confusion.tn, "bg-raised text-muted"]].map(([k, v, cls]) => (
                  <div key={k} className={clsx("rounded-xl px-3.5 py-2.5", cls)}><div className="text-[12px]">{k}</div><div className="num text-[22px] font-semibold">{fmtInt(v)}</div></div>
                ))}
              </div>
              <div className="num grid grid-cols-2 gap-x-4 gap-y-3 self-center">
                {[["Precision", gt.precision?.toFixed(3)], ["Recall", gt.recall?.toFixed(3)], ["F1", gt.f1?.toFixed(3)], ["False alarms", fmtPct(gt.fpr, 2)]].map(([k, v]) => (
                  <div key={k}><div className="text-[22px] font-semibold leading-tight">{v ?? "—"}</div><div className="text-[12px] text-muted">{k}</div></div>
                ))}
              </div>
              <div className="max-h-[230px] overflow-auto">
                <table className="grid-table text-[13px]">
                  <thead className="sticky top-0 bg-tile"><tr><th>Label in file</th><th className="text-right">Flows</th><th className="text-right">Flagged</th><th className="w-[28%]" /></tr></thead>
                  <tbody>
                    {gt.per_label.map((r) => {
                      const rate = r.flagged / r.n;
                      return (
                        <tr key={r.label}>
                          <td><span className="flex items-center gap-2"><Dot color={FAMILY_COLORS[r.family]} />{r.label}</span></td>
                          <td className="text-right text-muted">{fmtInt(r.n)}</td>
                          <td className="text-right">{fmtPct(rate, 1)}</td>
                          <td><Bar value={rate} color={r.family === "Benign" ? "var(--color-orange)" : "var(--color-green)"} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </Tile>
        )}
      </div>
    </Page>
  );
}

export default function Analyze() {
  const { analysis, setAnalysis } = useApp();
  return analysis ? <Results a={analysis} onReset={() => setAnalysis(null)} /> : <Launcher onDone={setAnalysis} />;
}
