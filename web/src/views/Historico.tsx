import { useEffect, useState } from "react";
import { api, type Consulta } from "../lib/api";
import { brl, dateTime, num, pct, signed } from "../lib/format";
import { downloadCsv } from "../lib/download";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { Empty, Heading, Loader, Panel, Tag, TickerChips } from "../components/ui";

export function Historico({
  onReload,
  onPersist,
}: {
  onReload: (ticker: string) => void;
  onPersist: () => void;
}) {
  const [registros, setRegistros] = useState<Consulta[]>([]);
  const [filtro, setFiltro] = useState("");
  const [loading, setLoading] = useState(false);

  async function carregar(tk = filtro) {
    setLoading(true);
    try {
      setRegistros(await api.consultas(tk.trim().toUpperCase() || undefined, 200));
    } finally {
      setLoading(false);
    }
  }

  function filtrarPor(tk: string) {
    setFiltro(tk);
    carregar(tk);
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function apagar(id: number) {
    await api.apagarConsulta(id);
    setRegistros((r) => r.filter((x) => x.id !== id));
    onPersist();
  }

  function exportar() {
    downloadCsv("historico_consultas.csv", [
      ["id", "data_consulta", "ticker", "fonte", "preco", "dy", "pvp", "margem_seguranca"],
      ...registros.map((r) => [r.id, r.data_consulta, r.ticker, r.fonte, r.preco ?? "", r.dy ?? "", r.pvp ?? "", r.margem_seguranca ?? ""]),
    ]);
  }

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Persistência · SQLite (fii_dashboard.db)">Histórico de Consultas</Heading>

      <Panel
        title="Consultas gravadas"
        meta={`${registros.length} registros`}
        right={
          <div className="flex items-center gap-2">
            <input
              className="field !w-36 !py-1.5"
              placeholder="filtrar ticker"
              value={filtro}
              onChange={(e) => setFiltro(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && carregar()}
            />
            <button className="btn-ghost" onClick={() => carregar()}>↻</button>
            <button className="btn-ghost" onClick={exportar}>⬇ CSV</button>
          </div>
        }
      >
        <div className="mb-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={[filtro]} onPick={filtrarPor} />
        </div>
        {loading ? (
          <Loader />
        ) : registros.length === 0 ? (
          <Empty>Nenhuma consulta gravada. Faça uma busca em qualquer módulo.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse">
              <thead>
                <tr className="border-b border-line-strong text-left">
                  {["ID", "Data / Hora", "Ticker", "Fonte", "Preço", "DY", "P/VP", "Margem", ""].map((h) => (
                    <th key={h} className="eyebrow whitespace-nowrap px-2 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="tnum font-mono text-[0.8rem]">
                {registros.map((r) => (
                  <tr key={r.id} className="group border-b border-line hover:bg-ink-800/60">
                    <td className="px-2 py-2 text-paper-mute">{r.id}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-paper-dim">{dateTime(r.data_consulta)}</td>
                    <td className="px-2 py-2 font-semibold text-paper">{r.ticker}</td>
                    <td className="px-2 py-2">
                      <Tag tone={r.fonte === "yfinance" ? "azure" : "amber"}>{r.fonte}</Tag>
                    </td>
                    <td className="px-2 py-2 text-amber">{brl(r.preco)}</td>
                    <td className="px-2 py-2 text-up">{pct(r.dy)}</td>
                    <td className="px-2 py-2 text-paper-dim">{num(r.pvp)}</td>
                    <td className={`px-2 py-2 ${r.margem_seguranca != null && r.margem_seguranca >= 0 ? "text-up" : "text-down"}`}>
                      {signed(r.margem_seguranca)}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex justify-end gap-1 opacity-40 transition-opacity group-hover:opacity-100">
                        <button
                          title="recarregar na Análise"
                          onClick={() => onReload(r.ticker)}
                          className="rounded-[2px] border border-line px-1.5 py-0.5 text-azure hover:border-azure/60"
                        >
                          ↩
                        </button>
                        <button
                          title="apagar"
                          onClick={() => apagar(r.id)}
                          className="rounded-[2px] border border-line px-1.5 py-0.5 text-down hover:border-down/60"
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
