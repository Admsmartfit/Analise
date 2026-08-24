# 📖 Manual Passo a Passo — Como Testar o Sistema no Windows 11

Este manual foi escrito para você que **nunca programou na vida**. Todos os passos abaixo foram testados neste computador antes de serem escritos aqui, então basta seguir com calma, copiando e colando cada comando exatamente como está.

> 💡 **Dica geral:** para copiar um comando, clique no ícone de cópia que aparece ao passar o mouse sobre a caixinha cinza do comando (ou selecione o texto com o mouse e aperte `Ctrl+C`). Para colar dentro do terminal, aperte `Ctrl+V` (ou clique com o botão direito do mouse).

---

## ✅ O que você vai conseguir testar

Este programa lê relatórios diários que a Smart Fit manda por e-mail, organiza esses dados e guarda tudo de forma organizada. Neste manual você vai:

1. Preparar o computador para rodar o programa.
2. Rodar os testes automáticos (sem precisar de e-mail real nem banco de dados).
3. Ver o painel visual (dashboard) funcionando no navegador, já ligado ao banco de dados PostgreSQL real e à sua conta de e-mail real.

Os passos 1 a 6 funcionam **sem instalar mais nada** além do que já está no seu computador. Os Passos 7 e 8 (banco de dados e e-mail) já foram configurados neste computador durante os testes.

---

## 🛠️ Passo 1: Abrir o Terminal (PowerShell)

1. No teclado, pressione a tecla **Windows** (aquela com o símbolo do Windows) e, sem soltar, aperte a letra **X**.
2. No menu que aparecer, clique em **Terminal** (ou **Windows PowerShell**).
3. Vai abrir uma janela azul/preta com um cursor piscando. É nela que vamos digitar (ou colar) os comandos.
4. Copie o comando abaixo, cole na janela e aperte **ENTER**:

```powershell
cd C:\Users\ralan\programa\Analise
```

*(Esse comando "entra" na pasta do programa. Se der certo, o caminho `C:\Users\ralan\programa\Analise>` vai aparecer antes do cursor.)*

---

## 🔎 Passo 2: Conferir se o Python está instalado

Este computador já tem o Python instalado (versão 3.13), mas é bom confirmar. Digite:

```powershell
python --version
```

Se aparecer algo como `Python 3.13.9`, está tudo certo — pode seguir para o Passo 3.

Se aparecer uma mensagem de erro dizendo que o `python` não foi encontrado, ou se abrir a Microsoft Store sozinha, é só avisar que farei a instalação com você antes de continuar.

---

## 📦 Passo 3: Preparar o "Ambiente" do Python

Isso cria uma pastinha isolada só para os componentes deste programa, sem bagunçar o resto do seu computador.

1. Digite e aperte **ENTER**:
   ```powershell
   python -m venv venv
   ```
   *(Vai demorar alguns segundos e não vai mostrar nada na tela — é normal. Quando o cursor voltar, terminou.)*

2. Se o Windows recusar o próximo passo com uma mensagem sobre "política de execução" (`execution policy`), rode este comando de liberação e depois tente de novo:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```
   Se ele perguntar algo, digite `S` (de "Sim") e aperte **ENTER**.

3. Agora ative o ambiente:
   ```powershell
   .\venv\Scripts\activate
   ```
   *(Você vai notar que apareceu `(venv)` em verde antes do caminho no terminal — isso confirma que está ativo.)*

   ⚠️ **Atenção:** a partir de agora, toda vez que você abrir um terminal novo para mexer neste programa, repita os Passos 1 e este item 3 (`cd` até a pasta + `.\venv\Scripts\activate`) antes de qualquer outro comando.

4. Instale os componentes necessários:
   ```powershell
   pip install -r requirements.txt
   ```
   *(Isso baixa da internet vários "pacotes" que o programa precisa. Pode levar de 1 a 3 minutos, com bastante texto passando na tela — é normal. Quando terminar, vai aparecer uma linha `Successfully installed ...`.)*

---

## 🧪 Passo 4: Rodar os Testes Automáticos (Modo Simulação / Offline)

Você **não precisa** ter banco de dados instalado nem senha do Gmail configurada para este passo. São testes simulados e seguros, que não mexem em nada real.

1. Digite:
   ```powershell
   python -m pytest -q
   ```
2. Depois de alguns segundos, você deve ver algo como:
   ```
   ...                                                                      [100%]
   3 passed in 1.13s
   ```
   Isso significa que a leitura do e-mail, a organização dos dados e o teste de gravação passaram 100% ✅.

---

## 📊 Passo 5: Testar o Scanner de Cobertura do E-mail

Esse teste confirma que o programa consegue ler um e-mail de relatório da Smart Fit e capturar **todas** as informações da planilha, sem perder nada.

1. Digite:
   ```powershell
   python -m app.cli test-coverage --file tests/fixtures/smartfit_email_2026.html
   ```
2. O programa vai mostrar um relatório na tela terminando com:
   ```
   [SUCESSO] TESTE PASSOU COM 100% DE COBERTURA E INTEGRIDADE!
   ```

> Nota: alguns acentos podem aparecer estranhos no terminal (como `�`) — é só um detalhe visual do PowerShell, não afeta o resultado do teste.

---

## 🌐 Passo 6: Ver o Painel Web Visual no Navegador

1. No terminal, digite:
   ```powershell
   python -m app.web.routes
   ```
2. Vão aparecer várias linhas de texto, incluindo algo como:
   ```
   * Running on http://127.0.0.1:5000
   ```
   Isso quer dizer que o painel está "ligado" e esperando você acessá-lo.
3. Abra seu navegador (Chrome, Edge, etc.) e digite no topo, onde ficam os endereços de sites:
   ```
   http://localhost:5000
   ```
   e aperte **ENTER**.
4. Você verá o painel escuro com os indicadores do sistema, já conectado ao banco de dados real (Passo 7). Os números começam zerados até você rodar uma descoberta/importação dos e-mails (comando `backfill`, explicado no `README.md`).
5. **Para fechar o painel:** volte para a janela do terminal e aperte **Ctrl + C**. Se pedir confirmação, digite `S` e **ENTER**.

---

## 🗄️ Passo 7: Banco de Dados PostgreSQL (já configurado neste computador)

Este computador já tinha o **PostgreSQL 18** instalado e rodando como serviço do Windows. O banco `smartfit_db` e todas as 5 tabelas necessárias já foram criados, usando a senha padrão que estava no `.env` (`DB_PASSWORD=postgres`).

Se um dia precisar recriar as tabelas (por exemplo, depois de apagar o banco), rode:
```powershell
python -m app.cli init-db
```

Se quiser conferir as tabelas manualmente, pode abrir o **pgAdmin** (instalado junto com o PostgreSQL) e procurar pelo banco `smartfit_db`.

---

## 🔑 Passo 8 (Opcional): Conectar a uma conta real de e-mail (IMAP + Senha de App)

Só necessário se você quiser que o programa busque e-mails de verdade da caixa de entrada. **Não precisa de Google Cloud nem de projetos complicados** — só uma "Senha de App".

1. Acesse, no navegador, **logado na conta que recebe os relatórios da Smart Fit**:
   ```
   https://myaccount.google.com/apppasswords
   ```
2. Dê um nome para a aplicação (por exemplo `Python ETL Smartfit`) e clique em **Criar**.
3. O Google vai mostrar uma senha de **16 letras** (algo como `abcd efgh ijkl mnop`). Copie essa senha.
4. Abra o arquivo `.env`, na pasta do projeto, com o **Bloco de Notas** e preencha estas linhas:
   ```ini
   IMAP_USER=seuemail@suaempresa.com
   IMAP_APP_PASSWORD=asenhagerada
   ```
   *(Pode colar a senha com ou sem espaços — o programa entende dos dois jeitos. Salve o arquivo com `Ctrl+S`.)*
5. No terminal (lembre de ativar o ambiente — Passo 3, item 3 — se abriu um terminal novo), rode:
   ```powershell
   python -m app.cli setup-gmail
   ```
6. O programa vai testar a conexão e mostrar `[OK] Conexão IMAP validada com sucesso.`. Em seguida ele pergunta o remetente e o assunto dos relatórios — pode apertar **ENTER** para aceitar os valores sugeridos, ou digitar os seus.

> ⚠️ A Senha de App é um dado sensível, equivalente a uma senha da sua conta. Guarde-a apenas no `.env` deste computador e não a compartilhe por e-mail, chat ou mensagens.

---

## 📋 Passo 9: Conferir os Dados Capturados numa Planilha Excel

Depois de processar e-mails (Passo 8 + `backfill`), você pode gerar uma planilha para conferir manualmente se todas as unidades e colunas foram capturadas corretamente:

```powershell
python -m app.cli export-xlsx
```

O arquivo é salvo em `exports\dados_capturados.xlsx` (abra normalmente com o Excel). Ele tem 3 abas: **Resumo** (contagens), **Unidades** (todas as unidades do formato padrão, com todas as colunas do e-mail) e **Pré-vendas** (unidades ainda não inauguradas).

---

## 📉 Passo 10 (Opcional): Previsão de Risco de Cancelamento

Este é um módulo avançado que tenta prever quais unidades correm risco de ter mais cancelamentos no mês seguinte. Só funciona depois de já ter alguns meses de e-mails processados (Passo 8 + `backfill`).

1. Instale os componentes extras (só precisa fazer isso uma vez):
   ```powershell
   pip install -r requirements-ml.txt
   ```
2. Treine o modelo:
   ```powershell
   python -m app.cli train-churn-model
   ```
3. Abra o painel visual:
   ```powershell
   streamlit run app/ml/streamlit_app.py
   ```
   Acesse `http://localhost:8501` no navegador. Ele também aparece como um botão "📉 Previsão de Cancelamento" no painel principal (`http://localhost:5000`).

---

## 📊 Passo 11 (Opcional): Painel de Comparação entre Unidades (estilo Power BI)

Este painel permite comparar várias unidades ou uma unidade contra a média da região dela, com gráficos de tendência — sem precisar programar nada.

1. Abra o Docker Desktop (se não estiver aberto).
2. No terminal, na pasta do projeto, rode:
   ```powershell
   docker compose up -d
   ```
3. Acesse `http://localhost:3000` no navegador. Da primeira vez, crie sua conta de administrador do painel.
4. Ele também aparece como o botão "📊 Painel Analítico (BI)" no painel principal (`http://localhost:5000`).
5. Dentro do painel, escolha o dashboard **"Comparacao entre Unidades"** e use o filtro no topo para escolher 2 ou mais unidades — o gráfico se atualiza sozinho.

---

## 🆘 Problemas Comuns

| O que aconteceu | O que fazer |
|---|---|
| `python não é reconhecido como comando` | O Python não está instalado ou não está no PATH. Me avise para instalarmos juntos. |
| Erro sobre "política de execução" ao ativar o `venv` | Rode o comando `Set-ExecutionPolicy` do Passo 3, item 2. |
| `(venv)` não aparece antes do caminho no terminal | O ambiente não foi ativado. Rode de novo `.\venv\Scripts\activate` dentro da pasta do projeto. |
| Painel web mostra tudo zerado | Normal antes de rodar a primeira descoberta/importação de e-mails (comando `backfill`). |
| Quero rodar o painel de novo depois de já ter fechado | Repita o Passo 6. Não precisa reinstalar nada (Passos 2 e 3 já feitos ficam salvos). |
| Erro de login IMAP (autenticação falhou) | Confira se o e-mail em `IMAP_USER` está certo e gere uma nova Senha de App em [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), colando o novo valor em `IMAP_APP_PASSWORD` no `.env`. |

---

## 📋 Resumo rápido (depois da primeira vez)

Depois de fazer os Passos 1 a 3 uma vez, nas próximas vezes que quiser testar basta:

```powershell
cd C:\Users\ralan\programa\Analise
.\venv\Scripts\activate
python -m pytest -q
python -m app.web.routes
```
