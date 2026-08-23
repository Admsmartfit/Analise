import os
from app.etl.raw_headers_scanner import run_coverage_report

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "tests", "fixtures", "smartfit_email_2026.html")

def test_coverage_report():
    assert os.path.exists(FIXTURE_PATH)
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    report = run_coverage_report(html_content)
    
    # Validações do relatório de cobertura
    assert len(report["unmapped_fields"]) == 0
    assert report["coverage_pct"] == 100.0
    assert report["units_raw"] == 2
    assert report["units_parsed"] == 2
    
    # Checksum de vendas
    # Na Paulista: 
    # Vendas Total Dia: 47, Total Mes: 1155, e a soma das 20 sub-colunas:
    # 5+120 + 10+250 + 2+50 + 1+30 + 0+10 + 8+180 + 12+300 + 3+70 + 2+40 + 1+15 + 1+20 + 2+40 + 0+10 + 0+5 + 0+2 + 0+5 + 0+10 + 0+2 + 0+1 + 0+0 = 1204
    # Soma total vendas Paulista = 47 + 1155 + 1204 = 2406
    # Na Berrini:
    # Vendas Total Dia: 11, Total Mes: 248, sub-colunas:
    # 1+20 + 2+40 + 0+5 + 0+2 + 0+1 + 3+60 + 4+80 + 0+10 + 0+4 + 0+2 + 0+5 + 1+15 + 0+1 + 0+0 + 0+0 + 0+1 + 0+2 + 0+0 + 0+0 + 0+0 = 257
    # Soma total vendas Berrini = 11 + 248 + 257 = 516
    # Checksum total = 2406 + 516 = 2922
    assert report["checksum_raw"] == report["checksum_parsed"]
    print(f"Checksum raw: {report['checksum_raw']}, parsed: {report['checksum_parsed']}")
