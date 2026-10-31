import { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "../api.js";
import { Button, Page, Segmented, Stat, Tag } from "../components/ui.jsx";
import { MODEL_LABEL, fmtInt, fmtMs, timeAgo } from "../lib/format.js";

function toCSV(rows) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

const when = (iso) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function DraftSheet({ id, onClose }) {
  const [b, setB] = useState(null);
  useEffect(() => { api.brief(id).then(setB); }, [id]);
  useEffect(() => {
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/35 sm:items-center sm:p-6" onClick={onClose}>
      <div className="appear max-h-[88vh] w-full max-w-2xl overflow-auto rounded-t-[22px] bg-bg p-6 shadow-2xl ring-1 ring-hair sm:rounded-[22px]" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-baseline justify-between">
          <h3 className="text-[21px] font-semibold tracking-[-0.02em]">Draft {id}</h3>
          <button onClick={onClose} className="text-[14px] text-link hover:underline">Done</button>
        </div>
        {!b ? <span className="spinner inline-block" /> : (
          <div className="space-y-4 text-[14px]">
            <div className="flex flex-wrap gap-1.5">
              <Tag>Record {b.record_id}</Tag>
              <Tag tone={b.provider === "playbook" ? "orange" : "blue"}>{b.provider === "playbook" ? "Offline playbook" : b.model}</Tag>
              <Tag>{fmtMs(b.latency_ms)}</Tag>
              {b.family_hint && <Tag>Asked to consider {b.family_hint}</Tag>}
            </div>
            <p className="text-[16px] leading-relaxed">{b.brief.summary}</p>
            <ol className="list-decimal space-y-1 pl-5 marker:text-faint">{b.brief.actions.map((a, i) => <li key={i}>{a.step}</li>)}</ol>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[13px] font-semibold">Prompt sent</div>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-tile p-3.5 font-mono text-[11.5px] leading-relaxed text-muted">{b.prompt}</pre>
              </div>
              {b.raw_response && (
                <div>
                  <div className="mb-1 text-[13px] font-semibold">Model output</div>
                  <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-tile p-3.5 font-mono text-[11.5px] leading-relaxed text-muted">{b.raw_response}</pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Audit() {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("decisions");
  const [open, setOpen] = useState(null);
  useEffect(() => { api.audit().then(setData); }, []);

  const rows = data?.[tab] ?? [];
  const approved = data?.decisions.filter((d) => d.status === "approved").length ?? 0;
  const edited = data?.decisions.filter((d) => d.edited).length ?? 0;
  const download = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([toCSV(rows)], { type: "text/csv" }));
    a.download = `nids-${tab}.csv`; a.click();
  };

  return (
    <Page title="Audit" meta="Every analysis, every draft with the exact prompt behind it, and every decision."
      actions={<>
        <Segmented value={tab} onChange={setTab} options={[{ value: "decisions", label: "Decisions" }, { value: "briefs", label: "Drafts" }, { value: "analyses", label: "Analyses" }]} />
        <Button size="sm" variant="raised" onClick={download} disabled={!rows.length}>Export CSV</Button>
      </>}>
      <div className="grid gap-3 lg:grid-cols-12">
        {data && (<>
          <Stat className="lg:col-span-3" label="Analyses" color="var(--color-blue)" value={fmtInt(data.analyses.length)} note={data.analyses[0] ? `Last ${timeAgo(data.analyses[0].created_at)}` : "None yet"} />
          <Stat className="lg:col-span-3" label="Drafts written" color="var(--color-purple)" value={fmtInt(data.briefs.length)} note={`${fmtInt(data.briefs.filter((b) => b.provider === "playbook").length)} by the offline playbook`} />
          <Stat className="lg:col-span-3" label="Approved" color="var(--color-green)" value={fmtInt(approved)} note={`${fmtInt(edited)} edited before deciding`} />
          <Stat className="lg:col-span-3" label="Rejected" color="var(--color-red)" value={fmtInt(data.decisions.length - approved)} note="drafts the analyst did not accept" />
        </>)}

        <section className="tile overflow-x-auto p-5 lg:col-span-12">
          {!rows.length ? <p className="py-10 text-center text-muted">Nothing recorded yet. Decisions you make on the Alerts page appear here.</p> : (
            <table className="grid-table min-w-[720px] text-[13.5px]">
              <thead>
                {tab === "decisions" && <tr><th>When</th><th>Decision</th><th>Analyst</th><th>File</th><th>Record</th><th>Note</th><th /></tr>}
                {tab === "briefs" && <tr><th>When</th><th>Record</th><th>Written by</th><th>Time</th><th>File</th><th /></tr>}
                {tab === "analyses" && <tr><th>When</th><th>File</th><th className="text-right">Flows</th><th className="text-right">Flagged</th><th>Model</th></tr>}
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="whitespace-nowrap text-muted">{when(r.created_at)}</td>
                    {tab === "decisions" && (<>
                      <td><span className={clsx(r.status === "approved" ? "text-green" : "text-red")}>{r.status === "approved" ? "Approved" : "Rejected"}</span>{r.edited ? <span className="text-muted">, edited</span> : ""}</td>
                      <td>{r.analyst}</td>
                      <td className="max-w-[200px] truncate text-muted">{r.file_name}</td>
                      <td>{r.record_id}</td>
                      <td className="max-w-[240px] truncate text-muted">{r.notes}</td>
                      <td className="text-right">{r.brief_id && <button onClick={() => setOpen(r.brief_id)} className="text-link hover:underline">View draft</button>}</td>
                    </>)}
                    {tab === "briefs" && (<>
                      <td>{r.record_id}</td>
                      <td>{r.provider === "playbook" ? "Offline playbook" : r.model}</td>
                      <td>{fmtMs(r.latency_ms)}</td>
                      <td className="max-w-[220px] truncate text-muted">{r.file_name}</td>
                      <td className="text-right"><button onClick={() => setOpen(r.id)} className="text-link hover:underline">View</button></td>
                    </>)}
                    {tab === "analyses" && (<>
                      <td className="max-w-[280px] truncate">{r.file_name}</td>
                      <td className="text-right">{fmtInt(r.rows)}</td>
                      <td className="text-right text-red">{fmtInt(r.flagged)}</td>
                      <td>{MODEL_LABEL[r.model]}</td>
                    </>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
      {open && <DraftSheet id={open} onClose={() => setOpen(null)} />}
    </Page>
  );
}
