# 📖 Manual — Instalar o Sistema Smart Fit no Servidor Linux (porta 5030 + Cloudflare Tunnel)

Todos os arquivos citados aqui (`Dockerfile`, `docker-compose.server.yml`, `scripts/daily_loop.sh`, `scripts/setup_metabase.py`, `.env.server.example`) **já foram criados e testados neste computador** antes de este manual ser escrito — o `Dockerfile` builda sem erro, o script de agendamento diário funciona, e o script do Metabase foi testado do zero (criando os 5 dashboards automaticamente) e rodando duas vezes seguidas sem duplicar nada.

---

## ✅ O que vai ficar rodando no servidor

| Serviço | Container | Porta no servidor | Acesso |
|---|---|---|---|
| Painel de Operações (Flask) | `smartfit-web` | **5030** | Público (via Cloudflare Tunnel) |
| Banco de Dados (PostgreSQL) | `smartfit-db` | — (sem porta exposta) | Só os outros containers |
| Ingestão diária automática | `smartfit-ingestor` | — (sem porta) | Roda sozinho, todo dia às 7h |
| Previsão de Cancelamento (Streamlit) | `smartfit-ml` | 8501 (só `127.0.0.1`) | Só local/túnel SSH |
| Painel Analítico BI (Metabase) | `smartfit-bi` | 3000 (só `127.0.0.1`) | Só local/túnel SSH |

**Por que só a porta 5030 fica pública:** o Streamlit tem um botão de "retreinar modelo" sem senha nenhuma, e por padrão é mais seguro expor só o painel principal (que tem os links pros outros). Se mais tarde você quiser acesso público a esses dois também, é só repetir o Passo 9 com outro subdomínio (ex: `s4`, `s5`) — não precisa mexer em mais nada.

---

## 📋 O que você vai precisar

- Acesso SSH ao servidor Linux (usuário com permissão de rodar `docker`).
- Docker e Docker Compose já instalados no servidor (confirmamos no Passo 1).
- Acesso ao painel do Cloudflare Zero Trust (a tela que você me mostrou).
- Uns 20-30 minutos de trabalho ativo (Passos 1-9) **+ 12-17 horas rodando sozinho em segundo plano** no Passo 6 (baixar todo o histórico de e-mail — você não precisa ficar acompanhando).

---

## 🛠️ Passo 1: Conferir se o servidor tem Docker

No seu computador Windows, abra o terminal e conecte no servidor (troque `usuario` e `ip-do-servidor` pelos seus dados reais):

```powershell
ssh usuario@ip-do-servidor
```

Dentro do servidor, rode:

```bash
docker --version
docker compose version
```

Se aparecerem as versões, está tudo certo — pule pro Passo 2. Se der erro de "comando não encontrado", instale primeiro (exemplo para Ubuntu/Debian):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Depois disso, saia (exit) e entre de novo no SSH para a permissão valer
```

---

## 📦 Passo 2: Clonar o código do GitHub no servidor

Direto no SSH do servidor (não precisa mais copiar nada do Windows):

```bash
mkdir -p ~/Programa
git clone https://github.com/Admsmartfit/Analise.git ~/Programa/analise
cd ~/Programa/analise
```

> Se o repositório estiver **privado**, o `git` vai pedir usuário e senha — use seu usuário do GitHub e, no lugar da senha, um **Personal Access Token** (Settings → Developer settings → Personal access tokens, no próprio GitHub). Se estiver público, clona direto sem pedir nada.

**Confira se o filtro de e-mail veio certo** (arquivo já deve existir, versionado no repositório):

```bash
cat config/config.ini
```

Deve mostrar:
```ini
[gmail]
sender = notificacoes-smartfit@smartfit.com.br
subject = Relatório Consolidado

[etl]
batch_size = 50
```

Se o arquivo não existir ou estiver diferente, crie/corrija manualmente com o conteúdo acima (`nano config/config.ini`) — é ele que diz ao sistema qual e-mail é o "Relatório Consolidado" que interessa, entre os vários tipos de e-mail que a Smart Fit manda.

---

## ⚙️ Passo 3: Configurar o `.env` do servidor

Conecte no servidor de novo (`ssh usuario@ip-do-servidor`) e rode este comando único — ele **gera as 4 senhas sozinho** (com `openssl`, que já vem em praticamente todo Linux) e escreve o `.env` de uma vez, sem passar pelo `nano` (evita o problema de acentuação/corrupção que já aconteceu):

```bash
cd ~/Programa/analise

DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
FLASK_SECRET_KEY=$(openssl rand -hex 32)
MB_ADMIN_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=')
MB_PG_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')

cat > .env << EOF
DB_HOST=db
DB_PORT=5432
DB_NAME=smartfit_db
DB_USER=postgres
DB_PASSWORD=${DB_PASSWORD}

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=seuemail@suaempresa.com
IMAP_APP_PASSWORD=suasenhadeapp16chr
IMAP_MAILBOX=INBOX

FLASK_SECRET_KEY=${FLASK_SECRET_KEY}
FLASK_PORT=5000
FLASK_DEBUG=False

STREAMLIT_PORT=8501
STREAMLIT_URL=

METABASE_PORT=3000
METABASE_URL=

MB_ADMIN_EMAIL=seuemail@suaempresa.com
MB_ADMIN_PASSWORD=${MB_ADMIN_PASSWORD}
MB_PG_PASSWORD=${MB_PG_PASSWORD}
EOF

echo "Senhas geradas — guarde num cofre de senhas antes de continuar:"
echo "DB_PASSWORD=${DB_PASSWORD}"
echo "FLASK_SECRET_KEY=${FLASK_SECRET_KEY}"
echo "MB_ADMIN_PASSWORD=${MB_ADMIN_PASSWORD}"
echo "MB_PG_PASSWORD=${MB_PG_PASSWORD}"
```

Isso deixa só **2 campos** para você preencher manualmente (o resto já vem pronto e seguro). Edite só essas duas linhas:

```bash
nano .env
```
- `IMAP_USER=` → coloque seu e-mail real (ex: `ricardo.landeiro@smartfit.com`)
- `IMAP_APP_PASSWORD=` → cole a Senha de App do Gmail (gerada em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)) — **sem espaços**
- `MB_ADMIN_EMAIL=` → o e-mail que você vai usar para entrar no Metabase do servidor

Salve com `Ctrl+O`, `Enter`, e saia com `Ctrl+X`.

> ⚠️ Se a Senha de App que você tinha usada antes parar de funcionar, gere uma nova em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) — mais seguro do que reaproveitar uma senha que já apareceu corrompida várias vezes no `.env` do Windows.

---

## 🚀 Passo 4: Subir os containers

De volta no SSH do servidor:

```bash
cd ~/Programa/analise
docker compose -f docker-compose.server.yml up -d --build
```

Isso baixa a imagem do PostgreSQL e do Metabase, builda a imagem da aplicação (Flask/Streamlit/ingestão) e sobe os 5 containers. A primeira vez demora alguns minutos (baixando as imagens).

Confira se todos os 5 estão de pé:

```bash
docker compose -f docker-compose.server.yml ps
```

Todos devem aparecer como `running` ou `Up`.

---

## 🗄️ Passo 5: Preparar o banco de dados (do zero)

Instalação nova — sem restaurar nada, o banco começa vazio. Crie as tabelas/views (idempotente — seguro rodar sempre) e o usuário só-leitura para o Metabase:

```bash
docker exec smartfit-web python -m app.cli init-db

docker exec smartfit-db psql -U postgres -d smartfit_db -c "
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'metabase_reader') THEN
      CREATE ROLE metabase_reader LOGIN PASSWORD 'COLOQUE_A_MESMA_SENHA_DO_MB_PG_PASSWORD_NO_ENV';
   END IF;
END
\$\$;
GRANT CONNECT ON DATABASE smartfit_db TO metabase_reader;
GRANT USAGE ON SCHEMA public TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_reader;
"
```

> ⚠️ Troque `COLOQUE_A_MESMA_SENHA_DO_MB_PG_PASSWORD_NO_ENV` pelo mesmo valor que você colocou em `MB_PG_PASSWORD` no `.env` (Passo 3) — precisam ser idênticos.

---

## 📧 Passo 6: Baixar todo o histórico de e-mail (backfill completo)

Como é instalação do zero, o sistema vai buscar e processar **todos os anos** de e-mail "Relatório Consolidado" já recebidos — cerca de **2.947 e-mails** (de dezembro/2019 até hoje, pelo que já mapeamos). Isso é bem mais demorado que os outros passos.

### 6.1 Testar a conexão IMAP

```bash
docker exec -it smartfit-web python -m app.cli setup-gmail
```

Deve mostrar `[OK] Conexão IMAP validada com sucesso.` e confirmar os filtros de `config/config.ini` (pode só apertar **ENTER** nas perguntas para manter os valores já salvos).

### 6.2 Validar o parser (obrigatório antes do backfill)

```bash
docker exec smartfit-web python -m app.cli test-coverage --file tests/fixtures/smartfit_email_2026.html
```

Deve terminar com `[SUCESSO] TESTE PASSOU COM 100% DE COBERTURA E INTEGRIDADE!` — isso libera o comando de backfill (existe um bloqueio de segurança que impede rodar a carga histórica sem essa validação passar antes).

### 6.3 Descobrir e registrar todos os e-mails

```bash
docker exec smartfit-web python -m app.cli backfill --discover --limit 1
```

*(`--limit 1` aqui só evita processar nada ainda — o `--discover` já varre e registra os ~2.947 e-mails como "pendentes" no banco, é isso que queremos neste comando.)*

### 6.4 Processar tudo (⏱️ estimativa: 12–17 horas)

Cada e-mail leva uns 15-20 segundos para baixar e processar (são tabelas grandes, com milhares de linhas cada). Para não perder o progresso se a conexão SSH cair, rode em segundo plano **dentro do container** com `-d` (detached — continua rodando mesmo depois que você sair do terminal):

```bash
docker exec -d smartfit-web python -m app.cli backfill --limit 3000
```

**Acompanhar o progresso** (pode fechar e abrir o terminal quando quiser, o processamento continua rodando no container):

```bash
# Ver o log em tempo real
docker exec smartfit-web tail -f logs/etl.log

# Ou conferir quantos já foram processados
docker exec smartfit-db psql -U postgres -d smartfit_db -c \
  "SELECT status, COUNT(*) FROM controle_backfill GROUP BY status;"
```

Quando a contagem de `pendente` chegar a zero (e `processado` estiver perto de 2.947), terminou. Se aparecerem alguns `erro`, não é motivo de pânico — geralmente são poucos e-mails com formato levemente diferente; pode reprocessá-los depois pelo painel Flask (botão "⚡ Reprocessar" na tela de erros) ou rodando o comando de novo (ele só tenta de novo quem está `pendente` ou `erro`).

---

## 📊 Passo 7: Configurar o Painel Analítico BI automaticamente

Em vez de clicar dashboard por dashboard na tela do Metabase, rode o script pronto (já testado do zero neste computador):

```bash
docker exec \
  -e MB_URL=http://localhost:3000 \
  -e MB_ADMIN_EMAIL="$(grep MB_ADMIN_EMAIL .env | cut -d= -f2)" \
  -e MB_ADMIN_PASSWORD="$(grep MB_ADMIN_PASSWORD .env | cut -d= -f2)" \
  -e MB_PG_HOST=db \
  -e MB_PG_PASSWORD="$(grep MB_PG_PASSWORD .env | cut -d= -f2)" \
  smartfit-web python scripts/setup_metabase.py
```

Ao final, deve aparecer `[SUCESSO] Painel Analítico BI configurado.` com os 5 dashboards criados (Comparação entre Unidades, Unidade vs Região, Visão Geral da Rede, Risco de Cancelamento, Pré-vendas).

---

## 🧪 Passo 8: Testar localmente no servidor (antes de publicar)

Ainda no SSH:

```bash
curl -I http://localhost:5030
```

Deve responder `HTTP/1.1 200 OK`. Se quiser ver visualmente, abra um túnel SSH temporário a partir do seu Windows:

```powershell
ssh -L 5030:localhost:5030 usuario@ip-do-servidor
```

E acesse `http://localhost:5030` no seu navegador — deve mostrar o painel Smart Fit já rodando no servidor.

---

## 🌐 Passo 9: Publicar no Cloudflare Tunnel

Use a mesma tela que você me mostrou (Cloudflare Zero Trust → Networks → Tunnels → seu túnel → Public Hostname → **Add a public hostname**, ou editar um existente):

1. **Subdomínio:** escolha um, ex. `smartfit` (ou `s6`, seguindo o padrão que você já usa).
2. **Domínio:** `ricardo.home.nom.br` (o mesmo da sua zona).
3. **Caminho:** deixe em branco.
4. **URL do serviço:** `http://localhost:5030`
5. Clique em **Salvar alterações**.

O hostname completo vai ficar algo como `smartfit.ricardo.home.nom.br`.

> Isso só funciona se o `cloudflared` já estiver rodando **no mesmo servidor** onde os containers subiram (Passo 4) — já que a URL do serviço é `localhost:5030`. Se o túnel roda em outra máquina, troque `localhost` pelo IP do servidor Docker na rede local.

---

## ✅ Passo 10: Testar o acesso externo

No navegador (de qualquer lugar, não precisa estar na mesma rede), acesse:

```
https://smartfit.ricardo.home.nom.br
```

Deve aparecer o painel de operações Smart Fit, com os botões "📊 Painel Analítico (BI)" e "📉 Previsão de Cancelamento" — esses dois últimos só vão funcionar de dentro da rede local ou via túnel SSH (Passo 8), a não ser que você publique rotas próprias pra eles também (repetindo o Passo 9 com `http://localhost:8501` e `http://localhost:3000`).

---

## 🔄 Manutenção

**Atualizar o código depois de uma mudança no GitHub:**
```bash
cd ~/Programa/analise
git pull
docker compose -f docker-compose.server.yml up -d --build
```

**Ver logs de um serviço:**
```bash
docker compose -f docker-compose.server.yml logs -f web        # painel Flask
docker compose -f docker-compose.server.yml logs -f ingestor   # ingestão diária
```

**Rodar a ingestão diária manualmente (sem esperar as 7h):**
```bash
docker exec smartfit-ingestor python -m app.cli run-daily
```

**Parar tudo:**
```bash
docker compose -f docker-compose.server.yml down
```
*(Os dados continuam guardados nos volumes do Docker — não some ao parar.)*

---

## 🔒 Checklist de Segurança

- [ ] `.env` do servidor tem senhas **diferentes** das usadas no Windows (não reaproveitar).
- [ ] `FLASK_DEBUG=False` no `.env` do servidor (já vem assim no `.env.server.example`) — nunca deixe `True` em produção, isso expõe informação sensível em erros.
- [ ] `smartfit-ml` (Streamlit) e `smartfit-bi` (Metabase) continuam só em `127.0.0.1` — não publique no Cloudflare Tunnel sem pensar em autenticação primeiro (o Streamlit não tem login).
- [ ] Se o repositório `Admsmartfit/Analise` no GitHub estiver público, confirme que **nenhum arquivo `.env` real** está commitado nele (só os `.env.example`) — o `.gitignore` do projeto já protege isso, mas vale conferir em `github.com/Admsmartfit/Analise` antes de clonar em produção.
