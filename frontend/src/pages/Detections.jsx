import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { Search } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../state.jsx";
import { Button, Dot, Empty, Page, Segmented, Tag } from "../components/ui.jsx";
import RecordPanel from "../components/RecordPanel.jsx";
import { BAND, FAMILY_COLORS, familyOf, fmtInt, fmtScore } from "../lib/format.js";

const SIZE = 40;

export default function Detections() {
  const { analysis } = useApp();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get("r")) || null;
  const [filters, setFilters] = useState({ band: "", label: "", q: "", sort: "score" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const reqId = useRef(0);

  const setFilter = (k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };

  useEffect(() => {
    if (!analysis) return;
    const id = ++reqId.current;                         // only the latest request may update the list
    setLoading(true);
    const p = { page, size: SIZE, sort: filters.sort };
    if (filters.band) p.band = filters.band;
    if (filters.label) p.label = filters.label;
    if (filters.q) p.q = filters.q;
    api.detections(analysis.id, p).then((d) => {
      if (id !== reqId.current) return;
      setData(d);
      if (!selected && d.rows[0]) setParams({ r: d.rows[0].record }, { replace: true });
    }).catch(() => {}).finally(() => id === reqId.current && setLoading(false));
  }, [analysis, page, filters, tick]); // eslint-disable-line

  const labels = useMemo(() => (analysis?.ground_truth?.per_label || []).filter((l) => l.flagged > 0), [analysis]);

  useEffect(() => {
    const h = (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || !data?.rows?.length) return;
      const i = data.rows.findIndex((r) => r.record === selected);
      if ((e.key === "j" || e.key === "ArrowDown") && i < data.rows.length - 1) { e.preventDefault(); setParams({ r: data.rows[i + 1].record }); }
      if ((e.key === "k" || e.key === "ArrowUp") && i > 0) { e.preventDefault(); setParams({ r: data.rows[i - 1].record }); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [data, selected, setParams]);

  if (!analysis) {
    return (
      <Page title="Alerts">
        <Empty title="No alerts yet." action={<Button variant="primary" onClick={() => nav("/")}>Analyze a file</Button>}>
          Analyze a flow file first. Flagged flows show up here for review.
        </Empty>
      </Page>
    );
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1;

  return (
    <Page title="Alerts" meta={`${fmtInt(analysis.flagged)} flagged in ${analysis.file_name}. Arrow keys move between alerts.`}
      actions={Object.entries(BAND).map(([k, b]) => <span key={k} className="flex items-center gap-1.5 text-[12.5px] text-muted"><Dot color={b.color} /><span className="num text-ink">{fmtInt(analysis.bands[k])}</span> {b.label.toLowerCase()}</span>)}>
      <div className="grid items-start gap-3 lg:grid-cols-12">
        <section className="tile min-w-0 overflow-hidden lg:sticky lg:top-[112px] lg:col-span-4">
          <div className="space-y-2 p-3">
            <Segmented value={filters.band} onChange={(v) => setFilter("band", v)} className="flex w-full [&>button]:flex-1"
              options={[{ value: "", label: "All" }, ...Object.entries(BAND).map(([k, v]) => ({ value: k, label: v.label }))]} />
            <div className="flex gap-2">
              <label className="relative flex-1">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <input value={filters.q} onChange={(e) => setFilter("q", e.target.value)} placeholder="Record number" inputMode="numeric" className="input !py-[5px] !pl-8 text-[13px]" />
              </label>
              <select value={filters.sort} onChange={(e) => setFilter("sort", e.target.value)} className="select text-[13px]">
                <option value="score">Highest score</option>
                <option value="record">File order</option>
              </select>
            </div>
            {labels.length > 0 && (
              <select value={filters.label} onChange={(e) => setFilter("label", e.target.value)} className="select w-full text-[13px]">
                <option value="">Any file label</option>
                {labels.map((l) => <option key={l.label} value={l.label}>{l.label} ({l.flagged})</option>)}
              </select>
            )}
          </div>
          <ul className={clsx("max-h-[calc(100vh-17rem)] min-h-[200px] overflow-y-auto bg-raised", loading && "opacity-60")}>
            {data?.rows?.length === 0 && <li className="px-4 py-10 text-center text-muted">No alerts match.</li>}
            {data?.rows?.map((r) => (
              <li key={r.record}>
                <button onClick={() => setParams({ r: r.record })}
                  className={clsx("flex w-full items-start gap-2.5 border-b border-hair px-3.5 py-2 text-left transition-colors", selected === r.record ? "bg-blue-soft" : "hover:bg-hover")}>
                  <Dot color={BAND[r.band].color} className="mt-[7px]" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="num font-medium">{r.record}</span>
                      {r.decision && <Tag tone={r.decision === "approved" ? "green" : "red"} className="!text-[11px]">{r.decision === "approved" ? "Approved" : "Rejected"}</Tag>}
                      <span className="num ml-auto text-[12.5px] text-muted">{fmtScore(r.score)}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[12.5px]">
                      <span className="truncate text-muted">{r.top_feature}</span>
                      {r.ground_truth && (
                        <span className="ml-auto flex max-w-[50%] shrink-0 items-center gap-1 truncate text-faint" title="From the uploaded file. Never used by the model.">
                          <Dot color={FAMILY_COLORS[familyOf(r.ground_truth)]} className="!h-1.5 !w-1.5" />{r.ground_truth}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
          <div className="num flex items-center justify-between px-3.5 py-2 text-[12.5px] text-muted">
            <button className="text-link disabled:text-faint" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span>{data ? `${fmtInt(data.total)} alerts, page ${page} of ${pages}` : "Loading"}</span>
            <button className="text-link disabled:text-faint" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </section>

        <div className="min-w-0 lg:col-span-8">
          {selected
            ? <RecordPanel key={`${analysis.id}-${selected}`} analysisId={analysis.id} record={selected} onDecided={() => setTick((t) => t + 1)} />
            : <Empty title="Select an alert." />}
        </div>
      </div>
    </Page>
  );
}
