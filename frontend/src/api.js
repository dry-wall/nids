async function request(path, opts = {}) {
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    let detail = null;
    try {
      const body = await res.json();
      detail = body.error || body.detail;
      msg = detail?.message || (typeof detail === "string" ? detail : msg);
    } catch {}
    const err = new Error(msg);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json();
}

const post = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

export const api = {
  health: () => request("/health"),
  metrics: () => request("/metrics"),
  dataCard: () => request("/data-card"),
  samples: () => request("/samples"),
  detectSample: (name, model) => request(`/samples/${encodeURIComponent(name)}/detect?model=${model}`, { method: "POST" }),
  detectFile: (file, model) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/detect?model=${model}`, { method: "POST", body: fd });
  },
  analysis: (id) => request(`/analyses/${id}`),
  detections: (id, params) => request(`/analyses/${id}/detections?${new URLSearchParams(params)}`),
  record: (id, rec) => request(`/analyses/${id}/records/${rec}`),
  decide: (body) => post("/decisions", body),
  audit: (limit = 300) => request(`/audit?limit=${limit}`),
  brief: (id) => request(`/briefs/${id}`),
  kbStats: () => request("/kb/stats"),
  kbSearch: (params) => request(`/kb/search?${new URLSearchParams(params)}`),
  kbRelated: (family, q = "") => request(`/kb/related?${new URLSearchParams({ family, q })}`),

  /** Streams NDJSON events from the brief endpoint. Returns an abort function. */
  streamBrief(id, rec, body, onEvent, onError) {
    const ctrl = new AbortController();
    (async () => {
      try {
        const res = await fetch(`/api/analyses/${id}/records/${rec}/brief`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body), signal: ctrl.signal,
        });
        if (!res.ok) throw new Error((await res.json()).error?.message || res.statusText);
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, i).trim();
            buf = buf.slice(i + 1);
            if (line) onEvent(JSON.parse(line));
          }
        }
      } catch (e) {
        if (e.name !== "AbortError") onError?.(e);
      }
    })();
    return () => ctrl.abort();
  },
};
