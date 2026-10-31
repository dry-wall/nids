import clsx from "clsx";

export function Button({ variant = "secondary", size = "md", loading, icon: Icon, children, className, ...rest }) {
  const v = {
    primary: "bg-blue text-white hover:bg-blue-hover",
    secondary: "bg-tile text-ink hover:bg-hair",
    raised: "bg-raised text-ink ring-1 ring-inset ring-line hover:bg-tile",
    approve: "bg-green text-white hover:opacity-90",
    reject: "bg-raised text-red ring-1 ring-inset ring-red/40 hover:bg-red-soft",
    plain: "text-link hover:underline !px-0",
  }[variant];
  const s = { sm: "h-7 px-3.5 text-[12.5px] gap-1.5", md: "h-9 px-4 text-[14px] gap-2" }[size];
  return (
    <button {...rest} disabled={rest.disabled || loading}
      className={clsx("inline-flex shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-default disabled:opacity-40", v, s, className)}>
      {loading ? <span className="spinner !h-3.5 !w-3.5" /> : Icon && <Icon size={size === "sm" ? 13 : 15} strokeWidth={2} />}
      {children}
    </button>
  );
}

export function Segmented({ options, value, onChange, className }) {
  return (
    <div role="tablist" className={clsx("inline-flex rounded-[9px] bg-hair p-[2px]", className)}>
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        const active = opt.value === value;
        return (
          <button key={opt.value} role="tab" aria-selected={active} onClick={() => onChange(opt.value)} title={opt.title}
            className={clsx("rounded-[7px] px-3 py-[3px] text-[12.5px] transition-colors",
              active ? "bg-raised font-medium text-ink shadow-[0_1px_2px_rgba(0,0,0,.12)]" : "text-ink/75 hover:text-ink")}>
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/** Apple-style page: a sticky local bar (title left, actions right) and a dense full-width body. */
export function Page({ title, meta, actions, children }) {
  return (
    <>
      <div className="sticky top-11 z-30 border-b border-nav-line bg-nav backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex min-h-[52px] max-w-[1280px] flex-wrap items-center gap-x-5 gap-y-2 px-5 py-2 sm:px-6">
          <h1 className="text-[21px] font-semibold tracking-[-0.02em]">{title}</h1>
          {meta && <div className="min-w-0 truncate text-[13px] text-muted">{meta}</div>}
          {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      </div>
      <div className="appear mx-auto max-w-[1280px] px-5 pb-14 pt-5 sm:px-6">{children}</div>
    </>
  );
}

export function Tile({ title, aside, sub, children, className, pad = "p-5" }) {
  return (
    <section className={clsx("tile min-w-0", pad, className)}>
      {(title || aside) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <div className="min-w-0">
            {title && <h2 className="text-[16px] font-semibold tracking-[-0.01em]">{title}</h2>}
            {sub && <p className="text-[12.5px] text-muted">{sub}</p>}
          </div>
          {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, note, color, valueColor, className }) {
  return (
    <div className={clsx("tile px-5 py-4", className)}>
      <div className="flex items-center gap-1.5 text-[12.5px] text-muted">{color && <Dot color={color} />}{label}</div>
      <div className="num mt-1 text-[30px] font-semibold leading-none tracking-[-0.025em]" style={valueColor ? { color: valueColor } : undefined}>{value}</div>
      {note && <div className="mt-1.5 text-[12.5px] text-muted">{note}</div>}
    </div>
  );
}

export function Dot({ color, className }) {
  return <span className={clsx("inline-block h-2 w-2 shrink-0 rounded-full", className)} style={{ background: color }} />;
}

const TAGS = {
  red: "bg-red-soft text-red", orange: "bg-orange-soft text-orange", green: "bg-green-soft text-green",
  blue: "bg-blue-soft text-link", gray: "bg-hair text-muted",
};
export function Tag({ tone = "gray", children, className, title }) {
  return <span title={title} className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-[1px] text-[12px] font-medium", TAGS[tone], className)}>{children}</span>;
}

export function Bar({ value, color, className }) {
  return (
    <div className={clsx("h-1.5 rounded-full bg-hair", className)}>
      <div className="h-1.5 rounded-full" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }} />
    </div>
  );
}

export function Spinner({ label }) {
  return <div className="flex items-center gap-3 py-8 text-muted"><span className="spinner" />{label}</div>;
}

export function Empty({ title, children, action }) {
  return (
    <div className="tile flex flex-col items-center px-6 py-16 text-center">
      <div className="text-[19px] font-semibold">{title}</div>
      {children && <p className="mt-1 max-w-sm text-[14px] text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Row({ k, v }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-t border-line py-2 first:border-0">
      <span className="text-muted">{k}</span>
      <span className="text-right">{v}</span>
    </div>
  );
}

export const ChartTip = ({ active, payload, label, fmt = (v) => v, labelFmt = (l) => l }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl bg-raised px-3 py-2 text-[12.5px] shadow-[0_4px_20px_rgba(0,0,0,.14)]">
      {label != null && <div className="mb-0.5 text-muted">{labelFmt(label)}</div>}
      {payload.map((p) => (
        <div key={p.dataKey + p.name} className="flex items-center gap-2">
          <Dot color={p.color || p.fill} />
          <span className="text-muted">{p.name}</span>
          <span className="num ml-auto pl-4 font-medium">{fmt(p.value, p)}</span>
        </div>
      ))}
    </div>
  );
};
