"""
historico_precos.py — Série histórica de preços de fechamento (yfinance)
========================================================================
O scraper do Investidor10 (scraper.py) só devolve um *snapshot* atual do FII.
A aba de Análise Empírica precisa de uma série histórica de preços de
fechamento filtrável por data, então usamos o Yahoo Finance via `yfinance`.

Decisão arquitetural (ver seção 3 do enunciado): FIIs da B3 são consultados no
Yahoo Finance acrescentando o sufixo ".SA" ao ticker (ex.: MXRF11 → MXRF11.SA).
É gratuito e não exige chave de API. O Playwright/Investidor10 continua
responsável apenas pelos indicadores fundamentalistas (DY, P/VP, preço teto).

Este módulo é independente do Streamlit; o cache via `st.cache_data` é aplicado
na camada de app. Aqui há um cache local opcional em SQLite (bônus 7.8) para
evitar rebater o Yahoo Finance a cada execução.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pandas as pd

from db import DB_PATH_PADRAO, _conectar

# Sufixo do Yahoo Finance para ativos negociados na B3.
SUFIXO_B3 = ".SA"

_SCHEMA_HIST = """
CREATE TABLE IF NOT EXISTS historico_precos (
    ticker TEXT NOT NULL,
    data TEXT NOT NULL,
    close REAL NOT NULL,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (ticker, data)
);
"""


class HistoricoError(Exception):
    """Erro amigável para problemas ao obter a série histórica."""


# ══════════════════════════════════════════════════════════════════════════════
# CACHE LOCAL EM SQLITE (bônus 7.8)
# ══════════════════════════════════════════════════════════════════════════════

def init_cache(path: str = DB_PATH_PADRAO) -> None:
    """Cria a tabela de cache de histórico se não existir."""
    with _conectar(path) as conn:
        conn.executescript(_SCHEMA_HIST)
        conn.commit()


def _ler_cache(ticker: str, data_inicial: date, data_final: date,
               path: str = DB_PATH_PADRAO) -> pd.DataFrame | None:
    """Lê a série do cache local; retorna None se a tabela ainda não existe."""
    try:
        with _conectar(path) as conn:
            cur = conn.execute(
                """
                SELECT data, close FROM historico_precos
                WHERE ticker = ? AND data >= ? AND data <= ?
                ORDER BY data ASC
                """,
                (ticker, data_inicial.isoformat(), data_final.isoformat()),
            )
            linhas = cur.fetchall()
    except sqlite3.OperationalError:
        return None
    if not linhas:
        return None
    df = pd.DataFrame([dict(r) for r in linhas])
    df["data"] = pd.to_datetime(df["data"])
    return df[["data", "close"]]


def _gravar_cache(ticker: str, df: pd.DataFrame, path: str = DB_PATH_PADRAO) -> None:
    """Grava/atualiza a série no cache local (UPSERT por ticker+data)."""
    init_cache(path)
    agora = datetime.now().isoformat(timespec="seconds")
    registros = [
        (ticker, row["data"].date().isoformat(), float(row["close"]), agora)
        for _, row in df.iterrows()
    ]
    with _conectar(path) as conn:
        conn.executemany(
            """
            INSERT INTO historico_precos (ticker, data, close, atualizado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker, data) DO UPDATE SET
                close = excluded.close,
                atualizado_em = excluded.atualizado_em
            """,
            registros,
        )
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def _normalizar_para_b3(ticker: str) -> str:
    """MXRF11 → MXRF11.SA; se já tiver o sufixo, mantém."""
    t = ticker.upper().strip()
    return t if t.endswith(SUFIXO_B3) else f"{t}{SUFIXO_B3}"


def obter_serie_historica(
    ticker: str,
    data_inicial: date,
    data_final: date | None = None,
    usar_cache: bool = True,
    path: str = DB_PATH_PADRAO,
) -> pd.DataFrame:
    """
    Busca o histórico diário de preços de fechamento de um FII no Yahoo Finance.

    Parâmetros:
      ticker       : ex "MXRF11" (o sufixo ".SA" é adicionado automaticamente).
      data_inicial : primeira data da janela.
      data_final   : última data (inclusiva). None = até o momento atual.
      usar_cache   : se True, tenta o cache local em SQLite antes do Yahoo e
                     grava o resultado para consultas futuras (bônus 7.8).
      path         : caminho do banco usado como cache.

    Retorna um DataFrame com colunas ["data", "close"] ordenado por data.

    Levanta `HistoricoError` (com mensagem amigável) para ticker inexistente,
    período sem dados ou erro de rede. A camada de UI deve capturar essa
    exceção e exibi-la via box(msg, kind="error"), nunca deixá-la propagar.
    """
    if data_final is None:
        data_final = date.today()
    if data_inicial > data_final:
        raise HistoricoError("A data inicial deve ser anterior à data final.")

    ticker = ticker.upper().strip()

    # 1) Cache local, se disponível e solicitado.
    if usar_cache:
        cache = _ler_cache(ticker, data_inicial, data_final, path)
        # Só confia no cache se houver uma amostra minimamente útil.
        if cache is not None and len(cache) >= 2:
            return cache.reset_index(drop=True)

    # 2) Yahoo Finance via yfinance.
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - ambiente sem yfinance
        raise HistoricoError(
            "yfinance não instalado. Execute: pip install yfinance"
        ) from exc

    simbolo = _normalizar_para_b3(ticker)
    try:
        # end é exclusivo no yfinance → soma 1 dia para incluir data_final.
        bruto = yf.download(
            simbolo,
            start=data_inicial.isoformat(),
            end=(data_final + pd.Timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
            actions=False,
        )
    except Exception as exc:  # rede, timeout etc.
        raise HistoricoError(
            f"Falha ao consultar o Yahoo Finance para {simbolo}: {exc}"
        ) from exc

    if bruto is None or bruto.empty:
        raise HistoricoError(
            f"Nenhum dado histórico encontrado para {simbolo} no período "
            f"{data_inicial.isoformat()} a {data_final.isoformat()}. "
            f"Verifique o ticker (ex.: 'MXRF11') e o intervalo de datas."
        )

    df = _extrair_close(bruto)
    if df.empty:
        raise HistoricoError(
            f"Série de {simbolo} sem preços de fechamento válidos no período."
        )

    if usar_cache:
        try:
            _gravar_cache(ticker, df, path)
        except sqlite3.Error:
            # Cache é best-effort: falha de gravação não deve quebrar a busca.
            pass

    return df.reset_index(drop=True)


def _extrair_close(bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza o DataFrame do yfinance para colunas ["data", "close"].

    O yfinance pode devolver colunas simples ou um MultiIndex
    (quando há mais de um ticker ou dependendo da versão). Tratamos ambos.
    """
    df = bruto.copy()

    # Achata MultiIndex de colunas (ex.: ("Close", "MXRF11.SA")).
    if isinstance(df.columns, pd.MultiIndex):
        nivel0 = df.columns.get_level_values(0)
        df.columns = nivel0

    if "Close" not in df.columns:
        return pd.DataFrame(columns=["data", "close"])

    close = df["Close"]
    # Se ainda houver duplicidade de "Close", pega a primeira coluna.
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    out = pd.DataFrame({
        "data": pd.to_datetime(df.index),
        "close": pd.to_numeric(close.values, errors="coerce"),
    }).dropna(subset=["close"])

    return out[out["close"] > 0].sort_values("data").reset_index(drop=True)
