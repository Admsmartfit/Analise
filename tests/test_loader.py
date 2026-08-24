import os
from datetime import date
from unittest.mock import MagicMock
from app.etl.parser import parse_html
from app.etl.loader import load_parsed_data

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "tests", "fixtures", "smartfit_email_2026.html")

def test_loader_idempotency_calls():
    # Carrega dados do fixture
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
    parsed_data = parse_html(html_content)
    
    # Mock do cursor e da conexão
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    
    # Simula o retorno de IDs do banco (RETURNING id)
    # Temos 2 unidades no total (Paulista e Berrini)
    # Cada uma retorna:
    # 1. id de dim_unidade (ex: 10, 11)
    # 2. id de fato_metricas_diarias (ex: 100, 101)
    mock_cur.fetchone.side_effect = [
        (10,),  # dim_unidade Paulista
        (100,), # fato_metricas_diarias Paulista
        (11,),  # dim_unidade Berrini
        (101,), # fato_metricas_diarias Berrini
    ]
    
    # Executa a carga
    ref_date = date(2026, 8, 20)
    msg_id = "test_message_123"
    load_parsed_data(mock_conn, parsed_data, ref_date, msg_id)
    
    # Valida se commit foi chamado
    mock_conn.commit.assert_called_once()
    
    # Valida chamadas executadas no cursor
    execute_calls = mock_cur.execute.call_args_list
    assert len(execute_calls) > 4
    
    # Verifica se os inserts para as tabelas principais foram feitos com parâmetros corretos
    dim_unidade_calls = [call for call in execute_calls if "INSERT INTO dim_unidade" in call[0][0]]
    assert len(dim_unidade_calls) == 2
    
    # Primeiro insert (Paulista) — colunas: nome_digital, pais, sigla_atual, regiao_uf, tipo_operacao, data_inauguracao
    args_p = dim_unidade_calls[0][0][1]
    assert args_p[0] == "Paulista"
    assert args_p[1] == "Brasil"  # país extraído do texto da região ("Brasil - SP" -> "Brasil"), não da sigla
    assert args_p[2] == "SP01"
    assert args_p[3] == "Brasil - SP"
    assert args_p[4] == "Própria"

    # Segundo insert (Berrini)
    args_b = dim_unidade_calls[1][0][1]
    assert args_b[0] == "Berrini"
    assert args_b[1] == "Brasil"
    assert args_b[2] == "SP02"
    assert args_b[3] == "Brasil - SP"
    assert args_b[4] == "Própria"
    
    fato_calls = [call for call in execute_calls if "INSERT INTO fato_metricas_diarias" in call[0][0]]
    assert len(fato_calls) == 2
    
    # Verifica vendas Paulista
    vendas_calls_p = [call for call in execute_calls if "INSERT INTO fato_vendas_detalhada" in call[0][0] and call[0][1][0] == 100]
    # Balcao, Web, Totem, Outros x Smart, Black, Fit, Black+, Studio = 20 combinações
    assert len(vendas_calls_p) == 20
    
    # Verifica cancelamentos Paulista
    cancel_calls_p = [call for call in execute_calls if "INSERT INTO fato_cancelamentos_detalhada" in call[0][0] and call[0][1][0] == 100]
    # Smart, Black, Studio, Total = 4 planos
    assert len(cancel_calls_p) == 4
    
    print("✅ Loader executou todas as chamadas SQL esperadas com sucesso.")
stream = None
