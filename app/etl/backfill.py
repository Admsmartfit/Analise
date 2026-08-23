import os
import re
import sys
import logging
import traceback
import configparser
from datetime import datetime
from app.auth.gmail_client import GmailClient
from app.etl.parser import parse_html
from app.etl.loader import load_parsed_data
from app.etl.normalizer import parse_date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.ini")
COVERAGE_PASSED_PATH = os.path.join(BASE_DIR, "logs", ".coverage_passed")
LOG_PATH = os.path.join(BASE_DIR, "logs", "etl.log")

# Configura o Logger
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("etl_logger")

def check_coverage_passed():
    """Verifica se o teste de cobertura passou (carimbo em logs/.coverage_passed)."""
    return os.path.exists(COVERAGE_PASSED_PATH)

def process_single_email(conn, client, msg_id):
    """Obtém, parseia, normaliza e persiste os dados de um único e-mail."""
    # Busca mensagem no Gmail
    msg = client.get_message(msg_id)
    
    # Obtém data do e-mail
    raw_date = client.get_message_date(msg)
    parsed_date = parse_date(raw_date) if raw_date else None
    
    # Extrai o HTML
    html = client.extract_html_payload(msg)
    if not html:
        raise ValueError(f"E-mail {msg_id} não possui corpo HTML.")
        
    # Executa parser
    parsed_data = parse_html(html)
    if not parsed_data:
        raise ValueError(f"Parser não encontrou nenhuma tabela no e-mail {msg_id}.")
        
    # Data de referência padrão do relatório (se não achar na data do e-mail, tenta do assunto)
    # Geralmente, a data do e-mail representa a data em que o relatório foi gerado.
    if not parsed_date:
        # Tenta extrair do assunto (ex: "Relatório Diário - 20/08/2026")
        subject = client.get_message_subject(msg)
        match = re.search(r'(\d{2}/\d{2}/\d{4})', subject)
        if match:
            parsed_date = parse_date(match.group(1))
            
    if not parsed_date:
        parsed_date = datetime.now().date()
        
    # Persiste no banco de dados (Loader realiza commit)
    load_parsed_data(conn, parsed_data, parsed_date, msg_id)
    return parsed_date

def run_backfill(conn, client, limit=None):
    """Executa o processamento em lote de todos os e-mails marcados como pendentes ou com erro."""
    if not check_coverage_passed():
        print("\n[ERRO] BLOQUEIO: O teste de cobertura de campos (--test-coverage) não foi executado ou falhou.")
        print("   Você precisa rodar 'python -m app.cli test-coverage' com sucesso antes de iniciar o backfill.\n")
        sys.exit(1)
        
    # Lê tamanho do lote
    config = configparser.ConfigParser()
    batch_size = 50
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
        if 'etl' in config:
            batch_size = config['etl'].getint('batch_size', batch_size)
            
    if limit:
        batch_size = limit
        
    # Busca e-mails pendentes ou com erro
    with conn.cursor() as cur:
        cur.execute("""
            SELECT gmail_message_id, tentativas
            FROM controle_backfill
            WHERE status IN ('pendente', 'erro')
            ORDER BY id ASC
            LIMIT %s;
        """, (batch_size,))
        emails = cur.fetchall()
        
    if not emails:
        logger.info("[INFO] Nenhum e-mail pendente para processar.")
        return 0, 0
        
    logger.info(f"[ETL] Iniciando lote de backfill para {len(emails)} e-mails...")
    
    success_count = 0
    fail_count = 0
    
    for msg_id, tentativas in emails:
        logger.info(f"[ETL] Processando e-mail ID: {msg_id} (Tentativa {tentativas + 1})...")
        try:
            # Processa e persiste (loader comita)
            email_date = process_single_email(conn, client, msg_id)
            
            # Atualiza controle de backfill como processado
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE controle_backfill
                    SET status = 'processado',
                        data_email = %s,
                        tentativas = %s,
                        ultimo_erro = NULL,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE gmail_message_id = %s;
                """, (email_date, tentativas + 1, msg_id))
            conn.commit()
            success_count += 1
            logger.info(f"[OK] E-mail {msg_id} processado com sucesso. Data: {email_date}.")
            
        except Exception as e:
            conn.rollback()
            fail_count += 1
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"[ERRO] Erro ao processar e-mail {msg_id}: {e}")
            
            # Atualiza controle com status de erro
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE controle_backfill
                        SET status = 'erro',
                            tentativas = %s,
                            ultimo_erro = %s,
                            atualizado_em = CURRENT_TIMESTAMP
                        WHERE gmail_message_id = %s;
                    """, (tentativas + 1, err_msg, msg_id))
                conn.commit()
            except Exception as db_err:
                logger.error(f"[ALERTA] Erro ao atualizar status de erro no banco: {db_err}")
                conn.rollback()
                
    logger.info(f"[ETL] Lote finalizado. Sucesso: {success_count} | Erro: {fail_count}.")
    return success_count, fail_count
