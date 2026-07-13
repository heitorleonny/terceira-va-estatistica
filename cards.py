"""
cards.py — Cards configuráveis de FIIs
======================================
Gerencia a configuração (persistida em `cards_config.json`) e o preparo dos
dados exibidos nos cards de destaque de FIIs. A renderização visual em si fica
em app.py (usa o helper `mcard()` e o tema escuro do dashboard); aqui só há a
lógica de configuração e de cálculo, para manter este módulo independente do
Streamlit e testável.

Reaproveita, sem duplicar:
  • utils.calcular_preco_teto_row → preço teto e margem de segurança
  • utils.get_grade_label         → classificação High/Middle/High Yield
"""

from __future__ import annotations

import json
import os

from utils import calcular_preco_teto_row, get_grade_label, _is_valid

CONFIG_PADRAO_PATH = "cards_config.json"

# Usado quando o arquivo de config não existe ainda.
_CONFIG_DEFAULT = {
    "cards_padrao": ["KNRI11", "HGLG11", "XPML11", "MXRF11", "BTLG11"],
    "cards_ativos": [],
}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO (carregar / salvar)
# ══════════════════════════════════════════════════════════════════════════════

def carregar_config(path: str = CONFIG_PADRAO_PATH) -> dict:
    """
    Carrega a configuração dos cards do JSON. Se o arquivo não existir ou
    estiver corrompido, devolve uma configuração padrão (sem lançar exceção).

    Garante que 'cards_ativos' esteja preenchido: se estiver vazio, popula a
    partir de 'cards_padrao' com todos visíveis e ordem sequencial.
    """
    config = dict(_CONFIG_DEFAULT)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                carregado = json.load(f)
            if isinstance(carregado, dict):
                config = {**_CONFIG_DEFAULT, **carregado}
        except (json.JSONDecodeError, OSError):
            config = dict(_CONFIG_DEFAULT)

    if not config.get("cards_ativos"):
        config["cards_ativos"] = [
            {"ticker": tk, "visivel": True, "ordem": i + 1}
            for i, tk in enumerate(config.get("cards_padrao", []))
        ]
    return config


def salvar_config(config: dict, path: str = CONFIG_PADRAO_PATH) -> None:
    """Persiste a configuração (visível/ordem de cada card) de volta no JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def tickers_visiveis(config: dict) -> list[str]:
    """Lista os tickers visíveis, na ordem definida em 'ordem'."""
    ativos = [c for c in config.get("cards_ativos", []) if c.get("visivel", True)]
    ativos.sort(key=lambda c: c.get("ordem", 999))
    return [c["ticker"] for c in ativos]


def adicionar_card(config: dict, ticker: str) -> dict:
    """
    Adiciona um novo card (ou reativa um já existente que estava invisível).
    A ordem recebida é a maior existente + 1. Retorna a config atualizada.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        return config
    ativos = config.setdefault("cards_ativos", [])
    for c in ativos:
        if c["ticker"] == ticker:
            c["visivel"] = True
            return config
    proxima_ordem = max((c.get("ordem", 0) for c in ativos), default=0) + 1
    ativos.append({"ticker": ticker, "visivel": True, "ordem": proxima_ordem})
    return config


def remover_card(config: dict, ticker: str) -> dict:
    """Remove um card da configuração pelo ticker. Retorna a config atualizada."""
    ticker = ticker.upper().strip()
    config["cards_ativos"] = [
        c for c in config.get("cards_ativos", []) if c["ticker"] != ticker
    ]
    return config


# ══════════════════════════════════════════════════════════════════════════════
# PREPARO DOS DADOS DO CARD
# ══════════════════════════════════════════════════════════════════════════════

def preparar_card(dado_fii: dict) -> dict:
    """
    A partir de um dict cru de FII (retorno de get_fii_data), calcula os campos
    exibidos no card: preço teto, margem de segurança e classificação (grade).

    Reutiliza calcular_preco_teto_row e get_grade_label de utils — não recria
    a lógica de preço teto/margem/grade.

    Retorna um dict pronto para exibição, incluindo o campo "erro" (str|None).
    """
    calc = calcular_preco_teto_row(dado_fii)
    premio = dado_fii.get("premio", 0.01)

    return {
        "ticker": dado_fii.get("ticker", "?"),
        "preco": dado_fii.get("preco"),
        "dy": dado_fii.get("dy"),
        "pvp": dado_fii.get("pvp"),
        "tipo": dado_fii.get("tipo", "Indefinido"),
        "preco_teto": calc["preco_teto"],
        "margem_seguranca": (
            calc["margem_seguranca"] * 100
            if _is_valid(calc["margem_seguranca"]) else None
        ),
        "grade": get_grade_label(premio),
        "erro": dado_fii.get("erro"),
    }


def ordenar_por_margem(cards: list[dict], limite: int | None = None) -> list[dict]:
    """
    Ordena os cards pela margem de segurança (maior primeiro). Cards sem margem
    válida vão para o fim. `limite` opcional recorta os N melhores (para o
    comportamento padrão de "4 a 5 FIIs com as melhores margens").
    """
    def chave(card: dict):
        m = card.get("margem_seguranca")
        # -inf empurra os inválidos para o final na ordenação decrescente.
        return m if _is_valid(m) else float("-inf")

    ordenados = sorted(cards, key=chave, reverse=True)
    return ordenados[:limite] if limite else ordenados
