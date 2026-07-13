import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./lib/api";
import { AnaliseEmpirica } from "./views/AnaliseEmpirica";
import { CardsView } from "./views/Cards";
import { Historico } from "./views/Historico";
import { Simulacao } from "./views/Simulacao";
import { Carteira } from "./views/Carteira";
import { PrecoTeto } from "./views/PrecoTeto";
import { Comparar } from "./views/Comparar";

type ViewKey =
  | "analise" | "comparar" | "cards" | "historico" | "simulacao" | "carteira" | "preco-teto";

const NAV: { key: ViewKey; code: string; label: string; hint: string }[] = [
  { key: "analise", code: "01", label: "Análise Empírica", hint: "Retornos · Normal · Cauda" },
  { key: "comparar", code: "02", label: "Comparar", hint: "Séries · correlação" },
  { key: "cards", code: "03", label: "Cards", hint: "Destaques por margem" },
  { key: "historico", code: "04", label: "Histórico", hint: "Consultas · SQLite" },
  { key: "simulacao", code: "05", label: "Simulação", hint: "Aporte mensal" },
  { key: "carteira", code: "06", label: "Carteira", hint: "Múltiplos FIIs" },
  { key: "preco-teto", code: "07", label: "Preço Teto", hint: "Margem de segurança" },
];

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="tnum font-mono text-micro text-paper-dim">
      {new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      }).format(now)}
    </span>
  );
}

export default function App() {
  const [view, setView] = useState<ViewKey>("analise");
  const [health, setHealth] = useState<{ consultas: number; ipca_mais: number } | null>(null);
  const [reloadTicker, setReloadTicker] = useState<{ ticker: string; nonce: number } | null>(null);

  const refreshHealth = () =>
    api.health().then((h) => setHealth({ consultas: h.consultas, ipca_mais: h.ipca_mais })).catch(() => {});

  useEffect(() => {
    refreshHealth();
  }, [view]);

  const active = NAV.find((n) => n.key === view)!;

  return (
    <div className="mx-auto grid min-h-screen max-w-[1500px] grid-cols-1 md:grid-cols-[236px_1fr]">
      {/* ── Function rail ── */}
      <aside className="flex flex-col border-b border-line md:border-b-0 md:border-r">
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-4">
          <div className="grid h-8 w-8 place-items-center rounded-[3px] border border-amber/40 bg-amber/10">
            <span className="font-display text-lg font-semibold text-amber">F</span>
          </div>
          <div className="leading-tight">
            <div className="font-display text-[1.02rem] font-semibold tracking-tight text-paper">
              FII Analyzer
            </div>
            <div className="eyebrow !text-[0.6rem]">Terminal · v2</div>
          </div>
        </div>

        <nav className="flex gap-1 overflow-x-auto px-2 py-2 md:flex-col md:gap-0.5 md:py-3">
          {NAV.map((n) => {
            const on = n.key === view;
            return (
              <button
                key={n.key}
                onClick={() => setView(n.key)}
                className={`group flex min-w-[150px] items-center gap-3 rounded-[2px] px-3 py-2 text-left transition-colors md:min-w-0 ${
                  on ? "bg-amber/10" : "hover:bg-ink-800"
                }`}
              >
                <span
                  className={`font-mono text-micro ${on ? "text-amber" : "text-paper-mute group-hover:text-paper-dim"}`}
                >
                  {n.code}
                </span>
                <span className="flex flex-col">
                  <span
                    className={`font-mono text-[0.78rem] uppercase tracking-[0.06em] ${
                      on ? "text-paper" : "text-paper-dim group-hover:text-paper"
                    }`}
                  >
                    {n.label}
                  </span>
                  <span className="hidden font-mono text-[0.6rem] text-paper-mute md:block">{n.hint}</span>
                </span>
                {on && <span className="ml-auto hidden h-3 w-[2px] bg-amber md:block" />}
              </button>
            );
          })}
        </nav>

        <div className="mt-auto hidden gap-2 border-t border-line px-5 py-3 md:flex md:flex-col">
          <div className="flex items-center justify-between">
            <span className="eyebrow">API</span>
            <span className="flex items-center gap-1.5 font-mono text-micro text-up">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-up" /> online
            </span>
          </div>
          <div className="flex items-center justify-between font-mono text-micro text-paper-mute">
            <span>consultas</span>
            <span className="tnum text-paper-dim">{health?.consultas ?? "—"}</span>
          </div>
          <div className="flex items-center justify-between font-mono text-micro text-paper-mute">
            <span>ipca+</span>
            <span className="tnum text-paper-dim">
              {health ? (health.ipca_mais * 100).toFixed(0) + "%" : "—"}
            </span>
          </div>
        </div>
      </aside>

      {/* ── Workspace ── */}
      <main className="flex min-w-0 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-2.5">
          <div className="flex items-center gap-2 font-mono text-micro uppercase tracking-[0.1em]">
            <span className="text-amber">{active.code}</span>
            <span className="text-paper-mute">/</span>
            <span className="text-paper-dim">{active.label}</span>
          </div>
          <div className="flex items-center gap-4">
            <Clock />
          </div>
        </header>

        <div className="min-w-0 flex-1 px-5 py-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={view}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.28, ease: "easeOut" }}
            >
              {view === "analise" && (
                <AnaliseEmpirica reload={reloadTicker} onPersist={refreshHealth} />
              )}
              {view === "comparar" && <Comparar onPersist={refreshHealth} />}
              {view === "cards" && <CardsView onPersist={refreshHealth} />}
              {view === "historico" && (
                <Historico
                  onPersist={refreshHealth}
                  onReload={(ticker) => {
                    setReloadTicker({ ticker, nonce: Date.now() });
                    setView("analise");
                  }}
                />
              )}
              {view === "simulacao" && <Simulacao onPersist={refreshHealth} />}
              {view === "carteira" && <Carteira onPersist={refreshHealth} />}
              {view === "preco-teto" && <PrecoTeto onPersist={refreshHealth} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
