import re
from bs4 import BeautifulSoup
from app.etl.parser import table_to_grid, get_header_rows_count, get_column_headers, normalize_str, map_header_to_field
from app.etl.normalizer import parse_int, normalize_pre_venda_data

def scan_raw_html(html_content):
    """Varre o HTML de forma direta (crua), sem filtros de negócio, para mapeamento."""
    soup = BeautifulSoup(html_content, 'lxml')
    tables = soup.find_all('table')
    
    scan_result = {
        'regions': set(),
        'columns': [],
        'total_units': 0,
        'total_pre_venda': 0,
        'sales_checksum': 0
    }
    
    # Identifica as regiões do HTML
    elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div'])
    for el in elements:
        text = el.get_text(strip=True)
        norm_text = normalize_str(text)
        if any(k in norm_text for k in ['brasil', 'franquia', 'digital', 'regional']) or (len(text) > 0 and len(text) < 40 and el.name in ['h1', 'h2', 'h3']):
            # Limpa para comparar com o parser oficial
            from app.etl.parser import extract_region_name
            scan_result['regions'].add(extract_region_name(text))
            
    for table in tables:
        matrix = table_to_grid(table)
        if not matrix:
            continue
            
        h_count = get_header_rows_count(matrix)
        if h_count == 0:
            continue
            
        col_headers = get_column_headers(matrix, h_count)
        
        # Classifica tabela
        mapped_fields = [map_header_to_field(h) for h in col_headers]
        is_main = 'sigla' in mapped_fields or 'total_ativos' in mapped_fields
        is_cancel = any(f and 'cancelamento' in f for f in mapped_fields) or 'transferencias_liquida_mes' in mapped_fields
        is_pre_venda = 'codigo_unidade' in mapped_fields and not is_main and not is_cancel

        if not (is_main or is_cancel or is_pre_venda):
            continue

        table_type = 'main' if is_main else ('cancel' if is_cancel else 'pre_venda')
        for h in col_headers:
            scan_result['columns'].append({
                'header': h,
                'table_type': table_type
            })

        # Contagem de linhas e checksum de vendas
        for r_idx in range(h_count, len(matrix)):
            row_cells = matrix[r_idx]

            # Valida se a linha tem dados de unidade
            row_text = " ".join(cell.get_text() for cell in row_cells if cell)
            if not row_text.strip():
                continue

            # Verifica se pelo menos o nome ou a sigla/código está preenchido
            has_identity = False
            for c_idx, cell in enumerate(row_cells):
                field = mapped_fields[c_idx]
                if field in ['sigla', 'nome_digital', 'codigo_unidade', 'nome_unidade'] and cell.get_text(strip=True):
                    has_identity = True
                    break

            if not has_identity:
                continue

            def _cell_text(field_name):
                idx = mapped_fields.index(field_name) if field_name in mapped_fields else None
                return row_cells[idx].get_text(strip=True) if idx is not None and row_cells[idx] else ''

            if is_pre_venda:
                # Ignora linhas de subtotal ("-" na unidade, ou nome "Total")
                if _cell_text('codigo_unidade').strip() == '-' or normalize_str(_cell_text('nome_unidade')) == 'total':
                    continue
                scan_result['total_pre_venda'] += 1
            elif is_main:
                # Ignora linhas de subtotal ("-" na sigla, ou nome "Total") ao fim de cada região
                nome_para_checar = _cell_text('nome_digital') or _cell_text('nome_unidade')
                if _cell_text('sigla').strip() == '-' or normalize_str(nome_para_checar) == 'total':
                    continue
                scan_result['total_units'] += 1

            # Soma checksum de vendas para colunas com vendas
            for c_idx, cell in enumerate(row_cells):
                if cell is None:
                    continue
                header = col_headers[c_idx]
                norm_header = normalize_str(header)
                if 'vendas' in norm_header or 'venda' in norm_header:
                    val_str = cell.get_text(strip=True)
                    scan_result['sales_checksum'] += parse_int(val_str)
                    
    return scan_result

def run_coverage_report(html_content):
    """Executa o relatório de cobertura comparando o scanner cru com o parser oficial."""
    # 1. Executa o scanner cru
    raw = scan_raw_html(html_content)
    
    # 2. Executa o parser oficial
    from app.etl.parser import parse_html
    from app.etl.normalizer import normalize_unit_data, normalize_cancel_data
    
    parsed = parse_html(html_content)
    
    # Consolida os dados do parser
    parsed_units_count = 0
    parsed_pre_venda_count = 0
    parsed_sales_checksum = 0
    parsed_regions = set(parsed.keys())

    # Analisa campos mapeados
    captured_fields = []
    unmapped_fields = []
    expected_missing = []

    for col in raw['columns']:
        header = col['header']
        field = map_header_to_field(header)
        if field:
            captured_fields.append((header, field))
        else:
            unmapped_fields.append(header)

    for region, data in parsed.items():
        parsed_units_count += len(data['main_rows'])

        for row in data['main_rows']:
            norm = normalize_unit_data(row)
            parsed_sales_checksum += norm.get('vendas_geral_dia', 0)
            parsed_sales_checksum += norm.get('vendas_geral_mes', 0)
            for k, val in norm.get('vendas_detalhe', {}).items():
                parsed_sales_checksum += val

        for row in data.get('pre_venda_rows', []):
            norm = normalize_pre_venda_data(row)
            parsed_pre_venda_count += 1
            parsed_sales_checksum += norm.get('vendas_total', 0)
            for k, val in norm.get('vendas_detalhe', {}).items():
                parsed_sales_checksum += val

    # Verifica divergências
    report = {
        'regions_raw': list(raw['regions']),
        'regions_parsed': list(parsed_regions),
        'units_raw': raw['total_units'],
        'units_parsed': parsed_units_count,
        'pre_venda_raw': raw['total_pre_venda'],
        'pre_venda_parsed': parsed_pre_venda_count,
        'checksum_raw': raw['sales_checksum'],
        'checksum_parsed': parsed_sales_checksum,
        'captured_fields': captured_fields,
        'unmapped_fields': unmapped_fields,
        'coverage_pct': 0.0
    }
    
    total_cols = len(raw['columns'])
    if total_cols > 0:
        report['coverage_pct'] = ((total_cols - len(unmapped_fields)) / total_cols) * 100.0
        
    return report
