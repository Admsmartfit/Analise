import os
import configparser
from app.auth.gmail_client import GmailClient, IMAP_USER, IMAP_APP_PASSWORD

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.ini")


def print_prerequisites():
    instructions = """
========================================================================
        PRE-REQUISITOS - SENHA DE APP DO GMAIL / GOOGLE WORKSPACE
========================================================================
Para conectar via IMAP (sem precisar de projeto no Google Cloud), gere
uma "Senha de App" na conta que recebe os relatórios da Smart Fit:

1. Acesse https://myaccount.google.com/apppasswords logado nessa conta.
2. Dê um nome para a aplicação (ex.: 'Python ETL Smartfit').
3. O Google vai gerar uma senha de 16 caracteres.
4. Abra o arquivo .env na pasta do projeto e preencha:
   IMAP_USER=seuemail@suaempresa.com
   IMAP_APP_PASSWORD=asenhagerada (sem espaços)
5. Rode este assistente novamente: python -m app.cli setup-gmail
========================================================================
"""
    print(instructions)


def setup_gmail_flow(interactive=True):
    if not IMAP_USER or not IMAP_APP_PASSWORD:
        print_prerequisites()
        return False

    print("[IMAP] Testando conexão com o servidor de e-mail...")
    try:
        client = GmailClient()
        client.close()
        print(f"[OK] Conexão IMAP validada com sucesso. Conta: {IMAP_USER}")
    except Exception as e:
        print(f"[ERRO] Falha no teste de conexão IMAP: {e}")
        return False

    if interactive:
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_PATH):
            config.read(CONFIG_PATH)

        if 'gmail' not in config:
            config['gmail'] = {}

        default_sender = config['gmail'].get('sender', 'no-reply@smartfit.com.br')
        default_subject = config['gmail'].get('subject', 'Relatório Diário')

        print("\n--- Configuração de Filtros de Busca ---")
        sender = input(f"Digite o remetente dos relatórios [{default_sender}]: ").strip()
        subject = input(f"Digite o assunto padrão ou palavra-chave [{default_subject}]: ").strip()

        config['gmail']['sender'] = sender if sender else default_sender
        config['gmail']['subject'] = subject if subject else default_subject

        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        print("[OK] Filtros salvos em config/config.ini.")

    return True


if __name__ == '__main__':
    setup_gmail_flow()
