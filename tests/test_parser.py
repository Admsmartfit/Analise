import os
from app.etl.parser import parse_html
from app.etl.normalizer import normalize_unit_data, normalize_cancel_data

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "tests", "fixtures", "smartfit_email_2026.html")

def test_parse_and_normalize():
    assert os.path.exists(FIXTURE_PATH), f"Fixture not found at {FIXTURE_PATH}"
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    parsed_data = parse_html(html_content)
    
    # 1. Verifica se a região 'Brasil - SP' foi identificada
    assert "Brasil - SP" in parsed_data
    region_data = parsed_data["Brasil - SP"]
    
    assert len(region_data["main_rows"]) == 2
    assert len(region_data["cancel_rows"]) == 2
    
    # 2. Testa a Unidade Paulista (main table)
    paulista_raw = region_data["main_rows"][0]
    paulista = normalize_unit_data(paulista_raw)
    
    assert paulista["sigla"] == "SP01"
    assert paulista["nome_digital"] == "Paulista"
    assert paulista["unidade_imatura"] is False
    assert paulista["total_ativos"] == 3500
    assert paulista["ativos_smart"] == 1000
    assert paulista["ativos_black"] == 1500
    assert paulista["ativos_fit"] == 500
    assert paulista["ativos_black_plus"] == 300
    assert paulista["ativos_studio"] == 100
    assert paulista["bloqueados"] == 100
    assert paulista["visitas_dia"] == 250
    assert paulista["visitas_mes"] == 6200
    assert paulista["conversao_dia"] == 8.5
    assert paulista["conversao_mes"] == 9.2
    assert paulista["vendas_geral_dia"] == 47
    assert paulista["vendas_geral_mes"] == 1155
    
    # Verifica vendas detalhadas
    vendas = paulista["vendas_detalhe"]
    assert vendas["venda_detalhe|balcao|smart|dia"] == 5
    assert vendas["venda_detalhe|balcao|smart|mes"] == 120
    assert vendas["venda_detalhe|web|black|dia"] == 12
    assert vendas["venda_detalhe|web|black|mes"] == 300
    assert vendas["venda_detalhe|totem|studio|dia"] == 0
    assert vendas["venda_detalhe|totem|studio|mes"] == 2
    
    # 3. Testa a Unidade Berrini (unidade imatura e valores nulos)
    berrini_raw = region_data["main_rows"][1]
    berrini = normalize_unit_data(berrini_raw)
    
    assert berrini["sigla"] == "SP02"
    assert berrini["nome_digital"] == "Berrini"
    assert berrini["unidade_imatura"] is True
    assert berrini["conversao_dia"] is None # '-' deve virar None
    assert berrini["conversao_mes"] == 5.4
    
    # 4. Testa cancelamentos e transferências
    paulista_cancel_raw = region_data["cancel_rows"][0]
    paulista_cancel = normalize_cancel_data(paulista_cancel_raw)
    
    assert paulista_cancel["nome_digital"] == "Paulista"
    assert paulista_cancel["transferencias_liquida_mes"] == -12.50
    assert paulista_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|smart"] == 15
    assert paulista_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|black"] == 25
    assert paulista_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|studio"] == 2
    assert paulista_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|total"] == 42
    
    berrini_cancel_raw = region_data["cancel_rows"][1]
    berrini_cancel = normalize_cancel_data(berrini_cancel_raw)
    
    assert berrini_cancel["nome_digital"] == "Berrini"
    assert berrini_cancel["transferencias_liquida_mes"] == 4.00
    assert berrini_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|smart"] == 5
    assert berrini_cancel["cancelamentos_detalhe"]["cancelamento_detalhe|total"] == 8
