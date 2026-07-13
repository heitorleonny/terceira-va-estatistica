// Formatação no padrão brasileiro (R$, %, números) e utilitários numéricos.

const nf = (dec: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec });

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function brl(v: number | null | undefined, dec = 2): string {
  if (!isNum(v)) return "—";
  return `R$ ${nf(dec).format(v)}`;
}

export function pct(v: number | null | undefined, dec = 2): string {
  if (!isNum(v)) return "—";
  return `${nf(dec).format(v)}%`;
}

/** Percentual a partir de um decimal (0.0872 → "8,72%"). */
export function pctDec(v: number | null | undefined, dec = 2): string {
  if (!isNum(v)) return "—";
  return pct(v * 100, dec);
}

export function num(v: number | null | undefined, dec = 2): string {
  if (!isNum(v)) return "—";
  return nf(dec).format(v);
}

/** Assinado, para variações (+12,3% / −4,4%). */
export function signed(v: number | null | undefined, dec = 2, suffix = "%"): string {
  if (!isNum(v)) return "—";
  const s = nf(dec).format(Math.abs(v));
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${s}${suffix}`;
}

export function shortDate(iso: string): string {
  const d = new Date(iso + (iso.length <= 10 ? "T00:00:00" : ""));
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(d);
}

export function dateTime(iso: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  }).format(d);
}

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}
