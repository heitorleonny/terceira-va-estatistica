"""
api.py — API REST (FastAPI) do FII Analyzer
===========================================
Expõe, como serviço HTTP, toda a lógica Python já testada do projeto:

  • scraper.py          → indicadores fundamentalistas (Investidor10/Playwright)
  • historico_precos.py → série histórica de fechamento (Yahoo Finance)
  • stats_empirical.py  → log-retornos, normal ajustada, probabilidade de cauda
  • utils.py            → simulação, carteira, preço teto
  • db.py               → persistência SQLite (histórico de consultas)
  • cards.py            → cards configuráveis

Esta camada cumpre os bônus 7.1 (aplicação web) e 7.3 (API REST) do enunciado e
serve de backend para o frontend React (pasta web/). Nenhuma regra de negócio é
reescrita aqui — a API apenas orquestra e serializa.

Rode em desenvolvimento com:
    uvicorn api:app --reload --port 8000

Uso exclusivamente educacional — não constitui recomendação de investimento.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from scipy.stats import norm

import db
import cards as cards_mod
from historico_precos import obter_serie_historica, HistoricoError, init_cache
from scraper import get_fii_data, get_multiplos_fiis, IPCA_MAIS_GLOBAL
from stats_empirical import (
    calcular_estatisticas_log_retornos,
    calcular_probabilidade_cauda,
    teste_normalidade,
    dados_qqplot,
    DIAS_UTEIS_ANO,
)
from utils import (
    simular_aporte, resumo_simulacao,
    montar_carteira, totais_carteira,
    calcular_preco_teto_row, get_grade_label,
    PREMIO_KNOWN, PREMIO_DEFAULT,
)

app = FastAPI(
    title="FII Analyzer API",
    version="2.0.0",
    description="Backend do dashboard de FIIs — uso educacional.",
)

# Em desenvolvimento o frontend roda em outra porta (Vite, 5173). Liberamos CORS
# amplamente por se tratar de um projeto local/educacional.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()
init_cache()


# ══════════════════════════════════════════════════════════════════════════════
# SERIALIZAÇÃO SEGURA (NaN/inf → null; tipos numpy → python)
# ══════════════════════════════════════════════════════════════════════════════

def _jsonable(obj):
    """Converte recursivamente para algo serializável em JSON válido."""
    if obj is None:
        return None
    if isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.ndarray,)):
        return [_jsonable(x) for x in obj.tolist()]
    if isinstance(obj, (pd.Series,)):
        return [_jsonable(x) for x in obj.tolist()]
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return obj.isoformat()
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# MODELOS DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

class SimulacaoIn(BaseModel):
    preco: float
    dy: float
    cotas_por_mes: int = 10
    meses: int = 240


class ItemCarteira(BaseModel):
    ticker: str
    quantidade: int = 100


class CarteiraIn(BaseModel):
    itens: list[ItemCarteira]


class ProbabilidadeIn(BaseModel):
    ultimo_preco: float
    sigma_anual: float
    media_log_anual: float
    preco_alvo: float
    cauda: str  # "inferior" | "superior"


class CardsConfigIn(BaseModel):
    cards_padrao: list[str] = []
    cards_ativos: list[dict] = []


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE DOMÍNIO
# ══════════════════════════════════════════════════════════════════════════════

def _ja_salvo_recente(ticker: str, periodo: str, fonte: str, janela_seg: int = 120) -> bool:
    """
    Evita poluir o histórico com consultas idênticas em sequência (ex.: reloads
    da página que reexecutam a análise automática do mesmo ticker/período).
    Retorna True se a consulta mais recente do ticker for da mesma fonte, mesmo
    período e tiver menos de `janela_seg` segundos.
    """
    ultimos = db.listar_historico(ticker=ticker, limite=1)
    if not ultimos:
        return False
    r = ultimos[0]
    if r.get("fonte") != fonte:
        return False
    try:
        dados = json.loads(r.get("json_dados") or "{}")
        recente = (datetime.now() - datetime.fromisoformat(r["data_consulta"])).total_seconds()
    except (json.JSONDecodeError, ValueError, TypeError):
        return False
    return dados.get("periodo") == periodo and recente < janela_seg


def _enriquecer(dado: dict) -> dict:
    """Anexa preço teto, margem e grade a um dict de FII."""
    calc = calcular_preco_teto_row(dado)
    dado = dict(dado)
    dado["preco_teto"] = calc["preco_teto"]
    dado["margem_seguranca"] = (
        calc["margem_seguranca"] * 100 if calc["margem_seguranca"] is not None else None
    )
    dado["taxa_requerida"] = calc["taxa_requerida"]
    dado["grade"] = get_grade_label(dado.get("premio", PREMIO_DEFAULT))
    return dado


@lru_cache(maxsize=64)
def _analise_cacheada(ticker: str, inicio: str, fim: str) -> dict:
    """
    Computa e memoiza o pacote completo de análise empírica para (ticker,
    período). O lru_cache evita recomputar histograma/QQ a cada requisição.
    """
    serie = obter_serie_historica(ticker, date.fromisoformat(inicio), date.fromisoformat(fim))
    stats = calcular_estatisticas_log_retornos(serie[["close"]])
    return _montar_pacote_analise(ticker, inicio, fim, serie, stats)


def _montar_pacote_analise(ticker, inicio, fim, serie: pd.DataFrame, stats: dict) -> dict:
    """Monta o dicionário de resposta da análise empírica (séries + gráficos)."""
    serie_out = [
        {"data": pd.Timestamp(r["data"]).date().isoformat(), "close": float(r["close"])}
        for _, r in serie.iterrows()
    ]

    lr = stats["log_retornos"]
    histograma = None
    normal = None
    if stats["n"] >= 2 and stats["dp_diario"] and stats["dp_diario"] > 0:
        counts, edges = np.histogram(lr.values, bins=40, density=True)
        histograma = [
            {"x0": float(edges[i]), "x1": float(edges[i + 1]),
             "centro": float((edges[i] + edges[i + 1]) / 2), "densidade": float(counts[i])}
            for i in range(len(counts))
        ]
        xs = np.linspace(float(lr.min()), float(lr.max()), 160)
        ys = norm.pdf(xs, stats["media_diaria"], stats["dp_diario"])
        normal = [{"x": float(a), "y": float(b)} for a, b in zip(xs, ys)]

    qq_raw = dados_qqplot(stats)
    qq = {
        "pontos": [
            {"teorico": t, "amostral": a}
            for t, a in zip(qq_raw["teoricos"], qq_raw["amostrais"])
        ],
        "reta": [
            {"x": qq_raw["reta_x"][0], "y": qq_raw["reta_y"][0]},
            {"x": qq_raw["reta_x"][1], "y": qq_raw["reta_y"][1]},
        ] if qq_raw["teoricos"] else [],
    }

    normalidade = teste_normalidade(stats)

    resumo = {k: stats[k] for k in (
        "n", "media_diaria", "dp_diario", "media_log_anual", "sigma_anual",
        "ultimo_preco", "preco_minimo", "preco_maximo",
    )}

    return _jsonable({
        "ticker": ticker,
        "periodo": {"inicio": inicio, "fim": fim, "pregoes": len(serie_out)},
        "serie": serie_out,
        "estatisticas": resumo,
        "histograma": histograma,
        "normal": normal,
        "qq": qq,
        "normalidade": normalidade,
        "dias_uteis_ano": DIAS_UTEIS_ANO,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — META
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {"status": "ok", "consultas": db.contar_consultas(), "ipca_mais": IPCA_MAIS_GLOBAL}


@app.get("/api/meta/premios")
def meta_premios():
    """Prêmios conhecidos por ticker + default, para a UI pré-preencher grades."""
    return {"conhecidos": PREMIO_KNOWN, "default": PREMIO_DEFAULT}


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — INDICADORES (Investidor10 / Playwright)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/fii/{ticker}")
def fii(ticker: str, premio: float | None = Query(None), ipca: float | None = Query(None)):
    """Indicadores + preço teto/margem/grade de um FII. Persiste a consulta."""
    ticker = ticker.upper().strip()
    premio_ov = {"default": PREMIO_DEFAULT}
    if premio is not None:
        premio_ov[ticker] = premio
    ipca_ov = {ticker: ipca} if ipca is not None else {}

    dado = get_fii_data(ticker, premio_override=premio_ov, ipca_override=ipca_ov)
    if dado.get("erro"):
        raise HTTPException(status_code=502, detail=dado["erro"])

    dado = _enriquecer(dado)
    try:
        db.salvar_consulta(dado, "investidor10")
    except Exception:
        pass
    return _jsonable(dado)


@app.post("/api/simular")
def simular(body: SimulacaoIn):
    """Projeção de aporte mensal — cálculo puro (utils.simular_aporte)."""
    df = simular_aporte(body.preco, body.dy, int(body.cotas_por_mes), int(body.meses))
    resumo = resumo_simulacao(df)
    return _jsonable({
        "resumo": resumo,
        "serie": df.to_dict(orient="records"),
    })


@app.post("/api/carteira")
def carteira(body: CarteiraIn):
    """Monta uma carteira de múltiplos FIIs (busca em sequência + totais)."""
    tickers = [i.ticker.upper().strip() for i in body.itens]
    qtds = {i.ticker.upper().strip(): int(i.quantidade) for i in body.itens}
    resultados = get_multiplos_fiis(tickers)
    for d in resultados:
        d["quantidade"] = qtds.get(d["ticker"], 0)
        if not d.get("erro"):
            try:
                db.salvar_consulta(_enriquecer(d), "investidor10")
            except Exception:
                pass
    df = montar_carteira([d for d in resultados])
    tot = totais_carteira(df)
    return _jsonable({
        "linhas": df.to_dict(orient="records"),
        "totais": tot,
        "erros": [{"ticker": d["ticker"], "erro": d["erro"]} for d in resultados if d.get("erro")],
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — SÉRIE HISTÓRICA E ANÁLISE EMPÍRICA (Yahoo Finance)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/precos/{ticker}")
def precos(ticker: str, inicio: str, fim: str | None = None):
    """Série histórica de fechamento (colunas data, close)."""
    try:
        d_ini = date.fromisoformat(inicio)
        d_fim = date.fromisoformat(fim) if fim else date.today()
        serie = obter_serie_historica(ticker, d_ini, d_fim)
    except HistoricoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas inválidas (use YYYY-MM-DD).")
    return _jsonable({
        "ticker": ticker.upper().strip(),
        "serie": [
            {"data": pd.Timestamp(r["data"]).date().isoformat(), "close": float(r["close"])}
            for _, r in serie.iterrows()
        ],
    })


@app.get("/api/analise/{ticker}")
def analise(ticker: str, inicio: str, fim: str | None = None):
    """
    Pacote completo de análise empírica: série, estatísticas descritivas,
    histograma dos log-retornos, curva normal ajustada, QQ-plot e teste de
    normalidade. Persiste um resumo da consulta (fonte yfinance).
    """
    ticker = ticker.upper().strip()
    d_fim = fim or date.today().isoformat()
    try:
        pacote = _analise_cacheada(ticker, inicio, d_fim)
    except HistoricoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas inválidas (use YYYY-MM-DD).")

    est = pacote["estatisticas"]
    periodo = f"{inicio} a {d_fim}"
    if est.get("ultimo_preco") is not None and not _ja_salvo_recente(ticker, periodo, "yfinance"):
        try:
            db.salvar_consulta({
                "ticker": ticker,
                "preco": est["ultimo_preco"],
                "periodo": periodo,
                "n_pregoes": pacote["periodo"]["pregoes"],
            }, "yfinance")
        except Exception:
            pass
    return pacote


@app.post("/api/probabilidade")
def probabilidade(body: ProbabilidadeIn):
    """Probabilidade de cauda (assumindo log-retornos normais)."""
    stats = {
        "ultimo_preco": body.ultimo_preco,
        "sigma_anual": body.sigma_anual,
        "media_log_anual": body.media_log_anual,
    }
    if body.cauda not in ("inferior", "superior"):
        raise HTTPException(status_code=400, detail="cauda deve ser 'inferior' ou 'superior'.")
    res = calcular_probabilidade_cauda(stats, body.preco_alvo, body.cauda)
    return _jsonable(res)


@app.get("/api/comparar")
def comparar(tickers: str, inicio: str, fim: str | None = None):
    """
    Comparação estatística de 2+ FIIs (bônus 7.6):
      • séries rebaseadas a 100 (comparáveis num único gráfico);
      • estatísticas descritivas: retorno total, retorno médio e volatilidade
        anualizados;
      • matriz de correlação entre os log-retornos diários (alinhados por data).

    A correlação mede o quanto os retornos dos fundos se movem juntos — útil
    para diversificação. Uso educacional, não é recomendação de investimento.
    """
    lista = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    if len(lista) < 2:
        raise HTTPException(status_code=400, detail="Informe pelo menos 2 tickers.")
    if len(lista) > 6:
        raise HTTPException(status_code=400, detail="Compare no máximo 6 FIIs por vez.")
    try:
        d_ini = date.fromisoformat(inicio)
        d_fim = date.fromisoformat(fim) if fim else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas inválidas (use YYYY-MM-DD).")

    ativos = []
    retornos: dict[str, pd.Series] = {}
    erros = []
    for tk in lista:
        try:
            serie = obter_serie_historica(tk, d_ini, d_fim)
        except HistoricoError as exc:
            erros.append({"ticker": tk, "erro": str(exc)})
            continue
        stats = calcular_estatisticas_log_retornos(serie[["close"]])
        base0 = float(serie["close"].iloc[0])
        serie_out = [
            {
                "data": pd.Timestamp(r["data"]).date().isoformat(),
                "close": float(r["close"]),
                "base100": float(r["close"]) / base0 * 100 if base0 else None,
            }
            for _, r in serie.iterrows()
        ]
        s = serie.set_index("data")["close"]
        retornos[tk] = np.log(s / s.shift(1)).dropna()
        ret_total = (float(serie["close"].iloc[-1]) / base0 - 1) * 100 if base0 else None
        ativos.append({
            "ticker": tk,
            "serie": serie_out,
            "estatisticas": {
                "n": stats["n"],
                "ultimo_preco": stats["ultimo_preco"],
                "retorno_total_pct": ret_total,
                "media_log_anual": stats["media_log_anual"],
                "sigma_anual": stats["sigma_anual"],
            },
        })

    correlacao = None
    if len(retornos) >= 2:
        dfc = pd.DataFrame(retornos).dropna()
        if len(dfc) >= 2:
            corr = dfc.corr()
            correlacao = {
                "tickers": list(corr.columns),
                "matriz": corr.values.tolist(),
                "observacoes": int(len(dfc)),
            }

    return _jsonable({
        "periodo": {"inicio": inicio, "fim": d_fim.isoformat()},
        "ativos": ativos,
        "correlacao": correlacao,
        "erros": erros,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — HISTÓRICO (SQLite)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/consultas")
def consultas(ticker: str | None = None, limite: int = 100):
    return _jsonable(db.listar_historico(ticker=ticker or None, limite=limite))


@app.get("/api/consultas/{id}")
def consulta(id: int):
    reg = db.buscar_consulta_por_id(id)
    if reg is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada.")
    return _jsonable(reg)


@app.delete("/api/consultas/{id}")
def apagar(id: int):
    db.apagar_consulta(id)
    return {"ok": True, "id": id}


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — CARDS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/cards/config")
def cards_config():
    return _jsonable(cards_mod.carregar_config())


@app.put("/api/cards/config")
def cards_config_salvar(body: CardsConfigIn):
    cfg = body.model_dump()
    cards_mod.salvar_config(cfg)
    return _jsonable(cards_mod.carregar_config())


@app.post("/api/cards/refresh")
def cards_refresh():
    """Busca os indicadores dos cards visíveis e devolve ordenado por margem."""
    cfg = cards_mod.carregar_config()
    visiveis = cards_mod.tickers_visiveis(cfg)
    if not visiveis:
        return {"cards": [], "config": _jsonable(cfg)}
    premio_ov = {tk: PREMIO_KNOWN.get(tk, PREMIO_DEFAULT) for tk in visiveis}
    premio_ov["default"] = PREMIO_DEFAULT
    resultados = get_multiplos_fiis(visiveis, premio_override=premio_ov)
    preparados = []
    for d in resultados:
        preparados.append(cards_mod.preparar_card(d))
        if not d.get("erro"):
            try:
                db.salvar_consulta(_enriquecer(d), "investidor10")
            except Exception:
                pass
    ordenados = cards_mod.ordenar_por_margem(preparados)
    return _jsonable({"cards": ordenados, "config": cfg})


# ══════════════════════════════════════════════════════════════════════════════
# FRONTEND ESTÁTICO (build de produção da pasta web/dist), se existir
# ══════════════════════════════════════════════════════════════════════════════

_DIST = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
