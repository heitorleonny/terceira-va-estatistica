"""
db.py — Persistência em SQLite
==============================
Guarda um histórico de consultas de FIIs em um banco SQLite local, para que os
dados coletados (via Playwright/Investidor10 ou via yfinance) sobrevivam entre
sessões do Streamlit. Também serve de cache local simples (bônus 7.8): cada
linha registra a data/hora da consulta e o dicionário completo em `json_dados`,
o que permite recarregar uma consulta antiga sem refazer o scraping.

Tabela `consultas`:
  id                INTEGER  PK autoincrement
  ticker            TEXT     ex "MXRF11"
  data_consulta     TEXT     ISO-8601 (UTC-naive local) da coleta
  preco             REAL     preço/cotação no momento da consulta
  dy                REAL     dividend yield 12M em % (ex 8.72)
  pvp               REAL     P/VP
  margem_seguranca  REAL     margem de segurança em % (pode ser NULL)
  fonte             TEXT     origem do dado ("investidor10", "yfinance", ...)
  json_dados        TEXT     dicionário completo serializado (JSON)

Todas as funções são puras em relação ao Streamlit (não importam `st`), para
poderem ser testadas isoladamente e reutilizadas por uma eventual API REST.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime

# Caminho padrão do banco. Mantido em uma constante para facilitar testes
# (que passam um arquivo temporário) e a eventual API REST.
DB_PATH_PADRAO = "fii_dashboard.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    data_consulta TEXT NOT NULL,
    preco REAL,
    dy REAL,
    pvp REAL,
    margem_seguranca REAL,
    fonte TEXT NOT NULL,
    json_dados TEXT NOT NULL
);
"""


# ══════════════════════════════════════════════════════════════════════════════
# INFRAESTRUTURA
# ══════════════════════════════════════════════════════════════════════════════

def _conectar(path: str) -> sqlite3.Connection:
    """Abre uma conexão com `row_factory` em dict-like (sqlite3.Row)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = DB_PATH_PADRAO) -> None:
    """
    Cria o banco e a tabela `consultas` se ainda não existirem.
    Idempotente: pode ser chamada em toda inicialização da aplicação.
    """
    with _conectar(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def _limpar_float(valor) -> float | None:
    """
    Normaliza valores numéricos para gravação: converte NaN/inf/None em None
    (que vira NULL no SQLite) e garante `float` para o resto.
    """
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _serializavel(dado: dict) -> dict:
    """
    Converte um dict de consulta em algo 100% serializável em JSON,
    trocando NaN/inf por None (JSON não representa NaN de forma portável).
    """
    limpo = {}
    for chave, valor in dado.items():
        if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
            limpo[chave] = None
        else:
            limpo[chave] = valor
    return limpo


# ══════════════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ══════════════════════════════════════════════════════════════════════════════

def salvar_consulta(dado: dict, fonte: str, path: str = DB_PATH_PADRAO) -> int:
    """
    Grava uma consulta de FII no banco e retorna o `id` gerado.

    Parâmetros:
      dado  : dicionário retornado por get_fii_data / obter_serie_historica etc.
              Espera-se ao menos a chave "ticker"; os demais campos são
              extraídos quando presentes (preco, dy, pvp, margem_seguranca).
      fonte : origem legível do dado ("investidor10", "yfinance", "manual", ...).
      path  : caminho do banco (padrão: fii_dashboard.db).

    O dicionário inteiro é serializado em `json_dados`, permitindo recarregar
    uma consulta antiga com todos os campos originais.
    """
    ticker = str(dado.get("ticker", "?")).upper().strip()
    data_consulta = datetime.now().isoformat(timespec="seconds")
    preco = _limpar_float(dado.get("preco"))
    dy = _limpar_float(dado.get("dy"))
    pvp = _limpar_float(dado.get("pvp"))
    margem = _limpar_float(dado.get("margem_seguranca"))
    json_dados = json.dumps(_serializavel(dado), ensure_ascii=False)

    with _conectar(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO consultas
                (ticker, data_consulta, preco, dy, pvp, margem_seguranca, fonte, json_dados)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, data_consulta, preco, dy, pvp, margem, fonte, json_dados),
        )
        conn.commit()
        return int(cur.lastrowid)


def listar_historico(
    ticker: str | None = None,
    limite: int = 100,
    path: str = DB_PATH_PADRAO,
) -> list[dict]:
    """
    Lista consultas, mais recentes primeiro, com filtro opcional por ticker.

    Retorna uma lista de dicts com as colunas da tabela (sem desserializar
    `json_dados`, que fica disponível como string caso o chamador precise).
    """
    with _conectar(path) as conn:
        if ticker:
            cur = conn.execute(
                """
                SELECT * FROM consultas
                WHERE ticker = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ticker.upper().strip(), int(limite)),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM consultas ORDER BY id DESC LIMIT ?",
                (int(limite),),
            )
        return [dict(row) for row in cur.fetchall()]


def buscar_consulta_por_id(id: int, path: str = DB_PATH_PADRAO) -> dict | None:
    """
    Recupera uma consulta pelo id, já com o `json_dados` desserializado no
    campo extra "dados". Retorna None se o id não existir.
    Usado para recarregar uma consulta antiga na UI.
    """
    with _conectar(path) as conn:
        cur = conn.execute("SELECT * FROM consultas WHERE id = ?", (int(id),))
        row = cur.fetchone()
    if row is None:
        return None
    registro = dict(row)
    try:
        registro["dados"] = json.loads(registro["json_dados"])
    except (json.JSONDecodeError, TypeError):
        registro["dados"] = {}
    return registro


def apagar_consulta(id: int, path: str = DB_PATH_PADRAO) -> None:
    """Remove uma consulta pelo id (no-op se o id não existir)."""
    with _conectar(path) as conn:
        conn.execute("DELETE FROM consultas WHERE id = ?", (int(id),))
        conn.commit()


def contar_consultas(path: str = DB_PATH_PADRAO) -> int:
    """Retorna o número total de consultas gravadas (útil para a UI/testes)."""
    with _conectar(path) as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM consultas")
        return int(cur.fetchone()["n"])
