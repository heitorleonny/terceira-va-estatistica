# 🏢 FII Analyzer

Aplicação web para análise de Fundos de Investimento Imobiliário (FIIs)
brasileiros: indicadores fundamentalistas em tempo real, série histórica de
preços, análise estatística empírica dos retornos e simulações de
investimento — tudo em um terminal financeiro construído com **React** sobre
uma **API REST em FastAPI**.

Projeto desenvolvido para a disciplina de Estatística, a partir do projeto-base
[Estatistica3-Va](https://github.com/Luko1de/Estatistica3-Va).

---

## ✨ O que a aplicação faz

| Módulo | Descrição |
|--------|-----------|
| **Análise Empírica** | Série temporal de preços, histograma dos log-retornos com normal ajustada, QQ-plot + teste de normalidade, e probabilidade de cauda interativa (slider + cair abaixo/subir acima) |
| **Comparar** | Compara 2–6 FIIs simultaneamente: séries rebaseadas a 100, volatilidade anualizada e matriz de correlação entre retornos |
| **Cards** | Destaques configuráveis dos FIIs com melhor margem de segurança |
| **Histórico** | Consultas persistidas em SQLite — listar, filtrar, recarregar, apagar e exportar |
| **Simulação de Aporte** | Projeção de patrimônio e renda com aportes mensais constantes |
| **Carteira** | Monta uma carteira com múltiplos FIIs e calcula totais/renda |
| **Preço Teto** | Preço justo e margem de segurança por FII, ranqueados |

Dados fundamentalistas vêm do [Investidor10](https://investidor10.com.br)
(via Playwright) e a série histórica de preços vem do Yahoo Finance
(`yfinance`). Tudo é persistido automaticamente em SQLite.

---

## 🏛️ Stack

- **Frontend:** React + TypeScript + Vite + Tailwind + Recharts + Framer Motion
- **Backend/API:** FastAPI (Python), servindo o build do React e os endpoints `/api/*`
- **Dados:** Playwright (Investidor10) + yfinance (Yahoo Finance)
- **Persistência:** SQLite (`fii_dashboard.db`)

Toda a lógica de negócio (scraping, estatística, cálculo de preço teto) fica
em módulos Python puros (`scraper.py`, `stats_empirical.py`,
`historico_precos.py`, `utils.py`, `cards.py`, `db.py`), reaproveitados
integralmente pela API.

---

## ⚙️ Como rodar (web)

```bash
# 1. Ambiente virtual + dependências Python
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# 2. Navegador do Playwright (uma vez só)
playwright install chromium

# 3. Build do frontend
cd web && npm install && npm run build && cd ..

# 4. Subir a aplicação (API + UI no mesmo servidor)
uvicorn api:app --port 8000
```

Abra **http://127.0.0.1:8000**.

**Modo desenvolvimento** (hot-reload no frontend): rode `uvicorn api:app --port 8000`
em um terminal e `cd web && npm run dev` em outro (porta 5173, com proxy de
`/api` para a 8000).

A documentação interativa da API fica em `http://127.0.0.1:8000/docs`.

### Testes

```bash
pytest -q
```

---

## 📁 Estrutura

```
terceira-va-estatistica/
├── api.py               # API REST FastAPI
├── scraper.py            # Coleta via Playwright (Investidor10)
├── historico_precos.py   # Série histórica (yfinance) + cache SQLite
├── stats_empirical.py    # Log-retornos, normal ajustada, prob. de cauda
├── utils.py               # Preço teto, margem, formatação
├── cards.py                # Cards configuráveis
├── db.py                    # Persistência SQLite
├── cards_config.json         # Configuração dos cards
├── tests/                     # pytest
├── app.py                      # Dashboard Streamlit (versão legada)
└── web/                         # Frontend React
    ├── src/views/                # Análise Empírica, Comparar, Cards, …
    ├── src/components/            # Design system + gráficos
    └── src/lib/                    # Cliente da API, formatação, estatística
```

O banco `fii_dashboard.db` é criado automaticamente na primeira execução.
