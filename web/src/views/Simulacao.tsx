import { useState } from "react";
import { api, ApiError, type SimResumo } from "../lib/api";
import { brl, num } from "../lib/format";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { ProjectionChart } from "../components/charts";
import { FadeIn, Heading, Loader, Note, Panel, Stat, TickerChips } from "../components/ui";

export function Simulacao({ onPersist }: { onPersist: () => void }) {
  const [ticker, setTicker] = useState("MXRF11");
  const [preco, setPreco] = useState(10);
  const [dy, setDy] = useState(9);
  const [cotas, setCotas] = useState(10);
  const [meses, setMeses] = useState(240);
  const [resumo, setResumo] = useState<SimResumo | null>(null);
  const [serie, setSerie] = useState<{ mes: number; investido: number; renda: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function buscar() {
    setLoading(true);
    setErro(null);
    try {
      const d = await api.fii(ticker.trim().toUpperCase());
      if (d.preco != null) setPreco(d.preco);
      if (d.dy != null) setDy(d.dy);
      onPersist();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao buscar o FII.");
    } finally {
      setLoading(false);
    }
  }

  async function simular() {
    setLoading(true);
    setErro(null);
    try {
      const d = await api.simular(preco, dy, cotas, meses);
      setResumo(d.resumo);
      setSerie(
        d.serie.map((r) => ({
          mes: r["Mês"],
          investido: r["Total Investido (R$)"],
          renda: r["Renda Acumulada (R$)"],
        })),
      );
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao simular.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Aporte mensal · preço e DY constantes">Simulação de Aporte</Heading>

      <Panel title="Parâmetros">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          <label className="col-span-2 flex flex-col gap-1 md:col-span-1">
            <span className="eyebrow">Ticker</span>
            <input className="field" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
          </label>
          <div className="flex items-end">
            <button className="btn-ghost h-[38px] w-full justify-center" onClick={buscar} disabled={loading}>
              buscar
            </button>
          </div>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Cotação R$</span>
            <input type="number" step="0.01" className="field" value={preco} onChange={(e) => setPreco(+e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">DY anual %</span>
            <input type="number" step="0.01" className="field" value={dy} onChange={(e) => setDy(+e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Cotas / mês</span>
            <input type="number" className="field" value={cotas} onChange={(e) => setCotas(+e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Meses</span>
            <input type="number" className="field" value={meses} onChange={(e) => setMeses(+e.target.value)} />
          </label>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={[ticker]} onPick={setTicker} />
        </div>
        <div className="mt-3">
          <button className="btn-amber" onClick={simular} disabled={loading}>▸ Simular</button>
        </div>
        {loading && <div className="mt-3"><Loader /></div>}
        {erro && <div className="mt-3"><Note kind="error">⚠ {erro}</Note></div>}
      </Panel>

      {resumo && (
        <FadeIn>
          <Panel title="Resultado" meta={`${meses} meses`}>
            <div className="grid grid-cols-2 gap-y-4 md:grid-cols-5">
              <Stat label="Cotas totais" value={num(resumo.cotas_total, 0)} />
              <Stat label="Total investido" value={brl(resumo.total_investido)} tone="azure" />
              <Stat label="Renda mensal final" value={brl(resumo.renda_mensal_final)} tone="up" />
              <Stat label="Renda acumulada" value={brl(resumo.renda_acumulada)} tone="up" />
              <Stat label="Patrimônio final" value={brl(resumo.patrimonio_final)} tone="amber" />
            </div>
            <div className="mt-5">
              <ProjectionChart data={serie} />
            </div>
          </Panel>
        </FadeIn>
      )}
    </div>
  );
}
