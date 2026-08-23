import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER")
IMAP_APP_PASSWORD = os.getenv("IMAP_APP_PASSWORD")
IMAP_MAILBOX = os.getenv("IMAP_MAILBOX", "INBOX")


def _decode_header_value(raw_value):
    """Decodifica um cabeçalho de e-mail (Subject/Date) que pode vir em partes codificadas."""
    if not raw_value:
        return None
    parts = decode_header(raw_value)
    decoded = ""
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded += text.decode(charset or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


class GmailClient:
    """Cliente de e-mail via IMAP + Senha de App (sem necessidade de Google Cloud/OAuth)."""

    def __init__(self):
        if not IMAP_USER or not IMAP_APP_PASSWORD:
            raise ValueError(
                "IMAP_USER e IMAP_APP_PASSWORD precisam estar configurados no arquivo .env. "
                "Gere uma Senha de App em myaccount.google.com/apppasswords."
            )
        self.conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        self.conn.login(IMAP_USER, IMAP_APP_PASSWORD)
        self.conn.select(IMAP_MAILBOX)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            self.conn.logout()
        except Exception:
            pass

    def list_messages(self, query="", page_token=None, max_results=100):
        """Busca UIDs de mensagens que correspondem aos critérios IMAP (query) e pagina o resultado."""
        criteria = query if query else "ALL"
        status, data = self.conn.uid('search', None, criteria)
        if status != 'OK':
            raise RuntimeError(f"Falha ao buscar e-mails via IMAP: {status}")

        all_uids = data[0].split() if data and data[0] else []

        offset = int(page_token) if page_token else 0
        page_uids = all_uids[offset:offset + max_results]
        next_offset = offset + max_results
        next_page_token = str(next_offset) if next_offset < len(all_uids) else None

        messages = [{'id': uid.decode('ascii')} for uid in page_uids]
        return messages, next_page_token

    def get_message(self, message_id):
        """Recupera a mensagem completa (objeto email.message.Message) por UID."""
        status, data = self.conn.uid('fetch', message_id, '(RFC822)')
        if status != 'OK' or not data or data[0] is None:
            raise RuntimeError(f"Não foi possível buscar o e-mail com UID {message_id}.")
        raw_email = data[0][1]
        return email.message_from_bytes(raw_email)

    def extract_html_payload(self, message):
        """Extrai o conteúdo HTML (corpo) de uma mensagem de e-mail."""
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == 'text/html' and not part.get('Content-Disposition'):
                    charset = part.get_content_charset() or 'utf-8'
                    return part.get_payload(decode=True).decode(charset, errors='replace')
            return None
        else:
            if message.get_content_type() == 'text/html':
                charset = message.get_content_charset() or 'utf-8'
                return message.get_payload(decode=True).decode(charset, errors='replace')
            return None

    def get_message_date(self, message):
        """Extrai a data do cabeçalho da mensagem."""
        return message.get('Date')

    def get_message_subject(self, message):
        """Extrai o assunto do cabeçalho da mensagem."""
        subject = _decode_header_value(message.get('Subject'))
        return subject if subject else "Sem Assunto"
