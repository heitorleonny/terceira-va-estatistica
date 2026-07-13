"""
Testes das funções estatísticas de stats_empirical.py.

Cobre os casos exigidos no enunciado:
  • série de preços constante   → log-retornos todos zero;
  • série sem dados suficientes → retorna NaN sem lançar exceção;
  • caso com dados conhecidos   → probabilidade conferível manualmente.

Rode com:  pytest -q
"""

import math

import numpy as np
import pandas as pd
import pytest

from stats_empirical import (
    calcular_estatisticas_log_retornos,
    calcular_probabilidade_cauda,
    teste_normalidade,
    dados_qqplot,
    DIAS_UTEIS_ANO,
)


# ── Série constante: log-retornos todos zero ──────────────────────────────────

def test_serie_constante_log_retornos_zero():
    hist = pd.DataFrame({"close": [10.0] * 30})
    s = calcular_estatisticas_log_retornos(hist)

    assert s["n"] == 29                       # 30 preços → 29 log-retornos
    assert np.allclose(s["log_retornos"].values, 0.0)
    assert s["media_diaria"] == pytest.approx(0.0)
    assert s["dp_diario"] == pytest.approx(0.0)
    # Desvio zero ⇒ z-scores indefinidos ⇒ série vazia (sem divisão por zero).
    assert s["z_valores"].empty
    assert s["ultimo_preco"] == 10.0
    assert s["preco_minimo"] == 10.0
    assert s["preco_maximo"] == 10.0


# ── Dados insuficientes: NaN sem exceção ──────────────────────────────────────

def test_serie_vazia_retorna_nan_sem_excecao():
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": []}))
    assert s["n"] == 0
    assert math.isnan(s["media_diaria"])
    assert math.isnan(s["dp_diario"])
    assert math.isnan(s["sigma_anual"])
    assert math.isnan(s["ultimo_preco"])


def test_serie_um_preco_retorna_nan_sem_excecao():
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": [10.0]}))
    assert s["n"] == 0                        # 1 preço → 0 log-retornos
    assert math.isnan(s["media_diaria"])
    assert math.isnan(s["dp_diario"])
    assert s["ultimo_preco"] == 10.0          # último preço ainda é definido


def test_dois_precos_media_definida_desvio_nan():
    # 2 preços → 1 log-retorno: média existe, desvio (ddof=1) é indefinido.
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": [10.0, 11.0]}))
    assert s["n"] == 1
    assert s["media_diaria"] == pytest.approx(math.log(11.0 / 10.0))
    assert math.isnan(s["dp_diario"])


# ── Anualização ───────────────────────────────────────────────────────────────

def test_anualizacao_usa_252():
    # Crescimento geométrico constante: log-retorno diário fixo r.
    r = 0.001
    precos = [100.0 * math.exp(r * i) for i in range(50)]
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": precos}))
    assert s["media_diaria"] == pytest.approx(r, rel=1e-9)
    assert s["media_log_anual"] == pytest.approx(r * DIAS_UTEIS_ANO, rel=1e-9)
    # Log-retorno constante ⇒ desvio zero ⇒ sigma anual zero.
    assert s["dp_diario"] == pytest.approx(0.0, abs=1e-12)


# ── Probabilidade de cauda: caso conferível manualmente ───────────────────────

def test_probabilidade_alvo_igual_preco_atual_media_zero_meio_a_meio():
    # Com deriva média zero e preço-alvo = preço atual, o z é 0 e a
    # probabilidade de qualquer cauda é exatamente 0,5 (verificável à mão).
    stats = {"ultimo_preco": 100.0, "sigma_anual": 0.20, "media_log_anual": 0.0}
    inf = calcular_probabilidade_cauda(stats, 100.0, "inferior")
    sup = calcular_probabilidade_cauda(stats, 100.0, "superior")
    assert inf["z"] == pytest.approx(0.0)
    assert inf["probabilidade"] == pytest.approx(0.5)
    assert sup["probabilidade"] == pytest.approx(0.5)
    # As duas caudas são complementares.
    assert inf["probabilidade"] + sup["probabilidade"] == pytest.approx(1.0)


def test_probabilidade_caudas_complementares_e_monotonas():
    stats = {"ultimo_preco": 100.0, "sigma_anual": 0.25, "media_log_anual": 0.05}
    for alvo in (90.0, 100.0, 110.0):
        inf = calcular_probabilidade_cauda(stats, alvo, "inferior")
        sup = calcular_probabilidade_cauda(stats, alvo, "superior")
        assert inf["probabilidade"] + sup["probabilidade"] == pytest.approx(1.0)
    # Alvo mais alto ⇒ maior prob. de cair abaixo dele.
    p_baixo = calcular_probabilidade_cauda(stats, 90.0, "inferior")["probabilidade"]
    p_alto = calcular_probabilidade_cauda(stats, 110.0, "inferior")["probabilidade"]
    assert p_alto > p_baixo


def test_probabilidade_z_calculado_conhecido():
    # z = [ln(alvo/S0) - m·t] / (sigma·sqrt(t)), t = 1/252.
    stats = {"ultimo_preco": 100.0, "sigma_anual": 0.20, "media_log_anual": 0.0}
    alvo = 105.0
    t = 1 / DIAS_UTEIS_ANO
    z_esperado = (math.log(alvo / 100.0)) / (0.20 * math.sqrt(t))
    res = calcular_probabilidade_cauda(stats, alvo, "superior")
    assert res["z"] == pytest.approx(z_esperado, rel=1e-9)


def test_probabilidade_parametros_invalidos_retorna_nan():
    # sigma não positivo, preço não positivo ou último preço ausente ⇒ NaN.
    base = {"ultimo_preco": 100.0, "sigma_anual": 0.2, "media_log_anual": 0.0}
    assert math.isnan(calcular_probabilidade_cauda({**base, "sigma_anual": 0.0}, 100.0, "inferior")["probabilidade"])
    assert math.isnan(calcular_probabilidade_cauda(base, -5.0, "inferior")["probabilidade"])
    assert math.isnan(calcular_probabilidade_cauda({**base, "ultimo_preco": float("nan")}, 100.0, "inferior")["probabilidade"])


# ── Bônus: teste de normalidade e QQ-plot ─────────────────────────────────────

def test_teste_normalidade_amostra_normal_nao_rejeita():
    rng = np.random.default_rng(42)
    precos = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, 500)))
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": precos}))
    tn = teste_normalidade(s)
    assert tn["teste"] == "Shapiro-Wilk"
    assert tn["n"] == 499
    assert tn["normal"] is True            # log-retornos gaussianos por construção


def test_teste_normalidade_dados_insuficientes():
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": [10.0, 10.1]}))
    tn = teste_normalidade(s)
    assert tn["teste"] is None
    assert tn["normal"] is None
    assert math.isnan(tn["p_valor"])


def test_dados_qqplot_estrutura():
    rng = np.random.default_rng(7)
    precos = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, 120)))
    s = calcular_estatisticas_log_retornos(pd.DataFrame({"close": precos}))
    qq = dados_qqplot(s)
    assert len(qq["teoricos"]) == len(qq["amostrais"]) == 119
    assert len(qq["reta_x"]) == len(qq["reta_y"]) == 2

    vazio = dados_qqplot(calcular_estatisticas_log_retornos(pd.DataFrame({"close": [1.0]})))
    assert vazio["teoricos"] == []
