"""Testes de db.py — persistência em SQLite (usa banco temporário)."""

import math

import pytest

import db


@pytest.fixture()
def banco(tmp_path):
    caminho = str(tmp_path / "teste.db")
    db.init_db(caminho)
    return caminho


def test_init_idempotente(banco):
    db.init_db(banco)   # segunda chamada não deve falhar
    assert db.contar_consultas(banco) == 0


def test_salvar_e_listar(banco):
    i1 = db.salvar_consulta(
        {"ticker": "mxrf11", "preco": 10.5, "dy": 8.72, "pvp": 1.01,
         "margem_seguranca": 12.3, "tipo": "papel"}, "investidor10", banco)
    i2 = db.salvar_consulta({"ticker": "KNRI11", "preco": 150.0}, "yfinance", banco)
    assert i1 == 1 and i2 == 2
    hist = db.listar_historico(path=banco)
    assert [h["ticker"] for h in hist] == ["KNRI11", "MXRF11"]   # mais recente 1º
    assert hist[1]["fonte"] == "investidor10"


def test_nan_vira_null(banco):
    db.salvar_consulta({"ticker": "AAA11", "preco": float("nan"), "dy": None}, "manual", banco)
    reg = db.listar_historico(path=banco)[0]
    assert reg["preco"] is None
    assert reg["dy"] is None


def test_filtro_por_ticker(banco):
    db.salvar_consulta({"ticker": "AAA11", "preco": 1.0}, "manual", banco)
    db.salvar_consulta({"ticker": "BBB11", "preco": 2.0}, "manual", banco)
    db.salvar_consulta({"ticker": "AAA11", "preco": 3.0}, "manual", banco)
    somente_a = db.listar_historico("aaa11", path=banco)
    assert len(somente_a) == 2
    assert all(r["ticker"] == "AAA11" for r in somente_a)


def test_recarregar_desserializa_json(banco):
    i = db.salvar_consulta(
        {"ticker": "MXRF11", "preco": 10.0, "tipo": "papel",
         "extra": {"aninhado": 1}}, "investidor10", banco)
    reg = db.buscar_consulta_por_id(i, banco)
    assert reg is not None
    assert reg["dados"]["tipo"] == "papel"
    assert reg["dados"]["extra"] == {"aninhado": 1}


def test_buscar_id_inexistente(banco):
    assert db.buscar_consulta_por_id(999, banco) is None


def test_apagar(banco):
    i = db.salvar_consulta({"ticker": "MXRF11", "preco": 10.0}, "manual", banco)
    assert db.contar_consultas(banco) == 1
    db.apagar_consulta(i, banco)
    assert db.contar_consultas(banco) == 0
    db.apagar_consulta(i, banco)   # apagar de novo é no-op, sem exceção
