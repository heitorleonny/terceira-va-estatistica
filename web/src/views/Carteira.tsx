import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { brl, num, pct } from "../lib/format";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { Empty, FadeIn, Heading, Loader, Note, Panel, Stat, TickerChips } from "../components/ui";

interface Linha {
  FII: string;
  Tipo: string;
  "Preço (R$)": number | null;
  Quantidade: number;
  "Investimento (R$)": number | null;
  "Renda Mensal (R$)": number | null;
  "DY (%)": number | null;
  "P/VP": number | null;
}

export function Carteira({ onPersist }: { onPersist: () => void }) {
  const [itens, setItens] = useState([
    { ticker: "KNRI11", quantidade: 100 },
    { ticker: "MXRF11", quantidade: 100 },
  ]);
  const [linhas, setLinhas] = useState<Linha[]>([]);
  const [totais, setTotais] = useState<Record<string, number> | null>(null);
  const [erros, setErros] = useState<{ ticker: string; erro: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  function setItem(i: number, patch: Partial<{ ticker: string; quantidade: number }>) {
    setItens((xs) => xs.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  }

  function pickTicker(tk: string) {
    setItens((xs) => {
      if (xs.some((x) => x.ticker === tk)) return xs;
      const vazio = xs.findIndex((x) => !x.ticker.trim());
      if (vazio >= 0) return xs.map((x, i) => (i === vazio ? { ...x, ticker: tk } : x));
      return [...xs, { ticker: tk, quantidade: 100 }];
    });
  }

  async function montar() {
    const validos = itens.filter((x) => x.ticker.trim());
    if (!validos.length) return;
    setLoading(true);
    setErro(null);
    try {
      const d = await api.carteira(validos.map((x) => ({ ticker: x.ticker.trim().toUpperCase(), quantidade: x.quantidade })));
      setLinhas(d.linhas as unknown as Linha[]);
      setTotais(d.totais);
      setErros(d.erros);
      onPersist();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao montar a carteira.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Múltiplos FIIs · coleta em sequência">Carteira</Heading>

      <Panel title="Ativos">
        <div className="flex flex-col gap-2">
          {itens.map((it, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className="field flex-1"
                value={it.ticker}
                placeholder="Ticker"
                onChange={(e) => setItem(i, { ticker: e.target.value.toUpperCase() })}
              />
              <input
                type="number"
                className="field w-28"
                value={it.quantidade}
                onChange={(e) => setItem(i, { quantidade: +e.target.value })}
              />
              <button
                className="btn-ghost"
                onClick={() => setItens((xs) => xs.filter((_, idx) => idx !== i))}
                disabled={itens.length <= 1}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <button className="btn-ghost" onClick={() => setItens((xs) => [...xs, { ticker: "", quantidade: 100 }])}>
            ＋ ativo
          </button>
          <button className="btn-amber" onClick={montar} disabled={loading}>▸ Montar carteira</button>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={itens.map((x) => x.ticker)} onPick={pickTicker} />
        </div>
        {loading && <div className="mt-3"><Loader label="coletando via playwright" /></div>}
        {erro && <div className="mt-3"><Note kind="error">⚠ {erro}</Note></div>}
      </Panel>

      {erros.map((e) => (
        <Note key={e.ticker} kind="error">⚠ {e.ticker}: {e.erro}</Note>
      ))}

      {totais && (
        <FadeIn>
          <Panel title="Totais">
            <div className="grid grid-cols-1 gap-y-4 sm:grid-cols-3">
              <Stat label="Investimento total" value={brl(totais.total_investido)} tone="azure" />
              <Stat label="Renda mensal total" value={brl(totais.total_renda_mensal)} tone="up" />
              <Stat label="DY médio ponderado" value={pct(totais.dy_medio_ponderado)} tone="amber" />
            </div>
          </Panel>
        </FadeIn>
      )}

      {linhas.length > 0 && (
        <Panel title="Composição">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse">
              <thead>
                <tr className="border-b border-line-strong">
                  {["FII", "Tipo", "Preço", "Qtd", "Investimento", "Renda mensal", "DY", "P/VP"].map((h) => (
                    <th key={h} className="eyebrow px-2 py-2 text-left">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="tnum font-mono text-[0.8rem]">
                {linhas.map((l) => (
                  <tr key={l.FII} className="border-b border-line hover:bg-ink-800/60">
                    <td className="px-2 py-2 font-semibold text-paper">{l.FII}</td>
                    <td className="px-2 py-2 text-paper-mute">{l.Tipo}</td>
                    <td className="px-2 py-2 text-amber">{brl(l["Preço (R$)"])}</td>
                    <td className="px-2 py-2 text-paper-dim">{num(l.Quantidade, 0)}</td>
                    <td className="px-2 py-2 text-azure">{brl(l["Investimento (R$)"])}</td>
                    <td className="px-2 py-2 text-up">{brl(l["Renda Mensal (R$)"])}</td>
                    <td className="px-2 py-2 text-up">{pct(l["DY (%)"])}</td>
                    <td className="px-2 py-2 text-paper-dim">{num(l["P/VP"])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {!loading && !totais && linhas.length === 0 && <Empty>Monte a carteira para ver os totais.</Empty>}
    </div>
  );
}
