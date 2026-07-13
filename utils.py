"""
utils.py — Cálculos financeiros, formatação e lógica de classificação
======================================================================
Centraliza toda a matemática do dashboard para manter app.py limpo.
"""

import math
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES GLOBAIS
# ══════════════════════════════════════════════════════════════════════════════

IPCA_MAIS_GLOBAL = 0.07   # 7% ao ano (spread fixo IPCA+)

# Prêmios padrão por grade de risco (usados se não houver override manual)
# HIGH GRADE = 1%, MIDDLE GRADE = 3%, HIGH YIELD = 5%
PREMIO_DEFAULT = 0.01

# Grades de risco pré-definidas para tickers conhecidos
PREMIO_KNOWN: dict[str, float] = {
    # HIGH GRADE
    "XPML11": 0.01, "BTLG11": 0.01, "KNRI11": 0.01,
    "LVBI11": 0.01, "HGLG11": 0.01, "HSLG11": 0.01,
    # MIDDLE GRADE
    "GARE11": 0.03, "GGRC11": 0.03, "BTCI11": 0.03,
    "TRXF11": 0.03, "RBVA11": 0.03, "KNCR11": 0.03, "SNAG11": 0.03,
    # HIGH YIELD
    "RECR11": 0.05, "VGHF11": 0.05, "MXRF11": 0.05, "PORD11": 0.05,
}


# ══════════════════════════════════════════════════════════════════════════════
# FORMATAÇÃO BR
# ══════════════════════════════════════════════════════════════════════════════

def fmt_brl(value, decimals: int = 2) -> str:
    """Ex: 1234.5 → 'R$ 1.234,50' | None/nan → 'N/D'"""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/D"
    s = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def fmt_pct(value, decimals: int = 2) -> str:
    """Ex: 8.72 → '8,72%' (valor já em %) | 0.0872 → '0,09%' (não converte automaticamente)"""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/D"
    return f"{value:.{decimals}f}%".replace(".", ",")


def fmt_pct_dec(value, decimals: int = 2) -> str:
    """Formata decimal para %. Ex: 0.0872 → '8,72%'"""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/D"
    return fmt_pct(value * 100, decimals)


def fmt_num(value, decimals: int = 2) -> str:
    """Número simples com separador BR. Ex: 1234.5 → '1.234,50'"""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/D"
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_cell(val, prefix: str = "R$ ", decimals: int = 2, suffix: str = "") -> str:
    """Formata célula para exibição em tabela (None/nan → 'N/D')."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "N/D"
    s = f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefix}{s}{suffix}"


def _is_valid(v) -> bool:
    """Checa se o valor é um número válido (não None, não nan)."""
    if v is None:
        return False
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# LÓGICA DE PRÊMIO DE RISCO
# ══════════════════════════════════════════════════════════════════════════════

def get_premio(ticker: str, override: dict | None = None) -> float:
    """
    Retorna o prêmio de risco decimal para um ticker.
    Prioridade: override manual > dicionário de conhecidos > default (1%).
    """
    if override and ticker in override:
        return override[ticker]
    return PREMIO_KNOWN.get(ticker, PREMIO_DEFAULT)


def get_grade_label(premio: float) -> str:
    """Converte o valor decimal do prêmio para label legível."""
    if premio <= 0.01: return "High Grade (1%)"
    if premio <= 0.03: return "Middle Grade (3%)"
    return "High Yield (5%)"


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 1 — SIMULAÇÃO DE APORTE MENSAL
# ══════════════════════════════════════════════════════════════════════════════

def simular_aporte(
    preco: float,
    dy_anual_pct: float,
    cotas_por_mes: int,
    meses: int,
) -> pd.DataFrame:
    """
    Simula acúmulo de cotas e renda mês a mês.

    FÓRMULAS:
      Dividendo mensal/cota = Preço × (DY_anual% / 100 / 12)
        → DY anual = dividendos_12m / preço, logo dividendo_mensal = preço × DY/12

      Renda mensal = cotas_acumuladas × dividendo_mensal/cota

      Total investido = cotas_acumuladas × preço  (sem reinvestimento de dividendos)

    PREMISSAS:
      • Preço da cota constante durante toda a projeção
      • DY anual constante (sem variação de mercado)
      • Dividendos NÃO são reinvestidos
      • Aportes ocorrem no início de cada mês
    """
    dy_mensal = (dy_anual_pct / 100) / 12
    div_mensal_por_cota = preco * dy_mensal

    registros = []
    cotas_acum = 0
    renda_acum = 0.0

    for mes in range(1, meses + 1):
        cotas_acum += cotas_por_mes
        total_inv   = cotas_acum * preco
        renda_mes   = cotas_acum * div_mensal_por_cota
        renda_acum += renda_mes

        registros.append({
            "Mês":                 mes,
            "Cotas Acumuladas":    cotas_acum,
            "Total Investido (R$)":round(total_inv,  2),
            "Renda Mensal (R$)":   round(renda_mes,  2),
            "Renda Acumulada (R$)":round(renda_acum, 2),
            "Patrimônio (R$)":     round(total_inv,  2),
        })

    return pd.DataFrame(registros)


def resumo_simulacao(df: pd.DataFrame) -> dict:
    """Métricas do último mês da simulação."""
    u = df.iloc[-1]
    return {
        "cotas_total":        int(u["Cotas Acumuladas"]),
        "total_investido":    u["Total Investido (R$)"],
        "renda_mensal_final": u["Renda Mensal (R$)"],
        "renda_acumulada":    u["Renda Acumulada (R$)"],
        "patrimonio_final":   u["Patrimônio (R$)"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 2 — CARTEIRA COM MÚLTIPLOS FIIs
# ══════════════════════════════════════════════════════════════════════════════

def montar_carteira(fiis: list[dict]) -> pd.DataFrame:
    """
    Constrói tabela de carteira a partir de lista de dicts de FIIs.

    FÓRMULAS:
      Investimento    = preço × quantidade
      Proventos/cota  = dividendo_12m (R$) / 12   → dividendo mensal por cota
      Renda Mensal    = proventos/cota × quantidade

    Cada item deve ter: ticker, preco, dy, dividendo_12m, pvp, tipo, quantidade
    Campos ausentes geram N/D na linha, sem quebrar a tabela.
    """
    linhas = []
    for fii in fiis:
        preco       = fii.get("preco")
        dy          = fii.get("dy")
        div12m      = fii.get("dividendo_12m")
        qtd         = fii.get("quantidade", 0)
        ticker      = fii.get("ticker", "?")

        # Sanitiza NaN de volta para None para consistência
        if isinstance(preco,  float) and math.isnan(preco):  preco  = None
        if isinstance(dy,     float) and math.isnan(dy):     dy     = None
        if isinstance(div12m, float) and math.isnan(div12m): div12m = None

        investimento  = preco * qtd         if _is_valid(preco)  else None
        proventos     = div12m / 12         if _is_valid(div12m) else None
        renda_mensal  = proventos * qtd     if _is_valid(proventos) else None
        pvp           = fii.get("pvp")
        if isinstance(pvp, float) and math.isnan(pvp): pvp = None

        linhas.append({
            "FII":                ticker,
            "Tipo":               fii.get("tipo", "Indefinido"),
            "Preço (R$)":          preco,
            "Quantidade":          qtd,
            "Investimento (R$)":   investimento,
            "Proventos/cota (R$)": proventos,
            "Renda Mensal (R$)":   renda_mensal,
            "DY (%)":              dy,
            "P/VP":               pvp,
        })

    return pd.DataFrame(linhas)


def totais_carteira(df: pd.DataFrame) -> dict:
    """
    Totais e DY médio ponderado pelo capital investido.

    DY médio ponderado:
      DY_médio = Σ(renda_mensal_i × 12) / Σ(investimento_i) × 100
    """
    total_inv   = df["Investimento (R$)"].sum(skipna=True)
    total_renda = df["Renda Mensal (R$)"].sum(skipna=True)
    dy_medio    = (total_renda * 12 / total_inv * 100) if total_inv > 0 else None
    return {
        "total_investido":      total_inv,
        "total_renda_mensal":   total_renda,
        "dy_medio_ponderado":   dy_medio,
    }


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 3 — PREÇO TETO (lógica fiel ao fiis.py)
# ══════════════════════════════════════════════════════════════════════════════

def calcular_preco_teto_row(row: dict) -> dict:
    """
    Calcula preço teto para um FII individual.

    FÓRMULAS (fiel ao fiis.py):
      DIVIDENDO 12M (R$) = PREÇO × DIVIDENDO 12M %
      TAXA REQUERIDA     = IPCA+ + PRÊMIO         ← nota: IPCA entra como info, não na taxa!
      PREÇO TETO         = DIVIDENDO 12M (R$) / TAXA REQUERIDA
      MARGEM DE SEG.     = (PREÇO TETO - PREÇO) / PREÇO

    NOTA IMPORTANTE: no fiis.py original, a TAXA REQUERIDA é IPCA+ + PRÊMIO.
    O IPCA do fundo (papel/tijolo) não entra diretamente na taxa — ele é
    informativo, representando quanto do rendimento é protegido contra inflação.
    Isso difere de outras metodologias que somam IPCA + IPCA+ + Prêmio.
    Aqui mantemos fidelidade ao fiis.py.

    Parâmetros esperados no dict:
      preco, dy (%), dividendo_12m (R$), ipca (decimal), ipca_mais (decimal), premio (decimal)
    """
    preco    = row.get("preco")
    div12m   = row.get("dividendo_12m")
    ipca     = row.get("ipca", math.nan)
    ipca_mais= row.get("ipca_mais", IPCA_MAIS_GLOBAL)
    premio   = row.get("premio", PREMIO_DEFAULT)
    dy_pct   = row.get("dy")

    # Sanitiza
    if isinstance(preco,  float) and math.isnan(preco):  preco  = None
    if isinstance(div12m, float) and math.isnan(div12m): div12m = None
    if isinstance(ipca,   float) and math.isnan(ipca):   ipca   = None
    if isinstance(dy_pct, float) and math.isnan(dy_pct): dy_pct = None

    # Recalcula dividendo_12m se ausente (preço × DY%)
    if div12m is None and _is_valid(preco) and _is_valid(dy_pct):
        div12m = preco * (dy_pct / 100)

    # Taxa requerida = IPCA+ + Prêmio (em decimal)
    taxa = ipca_mais + premio if _is_valid(ipca_mais) and _is_valid(premio) else None

    # Preço teto
    preco_teto = div12m / taxa if (_is_valid(div12m) and _is_valid(taxa) and taxa > 0) else None

    # Margem de segurança
    margem = ((preco_teto - preco) / preco) if (_is_valid(preco_teto) and _is_valid(preco) and preco > 0) else None

    return {
        "ipca":              ipca,
        "ipca_mais":         ipca_mais,
        "premio":            premio,
        "taxa_requerida":    taxa,
        "dividendo_12m_calc":div12m,
        "preco_teto":        preco_teto,
        "margem_seguranca":  margem,
    }


def tabela_preco_teto(fiis: list[dict]) -> pd.DataFrame:
    """
    Gera DataFrame completo de preço teto para lista de FIIs.
    Colunas espelhadas do fiis.py: FII, P/VP, PREÇO, DY 12M %, DY 12M R$,
    IPCA, IPCA+, PRÊMIO, TAXA REQ., PREÇO TETO, MARGEM SEG.
    """
    linhas = []
    for fii in fiis:
        calc = calcular_preco_teto_row(fii)
        pvp  = fii.get("pvp")
        if isinstance(pvp, float) and math.isnan(pvp): pvp = None

        linhas.append({
            "FII":                fii.get("ticker", "?"),
            "Tipo":               fii.get("tipo", "Indefinido"),
            "Grade":              get_grade_label(fii.get("premio", PREMIO_DEFAULT)),
            "P/VP":              pvp,
            "Preço (R$)":         fii.get("preco") if _is_valid(fii.get("preco")) else None,
            "DY 12M (%)":         fii.get("dy")    if _is_valid(fii.get("dy"))    else None,
            "Dividendo 12M (R$)": calc["dividendo_12m_calc"],
            "IPCA":               calc["ipca"],
            "IPCA+":              calc["ipca_mais"],
            "Prêmio":             calc["premio"],
            "Taxa Req.":          calc["taxa_requerida"],
            "Preço Teto (R$)":    calc["preco_teto"],
            "Margem Seg. (%)":    calc["margem_seguranca"] * 100
                                  if _is_valid(calc["margem_seguranca"]) else None,
        })

    return pd.DataFrame(linhas)
