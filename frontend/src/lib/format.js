export const fmtInt = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
export const fmtPct = (v, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
export const fmt4 = (v) => (v == null ? "—" : Number(v).toFixed(4));
export const fmtMs = (ms) => (ms == null ? "—" : ms < 1 ? `${ms.toFixed(1)} ms` : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);

export function fmtNum(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${(v / 1e3).toFixed(1)}k`;
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(2).replace(/\.00$/, "");
  if (a === 0) return "0";
  return v.toPrecision(2);
}

export const fmtScore = (p) => {
  if (p == null) return "—";
  if (p >= 0.99995) return "1.0000";
  return p.toFixed(4);
};

export const timeAgo = (iso) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
};

export const BAND = {
  strong: { label: "Strong", color: "var(--color-red)" },
  moderate: { label: "Moderate", color: "var(--color-orange)" },
  marginal: { label: "Marginal", color: "var(--color-faint)" },
};

export const MODEL_COLORS = { lr: "var(--color-faint)", rf: "var(--color-orange)", dnn: "var(--color-blue)" };

// One Apple system colour per attack type, used the same way everywhere.
export const FAMILY_COLORS = {
  Benign: "var(--color-faint)", DoS: "var(--color-red)", DDoS: "var(--color-orange)", PortScan: "var(--color-yellow)",
  "Brute Force": "var(--color-indigo)", "Web Attack": "var(--color-teal)", Bot: "var(--color-pink)",
  Infiltration: "var(--color-purple)", Heartbleed: "var(--color-green)", Other: "var(--color-faint)", Unknown: "var(--color-faint)",
};

export function familyOf(label) {
  if (!label) return null;
  const l = label.toUpperCase();
  if (l === "BENIGN") return "Benign";
  if (l.startsWith("DOS ")) return "DoS";
  if (l === "DDOS") return "DDoS";
  if (l === "PORTSCAN") return "PortScan";
  if (l.includes("PATATOR")) return "Brute Force";
  if (l.startsWith("WEB ATTACK")) return "Web Attack";
  if (l === "BOT") return "Bot";
  if (l === "INFILTRATION") return "Infiltration";
  if (l === "HEARTBLEED") return "Heartbleed";
  return "Other";
}

export const FEATURE_UNITS = {
  "Flow Duration": "µs", "Flow Bytes/s": "B/s", "Flow Packets/s": "pkt/s",
  "Total Length of Fwd Packets": "B", "Total Length of Bwd Packets": "B",
  "Fwd Packet Length Mean": "B", "Bwd Packet Length Mean": "B", "Average Packet Size": "B",
};

/** Tick label for a log-odds axis: show the probability without rounding 0.9975 up to "1.0". */
export function fmtLogitTick(l) {
  const p = 1 / (1 + Math.exp(-l));
  if (p < 0.001) return p.toExponential(0);
  if (p > 0.999) return `1−${(1 - p).toExponential(0)}`;
  return p >= 0.99 ? p.toFixed(4) : p.toPrecision(2);
}

export const MODEL_LABEL = { lr: "Logistic Regression", rf: "Random Forest", dnn: "Neural Network" };
