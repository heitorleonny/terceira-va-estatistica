"""
scraper.py — Coleta de dados via Playwright (browser real)
===========================================================
Usa Playwright com Chromium headless para renderizar o JavaScript do
Investidor10 por completo — mesma abordagem do fiis.py original, agora
integrada ao dashboard Streamlit.

Por que Playwright e não requests+BeautifulSoup?
  O Investidor10 usa React + Cloudflare. Os cards de indicadores
  (cotação, DY, P/VP etc.) são renderizados via JavaScript após o
  carregamento da página. Requests só vê o HTML estático inicial,
  sem esses dados. O Playwright abre um navegador real, espera o JS
  executar, e aí extrai o texto completo — garantindo os dados.

Funções públicas:
  get_fii_data(ticker)      → dict com dados de um FII
  get_multiplos_fiis(list)  → list[dict] para múltiplos tickers em sequência
"""

import re
import math
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
IPCA_MAIS_GLOBAL = 0.07   # 7% fixo (IPCA+)
PAUSA_ENTRE_FIIS = 1.5    # segundos entre requests para não sobrecarregar o site

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ══════════════════════════════════════════════════════════════════════════════
# PARSING NUMÉRICO
# ══════════════════════════════════════════════════════════════════════════════

def br_to_float(valor) -> float:
    """
    Converte texto BR para float. Ex: "R$ 11,48" → 11.48, "8,72%" → 8.72
    Retorna math.nan para ausentes/inválidos.
    """
    if valor is None:
        return math.nan
    txt = str(valor).strip()
    txt = txt.replace("R$", "").replace("%", "").replace("\xa0", "").strip()
    if txt in ("", "-", "–", "N/A", "NaN", "n/d", "N/D"):
        return math.nan
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return math.nan


def percent_to_decimal(valor) -> float:
    """Converte percentual BR para decimal. "8,72" → 0.0872"""
    x = br_to_float(valor)
    return math.nan if pd.isna(x) else x / 100


# ══════════════════════════════════════════════════════════════════════════════
# EXTRAÇÃO DE CAMPOS DO TEXTO DA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════

def extrair_valor_por_rotulo(texto: str, rotulos: list[str]) -> str | None:
    """
    Extrai o primeiro valor numérico que apareça após um dos rótulos.

    Exemplo no texto da página:
      "Cotação R$ 10,48"  → rotulo="Cotação" → retorna "10,48"
      "DY 12M 8,72%"      → rotulo="DY 12M"  → retorna "8,72"

    Estratégia: regex com os rótulos em ordem de prioridade.
    O grupo capturado é sempre o número, sem R$ ou %.
    """
    texto_limpo = re.sub(r"\s+", " ", texto)

    for rotulo in rotulos:
        # Escapa caracteres especiais do rótulo (ex: "/" em "P/VP")
        rotulo_esc = re.escape(rotulo)
        padrao = rf"{rotulo_esc}\s*[:\-]?\s*(?:R\$)?\s*(-?[\d\.]+,[\d]+|[\d]+,[\d]+|[\d]+\.[\d]+|[\d]+)%?"
        m = re.search(padrao, texto_limpo, re.IGNORECASE)
        if m:
            return m.group(1)

    return None


def extrair_tipo_fundo(texto: str) -> str:
    """
    Extrai o tipo do fundo (tijolo, papel, híbrido, etc.) do texto da página.
    Retorna string em minúsculas ou "" se não encontrar.
    """
    texto_limpo = re.sub(r"\s+", " ", texto)
    padroes = [
        r"Tipo de fundo\s*[:\-]?\s*([A-Za-zÀ-ÿ\s]{3,30})",
        r"Tipo\s*[:\-]?\s*([A-Za-zÀ-ÿ\s]{3,20})",
        r"Segmento\s*[:\-]?\s*([A-Za-zÀ-ÿ\s]{3,30})",
    ]
    for padrao in padroes:
        m = re.search(padrao, texto_limpo, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # Pega só a primeira palavra relevante para evitar capturar texto demais
            primeira = raw.split()[0].lower() if raw.split() else ""
            if primeira in ("tijolo", "papel", "híbrido", "hibrido", "outro", "fof", "desenvolvimento"):
                return primeira
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# LÓGICA DE IPCA (portada do fiis.py original)
# ══════════════════════════════════════════════════════════════════════════════

def ipca_por_percentual_fii(percentual_fii: float) -> float:
    """
    Calcula o IPCA a usar no preço teto baseado na % de FII na carteira do fundo.
    Regra original do fiis.py:
      0%   – 25%  → IPCA = 0%    (fundo tijolo puro)
      25%  – 40%  → IPCA = 1,5%  (pouco papel)
      40%  – 60%  → IPCA = 2,5%  (misto)
      60%  – 75%  → IPCA = 3,5%  (majoritariamente papel)
      75%  – 100% → IPCA = 5%    (papel puro)
    """
    if pd.isna(percentual_fii):
        return math.nan
    if 0.00 <= percentual_fii < 0.25: return 0.000
    if 0.25 <= percentual_fii < 0.40: return 0.015
    if 0.40 <= percentual_fii < 0.60: return 0.025
    if 0.60 <= percentual_fii < 0.75: return 0.035
    if 0.75 <= percentual_fii <= 1.00: return 0.050
    return math.nan


def classificar_ipca(
    fii: str,
    tipo_fundo: str,
    percentual_ativo_fii: float,
    ipca_override: dict | None = None,
) -> float:
    """
    Define o IPCA correto para o FII:
    1. Sobrescrita manual (dicionário ipca_override)
    2. Tijolo → 0%
    3. Papel/Outro → escala pelo % de FII na carteira
    4. Fallback → escala pelo % de FII se disponível

    Parâmetros:
      fii                 : ticker do FII
      tipo_fundo          : string extraída da página ("tijolo", "papel", etc.)
      percentual_ativo_fii: % de FII na carteira (float 0-1) ou nan
      ipca_override       : dict {ticker: valor_decimal} para sobrescritas manuais
    """
    if ipca_override and fii in ipca_override:
        return ipca_override[fii]

    tipo = str(tipo_fundo).lower()

    if "tijolo" in tipo:
        return 0.00

    if "papel" in tipo or "outro" in tipo or "hibrido" in tipo or "híbrido" in tipo:
        return ipca_por_percentual_fii(percentual_ativo_fii)

    # Fallback: se tiver percentual, usa a escala
    if not pd.isna(percentual_ativo_fii):
        return ipca_por_percentual_fii(percentual_ativo_fii)

    return math.nan


# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

def _limpar_tela(page) -> None:
    """Remove modais e banners que bloqueiam o conteúdo da página."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
    try:
        page.evaluate("""
            () => {
                const banner = document.querySelector('#guest-user-banner-irpf');
                if (banner) banner.remove();
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) backdrop.remove();
                document.body.classList.remove('modal-open');
                document.body.style.overflow = 'auto';
                document.body.style.paddingRight = '0px';
            }
        """)
    except Exception:
        pass


def _extrair_percentual_fii_js(page) -> float:
    """
    Usa JavaScript no contexto do browser para localizar o elemento
    .legend-name com texto "FII" e retorna o .legend-value correspondente.

    Esse dado vem do gráfico de composição de ativos do fundo.
    Ex: se o fundo tem 80% em CRI, o percentual FII = 0.20.
    Retorna 1.00 (100% FII) como fallback conservador.
    """
    try:
        valor = page.evaluate("""
            () => {
                const nomes   = Array.from(document.querySelectorAll('.legend-name'));
                const valores = Array.from(document.querySelectorAll('.legend-value'));
                for (let i = 0; i < nomes.length; i++) {
                    if (nomes[i].innerText.trim().toUpperCase() === 'FII') {
                        return valores[i] ? valores[i].innerText.trim() : null;
                    }
                }
                return null;
            }
        """)
        if valor is None:
            return 1.00
        result = percent_to_decimal(valor)
        return result if not pd.isna(result) else 1.00
    except Exception:
        return 1.00


def _coletar_pagina(page, ticker: str, premio_override: dict, ipca_override: dict) -> dict:
    """
    Abre a página do FII no Investidor10 e extrai todos os dados.
    Encapsula a lógica central do fiis.py original.
    """
    url = f"https://investidor10.com.br/fiis/{ticker}/"
    page.goto(url, wait_until="networkidle", timeout=60_000)
    page.wait_for_timeout(3000)
    _limpar_tela(page)

    texto = page.locator("body").inner_text()

    pvp    = extrair_valor_por_rotulo(texto, ["P/VP", "P VP", "PVP"])
    preco  = extrair_valor_por_rotulo(texto, ["Cotação", "Valor atual", "Preço atual"])
    dy_12m = extrair_valor_por_rotulo(texto, [
        "Dividend Yield 12M", "Dividend Yield", "DY 12M", "Dividendos 12M",
    ])
    tipo_fundo          = extrair_tipo_fundo(texto)
    percentual_fii      = _extrair_percentual_fii_js(page)
    ipca                = classificar_ipca(ticker, tipo_fundo, percentual_fii, ipca_override)
    premio              = premio_override.get(ticker, premio_override.get("default", 0.01))

    return {
        "ticker":          ticker,
        "pvp":             br_to_float(pvp),
        "preco":           br_to_float(preco),
        "dy":              br_to_float(dy_12m),          # em %  ex: 8.72
        "dy_decimal":      percent_to_decimal(dy_12m),   # ex: 0.0872
        "dividendo_12m":   br_to_float(preco) * percent_to_decimal(dy_12m)
                           if br_to_float(preco) and not pd.isna(percent_to_decimal(dy_12m))
                           else math.nan,
        "tipo":            tipo_fundo or "Indefinido",
        "percentual_fii":  percentual_fii,
        "ipca":            ipca,
        "ipca_mais":       IPCA_MAIS_GLOBAL,
        "premio":          premio,
        "erro":            None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def get_fii_data(
    ticker: str,
    premio_override: dict | None = None,
    ipca_override:  dict | None  = None,
) -> dict:
    """
    Busca dados de um único FII via Playwright.

    Parâmetros:
      ticker          : ex "MXRF11"
      premio_override : dict {ticker: decimal} para prêmio personalizado
      ipca_override   : dict {ticker: decimal} para IPCA manual

    Retorna dict com:
      ticker, pvp, preco, dy (%), dy_decimal, dividendo_12m (R$),
      tipo, percentual_fii, ipca, ipca_mais, premio, erro
    """
    ticker = ticker.upper().strip()
    premio_override = premio_override or {"default": 0.01}
    ipca_override   = ipca_override   or {}

    resultado_erro = {
        "ticker": ticker, "pvp": math.nan, "preco": math.nan,
        "dy": math.nan, "dy_decimal": math.nan, "dividendo_12m": math.nan,
        "tipo": "Indefinido", "percentual_fii": math.nan,
        "ipca": math.nan, "ipca_mais": IPCA_MAIS_GLOBAL,
        "premio": premio_override.get(ticker, premio_override.get("default", 0.01)),
        "erro": None,
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        resultado_erro["erro"] = (
            "Playwright não instalado. Execute: "
            "pip install playwright && playwright install chromium"
        )
        return resultado_erro

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            resultado = _coletar_pagina(page, ticker, premio_override, ipca_override)
            browser.close()
        return resultado

    except Exception as exc:
        resultado_erro["erro"] = f"Erro ao coletar {ticker}: {exc}"
        return resultado_erro


def get_multiplos_fiis(
    tickers: list[str],
    premio_override: dict | None = None,
    ipca_override:  dict | None  = None,
    progress_callback=None,
) -> list[dict]:
    """
    Busca dados de múltiplos FIIs reutilizando um único browser/página
    (muito mais eficiente que abrir um browser por ticker).

    Parâmetros:
      tickers           : lista de tickers
      premio_override   : dict de prêmios personalizados
      ipca_override     : dict de IPCAs manuais
      progress_callback : função(ticker, idx, total) chamada a cada FII coletado
                          útil para atualizar barra de progresso no Streamlit

    Retorna lista de dicts (mesma estrutura de get_fii_data).
    """
    import time

    tickers = [t.upper().strip() for t in tickers]
    premio_override = premio_override or {"default": 0.01}
    ipca_override   = ipca_override   or {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{
            "ticker": t, "pvp": math.nan, "preco": math.nan,
            "dy": math.nan, "dy_decimal": math.nan, "dividendo_12m": math.nan,
            "tipo": "Indefinido", "percentual_fii": math.nan,
            "ipca": math.nan, "ipca_mais": IPCA_MAIS_GLOBAL,
            "premio": premio_override.get(t, 0.01),
            "erro": "Playwright não instalado. Execute: pip install playwright && playwright install chromium",
        } for t in tickers]

    resultados = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        for idx, ticker in enumerate(tickers):
            try:
                dado = _coletar_pagina(page, ticker, premio_override, ipca_override)
                resultados.append(dado)
                logger.info(f"[{ticker}] coletado com sucesso")
            except Exception as exc:
                logger.error(f"[{ticker}] erro: {exc}")
                resultados.append({
                    "ticker": ticker, "pvp": math.nan, "preco": math.nan,
                    "dy": math.nan, "dy_decimal": math.nan, "dividendo_12m": math.nan,
                    "tipo": "Indefinido", "percentual_fii": math.nan,
                    "ipca": ipca_override.get(ticker, math.nan),
                    "ipca_mais": IPCA_MAIS_GLOBAL,
                    "premio": premio_override.get(ticker, premio_override.get("default", 0.01)),
                    "erro": str(exc),
                })

            if progress_callback:
                progress_callback(ticker, idx + 1, len(tickers))

            if idx < len(tickers) - 1:
                time.sleep(PAUSA_ENTRE_FIIS)

        browser.close()

    return resultados
