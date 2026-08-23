import os
import configparser
from app.auth.gmail_client import GmailClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.ini")

def get_email_filters():
    """Lê os filtros de busca (remetente e assunto) de config.ini."""
    config = configparser.ConfigParser()
    sender = "no-reply@smartfit.com.br"
    subject = "Relatório Diário"

    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
        if 'gmail' in config:
            sender = config['gmail'].get('sender', sender)
            subject = config['gmail'].get('subject', subject)

    return sender, subject

def discover_new_emails(conn, client):
    """Busca todas as mensagens que correspondem aos filtros via IMAP e as

    registra na tabela 'controle_backfill' como pendentes.
    """
    sender, subject_filter = get_email_filters()
    # IMAP SEARCH exige critérios em ASCII; o remetente é filtrado no servidor
    # e o assunto (que pode ter acentos) é conferido depois, em Python.
    criteria = f'FROM "{sender}"'
    print(f"[EMAIL] Buscando e-mails via IMAP com o critério: {criteria}")

    messages = []
    page_token = None

    while True:
        try:
            batch_messages, page_token = client.list_messages(query=criteria, page_token=page_token)
            messages.extend(batch_messages)
            print(f"   Encontradas {len(messages)} mensagens até agora...")
            if not page_token:
                break
        except Exception as e:
            print(f"[ERRO] Erro ao listar e-mails via IMAP: {e}")
            raise e

    if subject_filter:
        filtered = []
        for msg in messages:
            try:
                full_msg = client.get_message(msg['id'])
                msg_subject = client.get_message_subject(full_msg) or ""
                if subject_filter.lower() in msg_subject.lower():
                    filtered.append(msg)
            except Exception as e:
                print(f"[ALERTA] Não foi possível checar o assunto do e-mail {msg['id']}: {e}")
        messages = filtered

    # Grava no controle de backfill
    new_discovered = 0
    with conn.cursor() as cur:
        for msg in messages:
            msg_id = msg['id']
            # Se o ID já existir, ON CONFLICT faz nada
            cur.execute("""
                INSERT INTO controle_backfill (gmail_message_id, status)
                VALUES (%s, 'pendente')
                ON CONFLICT (gmail_message_id) DO NOTHING;
            """, (msg_id,))
            if cur.rowcount > 0:
                new_discovered += 1
                
    conn.commit()
    print(f"[OK] Varredura concluída. Total de e-mails na caixa: {len(messages)}. Novos registrados: {new_discovered}.")
    return new_discovered, len(messages)
