# PRD — Pipeline de Ingestão, Backfill Histórico e Configuração de Gmail — Smart Fit

**Projeto:** Sistema de Ingestão e Consolidação de Relatórios Diários (E-mail → Banco de Dados)
**Ambiente-alvo:** Linux (Ubuntu 22.04 LTS / Debian 12)
**Stack:** Python 3.11+, PostgreSQL 15+, Gmail API (OAuth2), APScheduler/cron
**Ferramenta de geração:** Este documento foi escrito para ser executado por um agente de codificação (Antigravity), dividido em **fases sequenciais**, cada uma com escopo fechado, entregável e critério de "pronto" (Definition of Done).
**Escopo desta versão:** ingestão, backfill histórico completo, normalização e persistência dos dados. O **módulo de análise/dashboard fica fora de escopo** e será um projeto separado que apenas consumirá o banco de dados aqui criado.

---

## 1. Objetivo

Criar um sistema que roda em um servidor Linux e que, **na primeira execução**, varre **toda a caixa de e-mail (todos os anos disponíveis)** em busca dos relatórios diários da Smart Fit, extrai as tabelas HTML (unidades, ativos, visitas, conversão, vendas por canal×plano×período, transferências e cancelamentos) e grava tudo em um banco de dados relacional robusto, sem duplicar dados e sem exigir alteração de código quando surgirem novos canais, planos ou regiões.

Depois do backfill inicial, o sistema passa a rodar diariamente (via `cron`) processando apenas os e-mails novos.

Um módulo separado, com passo a passo muito explicado, permite configurar o acesso ao Gmail sem que o usuário precise entender OAuth2 a fundo.

---

## 2. Fora de Escopo (explicitamente)

- Dashboard analítico avançado, gráficos de tendência, comparativos entre unidades — isso será um **módulo à parte**, construído depois, consumindo o banco já populado.
- Qualquer alteração na estrutura de e-mail vinda da Smart Fit que não esteja representada nos exemplos fornecidos (o parser deve ser tolerante a colunas novas, mas não é obrigado a "adivinhar" campos nunca vistos).
- Envio de e-mails, notificações ou alertas (pode ser sugerido como fase futura, mas não faz parte do MVP).

---

## 3. Campos identificados nos e-mails (base para o parser)

Com base nas capturas de tela analisadas, cada relatório diário contém, por bloco regional (`Brasil - SP`, `Brasil - AL`, `Franquia`, etc.):

**Bloco "Unidade"**
- Sigla, Nome (Nome Digital), Data de Inauguração
- Aviso especial: `* Unidade não atingiu o período de maturidade de 120 dias` (deve ser capturado como flag booleana `unidade_imatura`, não como texto solto)

**Bloco "Ativos"**
- Total, Smart, Black, Fit, Black+, Studio, Bloqueados

**Bloco "Visitas" e "Conversão"**
- Visitas Dia / Mês
- Conversão Dia / Mês (valores podem vir como `-`, que **não é zero**, é ausência de cálculo — deve virar `NULL`, não `0`)

**Bloco "Vendas" (matriz completa Canal × Plano × Período)**
- Canais observados: **Balcão, Web, Totem, Outros**
- Planos observados: **Smart, Black, Fit, Black+, Studio**
- Cada combinação Canal×Plano tem duas colunas: **Dia** e **Mês**
- Coluna final: **Vendas Total** (Dia / Mês) — soma de conferência

**Bloco "Transferências e Cancelados"** (tabela separada, aparece por região)
- Transferências: valor único por linha, **coluna "Mês"**, pode ser **negativo** (é um saldo líquido: entradas − saídas, não duas colunas separadas)
- Cancelados: **Smart, Black, Studio, Total** — apenas coluna **Mês** (não existe granularidade "Dia" para cancelamento)

> Importante para o parser: o layout real do e-mail é **mais largo do que a tela**, ou seja, o HTML normalmente contém uma única tabela grande com muitas colunas que "quebram" visualmente em várias imagens/capturas — o parser deve ler o HTML bruto (não a renderização visual) e mapear por **cabeçalho de coluna**, nunca por posição fixa.

---

## 4. Racional de Arquitetura (por que cada decisão)

- **Nome Digital como chave mestre:** siglas mudam (ex.: `AL01` → `AL99`) em reorganizações; o nome digital é o identificador estável do negócio. Toda a modelagem une o histórico por esse campo.
- **Modelo híbrido relacional + JSONB:** a matriz de vendas tem dezenas de combinações (Canal × Plano × Período) que crescem com o tempo (novo canal, novo plano). Colunas fixas para cada combinação quebram o sistema a cada mudança. Por isso:
  - Guardamos os totais e métricas mais usadas em **colunas fixas** (leitura rápida, índices simples).
  - Guardamos o detalhamento granular em **tabelas normalizadas** (`fato_vendas_detalhada`, `fato_cancelamentos_detalhada`) para consultas SQL diretas.
  - Guardamos o **payload bruto completo em JSONB** (`detalhe_vendas_json`, `detalhe_movimentacoes_json`) como rede de segurança: mesmo que um campo novo apareça e o parser ainda não tenha uma coluna para ele, **nada se perde**.
- **Idempotência (`ON CONFLICT DO UPDATE`):** o backfill histórico e a execução diária podem ser reexecutados (queda de energia, reprocessamento, erro de rede) sem duplicar linhas nem inflar totais.
- **Auditoria (`sigla_no_dia`, `bloco_email`, `message_id`, `processado_em`):** qualquer divergência deve ser rastreável até o e-mail exato de origem.
- **Backfill histórico completo desde o início:** diferente de uma ingestão incremental comum, a primeira execução precisa varrer **todos os anos de e-mail já recebidos**, então o sistema é desenhado com paginação robusta, checkpoints e retomada em caso de falha (rodar um backfill de vários anos não pode "morrer" no meio e perder o progresso).

---

## 5. Estrutura de Pastas do Projeto

```
/opt/smartfit_analytics/
├── app/
│   ├── auth/
│   │   ├── setup_gmail.py        # Assistente interativo de configuração do Gmail
│   │   ├── gmail_client.py       # Wrapper de autenticação/uso da API
│   │   └── credentials/          # (gitignored) credentials.json e token.json
│   ├── etl/
│   │   ├── discovery.py          # Busca e paginação de e-mails no Gmail
│   │   ├── parser.py             # Extração das tabelas HTML → dicionários
│   │   ├── normalizer.py         # Regras de negócio (ex: "-" -> NULL, unidade imatura)
│   │   ├── loader.py             # Upsert idempotente no banco
│   │   └── backfill.py           # Orquestrador do backfill histórico completo
│   ├── db/
│   │   ├── schema.sql            # DDL completo
│   │   └── database.py           # Conexão / pool / execução de queries
│   ├── web/                      # Painel mínimo de operação (não é o módulo de análise)
│   │   ├── routes.py
│   │   └── templates/
│   │       ├── index.html
│   │       ├── config_gmail.html
│   │       └── status_backfill.html
│   └── cli.py                    # Comandos de linha de comando (setup, backfill, run-daily)
├── logs/
│   └── etl.log
├── config/
│   └── config.ini                # Parâmetros não sensíveis (filtros de busca, paths)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 6. Módulo de Configuração do Gmail (passo a passo explicado)

Este é o módulo que o usuário final vai tocar. Precisa ser **muito claro**, com mensagens de erro amigáveis e nenhum passo "subentendido".

### 6.1 Pré-requisitos explicados na tela (texto a ser exibido pelo `setup_gmail.py`)

1. Acesse **https://console.cloud.google.com/**
2. Crie um novo projeto (ou use um existente) — qualquer nome, ex.: `smartfit-etl`
3. No menu lateral, vá em **APIs e Serviços → Biblioteca** e ative a **Gmail API**
4. Vá em **APIs e Serviços → Tela de Consentimento OAuth**
   - Tipo de usuário: **Externo** (a menos que a organização tenha Google Workspace, aí pode ser **Interno**)
   - Preencha nome do app e e-mail de suporte (qualquer um seu)
   - Em "Escopos", não precisa adicionar nada manualmente agora
   - Em "Usuários de teste", adicione o e-mail do Gmail que recebe os relatórios da Smart Fit
5. Vá em **APIs e Serviços → Credenciais → Criar Credenciais → ID do cliente OAuth**
   - Tipo de aplicativo: **App para computador (Desktop app)**
   - Dê um nome, ex.: `smartfit-desktop`
6. Clique em **Baixar JSON** — esse arquivo deve ser salvo como:
   `/opt/smartfit_analytics/app/auth/credentials/credentials.json`

### 6.2 Assistente interativo (`python -m app.cli setup-gmail`)

Fluxo do script, com mensagens explicativas em cada etapa:

1. Verifica se `credentials.json` existe no caminho esperado.
   - Se não existir → imprime o passo a passo da seção 6.1 e encerra sem erro feio (mensagem amigável).
2. Solicita apenas o **escopo de leitura** (`gmail.readonly`) — nunca escopo de escrita/exclusão, por segurança.
3. Abre automaticamente o navegador padrão com o link de autorização do Google (`InstalledAppFlow.run_local_server`).
4. Usuário faz login com a conta Gmail que recebe os relatórios e clica em "Permitir".
5. O script recebe o token, salva em `token.json` (no mesmo diretório, permissões de arquivo `600`, leitura restrita ao dono).
6. Executa um **teste de conexão**: busca 1 e-mail qualquer e imprime "✅ Conexão com Gmail validada com sucesso. Conta: {email}".
7. Pergunta ao usuário (via prompt) qual é o **remetente/assunto** típico do relatório, para já gravar o filtro de busca em `config.ini` (com um valor sugerido padrão, editável depois).

### 6.3 Renovação e problemas comuns (seção de troubleshooting no próprio script/README)

- **Token expirado/revogado (`invalid_grant`)** → instrução: apagar `token.json` e rodar `setup-gmail` novamente.
- **Erro "app não verificado" do Google** → explicar que, como é um app pessoal/interno, basta clicar em "Avançado → Acessar mesmo assim" (isso é esperado para apps em modo de teste).
- **Trocar de conta Gmail** → apagar `token.json`, rodar `setup-gmail` de novo e logar com a nova conta.
- **Revogar acesso manualmente** → link direto: `https://myaccount.google.com/permissions`

### 6.4 Segurança

- `credentials.json` e `token.json` nunca vão para o controle de versão (`.gitignore` já configurado).
- Apenas escopo `gmail.readonly` é solicitado — o sistema nunca apaga, move ou envia e-mails.
- Variáveis sensíveis do banco de dados (usuário/senha) ficam em `.env`, nunca em `config.ini`.

---

## 7. Estrutura Completa do Banco de Dados (SQL DDL)

### 7.1 Tabela Cadastral (Dimensão Unidade)

```sql
CREATE TABLE dim_unidade (
    id SERIAL PRIMARY KEY,
    nome_digital VARCHAR(150) NOT NULL UNIQUE,   -- Chave de unificação mestre
    sigla_atual VARCHAR(30),
    regiao_uf VARCHAR(50),                       -- Ex: 'Brasil - SP', 'Brasil - AL'
    tipo_operacao VARCHAR(30) DEFAULT 'Própria',  -- 'Própria' ou 'Franquia'
    data_inauguracao DATE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.2 Tabela Principal de Métricas Diárias (Fato)

```sql
CREATE TABLE fato_metricas_diarias (
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

    -- VISITAS E CONVERSÃO ("-" no e-mail deve virar NULL, não 0)
    visitas_dia INT DEFAULT 0,
    visitas_mes INT DEFAULT 0,
    conversao_dia NUMERIC(5,2),
    conversao_mes NUMERIC(5,2),

    -- MOVIMENTAÇÕES (saldo líquido, pode ser negativo)
    transferencias_liquida_mes NUMERIC(10,2) DEFAULT 0,

    -- TOTALIZADORES DE VENDAS
    vendas_geral_dia INT DEFAULT 0,
    vendas_geral_mes INT DEFAULT 0,

    -- Payloads brutos completos (rede de segurança contra campos novos)
    detalhe_vendas_json JSONB,
    detalhe_movimentacoes_json JSONB,

    -- Auditoria
    gmail_message_id VARCHAR(150),
    processado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unq_data_unidade UNIQUE (data_referencia, unidade_id)
);
```

### 7.3 Tabela de Vendas Detalhada (Canal × Plano × Período)

```sql
CREATE TABLE fato_vendas_detalhada (
    id BIGSERIAL PRIMARY KEY,
    fato_diaria_id BIGINT NOT NULL REFERENCES fato_metricas_diarias(id) ON DELETE CASCADE,
    canal_venda VARCHAR(50) NOT NULL,   -- 'Balcao', 'Web', 'Totem', 'Outros'
    plano VARCHAR(50) NOT NULL,         -- 'Smart', 'Black', 'Fit', 'Black+', 'Studio'
    qtd_dia INT DEFAULT 0,
    qtd_mes INT DEFAULT 0,

    CONSTRAINT unq_venda_item UNIQUE (fato_diaria_id, canal_venda, plano)
);
```

### 7.4 Tabela de Cancelamentos Detalhada (Plano × Mês, sem granularidade diária)

```sql
CREATE TABLE fato_cancelamentos_detalhada (
    id BIGSERIAL PRIMARY KEY,
    fato_diaria_id BIGINT NOT NULL REFERENCES fato_metricas_diarias(id) ON DELETE CASCADE,
    plano VARCHAR(50) NOT NULL,         -- 'Smart', 'Black', 'Studio', 'Total'
    qtd_mes INT DEFAULT 0,

    CONSTRAINT unq_cancelamento_item UNIQUE (fato_diaria_id, plano)
);
```

### 7.5 Índices de Performance

```sql
CREATE INDEX idx_fato_data ON fato_metricas_diarias(data_referencia);
CREATE INDEX idx_fato_unidade ON fato_metricas_diarias(unidade_id);
CREATE INDEX idx_vendas_detalhe ON fato_vendas_detalhada(canal_venda, plano);
CREATE INDEX idx_cancel_detalhe ON fato_cancelamentos_detalhada(plano);
CREATE INDEX idx_fato_message_id ON fato_metricas_diarias(gmail_message_id);
```

### 7.6 Tabela de Controle de Backfill (checkpoint/retomada)

```sql
CREATE TABLE controle_backfill (
    id SERIAL PRIMARY KEY,
    gmail_message_id VARCHAR(150) NOT NULL UNIQUE,
    data_email TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pendente', -- pendente | processado | erro
    tentativas INT DEFAULT 0,
    ultimo_erro TEXT,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> Esta tabela é o que permite que o backfill de **vários anos de e-mail** seja interrompido (queda de energia, `Ctrl+C`, erro de rede) e **retomado exatamente de onde parou**, sem reprocessar o que já foi feito e sem pular e-mails.

---

## 8. Requisitos Funcionais

- **FR-01 — Configuração de Gmail:** assistente interativo descrito na Seção 6, executável via `python -m app.cli setup-gmail`.
- **FR-02 — Descoberta de e-mails:** busca via Gmail API com filtro configurável (remetente/assunto), paginando com `nextPageToken` **sem limite de data** na primeira execução (para capturar todos os anos).
- **FR-03 — Parsing dinâmico de blocos regionais:** identificar cabeçalhos de região/tipo (`Brasil - SP`, `Brasil - AL`, `Franquia`, etc.) e associar corretamente as tabelas seguintes a cada bloco.
- **FR-04 — Mapeamento por cabeçalho, não por posição:** o parser lê os `<th>`/cabeçalhos de duas linhas (grupo + Dia/Mês) e monta dinamicamente as chaves `canal_plano_periodo`; nenhuma coluna é hardcoded por índice numérico.
- **FR-05 — Normalização de valores:** `"-"` em campos de contagem → `0`; `"-"` em campos de percentual/conversão → `NULL`; espaços/células mescladas → `0`.
- **FR-06 — Cadastro automático de unidades:** ao encontrar um "Nome Digital" novo, criar automaticamente linha em `dim_unidade`.
- **FR-07 — Persistência idempotente:** todo insert usa `ON CONFLICT (...) DO UPDATE`, chaveado por `(data_referencia, unidade_id)` na tabela principal e pelas `UNIQUE constraints` das tabelas de detalhamento.
- **FR-08 — Backfill histórico completo:** comando `python -m app.cli backfill --all-years` varre 100% do histórico do Gmail, grava progresso em `controle_backfill`, e pode ser interrompido/retomado sem perda ou duplicação.
- **FR-09 — Execução diária incremental:** comando `python -m app.cli run-daily`, agendado via `cron`, processa apenas e-mails com data posterior ao último processado com sucesso.
- **FR-10 — Painel mínimo de operação:** tela simples mostrando status do backfill (quantos e-mails encontrados/processados/com erro), log dos últimos erros, e botão para reprocessar um e-mail específico por `message_id`.
- **FR-11 — Teste de cobertura de campos:** comando `test-coverage` que compara, para um ou mais e-mails reais, os cabeçalhos/colunas encontrados no HTML bruto contra o que o parser efetivamente mapeou, apontando campos órfãos (não mapeados), campos esperados e ausentes, e um checksum numérico de conferência (Seção "Fase 2.5"). O backfill completo só deve rodar depois que este teste passar com 100% de cobertura.

---

## 9. Requisitos Não-Funcionais

- **NFR-01 (Resiliência do parser):** se uma linha/unidade falhar, o erro é logado (`logs/etl.log`) com o `message_id` e a unidade envolvida, e o script segue para a próxima unidade — nunca aborta o e-mail inteiro por causa de uma linha ruim.
- **NFR-02 (Performance):** *bulk upsert* / transações agrupadas por e-mail; processar um e-mail inteiro (todas as regiões e unidades) em menos de 5 segundos em hardware modesto.
- **NFR-03 (Backfill longo):** deve suportar milhares de e-mails históricos sem estourar memória — leitura e processamento em lotes (batches configuráveis, ex.: 50 e-mails por lote), nunca carregando toda a caixa de entrada de uma vez.
- **NFR-04 (Logs):** log rotativo (`RotatingFileHandler`) em `/opt/smartfit_analytics/logs/etl.log`, com nível configurável (INFO padrão, DEBUG para troubleshooting).
- **NFR-05 (Agendamento):** `crontab` isolado em `venv` Python; exemplo de entrada documentado no README (`0 7 * * * /opt/smartfit_analytics/venv/bin/python -m app.cli run-daily >> logs/cron.log 2>&1`).
- **NFR-06 (Segurança):** nenhuma credencial em texto puro versionado; arquivos de token com permissão `600`.

---

## 10. Fases de Implementação (para o Antigravity executar em ordem)

Cada fase deve ser tratada como uma entrega fechada, com testes antes de avançar para a próxima.

### Fase 0 — Fundação do projeto
- Criar estrutura de pastas (Seção 5), `requirements.txt`, `.env.example`, `venv`.
- Subir PostgreSQL local (ou apontar para instância existente) e rodar `schema.sql` (Seção 7) via `psql` ou script Python de migração.
- **DoD:** `python -m app.cli --version` roda sem erro; tabelas criadas e visíveis via `\dt` no `psql`.

### Fase 1 — Módulo de autenticação Gmail
- Implementar `setup_gmail.py` conforme Seção 6 (texto explicativo, fluxo OAuth, teste de conexão).
- Implementar `gmail_client.py` com métodos `list_messages(query, page_token)` e `get_message(id)`.
- **DoD:** rodar `setup-gmail`, autorizar no navegador, ver "✅ Conexão com Gmail validada com sucesso".

### Fase 2 — Parser de e-mail (offline, com exemplos salvos)
- Salvar 2–3 e-mails reais de exemplo como `.html` em `tests/fixtures/`.
- Implementar `parser.py` para extrair: unidades, ativos, visitas, conversão, matriz de vendas, transferências, cancelamentos — **por cabeçalho**, não por posição.
- Implementar `normalizer.py` (regras da Seção FR-05).
- **DoD:** rodar o parser contra os fixtures e obter estruturas Python (dicts/dataclasses) corretas, validadas com testes unitários (`pytest`) comparando contra valores esperados extraídos manualmente das imagens de exemplo.

### Fase 2.5 — Teste Inicial de Cobertura de Campos (obrigatório antes do backfill em massa)

**Objetivo:** provar, com e-mails reais, que **100% dos campos presentes na planilha do e-mail** estão sendo capturados — nenhuma coluna, canal, plano ou bloco regional ficando "invisível" para o parser antes de rodar o backfill de vários anos.

Comando: `python -m app.cli test-coverage --message-id <id>` ou `python -m app.cli test-coverage --sample 5` (pega uma amostra espalhada ao longo dos anos, ex.: um e-mail por ano disponível).

**Como funciona:**

1. Baixa o HTML bruto do(s) e-mail(s) selecionado(s) (sem passar pelo parser oficial ainda).
2. Um **leitor cru** (`raw_headers_scanner.py`) varre TODAS as tabelas do HTML, sem nenhum filtro de negócio, e lista:
   - Todos os cabeçalhos de coluna encontrados (inclusive os de duas linhas mescladas, ex.: "Vendas Web Black" + "Dia/Mês");
   - Todos os blocos regionais encontrados (`Brasil - SP`, `Brasil - AL`, `Franquia`, etc.);
   - Quantidade total de linhas de unidade por bloco.
3. Roda o parser oficial (`parser.py`) sobre o mesmo e-mail.
4. Compara os dois resultados e gera três listas:
   - ✅ **Campos capturados** — presentes no HTML e corretamente mapeados pelo parser;
   - ⚠️ **Campos encontrados no e-mail e NÃO mapeados pelo parser** (lista mais crítica — indica canal/plano novo ou coluna sendo ignorada);
   - ❌ **Campos que o parser espera mas não encontrou no e-mail** (pode indicar mudança de layout ou nome de coluna diferente do esperado).
5. Confere a **contagem de linhas**: nº de unidades no HTML bruto por bloco regional deve ser idêntico ao nº de linhas gravadas em `fato_metricas_diarias` para aquele `gmail_message_id` e bloco.
6. Confere um **checksum numérico**: soma bruta de todos os valores de vendas encontrados no HTML deve bater com a soma dos mesmos valores gravados no banco para aquele e-mail — serve como conferência de que nenhum valor "sumiu" silenciosamente (virou `0`/`NULL` por erro de parsing).
7. Gera um relatório (`logs/coverage_report_<message_id>.txt`) e imprime um resumo no terminal, exemplo de sucesso:
   ```
   Cobertura de Campos - Mensagem 18f3a...
   Blocos regionais encontrados: 5 (Brasil-SP, Brasil-AL, Brasil-AC, Franquia, Digital)
   Unidades no HTML: 342   |  Unidades gravadas no banco: 342   ✅
   Colunas de vendas no HTML: 42  |  Colunas mapeadas pelo parser: 42  ✅
   Checksum de vendas (soma bruta): 18342  |  Checksum gravado no banco: 18342  ✅
   Nenhum campo órfão encontrado. Cobertura: 100%
   ```
   Exemplo com divergência:
   ```
   ⚠️ 2 colunas encontradas no e-mail e NÃO mapeadas:
      - "Vendas Web Studio" (Dia/Mês)
      - "Vendas Outros Black+" (Dia/Mês)
   Cobertura: 95.2% — revisar parser.py antes de prosseguir.
   ```

**Regra de bloqueio:** o comando `backfill --all-years` (Fase 4) **não deve iniciar** enquanto o teste de cobertura não tiver passado com 100% (sem campos órfãos) em pelo menos um e-mail de cada "layout conhecido" — na prática, pelo menos um e-mail por ano disponível na caixa, já que layouts de relatório costumam mudar ao longo do tempo. Sugestão de implementação: ao passar, gravar um carimbo `logs/.coverage_passed`, que `backfill.py` verifica antes de rodar (se não existir, aborta com mensagem clara pedindo para rodar `test-coverage` antes).

**DoD:** rodar `test-coverage` contra pelo menos 3 e-mails de anos diferentes (ex.: um do ano mais antigo, um intermediário, um recente) e obter 100% de cobertura em todos — ou uma lista de divergências revisada e conscientemente incorporada ao parser antes de seguir para a Fase 4.

### Fase 3 — Persistência idempotente
- Implementar `loader.py` com upserts para as 4 tabelas de fato (Seção 7.2–7.4).
- Testar rodando o mesmo e-mail de exemplo duas vezes seguidas e confirmar que **não duplica linhas** e os valores batem.
- **DoD:** teste automatizado que roda o loader 2x e faz `SELECT COUNT(*)` estável.

### Fase 4 — Orquestrador de backfill histórico
- Implementar `backfill.py`: descobre todos os `message_id` via `discovery.py`, grava em `controle_backfill` como `pendente`, processa em lotes, marca `processado` ou `erro`.
- Implementar retomada: se rodar de novo, pula os já `processado`.
- **DoD:** rodar `backfill --all-years` contra a caixa real (ou uma cópia de teste), interromper no meio (`Ctrl+C`) e rodar de novo — deve continuar do ponto exato sem duplicar nem pular.

### Fase 5 — Execução diária + agendamento
- Implementar `run-daily` (mesma engine do backfill, mas filtrando apenas e-mails com data > último `processado_em` bem-sucedido).
- Documentar e testar a entrada de `cron`.
- **DoD:** rodar `run-daily` manualmente duas vezes no mesmo dia e confirmar que não duplica.

### Fase 6 — Painel mínimo de operação
- Tela Flask/FastAPI simples: status do backfill, últimos erros, botão de reprocessar por `message_id`.
- **DoD:** acessar via navegador, ver contagem de e-mails processados/pendentes/com erro em tempo real.

### Fase 7 — Documentação final
- `README.md` com: instalação, configuração do Gmail (reaproveitando texto da Seção 6), como rodar o backfill inicial, como configurar o `cron`, tabela de troubleshooting.
- **DoD:** uma pessoa sem conhecimento prévio do projeto consegue, só lendo o README, configurar o Gmail e rodar o backfill do zero.

---

## 11. Critérios de Aceite Gerais

1. **Backfill completo:** após a primeira execução, `SELECT MIN(data_referencia), MAX(data_referencia) FROM fato_metricas_diarias` deve refletir todos os anos de e-mail existentes na caixa configurada.
2. **Sem duplicação:** rodar o pipeline (backfill ou diário) múltiplas vezes sobre o mesmo conjunto de e-mails não gera linhas duplicadas em nenhuma das 4 tabelas de fato.
3. **Consolidação por Nome Digital:** trocar a sigla de uma unidade não quebra o histórico — a busca por Nome Digital agrupa tudo sob o mesmo `unidade_id`.
4. **Consulta granular:** `SELECT * FROM fato_vendas_detalhada WHERE canal_venda='Web' AND plano='Black'` retorna valores corretos de Dia e Mês.
5. **Cancelamentos:** `SELECT * FROM fato_cancelamentos_detalhada WHERE plano='Total'` bate com o total exibido no e-mail.
6. **Configuração de Gmail sem fricção:** um usuário novo, seguindo apenas a Seção 6, consegue autorizar o acesso e validar a conexão sem precisar de ajuda técnica externa.
7. **Retomada de backfill:** interromper o backfill no meio e rodá-lo novamente completa o restante sem reprocessar o que já foi feito.
8. **Cobertura de campos validada:** o teste `test-coverage` (Fase 2.5) roda com sucesso (100% de cobertura, sem colunas órfãs) em amostras de pelo menos 3 anos diferentes antes de qualquer backfill em massa ser autorizado a rodar.

---

## 12. Próximos Passos (fora deste PRD, apenas para contexto)

Após este pipeline estar validado e populando o banco de forma confiável, um **módulo separado de análise/dashboard** consumirá as tabelas `fato_metricas_diarias`, `fato_vendas_detalhada` e `fato_cancelamentos_detalhada` para gerar visões comparativas, tendências e relatórios customizados. Esse módulo terá seu próprio PRD.
