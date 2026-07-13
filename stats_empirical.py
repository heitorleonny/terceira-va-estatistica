"""
stats_empirical.py — Análise estatística empírica dos retornos
==============================================================
Funções de cálculo (sem Streamlit) para a aba "Análise Empírica dos Retornos".

Conceitos estatísticos usados (documentados aqui para clareza acadêmica):

  • Preço de fechamento: o último preço negociado do FII em cada pregão. É a
    série "bruta" a partir da qual tudo é derivado.

  • Log-retorno diário: r_t = ln(P_t / P_{t-1}). Usa-se o log-retorno (e não a
    variação percentual simples) porque ele é aditivo no tempo (o log-retorno de
    N dias é a soma dos log-retornos diários) e costuma se aproximar melhor de
    uma distribuição normal — hipótese central do modelo abaixo.

  • Anualização: assumindo dias i.i.d., a média e a variância escalam com o
    número de pregões. Usamos 252 dias úteis/ano (padrão de mercado):
        média_anual  = média_diária × 252
        sigma_anual  = desvio_diário × sqrt(252)

  • Probabilidade de cauda: sob a hipótese de que os log-retornos são normais,
    a probabilidade do preço futuro ficar abaixo/acima de um preço de referência
    vira uma probabilidade de cauda de uma normal (via z-score e norm.cdf).

LIMITAÇÃO IMPORTANTE (repetida na UI): a hipótese de normalidade dos
log-retornos é uma simplificação. Retornos reais têm caudas mais pesadas
(eventos extremos mais frequentes) e volatilidade que muda no tempo. Portanto
as probabilidades calculadas são ilustrativas e NÃO constituem recomendação de
investimento.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

# Nº padrão de dias úteis/pregões por ano usado para anualização em finanças.
DIAS_UTEIS_ANO = 252


def calcular_estatisticas_log_retornos(hist: pd.DataFrame) -> dict:
    """
    Calcula log-retornos diários e estatísticas empíricas a partir de uma
    série de preços de fechamento.

    Espera um DataFrame com uma coluna "close" (preço de fechamento).

    Retorna um dict com as séries intermediárias (`precos`, `log_retornos`,
    `z_valores`) e as estatísticas descritivas (n, média/desvio diários e
    anualizados, último preço, mínimo e máximo). Em séries curtas demais os
    campos que não podem ser calculados voltam como NaN, sem lançar exceção.
    """
    precos = pd.to_numeric(hist["close"], errors="coerce").dropna()
    log_retornos = np.log(precos / precos.shift(1)).dropna()

    n = int(log_retornos.shape[0])
    media_diaria = float(log_retornos.mean()) if n else np.nan
    dp_diario = float(log_retornos.std(ddof=1)) if n > 1 else np.nan
    media_log_anual = media_diaria * DIAS_UTEIS_ANO if np.isfinite(media_diaria) else np.nan
    sigma_anual = dp_diario * np.sqrt(DIAS_UTEIS_ANO) if np.isfinite(dp_diario) else np.nan

    z_valores = (
        (log_retornos - media_diaria) / dp_diario
        if n > 1 and np.isfinite(dp_diario) and dp_diario > 0
        else pd.Series(dtype=float)
    )

    return {
        "precos": precos,
        "log_retornos": log_retornos,
        "z_valores": z_valores,
        "n": n,
        "media_diaria": media_diaria,
        "dp_diario": dp_diario,
        "media_log_anual": media_log_anual,
        "sigma_anual": sigma_anual,
        "ultimo_preco": float(precos.iloc[-1]) if len(precos) else np.nan,
        "preco_minimo": float(precos.min()) if len(precos) else np.nan,
        "preco_maximo": float(precos.max()) if len(precos) else np.nan,
    }


def calcular_probabilidade_cauda(
    stats: dict, preco_alvo: float, cauda: str
) -> dict:
    """
    Calcula a probabilidade de o preço ficar abaixo (cauda="inferior") ou
    acima (cauda="superior") de um preço alvo, assumindo log-retornos
    normalmente distribuídos com os parâmetros anualizados de `stats`.

    Modelo (movimento log-normal em horizonte t = 1/252, ou seja, 1 pregão):
        z = [ ln(preco_alvo / S0) - média_log_anual · t ] / (sigma_anual · sqrt(t))
        P(cair abaixo) = Φ(z)          (cauda inferior)
        P(subir acima) = 1 − Φ(z)      (cauda superior)

    Retorna {"z", "probabilidade"}; ambos NaN se os parâmetros forem inválidos
    (preço não positivo, sigma não positivo ou último preço ausente).
    """
    s0 = float(stats.get("ultimo_preco", np.nan))
    sigma_anual = float(stats.get("sigma_anual", np.nan))
    media_log_anual = float(stats.get("media_log_anual", np.nan))
    t = 1 / DIAS_UTEIS_ANO

    valido = (
        np.isfinite(s0) and s0 > 0
        and np.isfinite(preco_alvo) and preco_alvo > 0
        and np.isfinite(sigma_anual) and sigma_anual > 0
        and np.isfinite(media_log_anual)
    )
    if not valido:
        return {"z": np.nan, "probabilidade": np.nan}

    z = (np.log(preco_alvo / s0) - media_log_anual * t) / (sigma_anual * np.sqrt(t))
    probabilidade = scipy_stats.norm.cdf(z) if cauda == "inferior" else 1 - scipy_stats.norm.cdf(z)

    return {"z": float(z), "probabilidade": float(probabilidade)}


def teste_normalidade(stats: dict) -> dict:
    """
    Aplica um teste de normalidade aos log-retornos (bônus 7.5).

    Usa Shapiro-Wilk quando há observações suficientes (3 ≤ n ≤ 5000). Para
    amostras maiores que 5000, o Shapiro fica excessivamente sensível a desvios
    minúsculos; nesse caso cai para D'Agostino-Pearson (`normaltest`).

    Retorna dict com: teste (nome), estatística, p_valor, n, e `normal`
    (bool | None) indicando se NÃO se rejeita normalidade a 5%. Campos ficam
    NaN/None quando não há dados suficientes.
    """
    log_retornos = stats.get("log_retornos", pd.Series(dtype=float))
    amostra = pd.to_numeric(log_retornos, errors="coerce").dropna()
    n = int(amostra.shape[0])

    if n < 3:
        return {"teste": None, "estatistica": np.nan, "p_valor": np.nan,
                "n": n, "normal": None}

    if n <= 5000:
        nome = "Shapiro-Wilk"
        estat, p_valor = scipy_stats.shapiro(amostra)
    else:
        nome = "D'Agostino-Pearson"
        estat, p_valor = scipy_stats.normaltest(amostra)

    return {
        "teste": nome,
        "estatistica": float(estat),
        "p_valor": float(p_valor),
        "n": n,
        # Não rejeitar H0 (p >= 0.05) ⇒ compatível com normalidade.
        "normal": bool(p_valor >= 0.05),
    }


def dados_qqplot(stats: dict) -> dict:
    """
    Gera os pontos de um QQ-plot dos log-retornos contra a normal teórica
    (bônus 7.5), usando `scipy.stats.probplot`.

    Retorna dict com:
      teoricos  : quantis teóricos da normal (eixo x)
      amostrais : quantis amostrais ordenados (eixo y)
      reta_x/reta_y : dois pontos da reta de referência ajustada
    Listas vazias quando não há dados suficientes.
    """
    log_retornos = stats.get("log_retornos", pd.Series(dtype=float))
    amostra = pd.to_numeric(log_retornos, errors="coerce").dropna()
    if amostra.shape[0] < 3:
        return {"teoricos": [], "amostrais": [], "reta_x": [], "reta_y": []}

    (teoricos, amostrais), (inclinacao, intercepto, _r) = scipy_stats.probplot(
        amostra, dist="norm"
    )
    x0, x1 = float(teoricos.min()), float(teoricos.max())
    return {
        "teoricos": teoricos.tolist(),
        "amostrais": amostrais.tolist(),
        "reta_x": [x0, x1],
        "reta_y": [inclinacao * x0 + intercepto, inclinacao * x1 + intercepto],
    }
