import { useEffect, useState } from "react";
import { api, ApiError, type CardItem, type CardsConfig } from "../lib/api";
import { brl, num, pct, signed } from "../lib/format";
import { TICKERS_SUGERIDOS } from "../lib/tickers";
import { Empty, FadeIn, Heading, Loader, Note, Panel, Stat, Tag, TickerChips } from "../components/ui";

function gradeTone(grade: string): "up" | "amber" | "down" {
  if (grade.startsWith("High Grade")) return "up";
  if (grade.startsWith("Middle")) return "amber";
  return "down";
}

export function CardsView({ onPersist }: { onPersist: () => void }) {
  const [config, setConfig] = useState<CardsConfig | null>(null);
  const [cards, setCards] = useState<CardItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [novo, setNovo] = useState("");

  useEffect(() => {
    api.cardsConfig().then(setConfig).catch(() => {});
  }, []);

  async function refresh() {
    setLoading(true);
    setErro(null);
    try {
      const r = await api.cardsRefresh();
      setCards(r.cards);
      setConfig(r.config);
      onPersist();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao coletar os cards.");
    } finally {
      setLoading(false);
    }
  }

  async function adicionar() {
    const tk = novo.trim().toUpperCase();
    if (!tk || !config) return;
    const existe = config.cards_ativos.some((c) => c.ticker === tk);
    const cfg: CardsConfig = existe
      ? { ...config, cards_ativos: config.cards_ativos.map((c) => (c.ticker === tk ? { ...c, visivel: true } : c)) }
      : {
          ...config,
          cards_ativos: [
            ...config.cards_ativos,
            { ticker: tk, visivel: true, ordem: Math.max(0, ...config.cards_ativos.map((c) => c.ordem)) + 1 },
          ],
        };
    const saved = await api.salvarCardsConfig(cfg);
    setConfig(saved);
    setNovo("");
  }

  async function remover(tk: string) {
    if (!config) return;
    const cfg = { ...config, cards_ativos: config.cards_ativos.filter((c) => c.ticker !== tk) };
    const saved = await api.salvarCardsConfig(cfg);
    setConfig(saved);
    setCards((cs) => cs.filter((c) => c.ticker !== tk));
  }

  const visiveis = (config?.cards_ativos ?? []).filter((c) => c.visivel).sort((a, b) => a.ordem - b.ordem);

  return (
    <div className="flex flex-col gap-5">
      <Heading kicker="Destaques por margem de segurança">Cards de FIIs</Heading>

      <Panel title="Configuração" meta="cards_config.json">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-1 flex-col gap-1" style={{ minWidth: 200 }}>
            <span className="eyebrow">Adicionar card (ticker)</span>
            <input
              className="field"
              value={novo}
              placeholder="BTLG11"
              onChange={(e) => setNovo(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && adicionar()}
            />
          </label>
          <button className="btn-ghost h-[38px]" onClick={adicionar}>＋ Adicionar</button>
          <button className="btn-amber h-[38px]" onClick={refresh} disabled={loading}>
            {loading ? "…" : "↻ Carregar / atualizar"}
          </button>
        </div>
        <div className="mt-3">
          <TickerChips tickers={TICKERS_SUGERIDOS} selected={[novo]} onPick={setNovo} />
        </div>
        {visiveis.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {visiveis.map((c) => (
              <button key={c.ticker} onClick={() => remover(c.ticker)} className="group" title="remover">
                <Tag tone="line">
                  {c.ticker}
                  <span className="ml-1 text-paper-mute group-hover:text-down">✕</span>
                </Tag>
              </button>
            ))}
          </div>
        )}
      </Panel>

      {loading && <Panel><Loader label="coletando indicadores via playwright" /></Panel>}
      {erro && <Note kind="error">⚠ {erro}</Note>}

      {!loading && cards.length === 0 && !erro && (
        <Empty>Clique em “Carregar / atualizar” para buscar os indicadores dos cards.</Empty>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.slice(0, 6).map((c, i) => (
          <FadeIn key={c.ticker} delay={i * 0.04}>
            {c.erro ? (
              <Panel title={c.ticker}>
                <Note kind="error">⚠ {c.erro}</Note>
              </Panel>
            ) : (
              <div className="panel overflow-hidden">
                <div className="flex items-center justify-between border-b border-line px-4 py-3">
                  <div className="flex items-baseline gap-2">
                    <span className="font-display text-xl font-semibold text-paper">{c.ticker}</span>
                    <span className="font-mono text-micro uppercase text-paper-mute">{c.tipo}</span>
                  </div>
                  <Tag tone={gradeTone(c.grade)}>{c.grade.split(" (")[0]}</Tag>
                </div>
                <div className="grid grid-cols-2 gap-y-4 p-4">
                  <Stat label="Preço" value={brl(c.preco)} tone="amber" />
                  <Stat label="DY 12M" value={pct(c.dy)} tone="up" />
                  <Stat label="P/VP" value={num(c.pvp)} />
                  <Stat label="Preço teto" value={brl(c.preco_teto)} />
                </div>
                <div className="flex items-center justify-between border-t border-line px-4 py-3">
                  <span className="eyebrow">Margem de segurança</span>
                  <span
                    className={`tnum font-mono text-lg ${
                      c.margem_seguranca != null && c.margem_seguranca >= 0 ? "text-up" : "text-down"
                    }`}
                  >
                    {signed(c.margem_seguranca)}
                  </span>
                </div>
                <button
                  onClick={() => remover(c.ticker)}
                  className="w-full border-t border-line py-2 font-mono text-micro uppercase tracking-[0.1em] text-paper-mute hover:bg-down/5 hover:text-down"
                >
                  remover card
                </button>
              </div>
            )}
          </FadeIn>
        ))}
      </div>
    </div>
  );
}
