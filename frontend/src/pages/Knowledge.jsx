import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api } from "../api.js";
import { Dot, Page, Segmented, Stat, Tile } from "../components/ui.jsx";
import { FAMILY_COLORS, fmtInt } from "../lib/format.js";

const SUGGESTIONS = ["slow HTTP requests exhausting a web server", "SSH password guessing", "contain the incident", "command and control over HTTP"];

function highlight(text, q) {
  const terms = q.toLowerCase().split(/\W+/).filter((t) => t.length > 3);
  if (!terms.length) return text;
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((p, i) => (i % 2 ? <mark key={i} className="bg-transparent font-semibold text-ink">{p}</mark> : p));
}

export default function Knowledge() {
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.kbStats().then(setStats).catch(() => {}); }, []);

  const search = async (query = q) => {
    if (query.trim().length < 2) return;
    setQ(query); setLoading(true);
    try {
      const p = { q: query, k: 10 };
      if (source) p.source = source;
      setRes(await api.kbSearch(p));
    } finally { setLoading(false); }
  };
  useEffect(() => { if (q) search(); }, [source]); // eslint-disable-line

  const s = stats?.stats;
  const ev = stats?.eval;
  const tf = ev?.systems?.["TF-IDF (1-2 gram)"];

  return (
    <Page title="Knowledge" meta="MITRE ATT&CK techniques and mitigations, and NIST SP 800-61 incident response guidance."
      actions={<Segmented value={source} onChange={setSource} options={[{ value: "", label: "All sources" }, { value: "MITRE ATT&CK Enterprise", label: "ATT&CK" }, { value: "NIST SP 800-61 Rev. 3", label: "NIST" }]} />}>
      <div className="grid gap-3 lg:grid-cols-12">
        <section className="tile p-5 lg:col-span-12">
          <form onSubmit={(e) => { e.preventDefault(); search(); }} className="relative">
            <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Describe what you're seeing, for example repeated SSH logins from one host"
              className="input !rounded-xl !py-3 !pl-11 text-[15px]" />
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((x) => <button key={x} onClick={() => search(x)} className="rounded-full bg-raised px-3 py-1 text-[12.5px] text-link ring-1 ring-inset ring-line hover:bg-blue-soft">{x}</button>)}
          </div>
        </section>

        {s && tf && (<>
          <Stat className="lg:col-span-3" label="ATT&CK techniques" color="var(--color-red)" value={fmtInt(s.attack.techniques)} note={`${fmtInt(s.by_doc_type.mitigation)} mitigation passages`} />
          <Stat className="lg:col-span-3" label="NIST passages" color="var(--color-blue)" value={fmtInt(s.by_source["NIST SP 800-61 Rev. 3"])} note={`${s.by_doc_type["csf-element"]} CSF 2.0 recommendations`} />
          <Stat className="lg:col-span-3" label="Found in the top five" color="var(--color-green)" value={`${Math.round(tf["recall@5"] * ev.n_queries)} of ${ev.n_queries}`} note="hand-written test questions" />
          <Stat className="lg:col-span-3" label="Ranked first" color="var(--color-orange)" value={`${Math.round(tf["recall@1"] * ev.n_queries)} of ${ev.n_queries}`} note="right answer at the top" />
        </>)}

        <section className={`tile min-w-0 p-5 lg:col-span-8 ${loading ? "opacity-60" : ""}`}>
          {!res ? (
            <div className="py-10 text-center text-muted">Results appear here. Try one of the suggestions above.</div>
          ) : (<>
            <div className="mb-1 text-[13px] text-muted">{res.results.length} results for "{res.query}"</div>
            {res.results.length === 0 && <p className="py-6 text-muted">Nothing found. Try different words.</p>}
            <ol>
              {res.results.map((r) => (
                <li key={r.chunk_id} className="border-t border-line py-3 first:border-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="min-w-0 font-semibold">{r.title}</h3>
                    <span className="flex shrink-0 items-center gap-1.5 text-[12px] text-muted"><Dot color={r.source.startsWith("MITRE") ? "var(--color-red)" : "var(--color-blue)"} />{r.source.startsWith("MITRE") ? "ATT&CK" : "NIST"}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted">{highlight(r.text, res.query)}</p>
                  {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="text-[12.5px] hover:underline">Read the full entry</a>}
                </li>
              ))}
            </ol>
          </>)}
        </section>

        <div className="grid content-start gap-3 lg:col-span-4">
          {stats && (
            <Tile title="Attack types" sub="The advisory may only cite these ATT&CK IDs">
              <ul className="text-[13px]">
                {Object.entries(stats.families).filter(([f]) => f !== "Unknown").map(([f, t]) => (
                  <li key={f} className="flex items-center justify-between border-t border-line py-1.5 first:border-0">
                    <span className="flex items-center gap-2"><Dot color={FAMILY_COLORS[f]} />{f}</span>
                    {t.length ? <a href={`https://attack.mitre.org/techniques/${t[0]}/`} target="_blank" rel="noreferrer" className="num hover:underline">{t[0]}</a> : <span className="text-faint">varies</span>}
                  </li>
                ))}
              </ul>
            </Tile>
          )}
          {ev && (
            <Tile title="Test questions" sub="Rank of the first useful result">
              <ul className="space-y-1 text-[12.5px]">
                {ev.per_query.map((p) => (
                  <li key={p.query} className="flex gap-2">
                    <span className="num w-5 shrink-0 text-right font-semibold" style={{ color: p.first_hit_rank === 1 ? "var(--color-green)" : p.first_hit_rank ? "var(--color-orange)" : "var(--color-red)" }}>{p.first_hit_rank ?? "–"}</span>
                    <button onClick={() => search(p.query)} className="text-left text-muted hover:text-ink">{p.query}</button>
                  </li>
                ))}
              </ul>
            </Tile>
          )}
        </div>
      </div>
    </Page>
  );
}
