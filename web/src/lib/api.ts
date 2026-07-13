// Cliente HTTP tipado para a API FastAPI (api.py). Usa URLs relativas (/api/…),
// que o Vite faz proxy para :8000 em dev e são servidas pelo próprio FastAPI em
// produção (build montado em web/dist).

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* mantém detail padrão */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ── Tipos ────────────────────────────────────────────────────────────────────

export interface Fii {
  ticker: string;
  preco: number | null;
  dy: number | null;
  pvp: number | null;
  tipo: string;
  dividendo_12m: number | null;
  premio: number;
  ipca: number | null;
  preco_teto: number | null;
  margem_seguranca: number | null;
  taxa_requerida: number | null;
  grade: string;
}

export interface Estatisticas {
  n: number;
  media_diaria: number | null;
  dp_diario: number | null;
  media_log_anual: number | null;
  sigma_anual: number | null;
  ultimo_preco: number | null;
  preco_minimo: number | null;
  preco_maximo: number | null;
}

export interface Analise {
  ticker: string;
  periodo: { inicio: string; fim: string; pregoes: number };
  serie: { data: string; close: number }[];
  estatisticas: Estatisticas;
  histograma: { x0: number; x1: number; centro: number; densidade: number }[] | null;
  normal: { x: number; y: number }[] | null;
  qq: {
    pontos: { teorico: number; amostral: number }[];
    reta: { x: number; y: number }[];
  };
  normalidade: {
    teste: string | null;
    estatistica: number | null;
    p_valor: number | null;
    n: number;
    normal: boolean | null;
  };
  dias_uteis_ano: number;
}

export interface Consulta {
  id: number;
  ticker: string;
  data_consulta: string;
  preco: number | null;
  dy: number | null;
  pvp: number | null;
  margem_seguranca: number | null;
  fonte: string;
  json_dados: string;
}

export interface CardItem {
  ticker: string;
  preco: number | null;
  dy: number | null;
  pvp: number | null;
  tipo: string;
  preco_teto: number | null;
  margem_seguranca: number | null;
  grade: string;
  erro: string | null;
}

export interface CardsConfig {
  cards_padrao: string[];
  cards_ativos: { ticker: string; visivel: boolean; ordem: number }[];
}

export interface SimResumo {
  cotas_total: number;
  total_investido: number;
  renda_mensal_final: number;
  renda_acumulada: number;
  patrimonio_final: number;
}

export interface AtivoComparado {
  ticker: string;
  serie: { data: string; close: number; base100: number | null }[];
  estatisticas: {
    n: number;
    ultimo_preco: number | null;
    retorno_total_pct: number | null;
    media_log_anual: number | null;
    sigma_anual: number | null;
  };
}

export interface Comparacao {
  periodo: { inicio: string; fim: string };
  ativos: AtivoComparado[];
  correlacao: { tickers: string[]; matriz: number[][]; observacoes: number } | null;
  erros: { ticker: string; erro: string }[];
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export const api = {
  health: () => req<{ status: string; consultas: number; ipca_mais: number }>("/api/health"),

  fii: (ticker: string) => req<Fii>(`/api/fii/${encodeURIComponent(ticker)}`),

  analise: (ticker: string, inicio: string, fim: string) =>
    req<Analise>(`/api/analise/${encodeURIComponent(ticker)}?inicio=${inicio}&fim=${fim}`),

  comparar: (tickers: string[], inicio: string, fim: string) =>
    req<Comparacao>(`/api/comparar?tickers=${encodeURIComponent(tickers.join(","))}&inicio=${inicio}&fim=${fim}`),

  simular: (preco: number, dy: number, cotas: number, meses: number) =>
    req<{ resumo: SimResumo; serie: Record<string, number>[] }>("/api/simular", {
      method: "POST",
      body: JSON.stringify({ preco, dy, cotas_por_mes: cotas, meses }),
    }),

  carteira: (itens: { ticker: string; quantidade: number }[]) =>
    req<{ linhas: Record<string, unknown>[]; totais: Record<string, number>; erros: { ticker: string; erro: string }[] }>(
      "/api/carteira",
      { method: "POST", body: JSON.stringify({ itens }) },
    ),

  consultas: (ticker?: string, limite = 100) =>
    req<Consulta[]>(`/api/consultas?limite=${limite}${ticker ? `&ticker=${ticker}` : ""}`),

  consulta: (id: number) =>
    req<Consulta & { dados: Record<string, unknown> }>(`/api/consultas/${id}`),

  apagarConsulta: (id: number) =>
    req<{ ok: boolean }>(`/api/consultas/${id}`, { method: "DELETE" }),

  cardsConfig: () => req<CardsConfig>("/api/cards/config"),

  salvarCardsConfig: (cfg: CardsConfig) =>
    req<CardsConfig>("/api/cards/config", { method: "PUT", body: JSON.stringify(cfg) }),

  cardsRefresh: () => req<{ cards: CardItem[]; config: CardsConfig }>("/api/cards/refresh", { method: "POST" }),
};
