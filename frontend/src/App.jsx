import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import clsx from "clsx";
import { Moon, Sun } from "lucide-react";
import { useApp } from "./state.jsx";
import Analyze from "./pages/Analyze.jsx";
import Detections from "./pages/Detections.jsx";
import ModelLab from "./pages/ModelLab.jsx";
import Knowledge from "./pages/Knowledge.jsx";
import Audit from "./pages/Audit.jsx";
import System from "./pages/System.jsx";
import { fmtInt } from "./lib/format.js";

const NAV = [
  { to: "/", label: "Analyze", end: true },
  { to: "/alerts", label: "Alerts" },
  { to: "/models", label: "Models" },
  { to: "/knowledge", label: "Knowledge" },
  { to: "/audit", label: "Audit" },
  { to: "/system", label: "System" },
];

function ThemeButton() {
  const { theme, toggleTheme } = useApp();
  const dark = theme === "dark";
  return (
    <button onClick={toggleTheme} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}
      className="grid h-8 w-8 place-items-center rounded-full text-ink/70 hover:text-ink">
      {dark ? <Sun size={15} strokeWidth={1.8} /> : <Moon size={15} strokeWidth={1.8} />}
    </button>
  );
}

function GlobalNav() {
  const { analysis, healthErr } = useApp();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const badge = analysis?.flagged > 0 && <span className="num ml-1 text-red">{fmtInt(analysis.flagged)}</span>;
  return (
    <header className="sticky top-0 z-40 border-b border-nav-line bg-nav backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-11 max-w-[1280px] items-center gap-6 px-5 sm:px-6">
        <NavLink to="/" className="text-[18px] font-semibold tracking-[-0.03em] text-ink no-underline">nids.</NavLink>
        <nav className="hidden items-center gap-7 text-[12.5px] md:flex">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx("transition-colors", isActive ? "text-ink" : "text-ink/65 hover:text-ink")}>
              {label}{to === "/alerts" && badge}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {analysis && <NavLink to="/" className="hidden max-w-[220px] truncate text-[12.5px] text-muted no-underline hover:text-ink lg:block" title={analysis.file_name}>{analysis.file_name}</NavLink>}
          {healthErr && <span className="text-[12.5px] text-red">Server offline</span>}
          <ThemeButton />
          <button onClick={() => setOpen((o) => !o)} aria-label="Menu" className="relative h-8 w-8 md:hidden">
            <span className={clsx("absolute left-2 h-px w-4 bg-ink transition-all", open ? "top-4 rotate-45" : "top-[13px]")} />
            <span className={clsx("absolute left-2 h-px w-4 bg-ink transition-all", open ? "top-4 -rotate-45" : "top-[19px]")} />
          </button>
        </div>
      </div>
      {open && (
        <nav className="border-t border-nav-line bg-bg px-6 pb-6 pt-3 md:hidden">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => clsx("block py-2 text-[22px] font-semibold tracking-[-0.02em]", isActive ? "text-ink" : "text-ink/55")}>
              {label}{to === "/alerts" && badge}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <GlobalNav />
      <main>
        <Routes>
          <Route path="/" element={<Analyze />} />
          <Route path="/alerts" element={<Detections />} />
          <Route path="/models" element={<ModelLab />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </main>
    </div>
  );
}
