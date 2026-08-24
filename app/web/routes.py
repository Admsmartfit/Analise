import os
from flask import Flask, render_template, redirect, url_for, flash, request
from app.db.database import get_connection
from app.auth.gmail_client import GmailClient
from app.etl.backfill import process_single_email

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "smartfit-etl-secret-key-12345")

STREAMLIT_PORT = os.getenv("STREAMLIT_PORT", "8501")
STREAMLIT_URL = f"http://localhost:{STREAMLIT_PORT}"

METABASE_PORT = os.getenv("METABASE_PORT", "3000")
METABASE_URL = f"http://localhost:{METABASE_PORT}"

def get_db_stats():
    """Busca as estatísticas gerais do controle de backfill no banco."""
    stats = {'total': 0, 'pendente': 0, 'processado': 0, 'erro': 0, 'success_rate': 100.0}
    latest_errors = []

    try:
        conn = get_connection()
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return stats, latest_errors

    try:
        with conn.cursor() as cur:
            # Conta por status
            cur.execute("""
                SELECT status, COUNT(*) 
                FROM controle_backfill 
                GROUP BY status;
            """)
            rows = cur.fetchall()
            for status, count in rows:
                if status in stats:
                    stats[status] = count
            
            stats['total'] = sum(count for status, count in rows)
            
            if stats['total'] > 0:
                stats['success_rate'] = (stats['processado'] / stats['total']) * 100.0
                
            # Busca as últimas falhas
            cur.execute("""
                SELECT gmail_message_id, data_email, tentativas, ultimo_erro, atualizado_em
                FROM controle_backfill
                WHERE status = 'erro'
                ORDER BY atualizado_em DESC
                LIMIT 10;
            """)
            error_rows = cur.fetchall()
            for r in error_rows:
                latest_errors.append({
                    'message_id': r[0],
                    'date': r[1].strftime('%d/%m/%Y') if r[1] else 'N/A',
                    'attempts': r[2],
                    'error': r[3],
                    'updated_at': r[4].strftime('%d/%m/%Y %H:%M:%S') if r[4] else 'N/A'
                })
    except Exception as e:
        print(f"Erro ao buscar estatísticas do banco: {e}")
    finally:
        conn.close()
        
    return stats, latest_errors

@app.route('/')
def index():
    stats, latest_errors = get_db_stats()
    return render_template('index.html', stats=stats, latest_errors=latest_errors, streamlit_url=STREAMLIT_URL, metabase_url=METABASE_URL)

@app.route('/reprocess/<message_id>', methods=['POST'])
def reprocess(message_id):
    """Executa o processamento forçado de um único e-mail pelo seu message_id."""
    conn = get_connection()
    try:
        client = GmailClient()
        email_date = process_single_email(conn, client, message_id)
        
        # Atualiza o status no banco
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE controle_backfill
                SET status = 'processado',
                    data_email = %s,
                    ultimo_erro = NULL,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE gmail_message_id = %s;
            """, (email_date, message_id))
        conn.commit()
        flash(f"Sucesso: E-mail {message_id} reprocessado com sucesso! Data: {email_date}.", "success")
    except Exception as e:
        conn.rollback()
        err_msg = str(e)
        # Registra o erro no banco
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE controle_backfill
                    SET status = 'erro',
                        tentativas = tentativas + 1,
                        ultimo_erro = %s,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE gmail_message_id = %s;
                """, (err_msg, message_id))
            conn.commit()
        except Exception:
            conn.rollback()
        flash(f"Erro ao reprocessar e-mail {message_id}: {err_msg}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('index'))

@app.route('/reset-status/<message_id>', methods=['POST'])
def reset_status(message_id):
    """Reseta o status de um e-mail para pendente."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE controle_backfill
                SET status = 'pendente',
                    ultimo_erro = NULL
                WHERE gmail_message_id = %s;
            """, (message_id,))
        conn.commit()
        flash(f"Status do e-mail {message_id} resetado para pendente.", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao resetar status: {e}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug)
