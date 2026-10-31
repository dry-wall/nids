import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

const Ctx = createContext(null);

const load = (k, d) => {
  try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; }
};
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

export function AppProvider({ children }) {
  const [analysis, setAnalysis] = useState(null);
  const [model, setModelState] = useState(() => load("nids.model", null));
  const [analyst, setAnalystState] = useState(() => load("nids.analyst", ""));
  const [health, setHealth] = useState(null);
  const [healthErr, setHealthErr] = useState(null);
  const [theme, setThemeState] = useState(() => document.documentElement.dataset.theme || "light");

  // Follow the system setting until the user picks a theme explicitly.
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e) => { if (!load("nids.theme", null)) applyTheme(e.matches ? "dark" : "light"); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const applyTheme = (t) => { document.documentElement.dataset.theme = t; setThemeState(t); };

  const refreshHealth = useCallback(async () => {
    try { setHealth(await api.health()); setHealthErr(null); }
    catch (e) { setHealthErr(e.message); }
  }, []);

  useEffect(() => {
    refreshHealth();
    const t = setInterval(refreshHealth, 15000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  // restore the last analysis after a page reload (if the backend still holds it)
  useEffect(() => {
    const id = load("nids.analysis", null);
    if (id) api.analysis(id).then(setAnalysis).catch(() => save("nids.analysis", null));
  }, []);

  const value = {
    analysis,
    setAnalysis: (a) => { setAnalysis(a); save("nids.analysis", a?.id ?? null); },
    model: model || health?.bundle?.default_model || "dnn",
    setModel: (m) => { setModelState(m); save("nids.model", m); },
    analyst,
    setAnalyst: (n) => { setAnalystState(n); save("nids.analyst", n); },
    health, healthErr, refreshHealth,
    theme,
    toggleTheme: () => { const t = theme === "dark" ? "light" : "dark"; try { localStorage.setItem("nids.theme", t); } catch {} applyTheme(t); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useApp = () => useContext(Ctx);
