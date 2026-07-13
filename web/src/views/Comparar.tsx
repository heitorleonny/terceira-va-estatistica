import { useState } from "react";
import { api, ApiError, type Comparacao } from "../lib/api";
import { brl, isoDaysAgo, num, pctDec, signed, todayISO } from "../lib/format";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { ComparisonChart } from "../components/charts";
import { Empty, FadeIn, Heading, Loader, Note, Panel, Tag, TickerChips } from "../components/ui";

// Paleta categórica (uma cor por FII), coerente com o tema do terminal.
const PALETTE = ["#E8A33D", "#78ABC4", "#48C06B", "#A78BFA", "#FB7185", "#5EEAD4"];

function corCelula(v: number): string {
  if (v >= 0) return `rgba(72, 192, 107, ${Math.min(Math.abs(v), 1) * 0.55})`;
  return `rgba(229, 72, 77, ${Math.min(Math.abs(v), 1) * 0.55})`;
}

export function Comparar({ onPersist }: { onPersist: () => void }) {
  const [raw, setRaw] = useState("MXRF11, KNRI11, HGLG11");
  const [inicio, setInicio] = useState(isoDaysAgo(365));
  const [fim, setFim] = useState(todayISO());
  const [ateHoje, setAteHoje] = useState(true);
  const [data, setData] = useState<Comparacao | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function comparar() {
    const tickers = raw.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
    if (tickers.length < 2) {
      setErro("Informe pelo menos 2 tickers separados por vírgula.");
      return;
    }
    setLoading(true);
    setErro(null);
    try {
      const d = await api.comparar(tickers, inicio, ateHoje ? todayISO() : fim);
      setData(d);
      onPersist();
    } catch (e) {
      setData(null);
      setErro(e instanceof ApiError ? e.message : "Falha ao comparar.");
    } finally {
      setLoading(false);
    }
  }

  const corDe = (ticker: string) => {
    const idx = data?.ativos.findIndex((a) => a.ticker === ticker) ?? 0;
    return PALETTE[idx % PALETTE.length];
  };

  const selecionados = raw.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
  function toggleTicker(tk: string) {
    const next = selecionados.includes(tk) ? selecionados.filter((t) => t !== tk) : [...selecionados, tk];
    setRaw(next.join(", "));
  }

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Séries · volatilidade · correlação entre retornos">Comparar FIIs</Heading>

      <Panel title="Consulta" meta="Yahoo Finance · 2 a 6 FIIs">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[2fr_1fr_1fr_auto_auto]">
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Tickers (vírgula)</span>
            <input
              className="field"
              value={raw}
              onChange={(e) => setRaw(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && comparar()}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Data inicial</span>
            <input type="date" className="field" value={inicio} max={todayISO()} onChange={(e) => setInicio(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Data final</span>
            <input type="date" className="field disabled:opacity-40" value={ateHoje ? todayISO() : fim} max={todayISO()} disabled={ateHoje} onChange={(e) => setFim(e.target.value)} />
          </label>
          <label className="flex items-end gap-2 pb-2">
            <input type="checkbox" checked={ateHoje} onChange={(e) => setAteHoje(e.target.checked)} className="accent-amber" />
            <span className="font-mono text-xs text-paper-dim">até hoje</span>
          </label>
          <div className="flex items-end">
            <button className="btn-amber h-[38px] w-full justify-center" onClick={comparar} disabled={loading}>
              {loading ? "…" : "▸ Comparar"}
            </button>
          </div>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={selecionados} onPick={toggleTicker} />
        </div>
      </Panel>

      {loading && <Panel><Loader label="buscando séries" /></Panel>}
      {erro && !loading && <Note kind="error">⚠ {erro}</Note>}
      {data?.erros.map((e) => <Note key={e.ticker} kind="warn">⚠ {e.ticker}: {e.erro}</Note>)}

      {data && data.ativos.length >= 2 && !loading && (
        <>
          <FadeIn>
            <Panel
              title="Desempenho relativo"
              meta="base 100 no início do período"
              right={
                <div className="flex flex-wrap gap-2">
                  {data.ativos.map((a) => (
                    <span key={a.ticker} className="flex items-center gap-1.5 font-mono text-micro text-paper-dim">
                      <span className="inline-block h-2 w-2 rounded-full" style={{ background: corDe(a.ticker) }} />
                      {a.ticker}
                    </span>
                  ))}
                </div>
              }
            >
              <ComparisonChart ativos={data.ativos} cores={data.ativos.map((a) => corDe(a.ticker))} />
              <p className="mt-2 font-mono text-micro text-paper-mute">
                Cada série é reescalada para 100 no início — assim FIIs de preços muito diferentes
                ficam comparáveis. Acima de 100 = valorização no período.
              </p>
            </Panel>
          </FadeIn>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_1fr]">
            <FadeIn delay={0.05}>
              <Panel title="Estatísticas descritivas" meta="anualizado (252 pregões)">
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b border-line-strong">
                        {["FII", "Retorno total", "Retorno anual", "Volatilidade", "n"].map((h) => (
                          <th key={h} className="eyebrow px-2 py-2 text-left">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="tnum font-mono text-[0.8rem]">
                      {data.ativos.map((a) => {
                        const e = a.estatisticas;
                        return (
                          <tr key={a.ticker} className="border-b border-line">
                            <td className="px-2 py-2">
                              <span className="flex items-center gap-2 font-semibold text-paper">
                                <span className="inline-block h-2 w-2 rounded-full" style={{ background: corDe(a.ticker) }} />
                                {a.ticker}
                              </span>
                            </td>
                            <td className={`px-2 py-2 ${e.retorno_total_pct != null && e.retorno_total_pct >= 0 ? "text-up" : "text-down"}`}>
                              {signed(e.retorno_total_pct)}
                            </td>
                            <td className={`px-2 py-2 ${e.media_log_anual != null && e.media_log_anual >= 0 ? "text-up" : "text-down"}`}>
                              {signed(e.media_log_anual != null ? e.media_log_anual * 100 : null)}
                            </td>
                            <td className="px-2 py-2 text-azure">{pctDec(e.sigma_anual)}</td>
                            <td className="px-2 py-2 text-paper-mute">{num(e.n, 0)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </FadeIn>

            <FadeIn delay={0.08}>
              <Panel title="Correlação dos log-retornos" meta={data.correlacao ? `${data.correlacao.observacoes} obs.` : "—"}>
                {data.correlacao ? (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-center">
                        <thead>
                          <tr>
                            <th className="px-2 py-1"></th>
                            {data.correlacao.tickers.map((t) => (
                              <th key={t} className="eyebrow px-2 py-1">{t}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="tnum font-mono text-[0.78rem]">
                          {data.correlacao.matriz.map((row, i) => (
                            <tr key={i}>
                              <td className="eyebrow px-2 py-1 text-left">{data.correlacao!.tickers[i]}</td>
                              {row.map((v, j) => (
                                <td key={j} className="px-1 py-1">
                                  <span
                                    className="block rounded-[2px] px-2 py-1.5 text-paper"
                                    style={{ background: corCelula(v) }}
                                  >
                                    {num(v, 2)}
                                  </span>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="mt-3 font-mono text-micro leading-relaxed text-paper-mute">
                      Correlação entre −1 e +1. Próximo de +1 = retornos andam juntos; próximo de 0 =
                      pouca relação (melhor diversificação); negativo = tendem a se mover em direções
                      opostas.
                    </p>
                  </>
                ) : (
                  <Empty>Dados insuficientes para a correlação.</Empty>
                )}
              </Panel>
            </FadeIn>
          </div>
        </>
      )}

      {!loading && !data && !erro && <Empty>Informe 2+ tickers e compare.</Empty>}
    </div>
  );
}
