import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "smartfit_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

def get_connection():
    """Retorna uma nova conexão com o banco de dados PostgreSQL."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def init_db():
    """Executa o script schema.sql para inicializar o banco de dados."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Arquivo schema.sql não encontrado em {schema_path}")
        
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)
        conn.commit()
        print("[OK] Banco de dados inicializado/verificado com sucesso.")
    except Exception as e:
        conn.rollback()
        print(f"[ERRO] Erro ao inicializar o banco de dados: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
