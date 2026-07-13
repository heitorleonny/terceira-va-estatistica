"""
app.py — Dashboard FII Analyzer
=================================
6 abas: Simulação de Aporte | Carteira | Preço Teto | Análise Empírica |
        Cards | Histórico

Scraping via Playwright (browser real) — bypassa Cloudflare/JS do Investidor10.
Série histórica de preços via Yahoo Finance (yfinance). Persistência em SQLite.

Uso exclusivamente educacional — não constitui recomendação de investimento.

Execute com:  streamlit run app.py
"""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

from scraper import (
    get_fii_data,
    get_multiplos_fiis,
    IPCA_MAIS_GLOBAL,
)
from utils import (
    fmt_brl, fmt_pct, fmt_pct_dec, fmt_num, fmt_cell, _is_valid,
    simular_aporte, resumo_simulacao,
    montar_carteira, totais_carteira,
    tabela_preco_teto, calcular_preco_teto_row,
    PREMIO_KNOWN, PREMIO_DEFAULT, get_grade_label,
)

# Módulos novos deste incremento acadêmico.
import db
import cards as cards_mod
from historico_precos import obter_serie_historica, HistoricoError, init_cache
from stats_empirical import (
    calcular_estatisticas_log_retornos,
    calcular_probabilidade_cauda,
    teste_normalidade,
    dados_qqplot,
    DIAS_UTEIS_ANO,
)

# ── Configuração da página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="FII Analyzer",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --bg:#0d1117; --surface:#161b22; --border:#30363d;
    --accent:#2563eb; --accent-l:#3b82f6;
    --green:#22c55e; --red:#ef4444; --yellow:#f59e0b;
    --text:#e6edf3; --muted:#8b949e;
}
.stApp { background:var(--bg); color:var(--text); }
.block-container { padding:1.5rem 2rem; max-width:1400px; }

.metric-card {
    background:var(--surface); border:1px solid var(--border);
    border-radius:8px; padding:1.1rem 1.2rem; text-align:center;
}
.metric-card .lbl {
    color:var(--muted); font-size:0.72rem; text-transform:uppercase;
    letter-spacing:.06em; margin-bottom:.3rem;
}
.metric-card .val { color:var(--text); font-size:1.45rem; font-weight:700; line-height:1.1; }
.metric-card .val.g { color:var(--green); }
.metric-card .val.r { color:var(--red); }
.metric-card .val.b { color:var(--accent-l); }
.metric-card .val.y { color:var(--yellow); }

.stTabs [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--border); background:transparent; }
.stTabs [data-baseweb="tab"] {
    background:transparent; color:var(--muted); border:none;
    border-bottom:2px solid transparent; padding:.75rem 1.5rem;
    font-size:.9rem; font-weight:500;
}
.stTabs [aria-selected="true"] { color:var(--accent-l) !important; border-bottom-color:var(--accent-l) !important; }
.stButton > button {
    background:var(--accent); color:white; border:none;
    border-radius:6px; font-weight:600; padding:.5rem 1.25rem;
}
.stButton > button:hover { background:var(--accent-l); }
.box-warn  { background:#1a1000; border:1px solid var(--yellow); border-radius:6px; padding:.7rem 1rem; color:var(--yellow); font-size:.84rem; margin:.4rem 0; }
.box-error { background:#1a0000; border:1px solid var(--red);    border-radius:6px; padding:.7rem 1rem; color:var(--red);    font-size:.84rem; margin:.4rem 0; }
.box-info  { background:#001a2a; border:1px solid var(--accent);  border-radius:6px; padding:.7rem 1rem; color:var(--accent-l);font-size:.84rem; margin:.4rem 0; }
.ph { border-bottom:1px solid var(--border); margin-bottom:1.5rem; padding-bottom:1rem; }
.ph h1 { font-size:1.6rem; font-weight:700; color:var(--text); margin:0; }
.ph p  { color:var(--muted); margin:.2rem 0 0; font-size:.9rem; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def mcard(label: str, value: str, color: str = "") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="lbl">{label}</div>'
        f'<div class="val {color}">{value}</div></div>',
        unsafe_allow_html=True,
    )

def box(msg: str, kind: str = "warn") -> None:
    st.markdown(f'<div class="box-{kind}">{msg}</div>', unsafe_allow_html=True)

def plotly_layout(fig, title=""):
    fig.update_layout(
        title=title, template="plotly_dark",
        paper_bgcolor="#161b22", plot_bgcolor="#161b22",
        margin=dict(t=45, b=15, l=10, r=10),
        font=dict(color="#e6edf3"),
    )
    return fig

@st.cache_data(ttl=600, show_spinner=False)
def _buscar_um(ticker, premio_override_frozen, ipca_override_frozen):
    """Cache por ticker + configurações (600s = 10 min)."""
    return get_fii_data(
        ticker,
        premio_override=dict(premio_override_frozen),
        ipca_override=dict(ipca_override_frozen),
    )

def buscar_fii(ticker, premio_override=None, ipca_override=None):
    po = tuple(sorted((premio_override or {}).items()))
    io = tuple(sorted((ipca_override  or {}).items()))
    return _buscar_um(ticker, po, io)


# ── Persistência (SQLite) ─────────────────────────────────────────────────────
db.init_db()      # cria fii_dashboard.db e a tabela `consultas` se preciso
init_cache()      # cria a tabela de cache de histórico de preços (bônus 7.8)


def _persistir_consulta(dado: dict, fonte: str = "investidor10") -> None:
    """
    Grava a consulta no banco (best-effort). Enriquece o dict com preço teto e
    margem de segurança calculados, para que o histórico tenha essas colunas.
    Persistência nunca deve quebrar a UI — por isso o try/except amplo.
    """
    if not dado or dado.get("erro"):
        return
    try:
        registro = dict(dado)
        calc = calcular_preco_teto_row(dado)
        if _is_valid(calc.get("preco_teto")):
            registro["preco_teto"] = calc["preco_teto"]
        if _is_valid(calc.get("margem_seguranca")):
            registro["margem_seguranca"] = calc["margem_seguranca"] * 100
        db.salvar_consulta(registro, fonte)
    except Exception:
        pass


@st.cache_data(ttl=3600, show_spinner=False)
def _serie_cache(ticker: str, d_ini: date, d_fim: date) -> pd.DataFrame:
    """
    Série histórica com cache do Streamlit por (ticker, data_inicial,
    data_final). A chave de cache varia com os parâmetros do usuário, então o
    gráfico se atualiza sozinho quando ele muda ticker ou datas. Exceções
    (HistoricoError) não são cacheadas e são re-levantadas para a UI tratar.
    """
    return obter_serie_historica(ticker, d_ini, d_fim)


# ── Recarregar consulta antiga (acionado pela aba Histórico) ──────────────────
# Precisa rodar ANTES de os widgets serem criados, pois injeta valores em
# st.session_state (ticker e dados) que a aba "Simulação de Aporte" vai ler.
st.session_state.setdefault("t1t", "MXRF11")
if st.session_state.get("_pending_reload"):
    _pend = st.session_state.pop("_pending_reload")
    st.session_state["t1t"] = _pend.get("ticker", st.session_state["t1t"])
    st.session_state["t1_dados"] = _pend.get("dados")
    st.session_state["t1_manual"] = False
    box(f"↩️ Consulta de <b>{st.session_state['t1t']}</b> recarregada do "
        f"histórico na aba <b>Simulação de Aporte</b>.", "info")


# ── Cabeçalho ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="ph">
  <h1>🏢 FII Analyzer</h1>
  <p>Dashboard de análise de FIIs · indicadores via Investidor10 (Playwright) ·
     série histórica via Yahoo Finance · persistência em SQLite</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈  Simulação de Aporte",
    "📦  Carteira",
    "🎯  Preço Teto",
    "📊  Análise Empírica",
    "⭐  Cards",
    "🗂️  Histórico",
])


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 1 — SIMULAÇÃO DE APORTE MENSAL
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Simulação de Aporte Mensal")
    st.caption(
        "Projeta patrimônio e renda com aportes fixos mensais em um único FII. "
        "**Premissa:** preço e DY constantes. Dividendos não reinvestidos."
    )

    # Inputs
    ca, cb, cc = st.columns([2, 1, 1])
    with ca: t1_ticker = st.text_input("Ticker", key="t1t").upper().strip()
    with cb: t1_cotas  = st.number_input("Cotas/mês", min_value=1, max_value=10000, value=10, step=1)
    with cc: t1_meses  = st.number_input("Meses", min_value=1, max_value=600, value=240, step=12)

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        buscar1 = st.button("🔍 Buscar e Simular", key="btn1")

    if "t1_dados" not in st.session_state: st.session_state.t1_dados = None
    if "t1_manual" not in st.session_state: st.session_state.t1_manual = False

    if buscar1 and t1_ticker:
        with st.spinner(f"Abrindo navegador e coletando {t1_ticker}… (pode levar ~10s)"):
            st.session_state.t1_dados  = buscar_fii(t1_ticker)
            st.session_state.t1_manual = False
        # Persiste a consulta no histórico automaticamente (sem ação do usuário).
        _persistir_consulta(st.session_state.t1_dados, "investidor10")

    d1 = st.session_state.t1_dados

    def _simular_e_exibir(preco, dy, cotas, meses):
        df_s = simular_aporte(preco, dy, int(cotas), int(meses))
        res  = resumo_simulacao(df_s)

        st.markdown("#### Resultado")
        r1,r2,r3,r4,r5 = st.columns(5)
        with r1: mcard("Cotas Totais",       fmt_num(res["cotas_total"], 0))
        with r2: mcard("Total Investido",    fmt_brl(res["total_investido"]))
        with r3: mcard("Renda Mensal Final", fmt_brl(res["renda_mensal_final"]), "g")
        with r4: mcard("Renda Acumulada",    fmt_brl(res["renda_acumulada"]),    "g")
        with r5: mcard("Patrimônio Final",   fmt_brl(res["patrimonio_final"]),   "b")

        st.divider()
        g1, g2 = st.columns(2)
        with g1:
            fig = px.area(df_s, x="Mês",
                          y=["Total Investido (R$)", "Renda Acumulada (R$)"],
                          color_discrete_map={"Total Investido (R$)":"#2563eb",
                                              "Renda Acumulada (R$)":"#22c55e"})
            st.plotly_chart(plotly_layout(fig, "Patrimônio vs Renda Acumulada"),
                            use_container_width=True)
        with g2:
            fig2 = px.line(df_s, x="Mês", y="Renda Mensal (R$)",
                           color_discrete_sequence=["#22c55e"])
            st.plotly_chart(plotly_layout(fig2, "Renda Mensal ao Longo do Tempo"),
                            use_container_width=True)

        with st.expander("📋 Tabela anual"):
            df_a = df_s[df_s["Mês"] % 12 == 0].copy()
            df_a["Ano"] = (df_a["Mês"] // 12).astype(str) + "º"
            st.dataframe(
                df_a[["Ano","Cotas Acumuladas","Total Investido (R$)",
                      "Renda Mensal (R$)","Renda Acumulada (R$)"]].set_index("Ano"),
                use_container_width=True,
            )

    if d1:
        if d1.get("erro"):
            box(f"⚠️ {d1['erro']}", "error")
            st.session_state.t1_manual = True
        elif not _is_valid(d1.get("preco")) or not _is_valid(d1.get("dy")):
            faltando = [f for f, v in [("Cotação", d1.get("preco")), ("DY", d1.get("dy"))]
                        if not _is_valid(v)]
            box(f"⚠️ <b>{t1_ticker}</b>: {', '.join(faltando)} não encontrados. "
                f"Use a entrada manual abaixo.", "warn")
            st.session_state.t1_manual = True
        else:
            # Sucesso — mostra dados do ativo
            ca2, cb2, cc2, cd2, ce2 = st.columns(5)
            with ca2: mcard("Ticker",      d1["ticker"])
            with cb2: mcard("Cotação",     fmt_brl(d1["preco"]), "b")
            with cc2: mcard("DY 12M",      fmt_pct(d1["dy"]) if _is_valid(d1.get("dy")) else "N/D", "g")
            with cd2: mcard("P/VP",        fmt_num(d1["pvp"])  if _is_valid(d1.get("pvp")) else "N/D")
            with ce2: mcard("Tipo",        d1.get("tipo","Indefinido").capitalize())
            st.divider()
            _simular_e_exibir(d1["preco"], d1["dy"], t1_cotas, t1_meses)

    # Fallback manual
    with st.expander("⚙️ Inserir dados manualmente",
                     expanded=st.session_state.get("t1_manual", False)):
        st.caption("Use quando o scraping não retornar valores ou para testar cenários.")
        ma, mb = st.columns(2)
        with ma: m_preco = st.number_input("Cotação (R$)", 0.01, value=10.00, step=0.01, key="t1mp")
        with mb: m_dy    = st.number_input("DY Anual (%)", 0.01, value=9.00, step=0.01, key="t1md")
        mc, md = st.columns(2)
        with mc: m_cotas = st.number_input("Cotas/mês", 1, value=int(t1_cotas), key="t1mc")
        with md: m_meses = st.number_input("Meses",     1, value=int(t1_meses), key="t1mm")
        if st.button("▶ Simular com dados manuais", key="btn1m"):
            _simular_e_exibir(m_preco, m_dy, m_cotas, m_meses)


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 2 — CARTEIRA COM MÚLTIPLOS FIIs
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Montagem de Carteira")
    st.caption(
        "Adicione múltiplos FIIs e quantidades. "
        "Os dados são coletados em sequência num único browser."
    )

    n = st.number_input("Quantos FIIs?", min_value=1, max_value=20, value=3, step=1)

    st.markdown("---")
    inputs2 = []
    for i in range(int(n)):
        ca, cb = st.columns([2, 1])
        with ca:
            tk = st.text_input(f"Ticker #{i+1}", value="", key=f"ct_{i}",
                               placeholder="Ex: KNRI11").upper().strip()
        with cb:
            qt = st.number_input(f"Cotas #{i+1}", min_value=0, value=100, step=1, key=f"cq_{i}")
        if tk:
            inputs2.append({"ticker": tk, "quantidade": int(qt)})

    buscar2 = st.button("🔍 Montar Carteira", key="btn2")

    if buscar2 and inputs2:
        tickers2 = [x["ticker"] for x in inputs2]
        qtds2    = {x["ticker"]: x["quantidade"] for x in inputs2}

        prog2 = st.progress(0, text="Iniciando coleta…")

        def cb2(ticker, idx, total):
            prog2.progress(idx / total, text=f"Coletado {ticker} ({idx}/{total})")

        with st.spinner("Abrindo navegador… pode levar alguns segundos por FII."):
            resultados2 = get_multiplos_fiis(
                tickers2,
                progress_callback=cb2,
            )
        prog2.progress(1.0, text="Concluído!")
        prog2.empty()

        # Injeta quantidade e exibe avisos
        fiis2 = []
        for d in resultados2:
            d["quantidade"] = qtds2.get(d["ticker"], 0)
            if d.get("erro"):
                box(f"⚠️ <b>{d['ticker']}</b>: {d['erro']}", "error")
            else:
                missing = [f for f, v in [("Preço", d.get("preco")), ("DY", d.get("dy"))]
                           if not _is_valid(v)]
                if missing:
                    box(f"⚠️ <b>{d['ticker']}</b>: {', '.join(missing)} não encontrados — "
                        f"linha exibirá N/D.", "warn")
            fiis2.append(d)
            _persistir_consulta(d, "investidor10")  # grava cada FII no histórico

        if fiis2:
            df2  = montar_carteira(fiis2)
            tot2 = totais_carteira(df2)

            st.divider()
            tc1, tc2, tc3 = st.columns(3)
            with tc1: mcard("Investimento Total",  fmt_brl(tot2["total_investido"]),    "b")
            with tc2: mcard("Renda Mensal Total",  fmt_brl(tot2["total_renda_mensal"]), "g")
            with tc3: mcard("DY Médio Ponderado",  fmt_pct(tot2["dy_medio_ponderado"]) if _is_valid(tot2.get("dy_medio_ponderado")) else "N/D", "g")

            st.divider()
            st.markdown("#### Composição da Carteira")

            # Formata para exibição
            df2_show = df2.copy()
            df2_show["Preço (R$)"]          = df2_show["Preço (R$)"].apply(lambda x: fmt_cell(x, "R$ "))
            df2_show["Investimento (R$)"]   = df2_show["Investimento (R$)"].apply(lambda x: fmt_cell(x, "R$ "))
            df2_show["Proventos/cota (R$)"] = df2_show["Proventos/cota (R$)"].apply(lambda x: fmt_cell(x, "R$ ", 4))
            df2_show["Renda Mensal (R$)"]   = df2_show["Renda Mensal (R$)"].apply(lambda x: fmt_cell(x, "R$ "))
            df2_show["DY (%)"]              = df2_show["DY (%)"].apply(
                lambda x: f"{x:.2f}%".replace(".", ",") if _is_valid(x) else "N/D"
            )
            df2_show["P/VP"] = df2_show["P/VP"].apply(
                lambda x: fmt_num(x) if _is_valid(x) else "N/D"
            )
            st.dataframe(df2_show, use_container_width=True, hide_index=True)

            # Gráficos
            df2_num = df2.dropna(subset=["Investimento (R$)", "Renda Mensal (R$)"])
            if not df2_num.empty:
                st.divider()
                g1, g2 = st.columns(2)
                with g1:
                    fig_i = px.pie(df2_num, names="FII", values="Investimento (R$)",
                                   color_discrete_sequence=px.colors.sequential.Blues_r)
                    st.plotly_chart(plotly_layout(fig_i, "Composição por Investimento"),
                                    use_container_width=True)
                with g2:
                    fig_r = px.pie(df2_num, names="FII", values="Renda Mensal (R$)",
                                   color_discrete_sequence=px.colors.sequential.Greens_r)
                    st.plotly_chart(plotly_layout(fig_r, "Composição por Renda Mensal"),
                                    use_container_width=True)

            df2_dy = df2.dropna(subset=["DY (%)"])
            if not df2_dy.empty:
                fig_dy = px.bar(df2_dy.sort_values("DY (%)", ascending=False),
                                x="FII", y="DY (%)", color="DY (%)",
                                color_continuous_scale="Blues", text_auto=".2f")
                st.plotly_chart(plotly_layout(fig_dy, "Dividend Yield por FII (%)"),
                                use_container_width=True)

    # Entrada manual
    with st.expander("⚙️ Adicionar ativo manualmente"):
        ma2, mb2 = st.columns(2)
        with ma2: m2_tk  = st.text_input("Ticker", key="m2tk").upper().strip()
        with mb2: m2_qt  = st.number_input("Cotas", min_value=0, value=100, key="m2qt")
        mc2, md2, me2, mf2 = st.columns(4)
        with mc2: m2_p  = st.number_input("Cotação (R$)",     0.01,  value=10.00, step=0.01,  key="m2p")
        with md2: m2_dy = st.number_input("DY (%)",           0.01,  value=9.00,  step=0.01,  key="m2dy")
        with me2: m2_d  = st.number_input("Dividendo 12M (R$)", 0.01, value=0.90,  step=0.01, key="m2d")
        with mf2: m2_ti = st.selectbox("Tipo", ["papel","tijolo","Indefinido"], key="m2ti")
        if st.button("➕ Calcular", key="btn2m"):
            fii_m = [{"ticker": m2_tk or "MANUAL", "preco": m2_p, "dy": m2_dy,
                      "dividendo_12m": m2_d, "pvp": None, "tipo": m2_ti,
                      "quantidade": int(m2_qt)}]
            df_m = montar_carteira(fii_m)
            tot_m = totais_carteira(df_m)
            xm1, xm2, xm3 = st.columns(3)
            with xm1: mcard("Investimento", fmt_brl(tot_m["total_investido"]),   "b")
            with xm2: mcard("Renda Mensal", fmt_brl(tot_m["total_renda_mensal"]),"g")
            with xm3: mcard("DY Anual",     fmt_pct(tot_m["dy_medio_ponderado"]) if _is_valid(tot_m.get("dy_medio_ponderado")) else "N/D", "g")


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 3 — PREÇO TETO
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Cálculo de Preço Teto")
    st.caption(
        "Baseado na metodologia do **fiis.py**: "
        "**Preço Teto = Dividendo 12M (R$) ÷ (IPCA+ + Prêmio)**"
    )

    with st.expander("📐 Metodologia completa"):
        st.markdown(f"""
**Fórmulas (fiel ao fiis.py):**
```
DIVIDENDO 12M (R$) = PREÇO × DY 12M%
TAXA REQUERIDA     = IPCA+ ({IPCA_MAIS_GLOBAL*100:.0f}%) + PRÊMIO
PREÇO TETO         = DIVIDENDO 12M (R$) / TAXA REQUERIDA
MARGEM DE SEG.     = (PREÇO TETO - PREÇO) / PREÇO × 100
```

**IPCA por tipo de fundo** (informativo — não entra na taxa):

| % FII na carteira | IPCA |
|---|---|
| 0% – 25%  | 0,0% — tijolo puro |
| 25% – 40% | 1,5% |
| 40% – 60% | 2,5% |
| 60% – 75% | 3,5% |
| 75% – 100%| 5,0% — papel puro |

**Prêmio de risco padrão:**

| Grade | Prêmio | Exemplos |
|---|---|---|
| High Grade  | 1% | KNRI11, HGLG11, XPML11, BTLG11 |
| Middle Grade| 3% | GARE11, BTCI11, TRXF11, KNCR11 |
| High Yield  | 5% | MXRF11, RECR11, VGHF11, PORD11 |
        """)

    # Tickers
    tickers_raw3 = st.text_input(
        "Tickers (separados por vírgula)",
        value="MXRF11, KNRI11, XPML11, BTLG11, HGLG11",
        key="t3raw"
    )
    tickers3 = [t.strip().upper() for t in tickers_raw3.split(",") if t.strip()]

    # Configurações por ticker
    if tickers3:
        st.markdown("##### Configurações de Prêmio e IPCA por ativo:")
        st.caption(
            "Prêmio pré-preenchido pelos valores do fiis.py. "
            "Ajuste conforme sua análise. IPCA é detectado automaticamente pelo tipo do fundo."
        )

        configs3 = {}
        # Grid de até 4 colunas
        num_cols = min(len(tickers3), 4)
        cols3 = st.columns(num_cols)

        for i, tk in enumerate(tickers3):
            default_prem = PREMIO_KNOWN.get(tk, PREMIO_DEFAULT)
            default_label = {0.01: "High Grade (1%)", 0.03: "Middle Grade (3%)", 0.05: "High Yield (5%)"}.get(
                default_prem, "High Grade (1%)"
            )
            with cols3[i % num_cols]:
                st.markdown(f"**{tk}**")
                prem_sel = st.selectbox(
                    "Prêmio",
                    options=["High Grade (1%)", "Middle Grade (3%)", "High Yield (5%)"],
                    index=["High Grade (1%)", "Middle Grade (3%)", "High Yield (5%)"].index(default_label),
                    key=f"p3_{tk}",
                )
                ipca_sel = st.selectbox(
                    "IPCA (override)",
                    options=["Auto (pelo tipo)", "0% Tijolo", "1,5%", "2,5%", "3,5%", "5% Papel"],
                    key=f"i3_{tk}",
                )
                configs3[tk] = {
                    "premio": {"High Grade (1%)": 0.01, "Middle Grade (3%)": 0.03, "High Yield (5%)": 0.05}[prem_sel],
                    "ipca_override": {
                        "Auto (pelo tipo)": None, "0% Tijolo": 0.00,
                        "1,5%": 0.015, "2,5%": 0.025, "3,5%": 0.035, "5% Papel": 0.05,
                    }[ipca_sel],
                }

    buscar3 = st.button("🔍 Calcular Preço Teto", key="btn3")

    if buscar3 and tickers3:
        premio_ov3 = {"default": 0.01}
        ipca_ov3   = {}
        for tk, cfg in configs3.items():
            premio_ov3[tk] = cfg["premio"]
            if cfg["ipca_override"] is not None:
                ipca_ov3[tk] = cfg["ipca_override"]

        prog3 = st.progress(0, text="Iniciando…")

        def cb3(ticker, idx, total):
            prog3.progress(idx / total, text=f"Coletado {ticker} ({idx}/{total})")

        with st.spinner("Coletando via Playwright… aguarde."):
            resultados3 = get_multiplos_fiis(
                tickers3,
                premio_override=premio_ov3,
                ipca_override=ipca_ov3,
                progress_callback=cb3,
            )
        prog3.progress(1.0, text="Concluído!")
        prog3.empty()

        erros3 = [d for d in resultados3 if d.get("erro")]
        validos3 = [d for d in resultados3 if not d.get("erro")]

        for d in erros3:
            box(f"⚠️ <b>{d['ticker']}</b>: {d['erro']}", "error")

        for d in validos3:
            _persistir_consulta(d, "investidor10")  # grava no histórico

        if validos3:
            df3 = tabela_preco_teto(validos3)

            st.divider()
            st.markdown("#### Tabela de Preço Teto")

            # Estilização condicional (pandas >= 2.1 usa .map)
            def _cor_margem(v):
                if v is None or (isinstance(v, float) and math.isnan(v)): return "color:#8b949e"
                return "color:#22c55e;font-weight:700" if v >= 0 else "color:#ef4444;font-weight:700"

            def _cor_pvp(v):
                if v is None or (isinstance(v, float) and math.isnan(v)): return ""
                if v < 1.0:  return "color:#22c55e"
                if v <= 1.1: return "color:#f59e0b"
                return "color:#ef4444"

            def _f(x, prefix="", dec=2, suffix=""):
                if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))): return "N/D"
                s = f"{x:,.{dec}f}".replace(",","X").replace(".",",").replace("X",".")
                return f"{prefix}{s}{suffix}"

            styled3 = (
                df3.style
                .map(_cor_margem, subset=["Margem Seg. (%)"])
                .map(_cor_pvp,    subset=["P/VP"])
                .format({
                    "P/VP":               lambda x: _f(x, dec=2),
                    "Preço (R$)":          lambda x: _f(x, "R$ "),
                    "DY 12M (%)":          lambda x: _f(x, dec=2, suffix="%"),
                    "Dividendo 12M (R$)":  lambda x: _f(x, "R$ ", 4),
                    "IPCA":                lambda x: _f(x*100 if _is_valid(x) else x, dec=1, suffix="%"),
                    "IPCA+":               lambda x: _f(x*100 if _is_valid(x) else x, dec=0, suffix="%"),
                    "Prêmio":              lambda x: _f(x*100 if _is_valid(x) else x, dec=0, suffix="%"),
                    "Taxa Req.":            lambda x: _f(x*100 if _is_valid(x) else x, dec=0, suffix="%"),
                    "Preço Teto (R$)":     lambda x: _f(x, "R$ "),
                    "Margem Seg. (%)":     lambda x: (
                        "N/D" if not _is_valid(x)
                        else f"{x:+.2f}%".replace(".", ",")
                    ),
                })
            )
            st.dataframe(styled3, use_container_width=True, hide_index=True)

            # ── Gráfico: Preço Atual vs Preço Teto ───────────────────────────
            df3_plot = df3.dropna(subset=["Preço (R$)", "Preço Teto (R$)"])
            if not df3_plot.empty:
                st.divider()
                fig_bar3 = go.Figure()
                fig_bar3.add_trace(go.Bar(
                    name="Preço Atual", x=df3_plot["FII"], y=df3_plot["Preço (R$)"],
                    marker_color="#2563eb",
                    text=df3_plot["Preço (R$)"].apply(lambda x: f"R$ {x:.2f}" if _is_valid(x) else ""),
                    textposition="outside",
                ))
                fig_bar3.add_trace(go.Bar(
                    name="Preço Teto", x=df3_plot["FII"], y=df3_plot["Preço Teto (R$)"],
                    marker_color="#22c55e",
                    text=df3_plot["Preço Teto (R$)"].apply(lambda x: f"R$ {x:.2f}" if _is_valid(x) else ""),
                    textposition="outside",
                ))
                fig_bar3.update_layout(barmode="group", legend=dict(orientation="h", y=-0.15))
                st.plotly_chart(plotly_layout(fig_bar3, "Preço Atual vs Preço Teto"),
                                use_container_width=True)

            # ── Gráfico de margens ────────────────────────────────────────────
            df3_mg = df3.dropna(subset=["Margem Seg. (%)"])
            if not df3_mg.empty:
                cores_mg = ["#22c55e" if v >= 0 else "#ef4444" for v in df3_mg["Margem Seg. (%)"]]
                fig_mg3 = go.Figure(go.Bar(
                    x=df3_mg["FII"], y=df3_mg["Margem Seg. (%)"],
                    marker_color=cores_mg,
                    text=df3_mg["Margem Seg. (%)"].apply(lambda x: f"{x:+.1f}%"),
                    textposition="outside",
                ))
                fig_mg3.add_hline(y=0, line_dash="dash", line_color="#8b949e")
                fig_mg3.update_layout(yaxis_ticksuffix="%")
                st.plotly_chart(plotly_layout(fig_mg3, "Margem de Segurança (%)"),
                                use_container_width=True)

            # ── Gráfico de IPCA por fundo ─────────────────────────────────────
            df3_ipca = df3.dropna(subset=["IPCA"])
            if not df3_ipca.empty:
                fig_ipca = px.bar(
                    df3_ipca, x="FII",
                    y=df3_ipca["IPCA"] * 100,
                    color="Tipo",
                    color_discrete_map={"papel":"#f59e0b","tijolo":"#2563eb","Indefinido":"#8b949e"},
                    text_auto=".1f",
                    labels={"y": "IPCA (%)"},
                )
                st.plotly_chart(plotly_layout(fig_ipca, "IPCA Estimado por Fundo (%)"),
                                use_container_width=True)

    # Entrada manual preço teto
    with st.expander("⚙️ Calcular preço teto manualmente"):
        pm1, pm2, pm3, pm4 = st.columns(4)
        with pm1: m3_tk  = st.text_input("Ticker", "TICKER",  key="m3tk")
        with pm2: m3_p   = st.number_input("Preço (R$)",       0.01, value=10.00, step=0.01, key="m3p")
        with pm3: m3_d   = st.number_input("Dividendo 12M (R$)", 0.001, value=0.90, step=0.01, key="m3d")
        with pm4: m3_dy  = st.number_input("DY (%)",           0.01, value=9.00, step=0.01, key="m3dy")
        pm5, pm6, pm7 = st.columns(3)
        with pm5: m3_ti  = st.selectbox("Tipo", ["papel","tijolo","Indefinido"], key="m3ti")
        with pm6: m3_pct = st.slider("% FII na carteira", 0, 100, 80, key="m3pct")
        with pm7: m3_gr  = st.selectbox("Grade de risco",
                                        ["High Grade (1%)", "Middle Grade (3%)", "High Yield (5%)"], key="m3gr")

        if st.button("🧮 Calcular", key="btn3m"):
            from scraper import ipca_por_percentual_fii
            prem_m = {"High Grade (1%)": 0.01, "Middle Grade (3%)": 0.03, "High Yield (5%)": 0.05}[m3_gr]
            ipca_m = 0.00 if "tijolo" in m3_ti else ipca_por_percentual_fii(m3_pct / 100)

            fii_m3 = [{
                "ticker": m3_tk.upper(), "preco": m3_p, "dy": m3_dy,
                "dividendo_12m": m3_d, "pvp": None, "tipo": m3_ti,
                "ipca": ipca_m, "ipca_mais": IPCA_MAIS_GLOBAL, "premio": prem_m,
            }]
            df_m3 = tabela_preco_teto(fii_m3)
            row   = df_m3.iloc[0]

            xm1, xm2, xm3, xm4, xm5 = st.columns(5)
            with xm1: mcard("IPCA Estimado", fmt_pct(ipca_m * 100, 1))
            with xm2: mcard("Taxa Req.",     fmt_pct((IPCA_MAIS_GLOBAL + prem_m) * 100, 0))
            with xm3: mcard("Preço Teto",    fmt_brl(row["Preço Teto (R$)"]))
            mg = row["Margem Seg. (%)"]
            cg = "g" if _is_valid(mg) and mg >= 0 else "r"
            with xm4: mcard("Margem Seg.",   fmt_pct(mg) if _is_valid(mg) else "N/D", cg)
            with xm5: mcard("Grade",         m3_gr.split(" ")[0] + " " + m3_gr.split(" ")[1])

# ══════════════════════════════════════════════════════════════════════════════
# JANELA 4 — ANÁLISE EMPÍRICA DOS RETORNOS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Análise Empírica dos Retornos")
    st.caption(
        "Série histórica de preços de fechamento, distribuição dos log-retornos "
        "diários (com normal ajustada) e probabilidade de o preço cruzar um "
        "valor de referência. Série via Yahoo Finance (yfinance)."
    )
    box(
        "📚 <b>Uso educacional.</b> As probabilidades abaixo assumem que os "
        "log-retornos diários seguem uma distribuição <b>normal</b> — uma "
        "simplificação conhecida: retornos reais têm caudas mais pesadas e "
        "volatilidade que varia no tempo. Nada aqui é recomendação de investimento.",
        "info",
    )

    # ── Inputs ────────────────────────────────────────────────────────────────
    ce1, ce2, ce3, ce4 = st.columns([2, 1.3, 1.1, 1.3])
    with ce1:
        t4_ticker = st.text_input("Ticker do FII", value="MXRF11", key="t4t").upper().strip()
    with ce2:
        t4_ini = st.date_input("Data inicial", value=date.today() - timedelta(days=365),
                               max_value=date.today(), key="t4ini")
    with ce3:
        t4_ate_hoje = st.checkbox("Até hoje", value=True, key="t4hoje")
    with ce4:
        t4_fim = st.date_input("Data final", value=date.today(),
                               max_value=date.today(), key="t4fim",
                               disabled=t4_ate_hoje)
    d_fim = date.today() if t4_ate_hoje else t4_fim

    if not t4_ticker:
        box("Informe um ticker (ex.: MXRF11) para carregar a série.", "warn")
    elif t4_ini >= d_fim:
        box("A data inicial deve ser anterior à data final.", "error")
    else:
        serie = None
        try:
            with st.spinner(f"Buscando histórico de {t4_ticker} no Yahoo Finance…"):
                serie = _serie_cache(t4_ticker, t4_ini, d_fim)
        except HistoricoError as exc:
            box(f"⚠️ {exc}", "error")

        if serie is not None and len(serie) >= 2:
            # Persiste um resumo desta consulta histórica (fonte yfinance) apenas
            # UMA vez por (ticker, período). Como o script reroda a cada interação
            # (mover o slider, trocar de aba…), sem essa trava o histórico
            # acumularia consultas duplicadas a cada rerun.
            _chave_serie = (t4_ticker, t4_ini.isoformat(), d_fim.isoformat())
            if st.session_state.get("_ultima_serie_persistida") != _chave_serie:
                _persistir_consulta({
                    "ticker": t4_ticker,
                    "preco": float(serie["close"].iloc[-1]),
                    "periodo": f"{t4_ini.isoformat()} a {d_fim.isoformat()}",
                    "n_pregoes": int(len(serie)),
                }, "yfinance")
                st.session_state["_ultima_serie_persistida"] = _chave_serie

            stats = calcular_estatisticas_log_retornos(serie[["close"]])

            # ── Métricas descritivas ──
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                mcard("Pregões (n)", fmt_num(stats["n"], 0))
            with m2:
                mcard("Último Preço", fmt_brl(stats["ultimo_preco"]), "b")
            with m3:
                ok_ma = _is_valid(stats["media_log_anual"])
                mcard("Retorno Médio Anual*",
                      fmt_pct(stats["media_log_anual"] * 100) if ok_ma else "N/D",
                      "g" if ok_ma and stats["media_log_anual"] >= 0 else "r")
            with m4:
                ok_sa = _is_valid(stats["sigma_anual"])
                mcard("Volatilidade Anual*",
                      fmt_pct(stats["sigma_anual"] * 100) if ok_sa else "N/D", "y")
            st.caption(f"*Anualização assumindo {DIAS_UTEIS_ANO} pregões/ano "
                       f"(média × {DIAS_UTEIS_ANO}; desvio × √{DIAS_UTEIS_ANO}).")

            # ── 4.3.1 Série temporal ──
            st.markdown("#### Série temporal — preço de fechamento")
            fig_serie = px.line(
                serie, x="data", y="close",
                labels={"data": "Data", "close": "Preço de fechamento (R$)"},
                color_discrete_sequence=["#3b82f6"],
            )
            fig_serie.update_traces(hovertemplate="%{x|%d/%m/%Y}<br>R$ %{y:.2f}")
            st.plotly_chart(plotly_layout(fig_serie, f"{t4_ticker} — Preço de Fechamento"),
                            use_container_width=True)
            st.caption("Preço de fechamento = último preço negociado em cada pregão. "
                       "É a série base para o cálculo dos log-retornos.")

            # ── 4.3.2 Histograma dos log-retornos + normal ──
            st.divider()
            st.markdown("#### Distribuição dos log-retornos diários")
            if stats["n"] < 2 or not _is_valid(stats["dp_diario"]) or stats["dp_diario"] == 0:
                box("Dados insuficientes (ou preço constante) para estimar a "
                    "distribuição dos log-retornos no período selecionado.", "warn")
            else:
                lr = stats["log_retornos"]
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=lr, histnorm="probability density", nbinsx=40,
                    marker_color="#2563eb", opacity=0.65, name="Log-retornos",
                ))
                x_norm = np.linspace(float(lr.min()), float(lr.max()), 200)
                y_norm = norm.pdf(x_norm, stats["media_diaria"], stats["dp_diario"])
                fig_hist.add_trace(go.Scatter(
                    x=x_norm, y=y_norm, mode="lines",
                    line=dict(color="#22c55e", width=2.5), name="Normal ajustada",
                ))
                fig_hist.add_vline(x=stats["media_diaria"], line_dash="dash",
                                   line_color="#f59e0b")
                fig_hist.update_layout(legend=dict(orientation="h", y=-0.2),
                                       xaxis_title="Log-retorno diário",
                                       yaxis_title="Densidade")
                st.plotly_chart(
                    plotly_layout(fig_hist, "Histograma dos Log-Retornos com Normal Ajustada"),
                    use_container_width=True)

                s1, s2, s3 = st.columns(3)
                with s1: mcard("Média diária (μ)", f"{stats['media_diaria']:.5f}")
                with s2: mcard("Desvio diário (σ)", f"{stats['dp_diario']:.5f}")
                with s3: mcard("Observações (n)", fmt_num(stats["n"], 0))
                st.caption(
                    "Log-retorno diário: r = ln(Pₜ / Pₜ₋₁). Usa-se o logaritmo porque é "
                    "aditivo no tempo e costuma se aproximar melhor de uma normal. A curva "
                    "verde é a normal N(μ, σ²) ajustada aos dados — compare-a com as barras "
                    "para julgar o quão razoável é a hipótese de normalidade."
                )

                # ── Bônus 7.5: QQ-Plot + teste de normalidade ──
                with st.expander("🔎 QQ-Plot e teste de normalidade (bônus)"):
                    qq = dados_qqplot(stats)
                    tn = teste_normalidade(stats)
                    cq1, cq2 = st.columns([1.5, 1])
                    with cq1:
                        if qq["teoricos"]:
                            fig_qq = go.Figure()
                            fig_qq.add_trace(go.Scatter(
                                x=qq["teoricos"], y=qq["amostrais"], mode="markers",
                                marker=dict(color="#3b82f6", size=5), name="Log-retornos"))
                            fig_qq.add_trace(go.Scatter(
                                x=qq["reta_x"], y=qq["reta_y"], mode="lines",
                                line=dict(color="#ef4444", dash="dash"), name="Normal teórica"))
                            fig_qq.update_layout(
                                xaxis_title="Quantis teóricos (normal)",
                                yaxis_title="Quantis amostrais",
                                legend=dict(orientation="h", y=-0.25))
                            st.plotly_chart(plotly_layout(fig_qq, "QQ-Plot"),
                                            use_container_width=True)
                    with cq2:
                        if tn["teste"]:
                            st.markdown(f"**Teste:** {tn['teste']}")
                            mcard("Estatística", f"{tn['estatistica']:.4f}")
                            mcard("p-valor", f"{tn['p_valor']:.4g}")
                            if tn["normal"]:
                                box("p ≥ 0,05 → <b>não</b> se rejeita a normalidade "
                                    "a 5%. Log-retornos compatíveis com uma normal.", "info")
                            else:
                                box("p &lt; 0,05 → rejeita-se a normalidade a 5%. Há "
                                    "evidência de desvio da normal (caudas pesadas, comum "
                                    "em ativos). Trate as probabilidades com cautela.", "warn")
                    st.caption("No QQ-plot, pontos sobre a reta indicam aderência à normal; "
                               "desvios nas pontas revelam caudas mais pesadas que a normal.")

                # ── 4.3.3 Controle de preço + probabilidade de cauda ──
                st.divider()
                st.markdown("#### Preço de referência e probabilidade de cauda")
                pmin_r = round(float(stats["preco_minimo"]), 2)
                pmax_r = round(float(stats["preco_maximo"]), 2)
                if _is_valid(pmin_r) and _is_valid(pmax_r) and pmax_r > pmin_r:
                    alvo_default = min(max(round(float(stats["ultimo_preco"]), 2), pmin_r), pmax_r)
                    cpa, cpb = st.columns([1.6, 1])
                    with cpa:
                        preco_alvo = st.slider(
                            "Preço de referência (R$)",
                            min_value=pmin_r, max_value=pmax_r,
                            value=float(alvo_default), step=0.01, key="t4alvo")
                    with cpb:
                        cauda_label = st.radio(
                            "Cenário",
                            ["Probabilidade de cair abaixo do preço escolhido",
                             "Probabilidade de subir acima do preço escolhido"],
                            key="t4cauda")
                    cauda = "inferior" if "cair abaixo" in cauda_label else "superior"
                    res = calcular_probabilidade_cauda(stats, preco_alvo, cauda)

                    rp1, rp2, rp3 = st.columns(3)
                    with rp1: mcard("Preço de referência", fmt_brl(preco_alvo), "y")
                    with rp2: mcard("z (desvios-padrão)",
                                    f"{res['z']:.4f}".replace(".", ",") if _is_valid(res["z"]) else "N/D")
                    with rp3:
                        prob = res["probabilidade"]
                        mcard("Probabilidade",
                              fmt_pct(prob * 100) if _is_valid(prob) else "N/D",
                              "r" if cauda == "inferior" else "g")

                    direcao = "abaixo de" if cauda == "inferior" else "acima de"
                    if _is_valid(res["probabilidade"]):
                        box(f"Sob a hipótese de log-retornos normais, a probabilidade "
                            f"(horizonte de 1 pregão) de <b>{t4_ticker}</b> fechar "
                            f"<b>{direcao} {fmt_brl(preco_alvo)}</b> é de "
                            f"<b>{fmt_pct(res['probabilidade'] * 100)}</b> "
                            f"(z = {res['z']:.3f}). Cálculo ilustrativo — não é "
                            f"recomendação de investimento.", "info")
                    st.caption(
                        "z mede quantos desvios-padrão o preço de referência está do preço "
                        "atual, já descontada a tendência média. A cauda inferior usa Φ(z) "
                        "(área à esquerda da normal); a superior usa 1 − Φ(z) (à direita)."
                    )

                    # ── Bônus 7.7: exportação CSV ──
                    with st.expander("⬇️ Exportar dados desta análise (bônus)"):
                        csv_serie = serie.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Baixar série de preços (CSV)", csv_serie,
                            file_name=f"{t4_ticker}_serie_precos.csv", mime="text/csv",
                            key="dl_serie")
                        df_lr = lr.reset_index(drop=True).rename("log_retorno").to_frame()
                        csv_lr = df_lr.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Baixar log-retornos (CSV)", csv_lr,
                            file_name=f"{t4_ticker}_log_retornos.csv", mime="text/csv",
                            key="dl_lr")
                else:
                    box("Faixa de preços insuficiente no período para o controle "
                        "de preço de referência.", "warn")
        elif serie is not None:
            box("Série encontrada, mas com pontos insuficientes para análise "
                "(mínimo 2 pregões). Amplie o intervalo de datas.", "warn")


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 5 — CARDS CONFIGURÁVEIS DE FIIs
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Cards de FIIs em Destaque")
    st.caption(
        "Cards configuráveis com os principais indicadores. Por padrão, destaca "
        "os FIIs configurados com as melhores margens de segurança. A configuração "
        "(visibilidade e ordem) é persistida em cards_config.json."
    )

    if "cards_config" not in st.session_state:
        st.session_state.cards_config = cards_mod.carregar_config()
    if "cards_dados" not in st.session_state:
        st.session_state.cards_dados = {}   # ticker -> dict preparado
    cfg = st.session_state.cards_config

    # ── Ações de configuração ──
    cc1, cc2, cc3 = st.columns([2, 1, 1.2])
    with cc1:
        novo_tk = st.text_input("Adicionar card (ticker)", key="card_novo",
                                placeholder="Ex: BTLG11").upper().strip()
    with cc2:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if st.button("➕ Adicionar", key="card_add") and novo_tk:
            cards_mod.adicionar_card(cfg, novo_tk)
            cards_mod.salvar_config(cfg)
            st.rerun()
    with cc3:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        recarregar_cards = st.button("🔄 Carregar/Atualizar dados", key="card_reload")

    visiveis = cards_mod.tickers_visiveis(cfg)
    if not visiveis:
        box("Nenhum card configurado. Adicione um ticker acima.", "warn")
    else:
        st.caption("Configurados: " + ", ".join(visiveis))

        # "Atualizar" força nova busca ignorando o cache do Streamlit
        # (get_multiplos_fiis é chamado diretamente, sem passar por buscar_fii).
        if recarregar_cards:
            premio_ovc = {tk: PREMIO_KNOWN.get(tk, PREMIO_DEFAULT) for tk in visiveis}
            premio_ovc["default"] = PREMIO_DEFAULT
            with st.spinner("Coletando indicadores dos cards via Playwright…"):
                resultados_c = get_multiplos_fiis(visiveis, premio_override=premio_ovc)
            novos = {}
            for d in resultados_c:
                novos[d["ticker"]] = cards_mod.preparar_card(d)
                _persistir_consulta(d, "investidor10")
            st.session_state.cards_dados = novos

        dados_c = st.session_state.cards_dados
        if not dados_c:
            box("Clique em <b>Carregar/Atualizar dados</b> para buscar os "
                "indicadores dos cards configurados.", "info")
        else:
            preparados = [dados_c[tk] for tk in visiveis if tk in dados_c]
            ordenados = cards_mod.ordenar_por_margem(preparados)
            destaques = ordenados[:5]   # 4 a 5 melhores margens

            st.markdown("#### Destaques (ordenados por margem de segurança)")
            for c in destaques:
                if c.get("erro"):
                    box(f"⚠️ <b>{c['ticker']}</b>: {c['erro']}", "error")
                    continue
                margem = c["margem_seguranca"]
                mcolor = "g" if _is_valid(margem) and margem >= 0 else "r"
                st.markdown(
                    f"<div style='margin-top:.7rem;font-weight:700;font-size:1.05rem;"
                    f"color:#e6edf3'>⭐ {c['ticker']} "
                    f"<span style='font-size:.8rem;color:#8b949e'>· {c['grade']} · "
                    f"{str(c['tipo']).capitalize()}</span></div>",
                    unsafe_allow_html=True)
                k1, k2, k3, k4, k5, k6 = st.columns(6)
                with k1: mcard("Preço", fmt_brl(c["preco"]) if _is_valid(c["preco"]) else "N/D", "b")
                with k2: mcard("DY 12M", fmt_pct(c["dy"]) if _is_valid(c["dy"]) else "N/D", "g")
                with k3: mcard("P/VP", fmt_num(c["pvp"]) if _is_valid(c["pvp"]) else "N/D")
                with k4: mcard("Preço Teto", fmt_brl(c["preco_teto"]) if _is_valid(c["preco_teto"]) else "N/D")
                with k5: mcard("Margem Seg.", fmt_pct(margem) if _is_valid(margem) else "N/D", mcolor)
                with k6:
                    st.markdown("<div style='height:.45rem'></div>", unsafe_allow_html=True)
                    if st.button("🗑 Remover", key=f"cardrm_{c['ticker']}"):
                        cards_mod.remover_card(cfg, c["ticker"])
                        cards_mod.salvar_config(cfg)
                        st.session_state.cards_dados.pop(c["ticker"], None)
                        st.rerun()

        # ── Editor de configuração (visibilidade e ordem) ──
        with st.expander("⚙️ Configuração dos cards (visibilidade e ordem)"):
            df_cfg = pd.DataFrame(cfg.get("cards_ativos", []))
            edit = st.data_editor(
                df_cfg, key="cards_editor", use_container_width=True, hide_index=True,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", disabled=True),
                    "visivel": st.column_config.CheckboxColumn("Visível"),
                    "ordem": st.column_config.NumberColumn("Ordem", min_value=1, step=1),
                },
            )
            if st.button("💾 Salvar configuração", key="cards_save"):
                cfg["cards_ativos"] = edit.to_dict(orient="records")
                cards_mod.salvar_config(cfg)
                st.session_state.cards_config = cfg
                box("Configuração salva em cards_config.json.", "info")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# JANELA 6 — HISTÓRICO DE CONSULTAS (SQLite)
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("Histórico de Consultas")
    st.caption(
        "Toda consulta bem-sucedida (indicadores via Investidor10 ou série via "
        "Yahoo Finance) é gravada automaticamente no banco SQLite "
        "(fii_dashboard.db). Aqui você pode revisar, exportar, apagar e "
        "recarregar consultas antigas."
    )

    cfa, cfb, cfc = st.columns([1.6, 1, 1])
    with cfa:
        filtro_tk = st.text_input("Filtrar por ticker (opcional)",
                                  key="hist_filtro").upper().strip()
    with cfb:
        limite = st.number_input("Limite", min_value=10, max_value=1000,
                                 value=100, step=10, key="hist_lim")
    with cfc:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar lista", key="hist_reload"):
            st.rerun()

    registros = db.listar_historico(ticker=filtro_tk or None, limite=int(limite))
    if not registros:
        box("Nenhuma consulta gravada ainda. Faça uma busca em qualquer aba.", "info")
    else:
        df_hist = pd.DataFrame(registros)[
            ["id", "data_consulta", "ticker", "fonte", "preco", "dy", "pvp", "margem_seguranca"]
        ].rename(columns={
            "id": "ID", "data_consulta": "Data/Hora", "ticker": "Ticker",
            "fonte": "Fonte", "preco": "Preço", "dy": "DY (%)", "pvp": "P/VP",
            "margem_seguranca": "Margem Seg. (%)",
        })
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        csv_hist = df_hist.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Exportar histórico (CSV)", csv_hist,
                           file_name="historico_consultas.csv", mime="text/csv",
                           key="dl_hist")

        st.divider()
        st.markdown("##### Ações por consulta")
        ids = [r["id"] for r in registros]
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            sel_id = st.selectbox("Selecione o ID", ids, key="hist_sel")
        with ac2:
            st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            if st.button("↩️ Recarregar na Simulação", key="hist_recarregar"):
                reg = db.buscar_consulta_por_id(int(sel_id))
                if reg:
                    st.session_state["_pending_reload"] = {
                        "ticker": reg["ticker"], "dados": reg.get("dados", {}),
                    }
                    st.rerun()
        with ac3:
            st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            if st.button("🗑 Apagar consulta", key="hist_apagar"):
                db.apagar_consulta(int(sel_id))
                box(f"Consulta {sel_id} apagada.", "info")
                st.rerun()


# ── Rodapé ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<p style='text-align:center;color:#8b949e;font-size:.78rem;'>"
    "Indicadores via Investidor10 (Playwright) · série histórica via Yahoo Finance · "
    "Uso exclusivamente educacional · Não constitui recomendação de investimento"
    "</p>",
    unsafe_allow_html=True,
)
