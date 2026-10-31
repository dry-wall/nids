import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Bar as RBar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { Bar, ChartTip, Dot, Page, Segmented, Spinner, Tag, Tile } from "../components/ui.jsx";
import { FAMILY_COLORS, MODEL_COLORS, MODEL_LABEL, fmtInt, fmtLogitTick, fmtPct } from "../lib/format.js";

const KEYS = ["lr", "rf", "dnn"];
const SHORT = { lr: "LR", rf: "RF", dnn: "NN" };

function Legend() {
  return (
    <div className="mt-2 flex flex-wrap gap-4 text-[12px] text-muted">
      {KEYS.map((k) => <span key={k} className="flex items-center gap-1.5"><span className="h-0.5 w-3.5 rounded" style={{ background: MODEL_COLORS[k] }} />{MODEL_LABEL[k]}</span>)}
    </div>
  );
}

function ModelTile({ k, m, best }) {
  const r = m.models[k], s = r.summary;
  const specs = [["Precision", s.precision.mean.toFixed(3)], ["Recall", s.recall.mean.toFixed(3)], ["ROC-AUC", s.roc_auc.mean.toFixed(4)],
    ["False alarms", fmtPct(s.fpr.mean, 2)], ["Threshold", r.primary_seed.threshold.toFixed(3)], ["10k flows", `${r.latency_ms_per_10k.p50} ms`]];
  return (
    <section className="tile p-5 lg:col-span-3">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-[15px] font-semibold"><Dot color={MODEL_COLORS[k]} />{MODEL_LABEL[k]}</span>
        {k === best ? <Tag tone="green">Highest F1</Tag> : k === "dnn" ? <Tag tone="blue">Default</Tag> : null}
      </div>
      <div className="num mt-3 text-[40px] font-semibold leading-none tracking-[-0.03em]">{s.f1.mean.toFixed(3)}</div>
      <div className="mt-1 text-[12.5px] text-muted">F1 on held-out flows, ±{s.f1.std.toFixed(4)}</div>
      <dl className="num mt-4 grid grid-cols-3 gap-x-3 gap-y-2.5 border-t border-line pt-3">
        {specs.map(([l, v]) => <div key={l}><dd className="text-[14px] font-medium">{v}</dd><dt className="text-[11.5px] text-muted">{l}</dt></div>)}
      </dl>
    </section>
  );
}

function UnseenTile({ m }) {
  return (
    <section className="tile p-5 lg:col-span-3">
      <div className="text-[15px] font-semibold">On new attack types</div>
      <div className="mt-0.5 text-[12.5px] text-muted">Trained Monday to Wednesday, tested on Thursday and Friday</div>
      <ul className="mt-4 space-y-3">
        {KEYS.map((k) => (
          <li key={k}>
            <div className="flex justify-between text-[13px]">
              <span className="flex items-center gap-1.5"><Dot color={MODEL_COLORS[k]} />{MODEL_LABEL[k]}</span>
              <span className="num"><span className="font-medium">{m.temporal[k].f1.toFixed(3)}</span> <span className="text-faint">vs {m.models[k].summary.f1.mean.toFixed(3)}</span></span>
            </div>
            <Bar className="mt-1" value={m.temporal[k].f1} color={MODEL_COLORS[k]} />
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[12px] text-muted">F1 drops sharply on attacks the models never saw. Phase 2 adds a zero-day detector.</p>
    </section>
  );
}

function Threshold({ m }) {
  const [key, setKey] = useState("dnn");
  const sw = m.models[key].primary_seed.sweep_val;
  const op = m.models[key].runs[0].operating_point;   // the exact threshold and its validation scores
  const chosenIdx = useMemo(() => {
    let b = 0;
    sw.thresholds.forEach((t, i) => { if (Math.abs(t - op.threshold) < Math.abs(sw.thresholds[b] - op.threshold)) b = i; });
    return b;
  }, [sw, op]);
  const [idx, setIdx] = useState(chosenIdx);
  useEffect(() => setIdx(chosenIdx), [chosenIdx]);

  const atChosen = idx === chosenIdx;
  let t, prec, rec, fpr, f1;
  if (atChosen) ({ threshold: t, val_precision: prec, val_recall: rec, val_fpr: fpr, val_f1: f1 } = op);
  else {
    t = sw.thresholds[idx];
    const tp = sw.tp[idx], fp = sw.fp[idx];
    prec = tp + fp ? tp / (tp + fp) : 1; rec = tp / sw.n_pos; fpr = fp / sw.n_neg;
    f1 = prec + rec ? (2 * prec * rec) / (prec + rec) : 0;
  }
  const e = sw.hist.logit_edges;
  const hist = sw.hist.benign.map((b, i) => ({ x: (e[i] + e[i + 1]) / 2, benign: b, attack: sw.hist.attack[i] }));

  return (
    <Tile title="Choosing the threshold" sub="Set on validation flows: best F1 with false alarms at or below 1%. Test flows are scored once, at the end." className="lg:col-span-8"
      aside={<Segmented value={key} onChange={setKey} options={KEYS.map((k) => ({ value: k, label: SHORT[k] }))} />}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={hist} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap={0} barGap={0}>
          <XAxis dataKey="x" type="number" domain={[-14, 14]} ticks={[-12, -6, 0, 6, 12]} tickFormatter={fmtLogitTick} axisLine={false} tickLine={false} />
          <YAxis scale="sqrt" axisLine={false} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v)} />
          <Tooltip cursor={{ fill: "var(--color-hover)" }} content={<ChartTip labelFmt={(l) => `Score ${(1 / (1 + Math.exp(-l))).toPrecision(4)}`} fmt={fmtInt} />} />
          <RBar isAnimationActive={false} dataKey="benign" name="Benign" fill="var(--color-green)" fillOpacity={0.5} />
          <RBar isAnimationActive={false} dataKey="attack" name="Attack" fill="var(--color-red)" fillOpacity={0.75} />
          <ReferenceLine x={Math.log(t / (1 - t))} stroke="var(--color-ink)" strokeWidth={1.5} />
        </BarChart>
      </ResponsiveContainer>
      <input type="range" min={0} max={sw.thresholds.length - 1} value={idx} onChange={(ev) => setIdx(Number(ev.target.value))} className="mt-2 w-full" aria-label="Threshold" />
      <div className="num mt-2 grid grid-cols-3 gap-3 sm:grid-cols-5">
        {[["Threshold", t >= 0.9999 ? t.toFixed(6) : t.toFixed(4)], ["Precision", prec.toFixed(4)], ["Recall", rec.toFixed(4)], ["F1", f1.toFixed(4)], ["False alarms", fmtPct(fpr, 2)]].map(([k, v]) => (
          <div key={k}>
            <div className={clsx("text-[20px] font-semibold", k === "False alarms" && fpr > m.manifest.target_fpr && "text-red")}>{v}</div>
            <div className="text-[12px] text-muted">{k}{k === "Threshold" && (atChosen ? ", chosen" : "")}</div>
          </div>
        ))}
      </div>
      {!atChosen && <button onClick={() => setIdx(chosenIdx)} className="mt-2 text-[13px] text-link hover:underline">Back to the chosen threshold</button>}
    </Tile>
  );
}

function Outcomes({ m }) {
  const [key, setKey] = useState("dnn");
  const c = m.models[key].runs[0].confusion;
  return (
    <Tile title="Test outcomes" sub={`${fmtInt(m.models[key].runs[0].n)} held-out flows`} className="lg:col-span-4"
      aside={<Segmented value={key} onChange={setKey} options={KEYS.map((k) => ({ value: k, label: SHORT[k] }))} />}>
      <div className="grid grid-cols-2 gap-2">
        {[["Attacks caught", c.tp, "bg-green-soft text-green"], ["Attacks missed", c.fn, "bg-red-soft text-red"],
          ["False alarms", c.fp, "bg-orange-soft text-orange"], ["Benign passed", c.tn, "bg-raised text-muted"]].map(([k, v, cls]) => (
          <div key={k} className={clsx("rounded-xl px-3.5 py-3", cls)}><div className="text-[12px]">{k}</div><div className="num text-[24px] font-semibold">{fmtInt(v)}</div></div>
        ))}
      </div>
      <div className="mt-3 text-[12.5px] text-muted">Recall {fmtPct(c.tp / (c.tp + c.fn), 2)}, false alarm rate {fmtPct(c.fp / (c.fp + c.tn), 2)}.</div>
    </Tile>
  );
}

function Families({ m }) {
  const fams = m.models.dnn.primary_seed.per_family_test.map((r) => r.family);
  const get = (k, f) => m.models[k].primary_seed.per_family_test.find((r) => r.family === f);
  return (
    <Tile title="By attack type" sub="Share flagged on test flows. For benign traffic, the false alarm rate." className="lg:col-span-7">
      <div className="overflow-x-auto">
        <table className="grid-table min-w-[480px] text-[13px]">
          <thead><tr><th>Type</th><th className="text-right">Flows</th>{KEYS.map((k) => <th key={k} className="w-[22%] text-right">{MODEL_LABEL[k]}</th>)}</tr></thead>
          <tbody>
            {fams.map((f) => (
              <tr key={f}>
                <td><span className="flex items-center gap-2"><Dot color={FAMILY_COLORS[f]} />{f}</span></td>
                <td className="text-right text-muted">{fmtInt(get("dnn", f).n)}</td>
                {KEYS.map((k) => {
                  const r = get(k, f).rate, benign = f === "Benign";
                  return (
                    <td key={k} className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {!benign && <Bar className="w-12" value={r} color={r >= 0.5 ? "var(--color-green)" : "var(--color-red)"} />}
                        <span className={clsx("w-12", !benign && r < 0.5 && "text-red")}>{fmtPct(r, benign ? 2 : 1)}</span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-muted">Web attacks look like ordinary web traffic in these twelve features. Heartbleed and Infiltration have only a handful of test flows.</p>
    </Tile>
  );
}

function UnseenTable({ m }) {
  const fams = (m.temporal.dnn?.per_family || []).filter((r) => r.family !== "Benign");
  return (
    <Tile title="New attack types, one by one" sub="Share flagged when the type was never in training" className="lg:col-span-5">
      <table className="grid-table text-[13px]">
        <thead><tr><th>Type</th><th className="text-right">Flows</th>{KEYS.map((k) => <th key={k} className="text-right">{SHORT[k]}</th>)}</tr></thead>
        <tbody>
          {fams.map((f) => (
            <tr key={f.family}>
              <td><span className="flex items-center gap-2"><Dot color={FAMILY_COLORS[f.family]} />{f.family}</span></td>
              <td className="text-right text-muted">{fmtInt(f.n)}</td>
              {KEYS.map((k) => <td key={k} className="text-right">{fmtPct(m.temporal[k].per_family.find((r) => r.family === f.family).rate, 1)}</td>)}
            </tr>
          ))}
          <tr><td className="text-muted">Benign false alarms</td><td />{KEYS.map((k) => <td key={k} className="text-right text-muted">{fmtPct(m.temporal[k].fpr, 2)}</td>)}</tr>
        </tbody>
      </table>
    </Tile>
  );
}

function Data({ card, m }) {
  const max = Math.max(...card.class_counts.map((r) => r.raw));
  return (
    <Tile title="The data" sub="CIC-IDS2017, de-duplicated before splitting so no flow is in both training and testing" className="lg:col-span-12">
      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <div className="num grid grid-cols-2 content-start gap-x-4 gap-y-3 lg:grid-cols-1">
          {[[fmtInt(card.rows_raw), "flows in the dataset"], [fmtInt(card.exact_duplicates_removed + card.feature_space_duplicates_removed), "duplicates removed"],
            [fmtInt(card.rows_clean), "flows kept"], [fmtInt(m.manifest.rows.test), `held-out test flows (${fmtInt(m.manifest.rows.train)} for training)`]].map(([v, l]) => (
            <div key={l}><div className="text-[20px] font-semibold leading-tight">{v}</div><div className="text-[12px] text-muted">{l}</div></div>
          ))}
        </div>
        <div className="grid gap-x-8 md:grid-cols-2">
          {card.class_counts.map((r) => (
            <div key={r.label} className="grid grid-cols-[1fr_auto] items-center gap-x-3 border-t border-line py-1.5 text-[13px]">
              <span className="flex min-w-0 items-center gap-2 truncate"><Dot color={FAMILY_COLORS[r.family]} />{r.label}</span>
              <span className="num text-muted"><span className="text-ink">{fmtInt(r.after_cleaning)}</span> of {fmtInt(r.raw)}</span>
              <div className="relative col-span-2 mt-1 h-1 rounded-full bg-hair">
                <div className="absolute inset-y-0 left-0 rounded-full opacity-30" style={{ width: `${(100 * Math.log1p(r.raw)) / Math.log1p(max)}%`, background: FAMILY_COLORS[r.family] }} />
                <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(100 * Math.log1p(r.after_cleaning)) / Math.log1p(max)}%`, background: FAMILY_COLORS[r.family] }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Tile>
  );
}

export default function ModelLab() {
  const [m, setM] = useState(null);
  const [card, setCard] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    api.metrics().then(setM).catch(setErr);
    api.dataCard().then(setCard).catch(() => {});
  }, []);
  if (err) return <Page title="Models"><div className="tile p-5 text-red">{err.message}</div></Page>;
  if (!m) return <Page title="Models"><Spinner label="Loading results" /></Page>;
  const best = KEYS.reduce((a, b) => (m.models[a].summary.f1.mean >= m.models[b].summary.f1.mean ? a : b));
  return (
    <Page title="Models" meta={`Held-out results, averaged over training runs with seeds ${m.manifest.model_seeds.join(", ")}. Produced by the training script.`}>
      <div className="grid gap-3 lg:grid-cols-12">
        {KEYS.map((k) => <ModelTile key={k} k={k} m={m} best={best} />)}
        {m.temporal?.dnn && <UnseenTile m={m} />}

        <Tile title="ROC curve" sub="Detection rate against false alarms, log scale. The dashed line marks 1%." className="lg:col-span-6">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid />
              <XAxis dataKey="fpr" type="number" scale="log" domain={[1e-5, 1]} allowDataOverflow ticks={[1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1]} tickFormatter={(v) => `${v * 100}%`} axisLine={false} tickLine={false} />
              <YAxis dataKey="tpr" type="number" domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip labelFmt={(l) => `False alarms ${(l * 100).toPrecision(2)}%`} fmt={(v) => v.toFixed(3)} />} />
              <ReferenceLine x={m.manifest.target_fpr} stroke="var(--color-red)" strokeDasharray="3 3" />
              {KEYS.map((k) => <Line key={k} isAnimationActive={false} data={m.models[k].primary_seed.roc.filter((p) => p.fpr > 0)} dataKey="tpr" name={MODEL_LABEL[k]} stroke={MODEL_COLORS[k]} dot={false} strokeWidth={2} />)}
            </LineChart>
          </ResponsiveContainer>
          <Legend />
        </Tile>
        <Tile title="Precision and recall" sub="Attacks are 17.8% of flows after cleaning" className="lg:col-span-6">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid />
              <XAxis dataKey="recall" type="number" domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} axisLine={false} tickLine={false} />
              <YAxis dataKey="precision" type="number" domain={[0.5, 1]} allowDataOverflow tickFormatter={(v) => v.toFixed(2)} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTip labelFmt={(l) => `Recall ${Number(l).toFixed(2)}`} fmt={(v) => v.toFixed(3)} />} />
              {KEYS.map((k) => <Line key={k} isAnimationActive={false} data={m.models[k].primary_seed.pr} dataKey="precision" name={MODEL_LABEL[k]} stroke={MODEL_COLORS[k]} dot={false} strokeWidth={2} />)}
            </LineChart>
          </ResponsiveContainer>
          <Legend />
        </Tile>

        <Threshold m={m} />
        <Outcomes m={m} />
        <Families m={m} />
        {m.temporal?.dnn && <UnseenTable m={m} />}
        {card && <Data card={card} m={m} />}
      </div>
    </Page>
  );
}
