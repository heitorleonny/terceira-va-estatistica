import { useState } from "react";
import { api, type Fii } from "../lib/api";
import { brl, num, pct, pctDec, signed } from "../lib/format";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { Empty, FadeIn, Heading, Loader, Note, Panel, Tag, TickerChips } from "../components/ui";

function gradeTone(grade: string): "up" | "amber" | "down" {
  if (grade.startsWith("High Grade")) return "up";
  if (grade.startsWith("Middle")) return "amber";
  return "down";
}

export function PrecoTeto({ onPersist }: { onPersist: () => void }) {
  const [raw, setRaw] = useState("MXRF11, KNRI11, HGLG11");
  const [rows, setRows] = useState<Fii[]>([]);
  const [erros, setErros] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  async function calcular() {
    const tickers = raw.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
    if (!tickers.length) return;
    setLoading(true);
    setErros([]);
    const ok: Fii[] = [];
    const bad: string[] = [];
    for (const tk of tickers) {
      try {
        ok.push(await api.fii(tk));
      } catch (e) {
        bad.push(`${tk}: ${e instanceof Error ? e.message : "erro"}`);
      }
    }
    ok.sort((a, b) => (b.margem_seguranca ?? -1e9) - (a.margem_seguranca ?? -1e9));
    setRows(ok);
    setErros(bad);
    setLoading(false);
    onPersist();
  }

  const selecionados = raw.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean);
  function toggleTicker(tk: string) {
    const next = selecionados.includes(tk) ? selecionados.filter((t) => t !== tk) : [...selecionados, tk];
    setRaw(next.join(", "));
  }

  const maxAbs = Math.max(1, ...rows.map((r) => Math.abs(r.margem_seguranca ?? 0)));

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Dividendo 12M ÷ (IPCA+ + prêmio)">Preço Teto</Heading>

      <Panel title="Tickers" meta="separados por vírgula">
        <div className="flex flex-wrap items-end gap-3">
          <input className="field flex-1" style={{ minWidth: 260 }} value={raw} onChange={(e) => setRaw(e.target.value.toUpperCase())} />
          <button className="btn-amber h-[38px]" onClick={calcular} disabled={loading}>▸ Calcular</button>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={selecionados} onPick={toggleTicker} />
        </div>
        {loading && <div className="mt-3"><Loader label="coletando via playwright" /></div>}
      </Panel>

      {erros.map((e) => <Note key={e} kind="error">⚠ {e}</Note>)}

      {rows.length > 0 && (
        <FadeIn>
          <Panel title="Ranking por margem de segurança">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse">
                <thead>
                  <tr className="border-b border-line-strong">
                    {["FII", "Grade", "Preço", "DY", "Div. 12M", "Taxa req.", "Preço teto", "Margem"].map((h) => (
                      <th key={h} className="eyebrow px-2 py-2 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="tnum font-mono text-[0.8rem]">
                  {rows.map((r) => {
                    const m = r.margem_seguranca;
                    const w = m != null ? (Math.abs(m) / maxAbs) * 100 : 0;
                    return (
                      <tr key={r.ticker} className="border-b border-line hover:bg-ink-800/60">
                        <td className="px-2 py-2 font-semibold text-paper">{r.ticker}</td>
                        <td className="px-2 py-2"><Tag tone={gradeTone(r.grade)}>{r.grade.split(" (")[0]}</Tag></td>
                        <td className="px-2 py-2 text-amber">{brl(r.preco)}</td>
                        <td className="px-2 py-2 text-up">{pct(r.dy)}</td>
                        <td className="px-2 py-2 text-paper-dim">{brl(r.dividendo_12m, 4)}</td>
                        <td className="px-2 py-2 text-paper-dim">{pctDec(r.taxa_requerida, 0)}</td>
                        <td className="px-2 py-2 text-paper">{brl(r.preco_teto)}</td>
                        <td className="px-2 py-2">
                          <div className="flex items-center gap-2">
                            <span className={`w-16 ${m != null && m >= 0 ? "text-up" : "text-down"}`}>{signed(m)}</span>
                            <span className="hidden h-1.5 flex-1 rounded-full bg-ink-700 sm:block">
                              <span
                                className={`block h-full rounded-full ${m != null && m >= 0 ? "bg-up" : "bg-down"}`}
                                style={{ width: `${w}%` }}
                              />
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 font-mono text-micro text-paper-mute">
              Taxa requerida = IPCA+ (fixo) + prêmio por grade. O IPCA do fundo é informativo e não
              entra na taxa (fiel ao fiis.py).
            </p>
          </Panel>
        </FadeIn>
      )}

      {!loading && rows.length === 0 && erros.length === 0 && <Empty>Informe tickers e calcule o preço teto.</Empty>}
    </div>
  );
}
