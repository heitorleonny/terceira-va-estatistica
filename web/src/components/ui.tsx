import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect, type ReactNode } from "react";

// ── Panel ─────────────────────────────────────────────────────────────────────
export function Panel({
  title,
  meta,
  children,
  className = "",
  right,
}: {
  title?: string;
  meta?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="flex items-baseline gap-3">
            {title && <span className="eyebrow">{title}</span>}
            {meta && <span className="font-mono text-micro text-paper-mute">{meta}</span>}
          </div>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

// ── Eyebrow / section heading ──────────────────────────────────────────────────
export function Heading({ children, kicker }: { children: ReactNode; kicker?: string }) {
  return (
    <div className="mb-4">
      {kicker && <div className="eyebrow mb-1.5">{kicker}</div>}
      <h2 className="font-display text-[1.7rem] font-medium leading-tight text-paper">{children}</h2>
    </div>
  );
}

// ── Animated number ─────────────────────────────────────────────────────────────
export function AnimatedNumber({
  value,
  format,
  className = "",
}: {
  value: number;
  format: (n: number) => string;
  className?: string;
}) {
  const mv = useMotionValue(value);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.5, ease: "easeOut" });
    return controls.stop;
  }, [value]);
  return <motion.span className={className}>{text}</motion.span>;
}

// ── Stat tile ────────────────────────────────────────────────────────────────
type Tone = "default" | "up" | "down" | "amber" | "azure";
const toneClass: Record<Tone, string> = {
  default: "text-paper",
  up: "text-up",
  down: "text-down",
  amber: "text-amber",
  azure: "text-azure",
};

export function Stat({
  label,
  value,
  tone = "default",
  sub,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  sub?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 border-l border-line pl-3">
      <span className="eyebrow">{label}</span>
      <span className={`tnum font-mono text-[1.35rem] font-medium leading-none ${toneClass[tone]}`}>
        {value}
      </span>
      {sub && <span className="font-mono text-micro text-paper-mute">{sub}</span>}
    </div>
  );
}

// ── Tag / grade chip ───────────────────────────────────────────────────────────
export function Tag({ children, tone = "default" }: { children: ReactNode; tone?: Tone | "line" }) {
  const map: Record<string, string> = {
    default: "border-line text-paper-dim",
    up: "border-up/40 text-up bg-up/5",
    down: "border-down/40 text-down bg-down/5",
    amber: "border-amber/40 text-amber bg-amber/5",
    azure: "border-azure/40 text-azure bg-azure/5",
    line: "border-line text-paper-mute",
  };
  return (
    <span
      className={`inline-flex items-center rounded-[2px] border px-1.5 py-0.5 font-mono text-micro uppercase tracking-[0.08em] ${map[tone]}`}
    >
      {children}
    </span>
  );
}

// ── Delta (variação assinada colorida) ──────────────────────────────────────────
export function Delta({ value, children }: { value: number | null; children: ReactNode }) {
  const tone = value == null ? "text-paper-mute" : value >= 0 ? "text-up" : "text-down";
  return <span className={`tnum font-mono ${tone}`}>{children}</span>;
}

// ── Notes ────────────────────────────────────────────────────────────────────
export function Note({
  kind = "info",
  children,
}: {
  kind?: "info" | "warn" | "error";
  children: ReactNode;
}) {
  const map = {
    info: "border-azure/30 text-azure/90 bg-azure/5",
    warn: "border-amber/30 text-amber/90 bg-amber/5",
    error: "border-down/40 text-down/90 bg-down/5",
  };
  return (
    <div className={`rounded-[2px] border px-3 py-2 font-mono text-[0.72rem] leading-relaxed ${map[kind]}`}>
      {children}
    </div>
  );
}

// ── Loader / empty ─────────────────────────────────────────────────────────────
export function Loader({ label = "carregando" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 font-mono text-xs text-paper-mute">
      <span className="inline-block h-1.5 w-1.5 animate-blink bg-amber" />
      <span className="uppercase tracking-[0.12em]">{label}…</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center rounded-[2px] border border-dashed border-line px-4 text-center font-mono text-xs text-paper-mute">
      {children}
    </div>
  );
}

// ── Ticker chips (seleção rápida) ────────────────────────────────────────────────
export function TickerChips({
  tickers,
  selected,
  onPick,
}: {
  tickers: string[];
  selected?: string[];
  onPick: (ticker: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="eyebrow !text-[0.6rem]">sugestões</span>
      {tickers.map((t) => {
        const on = selected?.includes(t);
        return (
          <button
            key={t}
            type="button"
            onClick={() => onPick(t)}
            className={`rounded-[2px] border px-2 py-0.5 font-mono text-[0.68rem] transition-colors ${
              on
                ? "border-amber/50 bg-amber/10 text-amber"
                : "border-line text-paper-dim hover:border-amber/40 hover:text-amber"
            }`}
          >
            {t}
          </button>
        );
      })}
    </div>
  );
}

// ── Fade-in wrapper ─────────────────────────────────────────────────────────────
export function FadeIn({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut", delay }}
    >
      {children}
    </motion.div>
  );
}
