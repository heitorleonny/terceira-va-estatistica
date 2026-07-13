import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { brl, num, shortDate } from "../lib/format";

const GRID_LINE = "#1c1c20";

function TipBox({ rows }: { rows: { k: string; v: string; c?: string }[] }) {
  return (
    <div className="panel !rounded-[2px] px-2.5 py-1.5 !bg-ink-750/95">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center justify-between gap-4 font-mono text-[0.7rem]">
          <span className="text-paper-mute">{r.k}</span>
          <span className={`tnum ${r.c ?? "text-paper"}`}>{r.v}</span>
        </div>
      ))}
    </div>
  );
}

// ── Série de preços ─────────────────────────────────────────────────────────────
export function PriceChart({ data }: { data: { data: string; close: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#E8A33D" stopOpacity={0.22} />
            <stop offset="100%" stopColor="#E8A33D" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_LINE} vertical={false} />
        <XAxis
          dataKey="data"
          tickFormatter={shortDate}
          tickLine={false}
          axisLine={{ stroke: GRID_LINE }}
          minTickGap={44}
        />
        <YAxis
          orientation="right"
          domain={["auto", "auto"]}
          tickFormatter={(v) => num(v, 2)}
          tickLine={false}
          axisLine={false}
          width={54}
        />
        <Tooltip
          cursor={{ stroke: "#E8A33D", strokeOpacity: 0.4, strokeDasharray: "3 3" }}
          content={({ active, payload }: any) =>
            active && payload?.length ? (
              <TipBox
                rows={[
                  { k: "Data", v: shortDate(String(payload[0].payload.data)), c: "text-paper-dim" },
                  { k: "Fech.", v: brl(payload[0].payload.close), c: "text-amber" },
                ]}
              />
            ) : null
          }
        />
        <Area
          type="monotone"
          dataKey="close"
          stroke="#E8A33D"
          strokeWidth={1.6}
          fill="url(#priceFill)"
          dot={false}
          activeDot={{ r: 3, fill: "#F6BC55", stroke: "none" }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Histograma dos log-retornos + normal ajustada ────────────────────────────────
export function Histogram({
  bins,
  mu,
  sigma,
}: {
  bins: { centro: number; densidade: number }[];
  mu: number;
  sigma: number;
}) {
  const pdf = (x: number) =>
    (1 / (sigma * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * ((x - mu) / sigma) ** 2);
  const data = bins.map((b) => ({ ...b, normal: pdf(b.centro) }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID_LINE} vertical={false} />
        <XAxis
          dataKey="centro"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(v) => (v * 100).toFixed(1) + "%"}
          tickLine={false}
          axisLine={{ stroke: GRID_LINE }}
          minTickGap={40}
        />
        <YAxis hide />
        <Tooltip
          cursor={{ fill: "#ffffff06" }}
          content={({ active, payload }: any) =>
            active && payload?.length ? (
              <TipBox
                rows={[
                  { k: "Log-ret.", v: (Number(payload[0].payload.centro) * 100).toFixed(2) + "%", c: "text-paper-dim" },
                  { k: "Densid.", v: num(payload[0].payload.densidade, 1), c: "text-azure" },
                  { k: "Normal", v: num(payload[0].payload.normal, 1), c: "text-amber" },
                ]}
              />
            ) : null
          }
        />
        <ReferenceLine x={mu} stroke="#78ABC4" strokeDasharray="4 3" strokeOpacity={0.7} />
        <Bar dataKey="densidade" fill="#78ABC4" fillOpacity={0.32} maxBarSize={26} />
        <Line type="monotone" dataKey="normal" stroke="#E8A33D" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ── QQ-Plot ──────────────────────────────────────────────────────────────────
export function QQPlot({
  pontos,
  reta,
}: {
  pontos: { teorico: number; amostral: number }[];
  reta: { x: number; y: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={GRID_LINE} />
        <XAxis
          type="number"
          dataKey="teorico"
          name="teórico"
          tickLine={false}
          axisLine={{ stroke: GRID_LINE }}
          tickFormatter={(v) => num(v, 1)}
        />
        <YAxis
          type="number"
          dataKey="amostral"
          name="amostral"
          tickLine={false}
          axisLine={false}
          width={54}
          tickFormatter={(v) => (v * 100).toFixed(1)}
        />
        {reta.length === 2 && (
          <ReferenceLine
            segment={[
              { x: reta[0].x, y: reta[0].y },
              { x: reta[1].x, y: reta[1].y },
            ]}
            stroke="#E8A33D"
            strokeDasharray="5 4"
            strokeOpacity={0.85}
          />
        )}
        <Scatter data={pontos} fill="#78ABC4" fillOpacity={0.75} shape="circle" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// ── Curva de projeção (simulação de aporte) ──────────────────────────────────────
export function ProjectionChart({
  data,
}: {
  data: { mes: number; investido: number; renda: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="invFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#78ABC4" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#78ABC4" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="rendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#48C06B" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#48C06B" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_LINE} vertical={false} />
        <XAxis dataKey="mes" tickLine={false} axisLine={{ stroke: GRID_LINE }} minTickGap={40} />
        <YAxis orientation="right" tickFormatter={(v) => num(v / 1000, 0) + "k"} tickLine={false} axisLine={false} width={48} />
        <Tooltip
          content={({ active, payload }: any) =>
            active && payload?.length ? (
              <TipBox
                rows={[
                  { k: "Mês", v: String(payload[0].payload.mes), c: "text-paper-dim" },
                  { k: "Investido", v: brl(payload[0].payload.investido), c: "text-azure" },
                  { k: "Renda ac.", v: brl(payload[0].payload.renda), c: "text-up" },
                ]}
              />
            ) : null
          }
        />
        <Area type="monotone" dataKey="investido" stroke="#78ABC4" strokeWidth={1.5} fill="url(#invFill)" dot={false} />
        <Area type="monotone" dataKey="renda" stroke="#48C06B" strokeWidth={1.5} fill="url(#rendFill)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Comparação de múltiplos FIIs (séries rebaseadas a 100) ───────────────────────
export function ComparisonChart({
  ativos,
  cores,
}: {
  ativos: { ticker: string; serie: { data: string; base100: number | null }[] }[];
  cores: string[];
}) {
  // Une as séries por data numa única tabela (uma coluna por ticker).
  const byDate = new Map<string, Record<string, unknown>>();
  ativos.forEach((a) =>
    a.serie.forEach((p) => {
      const row = byDate.get(p.data) ?? { data: p.data };
      row[a.ticker] = p.base100;
      byDate.set(p.data, row);
    }),
  );
  const data = [...byDate.values()].sort((x, y) => (String(x.data) < String(y.data) ? -1 : 1));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID_LINE} vertical={false} />
        <XAxis dataKey="data" tickFormatter={shortDate} tickLine={false} axisLine={{ stroke: GRID_LINE }} minTickGap={44} />
        <YAxis orientation="right" tickFormatter={(v) => num(v, 0)} tickLine={false} axisLine={false} width={44} />
        <ReferenceLine y={100} stroke="#37373f" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ stroke: "#E8A33D", strokeOpacity: 0.35, strokeDasharray: "3 3" }}
          content={({ active, payload, label }: any) =>
            active && payload?.length ? (
              <TipBox
                rows={[
                  { k: "Data", v: shortDate(String(label)), c: "text-paper-dim" },
                  ...payload.map((p: any) => ({
                    k: String(p.dataKey),
                    v: p.value != null ? num(p.value, 1) : "—",
                  })),
                ]}
              />
            ) : null
          }
        />
        {ativos.map((a, i) => (
          <Line
            key={a.ticker}
            type="monotone"
            dataKey={a.ticker}
            stroke={cores[i % cores.length]}
            strokeWidth={1.6}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
