-- DDL completo do banco de dados para o Pipeline de Ingestão Smart Fit

CREATE TABLE IF NOT EXISTS dim_unidade (
    id SERIAL PRIMARY KEY,
    nome_digital VARCHAR(150) NOT NULL,          -- Nome estável do negócio (sigla pode trocar)
    pais VARCHAR(20) NOT NULL,                    -- Código de país embutido na sigla (ex: 'BR', 'MX'); siglas fora do padrão (ex: 'DIGITAL') usam a própria sigla
    sigla_atual VARCHAR(30),
    regiao_uf VARCHAR(50),                       -- Ex: 'Brasil - SP', 'Brasil - AL'
    tipo_operacao VARCHAR(30) DEFAULT 'Própria',  -- 'Própria' ou 'Franquia'
    data_inauguracao DATE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Chave de unificação mestre: nome sozinho colide entre países/regiões
    -- (ex: existem 4 unidades chamadas "Santa Cruz" em 4 países diferentes).
    CONSTRAINT unq_unidade_identidade UNIQUE (nome_digital, pais, regiao_uf)
);

CREATE TABLE IF NOT EXISTS fato_metricas_diarias (
    id BIGSERIAL PRIMARY KEY,
    data_referencia DATE NOT NULL,
    unidade_id INT NOT NULL REFERENCES dim_unidade(id),
    sigla_no_dia VARCHAR(30),
    bloco_email VARCHAR(100),
    tendencia VARCHAR(20),
    unidade_imatura BOOLEAN DEFAULT FALSE,        -- flag do aviso "não atingiu 120 dias"

    -- ATIVOS
    total_ativos INT DEFAULT 0,
    ativos_smart INT DEFAULT 0,
    ativos_black INT DEFAULT 0,
    ativos_fit INT DEFAULT 0,
    ativos_black_plus INT DEFAULT 0,
    ativos_studio INT DEFAULT 0,
    bloqueados INT DEFAULT 0,

    -- VISITAS E CONVERSÃO
    visitas_dia INT DEFAULT 0,
    visitas_mes INT DEFAULT 0,
    conversao_dia NUMERIC(5,2),
    conversao_mes NUMERIC(5,2),

    -- MOVIMENTAÇÕES (saldo líquido)
    transferencias_liquida_mes NUMERIC(10,2) DEFAULT 0,

    -- TOTALIZADORES DE VENDAS
    vendas_geral_dia INT DEFAULT 0,
    vendas_geral_mes INT DEFAULT 0,

    -- Payloads brutos
    detalhe_vendas_json JSONB,
    detalhe_movimentacoes_json JSONB,

    -- Auditoria
    gmail_message_id VARCHAR(150),
    processado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unq_data_unidade UNIQUE (data_referencia, unidade_id)
);

CREATE TABLE IF NOT EXISTS fato_vendas_detalhada (
    id BIGSERIAL PRIMARY KEY,
    fato_diaria_id BIGINT NOT NULL REFERENCES fato_metricas_diarias(id) ON DELETE CASCADE,
    canal_venda VARCHAR(50) NOT NULL,   -- 'Balcao', 'Web', 'Totem', 'Outros'
    plano VARCHAR(50) NOT NULL,         -- 'Smart', 'Black', 'Fit', 'Black+', 'Studio'
    qtd_dia INT DEFAULT 0,
    qtd_mes INT DEFAULT 0,

    CONSTRAINT unq_venda_item UNIQUE (fato_diaria_id, canal_venda, plano)
);

CREATE TABLE IF NOT EXISTS fato_cancelamentos_detalhada (
    id BIGSERIAL PRIMARY KEY,
    fato_diaria_id BIGINT NOT NULL REFERENCES fato_metricas_diarias(id) ON DELETE CASCADE,
    plano VARCHAR(50) NOT NULL,         -- 'Smart', 'Black', 'Studio', 'Total'
    qtd_mes INT DEFAULT 0,

    CONSTRAINT unq_cancelamento_item UNIQUE (fato_diaria_id, plano)
);

CREATE TABLE IF NOT EXISTS dim_unidade_pre_venda (
    id SERIAL PRIMARY KEY,
    codigo_unidade VARCHAR(30) NOT NULL UNIQUE,  -- Chave de unificação (unidade ainda não tem "Nome Digital")
    nome_unidade VARCHAR(150),
    pais_regiao VARCHAR(100),                    -- Ex: 'México', 'Chile', 'Brasil'
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fato_pre_venda_diaria (
    id BIGSERIAL PRIMARY KEY,
    data_referencia DATE NOT NULL,
    unidade_pre_venda_id INT NOT NULL REFERENCES dim_unidade_pre_venda(id),
    vendas_total INT DEFAULT 0,                  -- Acumulado de pré-venda (sem quebra dia/mês)
    detalhe_vendas_json JSONB,                    -- Quebra por canal/plano (Balcão, Web x Smart, Black, Studio)
    gmail_message_id VARCHAR(150),
    processado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unq_data_unidade_pre_venda UNIQUE (data_referencia, unidade_pre_venda_id)
);

-- Guarda o histórico de predições de risco de cancelamento geradas pelo módulo de ML,
-- para acompanhar acerto/erro ao longo do tempo.
CREATE TABLE IF NOT EXISTS churn_predicoes (
    id BIGSERIAL PRIMARY KEY,
    unidade_id INT NOT NULL REFERENCES dim_unidade(id),
    mes_referencia DATE NOT NULL,                -- mês para o qual a previsão foi feita
    probabilidade_risco NUMERIC(5,4) NOT NULL,   -- 0.0000 a 1.0000
    nivel_risco VARCHAR(10) NOT NULL,            -- 'Baixo', 'Médio', 'Alto'
    versao_modelo VARCHAR(50) NOT NULL,          -- timestamp do treino, para rastreabilidade
    gerado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unq_predicao_unidade_mes UNIQUE (unidade_id, mes_referencia, versao_modelo)
);

CREATE TABLE IF NOT EXISTS controle_backfill (
    id SERIAL PRIMARY KEY,
    gmail_message_id VARCHAR(150) NOT NULL UNIQUE,
    data_email TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente', -- pendente | processado | erro
    tentativas INT DEFAULT 0,
    ultimo_erro TEXT,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices de performance
CREATE INDEX IF NOT EXISTS idx_fato_data ON fato_metricas_diarias(data_referencia);
CREATE INDEX IF NOT EXISTS idx_fato_unidade ON fato_metricas_diarias(unidade_id);
CREATE INDEX IF NOT EXISTS idx_vendas_detalhe ON fato_vendas_detalhada(canal_venda, plano);
CREATE INDEX IF NOT EXISTS idx_cancel_detalhe ON fato_cancelamentos_detalhada(plano);
CREATE INDEX IF NOT EXISTS idx_fato_message_id ON fato_metricas_diarias(gmail_message_id);
CREATE INDEX IF NOT EXISTS idx_pre_venda_data ON fato_pre_venda_diaria(data_referencia);
CREATE INDEX IF NOT EXISTS idx_pre_venda_unidade ON fato_pre_venda_diaria(unidade_pre_venda_id);
CREATE INDEX IF NOT EXISTS idx_churn_predicoes_unidade ON churn_predicoes(unidade_id);
CREATE INDEX IF NOT EXISTS idx_churn_predicoes_mes ON churn_predicoes(mes_referencia);
