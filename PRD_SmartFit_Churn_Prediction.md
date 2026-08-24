# PRD — Módulo de Previsão de Risco de Cancelamento (Churn) por Unidade — Smart Fit

> Repositório de referência: [Rinkyshu200/customer-churn-dashboard](https://github.com/Rinkyshu200/customer-churn-dashboard) (Streamlit + scikit-learn + Plotly, MIT License). Este PRD reaproveita ao máximo o código desse repositório — a arquitetura, o pipeline de ML e as visualizações são praticamente genéricos; o que muda é **de onde vêm os dados e o que a "coluna" representa**.

---

## 1. Objetivo

Construir um módulo de Machine Learning que preveja, **para cada unidade Smart Fit**, o risco de um aumento significativo de cancelamentos no mês seguinte — usando **exclusivamente dados que o pipeline de ingestão já captura** (`fato_metricas_diarias`, `fato_cancelamentos_detalhada`, `dim_unidade`). Nenhuma fonte de dados nova é necessária.

O módulo reaproveita a arquitetura já testada do repositório de referência (app Streamlit, modelo Decision Tree, visualizações Plotly, predição individual + em lote, dashboard de métricas do modelo) — só troca **o que entra no modelo**: em vez de atributos de cliente de telecom (Contrato, Internet, Parceiro...), usa métricas reais de operação de academia (tendência de ativos, taxa histórica de cancelamento, conversão, idade da unidade...).

---

## 2. Por que "churn de unidade" e não "churn de aluno" (contexto da decisão)

O repositório original prevê churn de **cliente individual** de telecom: cada linha é uma pessoa, com colunas como `Contract`, `InternetService`, `PhoneService`, `Partner`, `PaymentMethod`.

O banco Smart Fit **não tem esse grão**. O e-mail diário nunca trouxe dado de aluno individual — só métricas **agregadas por unidade/dia** (quantos ativos, quantos cancelamentos, qual a conversão). Portanto:

- **Não é possível** prever "o aluno João vai cancelar" sem uma fonte de dados nova (CRM/sistema de matrícula da Smart Fit com dado por aluno) — isso fica **fora de escopo** deste PRD (ver Seção 3).
- **É possível e tem valor de negócio real** prever "a unidade X vai ter um mês ruim de cancelamento" — isso substitui 1:1 o conceito de "churn" do repositório original, só trocando a unidade de análise de *pessoa* para *unidade de academia*.

Esta decisão foi confirmada com o usuário do projeto antes de escrever este PRD.

---

## 3. Fora de Escopo (explicitamente)

- Previsão de churn de aluno individual (exige nova fonte de dados — CRM/matrícula).
- Re-treinamento automático agendado (cron) — fica para uma fase futura, depois que o modelo v1 for validado com uso real.
- Deploy em nuvem/produção — roda local, como o resto do projeto (`streamlit run`, igual ao `python -m app.web.routes` do painel Flask).
- SHAP — o próprio repositório de referência já comentou o `import shap` no código por instabilidade de compatibilidade (`app.py`, linha 7). Mantemos comentado/opcional aqui também; a explicação por Feature Importance nativa da Decision Tree (`model.feature_importances_`) já está implementada no repositório e cobre a mesma necessidade.
- Definir o que a equipe de negócio deve **fazer** com uma unidade de alto risco (plano de ação, alçada, alertas automáticos) — este PRD entrega o **sinal** (probabilidade + nível de risco), não o processo de resposta.

---

## 4. Mapeamento de Reaproveitamento de Código (o que muda, o que não muda)

| Arquivo do repositório original | Reaproveitamento | O que muda |
|---|---|---|
| `visualization_utils.py` (227 linhas) | **~95% verbatim** | Só rótulos de texto (Churn → Risco de Cancelamento) e tradução para português. Os gráficos (distribuição, importância de features, matriz de confusão, distribuição de probabilidade, distribuição por nível de risco) são genéricos — não dependem do domínio telecom. |
| `model_utils.py` (204 linhas) | **Estrutura ~90% mantida** | `create_telco_dataset()` (dado sintético) é **substituída** por `build_training_dataset(conn)`, que monta o dataset a partir do banco real via SQL (Seção 6). `DecisionTreeClassifier(max_depth=10, min_samples_split=20, min_samples_leaf=10)` e o fluxo `train_model()` / `load_model()` / `get_model_metrics()` / `pickle` são mantidos como estão. |
| `data_utils.py` (174 linhas) | **Estrutura ~85% mantida** | `preprocess_input_data()` e `validate_csv_data()` mantêm o mesmo padrão (lista ordenada de features, `LabelEncoder`, validação de CSV com mensagens de erro), só trocando a lista de colunas de telecom pelas colunas reais da Smart Fit (Seção 5). |
| `app.py` (571 linhas) | **Estrutura de páginas mantida** | Mesmas 5 seções (Home, Predição Individual, Predição em Lote, Analytics do Modelo, Sobre), mesmo padrão de layout Streamlit (`st.form`, `st.columns`, `st.metric`). O **formulário de entrada** troca os campos de telecom pelos campos reais da unidade (Seção 5). |
| `churn_model.pkl` | **Descartado** | Modelo treinado em dado sintético de telecom não serve para o nosso domínio. Um novo `.pkl` é treinado do zero com `build_training_dataset()` (Fase 2). |
| `.streamlit/config.toml` | **Reaproveitado** | Configuração de porta/tema, sem mudanças. |

**Racional de arquitetura:** o app roda como um **processo Streamlit separado** (porta própria, ex. `8501`), independente do painel Flask (`app/web/routes.py`, porta `5000`) que já existe. Isso maximiza o reaproveitamento literal do código do repositório de referência (que é 100% Streamlit) em vez de reescrever 571 linhas de UI já testadas em Flask/Jinja2. O painel Flask existente ganha apenas um link/botão apontando para a URL do Streamlit.

---

## 5. Mapeamento de Features (Telecom → Smart Fit)

Grão de treino: **unidade × mês** (cancelamento só existe em granularidade mensal no e-mail — ver `fato_cancelamentos_detalhada`, que não tem coluna "dia").

| Coluna original (Telco) | Equivalente Smart Fit | Fonte (tabela.coluna) | Tipo |
|---|---|---|---|
| `SeniorCitizen`, `Partner`, `Dependents` | *(sem equivalente — descartadas)* | — | — |
| `tenure` (meses de casa) | `idade_unidade_meses` — meses desde a inauguração até o mês de referência | `dim_unidade.data_inauguracao` | numérico |
| `Contract` (tipo de contrato) | `tipo_operacao` — Própria ou Franquia | `dim_unidade.tipo_operacao` | categórico |
| `InternetService`, `PhoneService`, `MultipleLines`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies` | *(sem equivalente — descartadas, específicas de telecom)* | — | — |
| `PaperlessBilling`, `PaymentMethod` | *(sem equivalente — descartadas)* | — | — |
| `MonthlyCharges` | `vendas_geral_mes` — total vendido no mês | `fato_metricas_diarias.vendas_geral_mes` (última leitura do mês) | numérico |
| `TotalCharges` | `vendas_acumuladas_periodo` — soma de vendas no histórico disponível da unidade | agregado de `fato_metricas_diarias.vendas_geral_mes` | numérico |
| *(sem equivalente direto)* | `pais` — país da unidade | `dim_unidade.pais` | categórico |
| *(sem equivalente direto)* | `total_ativos` — ativos no fim do mês | `fato_metricas_diarias.total_ativos` (última leitura do mês) | numérico |
| *(sem equivalente direto)* | `variacao_ativos_mes` — Δ% de ativos vs. mês anterior (momentum) | calculado | numérico |
| *(sem equivalente direto)* | `visitas_mes` / `total_ativos` — engajamento por aluno ativo | `fato_metricas_diarias.visitas_mes` | numérico |
| *(sem equivalente direto)* | `conversao_mes` (%) | `fato_metricas_diarias.conversao_mes` | numérico |
| *(sem equivalente direto)* | `transferencias_liquida_mes` | `fato_metricas_diarias.transferencias_liquida_mes` | numérico |
| *(sem equivalente direto)* | `taxa_cancelamento_mes_anterior` — taxa do mês anterior (autocorrelação) | calculado (ver Seção 6) | numérico |
| *(sem equivalente direto)* | `unidade_imatura` — ainda não atingiu 120 dias | `fato_metricas_diarias.unidade_imatura` | booleano |
| `Churn` (alvo) | `alto_risco_cancelamento` — 1 se a **taxa de cancelamento do mês seguinte** está no quartil superior (top 25%) da rede | calculado (ver Seção 6) | booleano (alvo) |

> ⚠️ **Definição de "alto risco" é um ponto em aberto.** Este PRD assume, como *default* de implementação, o quartil superior (top 25%) da taxa de cancelamento mensal **da rede inteira** como corte entre risco normal e alto. Isso deve ser validado com quem entende o negócio assim que houver dados reais suficientes (ver Seção 13 — Riscos). O corte é um parâmetro isolado em `model_utils.py` (`RISK_THRESHOLD_PERCENTILE`), fácil de ajustar sem tocar no resto do código.

---

## 6. Construção do Dataset de Treino (a peça nova que não existe no repositório original)

Como o repositório original gera dado sintético (`create_telco_dataset()`), e nós temos dado real, esta é a única peça genuinamente nova (sem equivalente para copiar):

```sql
-- Rascunho da agregação mensal por unidade (executado em Python com psycopg2, não como view fixa,
-- para poder ser reaproveitado tanto no treino quanto na predição em lote)
SELECT
    u.id AS unidade_id,
    date_trunc('month', f.data_referencia)::date AS mes_referencia,
    u.tipo_operacao,
    u.pais,
    u.data_inauguracao,
    MAX(f.total_ativos) FILTER (WHERE f.data_referencia = (SELECT MAX(data_referencia) FROM fato_metricas_diarias f2 WHERE f2.unidade_id = u.id AND date_trunc('month', f2.data_referencia) = date_trunc('month', f.data_referencia))) AS total_ativos_fim_mes,
    AVG(f.visitas_mes) AS visitas_mes,
    AVG(f.conversao_mes) AS conversao_mes,
    SUM(f.vendas_geral_dia) AS vendas_geral_mes_soma,
    AVG(f.transferencias_liquida_mes) AS transferencias_liquida_mes,
    BOOL_OR(f.unidade_imatura) AS unidade_imatura,
    COALESCE(c.qtd_mes, 0) AS cancelados_total_mes
FROM fato_metricas_diarias f
JOIN dim_unidade u ON u.id = f.unidade_id
LEFT JOIN fato_cancelamentos_detalhada c
    ON c.fato_diaria_id = f.id AND c.plano = 'Total'
GROUP BY u.id, date_trunc('month', f.data_referencia), u.tipo_operacao, u.pais, u.data_inauguracao, c.qtd_mes;
```

A função Python `build_training_dataset(conn)` (em `app/ml/model_utils.py`) executa essa consulta, calcula as colunas derivadas (`idade_unidade_meses`, `variacao_ativos_mes`, `taxa_cancelamento_mes_anterior`, `taxa_cancelamento_mes_seguinte`) via `pandas`/Python puro, e monta o alvo `alto_risco_cancelamento` comparando a taxa do mês seguinte contra o percentil de corte da rede.

**Requisito mínimo de dados:** o modelo só é treinável depois que o backfill histórico tiver pelo menos **3 meses consecutivos** de dados para uma quantidade razoável de unidades (idealmente 6+ meses, para captar sazonalidade e ter mês "seguinte" suficiente para todas as linhas de treino). Antes disso, o comando de treino deve falhar com uma mensagem clara em vez de treinar num dataset minúsculo e não confiável.

---

## 7. Estrutura de Pastas Nova

```text
Analise/
├── app/
│   ├── ml/                              # [NOVO] Módulo de Machine Learning
│   │   ├── __init__.py
│   │   ├── model_utils.py               # Adaptado de model_utils.py do repo de referência
│   │   ├── data_utils.py                # Adaptado de data_utils.py do repo de referência
│   │   ├── visualization_utils.py       # Reaproveitado ~verbatim do repo de referência
│   │   ├── streamlit_app.py             # Adaptado de app.py do repo de referência
│   │   └── models/
│   │       └── churn_model.pkl          # [Ignorado no Git] Modelo treinado com dado real
│   └── cli.py                           # Ganha os comandos: train-churn-model, predict-churn
├── .streamlit/
│   └── config.toml                      # Reaproveitado do repo de referência
└── requirements-ml.txt                  # Dependências extras (streamlit, scikit-learn, plotly)
```

> `requirements-ml.txt` fica separado de `requirements.txt` porque o módulo de ML é opcional — quem só quer rodar a ingestão de e-mails não precisa instalar `streamlit`/`scikit-learn`/`plotly` (dependências relativamente pesadas).

---

## 8. Estrutura de Banco de Dados Adicional

```sql
-- Guarda o histórico de predições geradas, para acompanhar acerto/erro ao longo do tempo
CREATE TABLE IF NOT EXISTS churn_predicoes (
    id BIGSERIAL PRIMARY KEY,
    unidade_id INT NOT NULL REFERENCES dim_unidade(id),
    mes_referencia DATE NOT NULL,          -- mês para o qual a previsão foi feita
    probabilidade_risco NUMERIC(5,4) NOT NULL,   -- 0.0000 a 1.0000
    nivel_risco VARCHAR(10) NOT NULL,      -- 'Baixo', 'Médio', 'Alto' (mesmos cortes do repo: 0.3 / 0.7)
    versao_modelo VARCHAR(50) NOT NULL,    -- ex: hash do treino ou timestamp, para rastreabilidade
    gerado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unq_predicao_unidade_mes UNIQUE (unidade_id, mes_referencia, versao_modelo)
);

CREATE INDEX IF NOT EXISTS idx_churn_predicoes_unidade ON churn_predicoes(unidade_id);
CREATE INDEX IF NOT EXISTS idx_churn_predicoes_mes ON churn_predicoes(mes_referencia);
```

---

## 9. Requisitos Funcionais

- **FR-CH-01 — Dataset de treino real:** `build_training_dataset(conn)` monta o dataset a partir do banco (Seção 6), sem depender de dado sintético.
- **FR-CH-02 — Treino do modelo:** comando `python -m app.cli train-churn-model` treina uma `DecisionTreeClassifier` nos mesmos moldes do repositório de referência, imprime métricas (acurácia, precisão, recall, ROC AUC) e salva em `app/ml/models/churn_model.pkl`.
- **FR-CH-03 — Bloqueio por dado insuficiente:** o comando de treino deve recusar rodar (com mensagem explicativa) se houver menos de 3 meses de histórico consolidado no banco.
- **FR-CH-04 — App Streamlit funcional:** `streamlit run app/ml/streamlit_app.py` sobe um app com as 5 seções do repositório original (Home, Predição Individual, Predição em Lote, Analytics do Modelo, Sobre), adaptadas aos campos da Seção 5.
- **FR-CH-05 — Predição individual:** formulário para simular uma unidade hipotética (ou existente) e ver a probabilidade de risco + explicação por importância de feature.
- **FR-CH-06 — Predição em lote (CSV):** upload de CSV com uma linha por unidade/mês, retornando probabilidade e nível de risco por linha, com download do resultado — mesmo padrão do repositório original.
- **FR-CH-07 — Predição em lote (direto do banco):** comando `python -m app.cli predict-churn --month YYYY-MM` roda o modelo sobre todas as unidades com dado disponível naquele mês e grava o resultado em `churn_predicoes` (upsert idempotente, igual ao padrão do resto do pipeline).
- **FR-CH-08 — Dashboard de analytics do modelo:** métricas de performance, matriz de confusão, curva ROC e importância de features — reaproveitado do repositório original.
- **FR-CH-09 — Link a partir do painel existente:** o painel Flask (`app/web/templates/index.html`) ganha um botão/link "Ver Previsão de Cancelamento" apontando para a URL do Streamlit.
- **FR-CH-10 — Rastreabilidade:** toda predição gravada em `churn_predicoes` carrega `versao_modelo`, permitindo comparar previsões de modelos diferentes ao longo do tempo.

---

## 10. Requisitos Não-Funcionais

- **Independência de processo:** o app Streamlit roda em processo e porta próprios (não compartilha o processo do Flask). Documentar os dois comandos de subida no README (`python -m app.web.routes` e `streamlit run app/ml/streamlit_app.py`).
- **Dependências isoladas:** `requirements-ml.txt` separado, para não obrigar quem só usa a ingestão a instalar `scikit-learn`/`streamlit`/`plotly`.
- **Reprodutibilidade:** `random_state=42` mantido em todo o pipeline de treino (igual ao repositório original), para que o mesmo dataset sempre produza o mesmo modelo.
- **Sem dependência de internet em produção:** depois de treinado, o modelo roda 100% offline (mesmo padrão do resto do projeto).

---

## 11. Fases de Implementação (executar em ordem)

### Fase 0 — Fundação do módulo
- Criar `app/ml/__init__.py`, pasta `app/ml/models/` (com `.gitkeep`, o `.pkl` fica fora do controle de versão).
- Criar `requirements-ml.txt` com `streamlit`, `scikit-learn`, `plotly`, `pandas` (necessário aqui, diferente do resto do pipeline).
- Adicionar tabela `churn_predicoes` ao `app/db/schema.sql` (Seção 8) e rodar `python -m app.cli init-db`.

### Fase 1 — Dataset de treino real
- Implementar `build_training_dataset(conn)` em `app/ml/model_utils.py`, seguindo a consulta da Seção 6.
- Testar isoladamente contra o banco real (validar contagem de linhas, checar que `alto_risco_cancelamento` tem as duas classes representadas — sem isso o treino falha).

### Fase 2 — Adaptação de `model_utils.py`
- Portar `train_model()`, `load_model()`, `get_model_metrics()` do repositório original, trocando `create_telco_dataset()` por `build_training_dataset(conn)` e a lista `categorical_cols` pelas colunas reais (`tipo_operacao`, `pais`).
- Adicionar `RISK_THRESHOLD_PERCENTILE = 0.75` como constante isolada e documentada (ponto em aberto da Seção 5).

### Fase 3 — Adaptação de `data_utils.py`
- Portar `preprocess_input_data()` e `validate_csv_data()`, trocando a lista `feature_order` e `categorical_constraints` pelas colunas da Seção 5.

### Fase 4 — Reaproveitamento de `visualization_utils.py`
- Copiar o arquivo quase verbatim; traduzir títulos/rótulos para português e trocar "Churn"/"No Churn" por "Alto Risco"/"Risco Normal".

### Fase 5 — Adaptação de `streamlit_app.py` (era `app.py`)
- Portar a estrutura de 5 páginas do repositório original.
- Trocar o formulário de Predição Individual pelos campos da Seção 5 (idade da unidade, tipo de operação, país, ativos, visitas, conversão, vendas, transferências, taxa de cancelamento do mês anterior).
- Manter o padrão de cache (`@st.cache_resource`), tratamento de erro e template de CSV para download.

### Fase 6 — Persistência de predições + comando CLI
- Implementar `predict_batch(conn, model, mes_referencia)` e o comando `python -m app.cli predict-churn --month YYYY-MM`, gravando em `churn_predicoes` com `ON CONFLICT DO UPDATE` (mesmo padrão idempotente do `loader.py` de ingestão).

### Fase 7 — Integração visual no painel existente
- Adicionar link no `app/web/templates/index.html` para a URL do Streamlit (porta configurável via `.env`, ex. `STREAMLIT_PORT=8501`).

### Fase 8 — Documentação
- Atualizar `README.md` com a seção "Módulo de Previsão de Cancelamento": como instalar (`pip install -r requirements-ml.txt`), treinar (`train-churn-model`), rodar o app (`streamlit run ...`), e gerar predições em lote (`predict-churn`).
- Atualizar `MANUAL_PASSO_A_PASSO.md` com um passo opcional equivalente, em linguagem simples, para o usuário leigo testar o app Streamlit.

---

## 12. Critérios de Aceite

1. `python -m app.cli train-churn-model` roda sem erro contra o banco real e imprime métricas de acurácia/precisão/recall/ROC AUC.
2. `streamlit run app/ml/streamlit_app.py` sobe um app funcional nas 5 páginas, sem nenhum campo de telecom (Contract/InternetService/etc.) visível.
3. Upload de um CSV de exemplo (com as colunas da Seção 5) gera predições em lote e permite download do resultado.
4. `python -m app.cli predict-churn --month 2026-08` grava linhas em `churn_predicoes`, sem duplicar ao rodar duas vezes seguidas (idempotência).
5. O painel Flask existente (`http://localhost:5000`) mostra um link funcional para o app Streamlit.
6. Rodar o comando de treino duas vezes sobre o mesmo banco produz métricas idênticas (reprodutibilidade via `random_state=42`).

---

## 13. Riscos e Limitações Conhecidas

- **Cold start:** com poucos meses de backfill, o modelo terá poucochíssimos exemplos de treino e métricas pouco confiáveis. Recomenda-se rodar o backfill histórico completo (anos de e-mail já disponíveis, conforme o PRD de ingestão) antes de treinar o modelo v1.
- **Definição de "alto risco" é um placeholder** (top 25% da rede) até validação de negócio — ver nota na Seção 5. Trocar o percentil de corte não exige mudança de arquitetura, só do parâmetro `RISK_THRESHOLD_PERCENTILE`.
- **Vazamento de dados entre unidades correlacionadas:** franquias da mesma região podem ter cancelamentos correlacionados (ex: um evento macroeconômico local). O modelo atual não modela essa dependência espacial — fica como possível melhoria futura, não bloqueia o v1.
- **Sem re-treino automático:** o modelo precisa ser retreinado manualmente (`train-churn-model`) conforme novos meses de dado chegam. Agendamento automático fica fora de escopo deste PRD (Seção 3).
