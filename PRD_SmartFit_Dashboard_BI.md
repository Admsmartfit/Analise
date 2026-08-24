# PRD — Painel Analítico "Estilo Power BI" (Comparação de Unidades e Regiões) — Smart Fit

> Este PRD é para ser implementado por outra ferramenta ("Antigravity"). Aqui entrego: a ferramenta recomendada (com racional de escolha), as `VIEWS` SQL prontas para copiar, os dashboards a construir passo a passo, e um repositório de referência visual já baixado em `references/voltfit-dashboard/`.

---

## 1. Objetivo

Dar ao usuário (leigo, sem programar) um painel visual **interativo, estilo Power BI**, onde ele possa:
- Escolher uma ou várias unidades e ver a tendência delas lado a lado.
- Comparar uma unidade específica contra a média de uma região/país.
- Ver tudo em gráficos de tendência (linha do tempo), fáceis de entender, sem precisar saber SQL ou programação.

Sem escrever um frontend customizado do zero — reaproveitando uma ferramenta de BI open source já pronta e testada.

---

## 2. Escolha de Ferramenta (pesquisa e racional)

Pesquisei alternativas no GitHub e comparei três caminhos:

| Ferramenta | O que é | Por que sim / por que não |
|---|---|---|
| **Metabase** ([github.com/metabase/metabase](https://github.com/metabase/metabase)) | Plataforma de BI open source (licença própria + core aberto), autohospedada, feita para usuário de negócio autoatender-se | ✅ **Escolhida.** Conecta direto no PostgreSQL sem escrever código. Filtros de múltiplos valores nativos (selecionar várias unidades de uma vez). Filtros encadeados/em cascata (País → Região → Unidade). Gera dashboards automaticamente a partir de uma tabela ("X-ray"). Curva de aprendizado mínima — literalmente arrastar e soltar. |
| **Apache Superset** ([github.com/apache/superset](https://github.com/apache/superset)) | Plataforma de BI open source mais robusta, usada por times de dados grandes | ❌ Mais poderosa, mas exige mais infraestrutura (Redis, Celery para tarefas assíncronas) e tem curva de aprendizado maior — desproporcional para o tamanho deste projeto e para um usuário leigo administrar sozinho. |
| **Frontend customizado (React), inspirado em [kendrekaran/voltfit-dashboard](https://github.com/kendrekaran/voltfit-dashboard)** | Template de dashboard de operação de academia (React + Vite + Tailwind), MIT License, com cartões de KPI, mapa de unidades, layout de rede multi-loja | ⚠️ **Reaproveitado só como referência visual** (já baixado em `references/voltfit-dashboard/`). Usa dado mockado, sem filtros de comparação prontos, sem conexão a banco — construir os filtros/comparações do zero em React levaria muito mais tempo que configurar o Metabase, e introduziria uma 3ª stack de frontend no projeto (hoje é só Python: Flask + Streamlit). |

**Decisão:** Metabase como camada de BI principal, conectado direto em `smartfit_db` (mesmo banco que a ingestão já usa). O React do VoltFit fica como referência de estilo visual (cores, cartões de KPI, layout) caso mais adiante se queira um dashboard 100% customizado e com a marca da Smart Fit — não é necessário para este PRD funcionar.

---

## 3. Fora de Escopo

- White-label / remover a marca "Metabase" do rodapé (recurso pago da versão Enterprise) — não é bloqueio para uso interno.
- Embutir os dashboards do Metabase dentro do iframe do painel Flask com autenticação unificada (SSO) — fica para uma fase futura; nesta fase, o link simplesmente abre o Metabase em nova aba (mesmo padrão já usado para o link do Streamlit).
- Métricas em tempo real (o Metabase consulta o Postgres sob demanda; não há necessidade de streaming).
- Recriar em React o dashboard do VoltFit conectado a dado real — fica registrado como possível fase futura (Seção 12).

---

## 4. Arquitetura

```text
┌─────────────────────┐        ┌──────────────────────┐
│   Painel Flask       │───────▶│   Metabase (novo)     │
│   localhost:5000     │  link  │   localhost:3000      │
└─────────────────────┘        └──────────┬────────────┘
                                            │ conexão direta (leitura)
                                            ▼
                                ┌──────────────────────┐
                                │  PostgreSQL           │
                                │  smartfit_db           │
                                │  + 5 VIEWS novas       │
                                │    (Seção 5)           │
                                └──────────────────────┘
```

- O Metabase **não grava nada** no `smartfit_db` — só faz `SELECT`. O pipeline de ingestão e o módulo de ML continuam intocados.
- As 5 `VIEWS` (Seção 5) existem para dar ao Metabase (e a qualquer usuário de negócio explorando dentro dele) tabelas já "achatadas", com nomes de coluna em português, sem precisar entender os `JOIN`s entre `dim_unidade`, `fato_metricas_diarias`, `fato_cancelamentos_detalhada`, etc.
- O Metabase guarda sua própria configuração (usuários, dashboards salvos) num banco próprio — pode ser SQLite/H2 embutido (mais simples, recomendado para este porte) ou um Postgres separado.

---

## 5. Views SQL Novas (prontas para copiar em `app/db/schema.sql` ou rodar direto)

```sql
-- Grão: unidade x mês. Base para quase todos os gráficos de comparação.
CREATE OR REPLACE VIEW vw_unidade_metrica_mensal AS
SELECT
    u.id AS unidade_id,
    u.nome_digital AS unidade,
    u.pais,
    u.regiao_uf AS regiao,
    u.tipo_operacao,
    u.data_inauguracao,
    date_trunc('month', f.data_referencia)::date AS mes_referencia,
    MAX(f.total_ativos) AS ativos,
    MAX(f.ativos_smart) AS ativos_smart,
    MAX(f.ativos_black) AS ativos_black,
    MAX(f.ativos_fit) AS ativos_fit,
    MAX(f.ativos_black_plus) AS ativos_black_plus,
    MAX(f.ativos_studio) AS ativos_studio,
    MAX(f.bloqueados) AS ativos_bloqueados,
    AVG(f.visitas_mes) AS visitas_mes,
    AVG(f.conversao_mes) AS conversao_mes_pct,
    MAX(f.vendas_geral_mes) AS vendas_mes,
    MAX(f.transferencias_liquida_mes) AS transferencias_liquida_mes,
    MAX(c.qtd_mes) AS cancelados_mes,
    CASE WHEN MAX(f.total_ativos) > 0
         THEN ROUND(MAX(c.qtd_mes)::numeric / MAX(f.total_ativos) * 100, 2)
         ELSE 0 END AS taxa_cancelamento_pct
FROM fato_metricas_diarias f
JOIN dim_unidade u ON u.id = f.unidade_id
LEFT JOIN fato_cancelamentos_detalhada c ON c.fato_diaria_id = f.id AND c.plano = 'total'
GROUP BY u.id, u.nome_digital, u.pais, u.regiao_uf, u.tipo_operacao, u.data_inauguracao,
         date_trunc('month', f.data_referencia);

-- Grão: região x mês. Usada como "baseline" na comparação unidade-vs-região.
CREATE OR REPLACE VIEW vw_regiao_metrica_mensal AS
SELECT
    regiao,
    pais,
    mes_referencia,
    COUNT(DISTINCT unidade_id) AS total_unidades,
    SUM(ativos) AS ativos_totais,
    AVG(conversao_mes_pct) AS conversao_media_pct,
    AVG(taxa_cancelamento_pct) AS taxa_cancelamento_media_pct,
    SUM(vendas_mes) AS vendas_totais_mes
FROM vw_unidade_metrica_mensal
GROUP BY regiao, pais, mes_referencia;

-- Grão: unidade x mês x canal x plano. Para detalhar vendas por canal (Balcão/Web/...).
CREATE OR REPLACE VIEW vw_vendas_canal_plano_mensal AS
SELECT
    u.id AS unidade_id,
    u.nome_digital AS unidade,
    u.regiao_uf AS regiao,
    date_trunc('month', f.data_referencia)::date AS mes_referencia,
    v.canal_venda,
    v.plano,
    MAX(v.qtd_mes) AS qtd_vendida_mes
FROM fato_vendas_detalhada v
JOIN fato_metricas_diarias f ON f.id = v.fato_diaria_id
JOIN dim_unidade u ON u.id = f.unidade_id
GROUP BY u.id, u.nome_digital, u.regiao_uf, date_trunc('month', f.data_referencia),
         v.canal_venda, v.plano;

-- Junta as predições do módulo de ML (PRD_SmartFit_Churn_Prediction.md) para exibir
-- risco de cancelamento dentro do mesmo painel de BI.
CREATE OR REPLACE VIEW vw_risco_cancelamento AS
SELECT
    p.id,
    u.nome_digital AS unidade,
    u.pais,
    u.regiao_uf AS regiao,
    p.mes_referencia,
    p.probabilidade_risco,
    p.nivel_risco,
    p.versao_modelo,
    p.gerado_em
FROM churn_predicoes p
JOIN dim_unidade u ON u.id = p.unidade_id;

-- Unidades ainda não inauguradas (pré-venda), para acompanhamento à parte.
CREATE OR REPLACE VIEW vw_pre_venda_mensal AS
SELECT
    u.id AS unidade_pre_venda_id,
    u.nome_unidade AS unidade,
    u.pais_regiao AS regiao,
    date_trunc('month', f.data_referencia)::date AS mes_referencia,
    MAX(f.vendas_total) AS vendas_total_mes
FROM fato_pre_venda_diaria f
JOIN dim_unidade_pre_venda u ON u.id = f.unidade_pre_venda_id
GROUP BY u.id, u.nome_unidade, u.pais_regiao, date_trunc('month', f.data_referencia);
```

---

## 6. Instalação do Metabase (duas opções)

### Opção A — JAR (recomendada para este computador, sem precisar instalar Docker)
1. Instalar Java 21+ (JRE), se ainda não houver.
2. Baixar `metabase.jar` em [metabase.com/start/oss](https://www.metabase.com/start/oss/jar) (versão Community/Open Source, gratuita).
3. Rodar:
   ```powershell
   java -jar metabase.jar
   ```
4. Acessar `http://localhost:3000`, criar o usuário admin, e no assistente inicial escolher "Adicionar banco de dados" → PostgreSQL → apontar para `localhost:5432`, banco `smartfit_db`, usuário/senha do `.env`.

### Opção B — Docker
```yaml
# docker-compose.yml
services:
  metabase:
    image: metabase/metabase:latest
    ports:
      - "3000:3000"
    environment:
      MB_DB_FILE: /metabase-data/metabase.db
    volumes:
      - metabase-data:/metabase-data
volumes:
  metabase-data:
```
```bash
docker compose up -d
```

Em ambas as opções, o Metabase roda **separado** do Flask (porta 5000) e do Streamlit (porta 8501) — mesmo padrão dos dois módulos já existentes.

---

## 7. Dashboards a Construir

### 7.1 "Visão Geral da Rede"
- Filtro: País, Região, Mês (intervalo).
- Cartões de KPI: total de unidades, ativos totais, taxa média de cancelamento, vendas do mês.
- Gráfico de linha: ativos totais e vendas totais ao longo dos meses.
- Fonte: `vw_unidade_metrica_mensal` (agregada) + `vw_regiao_metrica_mensal`.

### 7.2 "Comparação entre Unidades" (pedido principal do usuário)
- Filtro **"Unidade"**: seleção múltipla (Metabase suporta nativamente — ver [tutorial de filtros ligados](https://www.metabase.com/learn/metabase-basics/querying-and-dashboards/dashboards/linking-filters)), fonte `vw_unidade_metrica_mensal.unidade`.
- Gráfico de linha: **uma série por unidade selecionada**, eixo X = mês, eixo Y = métrica escolhida (ativos, taxa de cancelamento, vendas, conversão — um seletor de métrica com "Tabs"/série de perguntas).
- Tabela auxiliar abaixo com os números exatos, lado a lado.

### 7.3 "Unidade vs. Região" (pedido principal do usuário)
- Filtro 1: **País** → filtro 2: **Região** (ligado/cascata) → filtro 3: **Unidade** (dentro da região escolhida).
- Dois gráficos de linha sobrepostos na mesma pergunta SQL (via `UNION`): a linha da unidade escolhida (`vw_unidade_metrica_mensal`) e a linha média da região (`vw_regiao_metrica_mensal`), para o mesmo intervalo de meses.
- Exemplo de pergunta SQL nativa (usa Field Filters do Metabase para os `{{ }}`):
  ```sql
  SELECT mes_referencia, 'Unidade selecionada' AS serie, taxa_cancelamento_pct
  FROM vw_unidade_metrica_mensal
  WHERE unidade = {{unidade}}
  UNION ALL
  SELECT mes_referencia, 'Média da região' AS serie, taxa_cancelamento_media_pct
  FROM vw_regiao_metrica_mensal
  WHERE regiao = {{regiao}}
  ORDER BY mes_referencia;
  ```

### 7.4 "Risco de Cancelamento" (integra com o módulo de ML já existente)
- Tabela/heatmap de `vw_risco_cancelamento`, ordenável por probabilidade, filtro por região/mês.
- Nota no dashboard explicando que os números vêm do modelo treinado via `python -m app.cli train-churn-model` (ver `PRD_SmartFit_Churn_Prediction.md`) — o Metabase só exibe, não recalcula a predição.

### 7.5 "Pré-vendas" (unidades ainda não inauguradas)
- Fonte: `vw_pre_venda_mensal`. Mesma lógica de filtro por região/mês.

---

## 8. Integração com o Painel Existente

- Adicionar, ao lado dos links já existentes (`📉 Previsão de Cancelamento`), um novo botão `📊 Painel Analítico (BI)` apontando para `http://localhost:3000` — mesmo padrão de `STREAMLIT_PORT` já implementado em `app/web/routes.py` (Seção 9 do `PRD_SmartFit_Churn_Prediction.md`), agora com `METABASE_PORT`.

---

## 9. Requisitos Funcionais

- **FR-BI-01:** As 5 views (Seção 5) existem no banco e retornam dados corretos (conferir manualmente contra `export-xlsx` já existente).
- **FR-BI-02:** Metabase conectado a `smartfit_db` em modo somente leitura de fato (usar um usuário Postgres com permissão `SELECT` apenas, se possível — ver Seção 10, Não-Funcionais).
- **FR-BI-03:** Dashboard "Comparação entre Unidades" permite selecionar 2+ unidades simultaneamente e ver as tendências lado a lado num único gráfico.
- **FR-BI-04:** Dashboard "Unidade vs. Região" permite escolher uma unidade e comparar contra a média da região dela, com filtro de região em cascata (País → Região).
- **FR-BI-05:** Todos os dashboards funcionam sem o usuário escrever SQL — apenas escolher filtros em menus suspensos.
- **FR-BI-06:** Link para o Metabase visível no painel Flask principal.

## 10. Requisitos Não-Funcionais

- **Somente leitura:** criar um usuário PostgreSQL dedicado ao Metabase com permissão `SELECT` apenas nas views/tabelas relevantes (`GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;`), para que um erro de configuração no Metabase nunca corrompa dado da ingestão.
- **Processo independente:** Metabase roda em processo/porta própria (`3000`), não compartilha runtime com Flask (`5000`) nem Streamlit (`8501`).
- **Sem dependência de internet em produção:** depois de instalado, roda 100% local (mesmo padrão do resto do projeto).

---

## 11. Fases de Implementação (executar em ordem)

### Fase 0 — Views
- Adicionar as 5 `CREATE OR REPLACE VIEW` da Seção 5 ao `app/db/schema.sql` (ou um `app/db/views.sql` separado) e rodar contra `smartfit_db`.
- Conferir manualmente os números de 1-2 views contra a planilha já gerada por `python -m app.cli export-xlsx`.

### Fase 1 — Instalação do Metabase
- Escolher Opção A (JAR) ou B (Docker) da Seção 6.
- Criar usuário PostgreSQL somente-leitura (`metabase_reader`) e conectar o Metabase com ele.

### Fase 2 — Dashboard "Visão Geral da Rede" (Seção 7.1)

### Fase 3 — Dashboard "Comparação entre Unidades" (Seção 7.2)

### Fase 4 — Dashboard "Unidade vs. Região" (Seção 7.3)

### Fase 5 — Dashboard "Risco de Cancelamento" (Seção 7.4)

### Fase 6 — Dashboard "Pré-vendas" (Seção 7.5)

### Fase 7 — Integração visual
- Botão no painel Flask (Seção 8) + variável `METABASE_PORT` no `.env`/`.env.example`.

### Fase 8 — Documentação
- Atualizar `README.md` e `MANUAL_PASSO_A_PASSO.md` com o passo a passo de instalação e uso do Metabase, em linguagem simples.

---

## 12. Critérios de Aceite

1. As 5 views existem e batem com os números da planilha `export-xlsx`.
2. É possível, sem escrever SQL, selecionar 3 unidades diferentes e ver a tendência de ativos das 3 no mesmo gráfico.
3. É possível escolher uma unidade e comparar sua taxa de cancelamento contra a média da região dela, num único gráfico.
4. O dashboard de risco de cancelamento reflete os dados gravados em `churn_predicoes` pelo comando `predict-churn`.
5. O painel Flask mostra um link funcional para o Metabase.
6. Nenhuma escrita é feita no banco pelo Metabase (usuário `metabase_reader` só tem `SELECT`).

---

## 13. Fase Futura (fora de escopo agora, registrado para referência)

Se mais adiante quiserem um visual 100% customizado com a marca Smart Fit (em vez do Metabase genérico), `references/voltfit-dashboard/` (React + Vite + Tailwind, MIT License) é um bom ponto de partida visual — teria que: (a) trocar o dado mockado (`src/data/dashboard.js`) por chamadas a uma API real (seria necessário criar endpoints JSON no Flask expondo as views da Seção 5), e (b) construir os componentes de filtro/comparação do zero, já que o VoltFit não os tem prontos.

---

## 14. Referências

- [metabase/metabase](https://github.com/metabase/metabase) — ferramenta escolhida.
- [Metabase — Tutorial de filtros ligados/em cascata](https://www.metabase.com/learn/metabase-basics/querying-and-dashboards/dashboards/linking-filters)
- [Metabase — Filtros de dashboard (documentação oficial)](https://www.metabase.com/docs/latest/dashboards/filters)
- [apache/superset](https://github.com/apache/superset) — alternativa avaliada e descartada por complexidade de operação.
- [kendrekaran/voltfit-dashboard](https://github.com/kendrekaran/voltfit-dashboard) — referência visual (já baixado em `references/voltfit-dashboard/`), MIT License.
