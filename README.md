# Pipeline de Ingestão e Ingestão Diária Smart Fit

Este projeto implementa um pipeline de ETL automatizado para extrair relatórios diários de e-mail da Smart Fit (enviados em formato HTML), normalizar os dados, e persisti-los de forma idempotente em um banco de dados PostgreSQL.

---

## 🛠️ Stack Tecnológica
- **Linguagem:** Python 3.11+
- **Banco de Dados:** PostgreSQL 15+
- **Integração:** IMAP (Senha de App do Gmail/Google Workspace — sem Google Cloud)
- **Engine de Parsing:** BeautifulSoup4 / LXML
- **Painel de Operações:** Flask
- **Previsão de Cancelamento (opcional):** Streamlit + scikit-learn + Plotly (ver `PRD_SmartFit_Churn_Prediction.md`)

---

## 📂 Estrutura de Diretórios

```text
/opt/smartfit_analytics/
├── app/
│   ├── auth/
│   │   ├── setup_gmail.py        # Assistente de teste de conexão IMAP
│   │   └── gmail_client.py       # Cliente de e-mail via IMAP (Senha de App)
│   ├── etl/
│   │   ├── discovery.py          # Módulo de varredura de novos e-mails
│   │   ├── parser.py             # BeautifulSoup HTML Parser
│   │   ├── normalizer.py         # Limpeza e normalização de dados
│   │   ├── loader.py             # Bulk Upsert idempotente no Banco
│   │   ├── backfill.py           # Orquestrador de backfill histórico em lotes
│   │   └── raw_headers_scanner.py# Scanner de cobertura de campos
│   ├── db/
│   │   ├── schema.sql            # Definição DDL do Banco de Dados
│   │   └── database.py           # Conexão e pooling de BD
│   ├── web/
│   │   ├── routes.py             # Rotas do Dashboard Flask
│   │   └── templates/            # Templates HTML do Painel
│   └── cli.py                    # Console CLI de Operações
├── config/
│   └── config.ini                # Parâmetros de Filtros e Lotes
├── logs/
│   └── etl.log                   # Arquivo de Logs de execução
├── tests/
│   ├── fixtures/                 # Fixtures HTML para testes offline
│   ├── test_parser.py            # Testes do parser e normalizador
│   ├── test_coverage.py          # Testes do scanner de cobertura
│   └── test_loader.py            # Testes de chamadas de persistência
├── requirements.txt              # Dependências do Python
├── .env                          # Configurações locais (Banco e Flask)
└── README.md                     # Documentação do Projeto
```

---

## 🚀 Instalação e Configuração

### 1. Clonar o projeto e criar Ambiente Virtual
No terminal:
```bash
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente
Copie o arquivo `.env.example` para `.env` e configure com suas credenciais locais do PostgreSQL, IMAP e porta do Flask:
```bash
cp .env.example .env
```
Exemplo de conteúdo `.env`:
```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smartfit_db
DB_USER=postgres
DB_PASSWORD=suasenhadopostgres

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=seuemail@suaempresa.com
IMAP_APP_PASSWORD=suasenhadeapp16chr
IMAP_MAILBOX=INBOX

FLASK_SECRET_KEY=suachavesecretaflask
FLASK_PORT=5000
FLASK_DEBUG=True
```

### 3. Configurar Integração com o E-mail (IMAP + Senha de App)
Não é necessário criar projeto no Google Cloud nem passar por tela de consentimento OAuth. Basta gerar uma **Senha de App**:
1. Acesse [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) logado na conta que recebe os relatórios diários da Smart Fit.
2. Dê um nome à aplicação (ex.: `Python ETL Smartfit`).
3. O Google gera uma senha de 16 caracteres — copie-a.
4. Preencha `IMAP_USER` (o e-mail) e `IMAP_APP_PASSWORD` (a senha gerada, sem espaços) no arquivo `.env`.
5. Rode o comando interativo no console para testar a conexão e configurar os filtros de busca:
   ```bash
   python -m app.cli setup-gmail
   ```
O comando testa o login IMAP e, se tudo estiver certo, pede o remetente e o assunto padrão dos relatórios para gravar em `config/config.ini`.

---

## ⚙️ Comandos Operacionais da CLI

### Inicializar Tabelas e Índices do Banco
```bash
python -m app.cli init-db
```

### Rodar o Teste de Cobertura de Campos (Obrigatório antes do Backfill)
O pipeline possui uma regra de segurança que impede a execução de cargas históricas sem que o parser seja testado contra layouts reais primeiro. Para rodar o teste com um e-mail de fixture local (offline):
```bash
python -m app.cli test-coverage --file tests/fixtures/smartfit_email_2026.html
```
Se a cobertura for 100% (zero colunas ou campos órfãos ignorados), o sistema gerará o arquivo carimbo `logs/.coverage_passed` liberando a execução dos comandos de backfill e ingestão diária.

Para testar a cobertura a partir de um e-mail real do Gmail:
```bash
python -m app.cli test-coverage --message-id <GMAIL_MESSAGE_ID>
```

### Rodar Descoberta e Ingestão do Backfill Histórico
Para varrer a caixa e processar e-mails históricos em lotes (configurados em `config/config.ini`):
```bash
# Executa descoberta de novas mensagens + backfill de mensagens pendentes
python -m app.cli backfill --discover

# Limita o número de mensagens a serem processadas no lote atual
python -m app.cli backfill --limit 10
```

### Executar a Ingestão Incremental Diária
Geralmente agendada no scheduler (`cron`):
```bash
python -m app.cli run-daily
```

---

### Exportar os Dados Capturados para Excel (Conferência)
Para gerar uma planilha `.xlsx` com todas as unidades e campos capturados, reconstituindo as colunas do e-mail (útil para conferir manualmente se nada ficou de fora):
```bash
# Exporta tudo
python -m app.cli export-xlsx

# Filtra por uma data específica
python -m app.cli export-xlsx --date 2026-08-23

# Escolhe o caminho de saída
python -m app.cli export-xlsx --output C:\Users\ralan\Desktop\conferencia.xlsx
```
Por padrão, o arquivo é salvo em `exports/dados_capturados.xlsx`, com 3 abas: **Resumo**, **Unidades** (formato padrão) e **Pré-vendas**.

---

## 📈 Painel Mínimo de Operações (Web)
O sistema conta com um painel web que monitora o status das cargas e permite gerenciar logs e mensagens com erro de ETL.

Para rodar o painel local:
```bash
python -m app.web.routes
```
Acesse em: `http://localhost:5000`.

**Recursos do Painel:**
- Contadores de mensagens: Total, Processadas com sucesso, Pendentes e Com Erro.
- Log detalhado das últimas falhas ocorridas no ETL.
- Botão **Reprocessar** para tentar ingerir novamente um e-mail que falhou.
- Botão **Resetar** para mover o e-mail de volta ao status de pendente.

---

## 📉 Módulo de Previsão de Risco de Cancelamento (opcional)

Prevê, por unidade, o risco de aumento de cancelamentos no mês seguinte, usando os dados já capturados pelo pipeline (sem depender de dado de aluno individual). Arquitetura adaptada do repositório
[Rinkyshu200/customer-churn-dashboard](https://github.com/Rinkyshu200/customer-churn-dashboard). Detalhamento completo em `PRD_SmartFit_Churn_Prediction.md`.

### 1. Instalar dependências extras
Essas dependências ficam separadas de `requirements.txt` porque o módulo é opcional:
```bash
pip install -r requirements-ml.txt
```

### 2. Treinar o modelo
Exige pelo menos 3 meses consecutivos de histórico consolidado no banco (rode o backfill primeiro):
```bash
python -m app.cli train-churn-model
```

### 3. Gerar predições em lote e gravar no banco
```bash
python -m app.cli predict-churn --month 2026-08
```

### 4. Rodar o app interativo (Streamlit)
```bash
streamlit run app/ml/streamlit_app.py
```
Acesse em: `http://localhost:8501`. O painel Flask (`http://localhost:5000`) também mostra um link direto para esse app.

**Recursos do App:**
- Predição individual (formulário) com explicação por importância de feature.
- Predição em lote via upload de CSV, com download do resultado.
- **Retreinar por Unidade** — escolha uma unidade específica e retreine um modelo local para ela.
- Dashboard de analytics do modelo (acurácia, matriz de confusão, curva ROC, importância de features).

### 5. Modelo local por unidade (opcional)

Cada unidade tem seu próprio perfil de público (cidade, mix de planos FitAcesso/SmartAcesso/Black),
então o modelo geral às vezes não captura bem a realidade de uma unidade específica. Como uma
única unidade só tem ~24 meses de histórico — pouco para um modelo confiável isolado — o retreino
local usa a unidade escolhida **+ um grupo de unidades parecidas** (mesma região + mix de planos
similar) como comparação.

```bash
# Lista as unidades disponíveis (com id, nome, região) para achar o id que você quer
python -m app.cli list-units --search "nome da unidade"

# Treina um modelo local só para essa unidade (usa até 40 unidades parecidas por padrão)
python -m app.cli train-churn-model --unit-id 1634 --n-peers 40

# Gera a predição da unidade usando o modelo local dela
python -m app.cli predict-churn --month 2026-08 --unit-id 1634
```

O mesmo fluxo está disponível visualmente na aba **"🏢 Retreinar por Unidade"** do app Streamlit —
basta buscar a unidade pelo nome e clicar em retreinar, sem usar o terminal.

---

## 📊 Painel Analítico BI — Comparação de Unidades e Regiões (opcional)

Painel interativo "estilo Power BI" para comparar unidades entre si e uma unidade contra a média
da sua região, com gráficos de tendência e filtros de múltipla seleção — sem escrever SQL.
Construído sobre o [Metabase](https://github.com/metabase/metabase) (open source), conectado
diretamente ao `smartfit_db`. Detalhamento completo em `PRD_SmartFit_Dashboard_BI.md`.

### 1. Views de apoio
Já aplicadas automaticamente por `python -m app.cli init-db` (arquivo `app/db/views.sql`).

### 2. Subir o Metabase (Docker)
```bash
docker compose up -d
```
Acesse `http://localhost:3000` na primeira vez para criar a conta de administrador e conectar o
banco `smartfit_db` (Adicionar banco de dados → PostgreSQL → host `host.docker.internal`, porta
`5432`, banco `smartfit_db`). Recomenda-se criar um usuário PostgreSQL somente-leitura dedicado:
```sql
CREATE ROLE metabase_reader LOGIN PASSWORD 'escolha-uma-senha';
GRANT CONNECT ON DATABASE smartfit_db TO metabase_reader;
GRANT USAGE ON SCHEMA public TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_reader;
```

O painel Flask (`http://localhost:5000`) mostra um link direto ("📊 Painel Analítico (BI)").

**Dashboards prontos:**
- **Visão Geral da Rede** — KPIs e tendência de ativos/vendas, filtráveis por país/região.
- **Comparação entre Unidades** — selecione 2 ou mais unidades e veja a tendência de todas no mesmo gráfico.
- **Unidade vs. Região** — compare uma unidade contra a média da sua região, com filtro em cascata.
- **Risco de Cancelamento** — visualiza as predições geradas por `predict-churn`.
- **Pré-vendas** — acompanhamento das unidades ainda não inauguradas.

---

## 🕒 Agendamento Diário (Scheduler/Cron no Linux)
Para agendar a execução automática todo dia às 7h da manhã no Linux, use a seguinte entrada do crontab (`crontab -e`):

```cron
0 7 * * * /opt/smartfit_analytics/venv/bin/python -m app.cli run-daily >> /opt/smartfit_analytics/logs/cron.log 2>&1
```

---

## 🛠️ Resolução de Problemas Comuns (Troubleshooting)

### Erro de autenticação IMAP (login falhou)
1. Confirme que `IMAP_USER` no `.env` é o e-mail correto.
2. Gere uma nova Senha de App em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) e atualize `IMAP_APP_PASSWORD` (sem espaços).
3. Se a conta for do Google Workspace, confirme com o administrador se o IMAP está habilitado e se Senhas de App são permitidas para o domínio.
4. Rode `python -m app.cli setup-gmail` novamente para testar a conexão.

---

## 🧪 Rodando a Suíte de Testes Automatizados
O projeto conta com testes unitários robustos e testes de integração mockados que rodam de forma 100% offline.

```bash
# Executa todos os testes
python -m pytest
```
