-- Views de apoio ao Painel Analítico (BI) — ver PRD_SmartFit_Dashboard_BI.md
-- Achatam os JOINs entre dim_unidade / fato_metricas_diarias / fato_cancelamentos_detalhada
-- em tabelas com nomes de coluna em português, prontas para uso direto no Metabase.

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
