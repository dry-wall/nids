import { useApp } from "../state.jsx";
import { Button, Dot, Empty, Page, Row, Spinner, Stat, Tag, Tile } from "../components/ui.jsx";
import { MODEL_COLORS, MODEL_LABEL, fmtMs } from "../lib/format.js";

export default function System() {
  const { health, healthErr, refreshHealth } = useApp();
  if (healthErr) return <Page title="System"><Empty title="The server isn't running.">Start it with python run.py, then reload this page.</Empty></Page>;
  if (!health) return <Page title="System"><Spinner label="Checking the server" /></Page>;
  const b = health.bundle;
  const llm = health.llm_chain.find((c) => c.available && c.name !== "playbook");
  const lat = health.brief_latency.find((l) => l.provider !== "playbook");

  return (
    <Page title="System" meta="What is running, which models are loaded, and how fast drafts are written."
      actions={<Button size="sm" variant="raised" onClick={refreshHealth}>Check again</Button>}>
      <div className="grid gap-3 lg:grid-cols-12">
        <Stat className="lg:col-span-3" label="Server" color="var(--color-green)" valueColor="var(--color-green)" value="Running" note={`Up for ${Math.max(1, Math.floor(health.uptime_s / 60))} min`} />
        <Stat className="lg:col-span-3" label="Draft writer" color={llm ? "var(--color-blue)" : "var(--color-orange)"} value={llm ? llm.label.replace("Local · ", "") : "Playbook"} note={llm ? "Local model through Ollama" : "No language model reachable"} />
        <Stat className="lg:col-span-3" label="Typical draft" color="var(--color-purple)" value={lat ? fmtMs(lat.p50_ms) : "—"} note={lat ? `${fmtMs(lat.p95_ms)} for the slowest 5%, ${lat.n} drafts` : "No drafts yet"} />
        <Stat className="lg:col-span-3" label="Knowledge base" color="var(--color-teal)" value={health.kb_chunks.toLocaleString()} note="passages indexed" />

        <Tile title="Draft writers" sub="Tried in this order. The offline playbook always works." className="lg:col-span-6">
          <ol>
            {health.llm_chain.map((c, i) => (
              <li key={c.name} className="flex items-center gap-3 border-t border-line py-2.5 first:border-0">
                <span className="num w-4 text-[13px] text-faint">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{c.name === "playbook" ? "Offline playbook" : c.label.replace("Local · ", "Ollama, ")}</div>
                  <div className="text-[12.5px] text-muted">{c.name === "playbook" ? "Fixed advice per attack type, no model needed" : c.detail}</div>
                </div>
                <Tag tone={c.available ? "green" : "red"}>{c.available ? "Ready" : "Unavailable"}</Tag>
              </li>
            ))}
          </ol>
        </Tile>

        <Tile title="Detection models" sub={`Trained ${new Date(b.created).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`} className="lg:col-span-6">
          {Object.entries(b.models).map(([k, m]) => (
            <Row key={k} k={<span className="flex items-center gap-2 text-ink"><Dot color={MODEL_COLORS[k]} />{MODEL_LABEL[k]}{k === b.default_model && <Tag tone="blue">default</Tag>}</span>}
              v={<span className="num text-muted">threshold {m.threshold.toFixed(4)}</span>} />
          ))}
          <Row k="Bundle version" v={b.version} />
          <Row k="Data fingerprint" v={<span className="num">{b.data_sha256_16}</span>} />
        </Tile>

        <Tile title="Server" className="lg:col-span-6">
          <Row k="Upload limit" v={`${health.limits.max_upload_mb} MB`} />
          <Row k="Features used" v={`${health.features.length} CICFlowMeter features`} />
          <Row k="Split seed" v={<span className="num">{b.split_seed}</span>} />
          <Row k="API reference" v={<a href="/docs" className="hover:underline">Open</a>} />
        </Tile>

        <Tile title="Software" className="lg:col-span-6">
          {Object.entries(b.versions).map(([k, v]) => <Row key={k} k={k === "scikit-learn" ? "scikit-learn" : k[0].toUpperCase() + k.slice(1)} v={<span className="num">{v}</span>} />)}
        </Tile>
      </div>
    </Page>
  );
}
