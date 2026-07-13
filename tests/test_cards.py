"""Testes de cards.py — configuração e preparo dos cards."""

import json

import pytest

import cards as cards_mod


@pytest.fixture()
def cfg_path(tmp_path):
    return str(tmp_path / "cards_config.json")


def test_carregar_config_ausente_usa_padrao(cfg_path):
    cfg = cards_mod.carregar_config(cfg_path)
    # cards_ativos populado a partir de cards_padrao, todos visíveis.
    assert cards_mod.tickers_visiveis(cfg) == cfg["cards_padrao"]


def test_carregar_config_corrompida_nao_quebra(cfg_path):
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("{ isso não é json válido ")
    cfg = cards_mod.carregar_config(cfg_path)   # não deve lançar
    assert cards_mod.tickers_visiveis(cfg)      # cai no padrão


def test_adicionar_e_remover(cfg_path):
    cfg = cards_mod.carregar_config(cfg_path)
    cards_mod.adicionar_card(cfg, "gare11")     # minúsculo → normaliza
    assert "GARE11" in cards_mod.tickers_visiveis(cfg)
    cards_mod.remover_card(cfg, "GARE11")
    assert "GARE11" not in cards_mod.tickers_visiveis(cfg)


def test_adicionar_duplicado_reativa(cfg_path):
    cfg = cards_mod.carregar_config(cfg_path)
    n_antes = len(cfg["cards_ativos"])
    primeiro = cfg["cards_ativos"][0]["ticker"]
    cfg["cards_ativos"][0]["visivel"] = False
    cards_mod.adicionar_card(cfg, primeiro)     # não duplica, só reativa
    assert len(cfg["cards_ativos"]) == n_antes
    assert cfg["cards_ativos"][0]["visivel"] is True


def test_salvar_persiste_visivel_e_ordem(cfg_path):
    cfg = cards_mod.carregar_config(cfg_path)
    cfg["cards_ativos"][0]["visivel"] = False
    cfg["cards_ativos"][0]["ordem"] = 99
    cards_mod.salvar_config(cfg, cfg_path)
    with open(cfg_path, encoding="utf-8") as f:
        salvo = json.load(f)
    assert salvo["cards_ativos"][0]["visivel"] is False
    assert salvo["cards_ativos"][0]["ordem"] == 99


def test_tickers_visiveis_respeita_ordem_e_visibilidade():
    cfg = {"cards_padrao": [], "cards_ativos": [
        {"ticker": "C", "visivel": True, "ordem": 3},
        {"ticker": "A", "visivel": True, "ordem": 1},
        {"ticker": "B", "visivel": False, "ordem": 2},
    ]}
    assert cards_mod.tickers_visiveis(cfg) == ["A", "C"]   # B oculto; ordenado


def test_preparar_card_reusa_calculo():
    dado = {"ticker": "A", "preco": 10.0, "dy": 9.0, "pvp": 1.0,
            "dividendo_12m": 0.9, "ipca_mais": 0.07, "premio": 0.01, "tipo": "tijolo"}
    card = cards_mod.preparar_card(dado)
    # Preço teto = div12m / (ipca_mais + premio) = 0.9 / 0.08 = 11.25
    assert card["preco_teto"] == pytest.approx(11.25)
    # Margem = (11.25 - 10) / 10 * 100 = 12.5%
    assert card["margem_seguranca"] == pytest.approx(12.5)
    assert card["grade"] == "High Grade (1%)"


def test_ordenar_por_margem_desc_e_invalidos_no_fim():
    cards = [
        {"ticker": "A", "margem_seguranca": 5.0},
        {"ticker": "B", "margem_seguranca": None},
        {"ticker": "C", "margem_seguranca": 20.0},
    ]
    ordem = [c["ticker"] for c in cards_mod.ordenar_por_margem(cards)]
    assert ordem == ["C", "A", "B"]
    assert [c["ticker"] for c in cards_mod.ordenar_por_margem(cards, limite=2)] == ["C", "A"]
