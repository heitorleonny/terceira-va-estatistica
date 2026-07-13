import { useEffect, useMemo, useState } from "react";
import { api, ApiError, type Analise } from "../lib/api";
import { brl, isoDaysAgo, num, pct, pctDec, signed, todayISO } from "../lib/format";
import { probabilidadeCauda } from "../lib/stats";
import { downloadCsv } from "../lib/download";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { PriceChart, Histogram, QQPlot } from "../components/charts";
import {
  AnimatedNumber, Empty, FadeIn, Heading, Loader, Note, Panel, Stat, Tag, TickerChips,
} from "../components/ui";

export function AnaliseEmpirica({
  reload,
  onPersist,
}: {
  reload: { ticker: string; nonce: number } | null;
  onPersist: () => void;
}) {
  const [ticker, setTicker] = useState("MXRF11");
  const [inicio, setInicio] = useState(isoDaysAgo(365));
  const [fim, setFim] = useState(todayISO());
  const [ateHoje, setAteHoje] = useState(true);
  const [data, setData] = useState<Analise | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [precoAlvo, setPrecoAlvo] = useState(0);
  const [cauda, setCauda] = useState<"inferior" | "superior">("inferior");

  async function run(tk = ticker) {
    const t = tk.trim().toUpperCase();
    if (!t) return;
    setLoading(true);
    setErro(null);
    try {
      const d = await api.analise(t, inicio, ateHoje ? todayISO() : fim);
      setData(d);
      onPersist();
    } catch (e) {
      setData(null);
      setErro(e instanceof ApiError ? e.message : "Falha ao carregar a análise.");
    } finally {
      setLoading(false);
    }
  }

  // Análise inicial + ao ser acionado por "recarregar" no Histórico.
  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (reload?.ticker) {
      setTicker(reload.ticker);
      run(reload.ticker);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload?.nonce]);

  // Define o preço-alvo padrão quando novos dados chegam.
  useEffect(() => {
    const e = data?.estatisticas;
    if (e && e.ultimo_preco != null && e.preco_minimo != null && e.preco_maximo != null) {
      const clamp = Math.min(Math.max(e.ultimo_preco, e.preco_minimo), e.preco_maximo);
      setPrecoAlvo(Number(clamp.toFixed(2)));
    }
  }, [data]);

  const e = data?.estatisticas;
  const tail = useMemo(() => {
    if (!e || e.sigma_anual == null || e.media_log_anual == null || e.ultimo_preco == null)
      return { z: null, probabilidade: null };
    return probabilidadeCauda({
      ultimoPreco: e.ultimo_preco,
      sigmaAnual: e.sigma_anual,
      mediaLogAnual: e.media_log_anual,
      precoAlvo,
      cauda,
    });
  }, [e, precoAlvo, cauda]);

  function exportarSerie() {
    if (!data) return;
    downloadCsv(`${data.ticker}_serie_precos.csv`, [
      ["data", "close"],
      ...data.serie.map((p) => [p.data, p.close]),
    ]);
  }
  function exportarLogRetornos() {
    if (!data) return;
    const rows: (string | number)[][] = [["data", "log_retorno"]];
    for (let i = 1; i < data.serie.length; i++) {
      rows.push([data.serie[i].data, Math.log(data.serie[i].close / data.serie[i - 1].close)]);
    }
    downloadCsv(`${data.ticker}_log_retornos.csv`, rows);
  }

  const podeCauda =
    e && e.preco_minimo != null && e.preco_maximo != null && e.preco_maximo > e.preco_minimo;

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Estatística empírica dos retornos">Análise Empírica</Heading>

      {/* Controles */}
      <Panel title="Consulta" meta="Yahoo Finance">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_auto_auto]">
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Ticker</span>
            <input
              className="field"
              value={ticker}
              onChange={(ev) => setTicker(ev.target.value.toUpperCase())}
              onKeyDown={(ev) => ev.key === "Enter" && run()}
              placeholder="MXRF11"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Data inicial</span>
            <input type="date" className="field" value={inicio} max={todayISO()} onChange={(ev) => setInicio(ev.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="eyebrow">Data final</span>
            <input
              type="date"
              className="field disabled:opacity-40"
              value={ateHoje ? todayISO() : fim}
              max={todayISO()}
              disabled={ateHoje}
              onChange={(ev) => setFim(ev.target.value)}
            />
          </label>
          <label className="flex items-end gap-2 pb-2">
            <input type="checkbox" checked={ateHoje} onChange={(ev) => setAteHoje(ev.target.checked)} className="accent-amber" />
            <span className="font-mono text-xs text-paper-dim">até hoje</span>
          </label>
          <div className="flex items-end">
            <button className="btn-amber h-[38px] w-full justify-center" onClick={() => run()} disabled={loading}>
              {loading ? "…" : "▸ Analisar"}
            </button>
          </div>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={[ticker]} onPick={setTicker} />
        </div>
        <div className="mt-3">
          <Note kind="warn">
            As probabilidades assumem log-retornos diários <b>normais</b> — simplificação conhecida
            (retornos reais têm caudas mais pesadas). Nada aqui é recomendação de investimento.
          </Note>
        </div>
      </Panel>

      {loading && (
        <Panel><Loader label={`buscando ${ticker}`} /></Panel>
      )}
      {erro && !loading && <Note kind="error">⚠ {erro}</Note>}

      {data && e && !loading && (
        <>
          {/* Métricas */}
          <FadeIn>
            <Panel
              title={data.ticker}
              meta={`${data.periodo.pregoes} pregões · ${data.periodo.inicio} → ${data.periodo.fim}`}
            >
              <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4">
                <Stat label="Pregões (n)" value={num(e.n, 0)} />
                <Stat label="Último preço" value={<AnimatedNumber value={e.ultimo_preco ?? 0} format={(v) => brl(v)} />} tone="amber" />
                <Stat
                  label="Retorno médio anual*"
                  value={signed(e.media_log_anual != null ? e.media_log_anual * 100 : null)}
                  tone={e.media_log_anual != null && e.media_log_anual >= 0 ? "up" : "down"}
                />
                <Stat label="Volatilidade anual*" value={pctDec(e.sigma_anual)} tone="azure" />
              </div>
              <p className="mt-3 font-mono text-micro text-paper-mute">
                * anualização com {data.dias_uteis_ano} pregões/ano (média × {data.dias_uteis_ano}; desvio × √{data.dias_uteis_ano}).
              </p>
            </Panel>
          </FadeIn>

          {/* Série temporal */}
          <FadeIn delay={0.04}>
            <Panel title="Série temporal" meta="preço de fechamento (R$)">
              <PriceChart data={data.serie} />
              <p className="mt-2 font-mono text-micro text-paper-mute">
                Preço de fechamento = último negócio de cada pregão. Base para os log-retornos.
              </p>
            </Panel>
          </FadeIn>

          {/* Histograma + normal */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.6fr_1fr]">
            <FadeIn delay={0.06}>
              <Panel title="Distribuição dos log-retornos" meta="histograma + normal ajustada">
                {data.histograma && e.media_diaria != null && e.dp_diario ? (
                  <>
                    <Histogram bins={data.histograma} mu={e.media_diaria} sigma={e.dp_diario} />
                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <Stat label="Média diária μ" value={num(e.media_diaria, 5)} />
                      <Stat label="Desvio diário σ" value={num(e.dp_diario, 5)} />
                      <Stat label="Observações" value={num(e.n, 0)} />
                    </div>
                    <p className="mt-3 font-mono text-micro leading-relaxed text-paper-mute">
                      r = ln(Pₜ / Pₜ₋₁). Usa-se o log por ser aditivo no tempo e mais próximo de uma
                      normal. A curva âmbar é a N(μ, σ²) ajustada — compare-a com as barras.
                    </p>
                  </>
                ) : (
                  <Empty>Dados insuficientes (ou preço constante) no período.</Empty>
                )}
              </Panel>
            </FadeIn>

            <FadeIn delay={0.08}>
              <Panel title="Normalidade" meta={data.normalidade.teste ?? "—"}>
                {data.qq.pontos.length ? (
                  <>
                    <QQPlot pontos={data.qq.pontos} reta={data.qq.reta} />
                    <div className="mt-3 flex flex-col gap-2">
                      <div className="grid grid-cols-2 gap-3">
                        <Stat label="Estatística" value={num(data.normalidade.estatistica, 4)} />
                        <Stat label="p-valor" value={num(data.normalidade.p_valor, 4)} />
                      </div>
                      {data.normalidade.normal === true ? (
                        <Note kind="info">p ≥ 0,05 → não se rejeita a normalidade a 5%.</Note>
                      ) : data.normalidade.normal === false ? (
                        <Note kind="warn">
                          p &lt; 0,05 → rejeita-se a normalidade. Evidência de caudas pesadas —
                          trate as probabilidades com cautela.
                        </Note>
                      ) : (
                        <Empty>Dados insuficientes para o teste.</Empty>
                      )}
                    </div>
                  </>
                ) : (
                  <Empty>Sem pontos suficientes para o QQ-plot.</Empty>
                )}
              </Panel>
            </FadeIn>
          </div>

          {/* Probabilidade de cauda */}
          <FadeIn delay={0.1}>
            <Panel title="Preço de referência & probabilidade de cauda" meta="modelo normal · 1 pregão">
              {podeCauda ? (
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.5fr_1fr]">
                  <div className="flex flex-col gap-4">
                    <div>
                      <div className="mb-2 flex items-baseline justify-between">
                        <span className="eyebrow">Preço de referência</span>
                        <span className="tnum font-mono text-lg text-amber">{brl(precoAlvo)}</span>
                      </div>
                      <input
                        type="range"
                        min={e.preco_minimo!}
                        max={e.preco_maximo!}
                        step={0.01}
                        value={precoAlvo}
                        onChange={(ev) => setPrecoAlvo(Number(ev.target.value))}
                        className="w-full accent-amber"
                      />
                      <div className="mt-1 flex justify-between font-mono text-micro text-paper-mute">
                        <span>mín {brl(e.preco_minimo)}</span>
                        <span>últ {brl(e.ultimo_preco)}</span>
                        <span>máx {brl(e.preco_maximo)}</span>
                      </div>
                    </div>

                    <div className="flex gap-2">
                      {(["inferior", "superior"] as const).map((c) => (
                        <button
                          key={c}
                          onClick={() => setCauda(c)}
                          className={`btn flex-1 justify-center ${
                            cauda === c ? "border-amber/60 bg-amber/10 text-amber" : "border-line text-paper-dim hover:text-paper"
                          }`}
                        >
                          {c === "inferior" ? "▾ Cair abaixo" : "▴ Subir acima"}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-col justify-center gap-4 border-l border-line pl-6">
                    <div>
                      <div className="eyebrow mb-1">Probabilidade</div>
                      <div className={`tnum font-mono text-[2.6rem] font-medium leading-none ${cauda === "inferior" ? "text-down" : "text-up"}`}>
                        {tail.probabilidade != null ? (
                          <AnimatedNumber value={tail.probabilidade * 100} format={(v) => pct(v)} />
                        ) : "—"}
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <Stat label="z (desv.-pad.)" value={num(tail.z, 4)} />
                      <div className="flex flex-col gap-1">
                        <span className="eyebrow">Cenário</span>
                        <Tag tone={cauda === "inferior" ? "down" : "up"}>
                          {cauda === "inferior" ? "P(fechar abaixo)" : "P(fechar acima)"}
                        </Tag>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <Empty>Faixa de preços insuficiente no período.</Empty>
              )}

              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button className="btn-ghost" onClick={exportarSerie}>⬇ Série CSV</button>
                <button className="btn-ghost" onClick={exportarLogRetornos}>⬇ Log-retornos CSV</button>
                <span className="font-mono text-micro text-paper-mute">
                  z = [ln(alvo/S₀) − μₐ·t] / (σₐ·√t), t = 1/{data.dias_uteis_ano}. Cauda inf. = Φ(z); sup. = 1−Φ(z).
                </span>
              </div>
            </Panel>
          </FadeIn>
        </>
      )}
    </div>
  );
}
