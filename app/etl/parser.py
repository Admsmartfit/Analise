import re
import unicodedata
from bs4 import BeautifulSoup

def normalize_str(s):
    if not s:
        return ""
    # Lowercase, remove accents, strip spaces
    s = s.strip().lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s)
    return s

def extract_region_name(text):
    """Extrai o nome estável da região a partir de um título (ex: 'Transferências - Brasil - SP' -> 'Brasil - SP')."""
    norm = normalize_str(text)
    
    # Procura por "brasil - xx" (onde xx é a sigla do estado de 2 ou 3 letras)
    match = re.search(r'brasil\s*-\s*([a-z]{2,3})', norm)
    if match:
        uf = match.group(1).upper()
        return f"Brasil - {uf}"
        
    for k in ['franquia', 'digital', 'regional']:
        if k in norm:
            return k.capitalize()
            
    # Fallback para o texto original limpo
    return text.strip()

def table_to_grid(table):
    """Converte uma tabela HTML em uma matriz 2D de elementos BeautifulSoup, 

    copiando valores de células que possuem rowspan ou colspan.
    """
    rows = table.find_all('tr')
    grid = {}
    r_idx = 0
    for row in rows:
        c_idx = 0
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        for cell in cells:
            # Encontra a próxima coluna vazia na linha atual
            while (r_idx, c_idx) in grid:
                c_idx += 1
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            for dr in range(rowspan):
                for dc in range(colspan):
                    grid[(r_idx + dr, c_idx + dc)] = cell
            c_idx += colspan
        r_idx += 1
        
    if not grid:
        return []
        
    max_r = max(coord[0] for coord in grid.keys()) + 1
    max_c = max(coord[1] for coord in grid.keys()) + 1
    
    matrix = [[None for _ in range(max_c)] for _ in range(max_r)]
    for (r, c), cell in grid.items():
        matrix[r][c] = cell
    return matrix

def get_header_rows_count(matrix):
    """Determina a quantidade de linhas de cabeçalho no topo da matriz."""
    h_count = 0
    for r_idx in range(len(matrix)):
        row_cells = matrix[r_idx]
        is_header = False
        for cell in row_cells:
            if cell is None:
                continue
            if cell.name == 'th':
                is_header = True
                break
            text = normalize_str(cell.get_text())
            if any(k in text for k in ['sigla', 'nome digital', 'inauguracao', 'ativos', 'visitas', 'conversao', 'vendas', 'transferencias', 'cancelado']):
                is_header = True
                break
        if is_header:
            h_count += 1
        else:
            break
    return h_count

def get_column_headers(matrix, h_count):
    """Gera uma string de cabeçalho combinando as linhas de cabeçalho para cada coluna."""
    headers = []
    num_cols = len(matrix[0]) if matrix else 0
    for c in range(num_cols):
        col_cells = []
        for r in range(h_count):
            cell = matrix[r][c]
            if cell and cell not in col_cells:
                col_cells.append(cell)
        texts = [cell.get_text(strip=True) for cell in col_cells]
        texts = [t for t in texts if t]
        headers.append(" | ".join(texts))
    return headers

def map_header_to_field(header_text):
    """Mapeia dinamicamente o texto do cabeçalho da coluna para o nome do campo correspondente."""
    norm = normalize_str(header_text)
    
    # 1. Unidade cadastral
    if 'sigla' in norm and 'ativos' not in norm:
        return 'sigla'
    if 'nome digital' in norm:
        return 'nome_digital'
    if 'nome' in norm:
        return 'nome_unidade'
    if norm == 'unidade':
        # Tabela de pré-vendas: coluna "Unidade" sozinha é o código da unidade
        return 'codigo_unidade'
    if 'inauguracao' in norm or 'inauguração' in norm:
        return 'data_inauguracao'
        
    # 2. Ativos
    if 'ativos' in norm:
        if 'total' in norm:
            return 'total_ativos'
        if 'smart' in norm:
            return 'ativos_smart'
        if 'black+' in norm or 'black plus' in norm:
            return 'ativos_black_plus'
        if 'black' in norm:
            return 'ativos_black'
        if 'fit' in norm:
            return 'ativos_fit'
        if 'studio' in norm:
            return 'ativos_studio'
        if 'bloqueados' in norm:
            return 'bloqueados'
            
    # 3. Visitas
    if 'visitas' in norm:
        if 'dia' in norm:
            return 'visitas_dia'
        if 'mes' in norm:
            return 'visitas_mes'
            
    # 4. Conversão
    if 'conversao' in norm:
        if 'dia' in norm:
            return 'conversao_dia'
        if 'mes' in norm:
            return 'conversao_mes'
            
    # 5. Transferências
    if 'transferencias' in norm or 'transferencia' in norm:
        return 'transferencias_liquida_mes'
        
    # 6. Cancelamentos
    if 'cancelado' in norm or 'cancelamento' in norm:
        for plano in ['smart', 'black', 'studio', 'total']:
            if plano in norm:
                return f"cancelamento_detalhe|{plano}"
                
    # 7. Vendas Geral
    if 'vendas' in norm or 'venda' in norm:
        if 'total' in norm:
            if 'dia' in norm:
                return 'vendas_geral_dia'
            if 'mes' in norm:
                return 'vendas_geral_mes'
            # Tabela de pré-vendas: valor acumulado desde o início da pré-venda,
            # sem quebra por dia ou mês.
            return 'pre_venda_total'
        else:
            # Identificação de Canal
            canal = None
            for c in ['balcao', 'web', 'totem', 'outros']:
                if c == 'balcao' and ('balcao' in norm or 'balcão' in norm):
                    canal = 'balcao'
                    break
                if c in norm:
                    canal = c
                    break

            # Identificação de Plano
            plano = None
            if 'black+' in norm or 'black plus' in norm:
                plano = 'black_plus'
            else:
                for p in ['smart', 'black', 'fit', 'studio']:
                    if p in norm:
                        plano = p
                        break

            # Identificação de Período (Dia ou Mês)
            periodo = None
            if 'dia' in norm:
                periodo = 'dia'
            elif 'mes' in norm:
                periodo = 'mes'

            if canal and plano and periodo:
                return f"venda_detalhe|{canal}|{plano}|{periodo}"
            if canal and plano:
                # Tabela de pré-vendas: mesmo canal/plano, sem quebra por dia/mês
                return f"pre_venda_detalhe|{canal}|{plano}"

    return None

def parse_html(html_content):
    """Varre o HTML bruto, mapeia e extrai os blocos regionais e tabelas."""
    soup = BeautifulSoup(html_content, 'lxml')
    regions = {}
    
    current_region = "Desconhecido"
    
    # Procura elementos na ordem em que aparecem no documento
    elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'p', 'div'])
    
    parsed_tables = set()
    
    for el in elements:
        if el.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] or (el.name in ['p', 'div'] and el.get('class') and 'region' in "".join(el.get('class')).lower()):
            text = el.get_text(strip=True)
            norm_text = normalize_str(text)
            # Verifica se o texto indica uma região (padrões típicos do e-mail)
            if any(k in norm_text for k in ['brasil', 'franquia', 'digital', 'regional']) or (len(text) > 0 and len(text) < 40 and el.name in ['h1', 'h2', 'h3']):
                current_region = extract_region_name(text)
                if current_region not in regions:
                    regions[current_region] = { 'main_rows': [], 'cancel_rows': [], 'pre_venda_rows': [] }
        elif el.name == 'table':
            if el in parsed_tables:
                continue
            parsed_tables.add(el)
            
            matrix = table_to_grid(el)
            if not matrix:
                continue
                
            h_count = get_header_rows_count(matrix)
            if h_count == 0:
                continue
                
            col_headers = get_column_headers(matrix, h_count)
            mapped_fields = [map_header_to_field(h) for h in col_headers]
            
            # Verifica o tipo de tabela com base nos campos mapeados
            if 'sigla' in mapped_fields or 'total_ativos' in mapped_fields:
                table_type = 'main'
            elif any(f and 'cancelamento' in f for f in mapped_fields) or 'transferencias_liquida_mes' in mapped_fields:
                table_type = 'cancel'
            elif 'codigo_unidade' in mapped_fields:
                # Tabela de pré-vendas: unidades ainda não inauguradas (sem Ativos/Visitas/Conversão)
                table_type = 'pre_venda'
            else:
                # Tabela desconhecida, ignora
                continue

            # Processa as linhas de dados da tabela
            for r_idx in range(h_count, len(matrix)):
                row_cells = matrix[r_idx]
                row_data = {}
                for c_idx, cell in enumerate(row_cells):
                    if cell is None:
                        continue
                    field = mapped_fields[c_idx]
                    if field:
                        row_data[field] = cell.get_text(strip=True)

                if current_region not in regions:
                    regions[current_region] = { 'main_rows': [], 'cancel_rows': [], 'pre_venda_rows': [] }

                if table_type == 'pre_venda':
                    if 'codigo_unidade' not in row_data and 'nome_unidade' not in row_data:
                        continue
                    # Ignora linhas de subtotal ("-" na unidade, ou nome "Total")
                    if row_data.get('codigo_unidade', '').strip() == '-' or normalize_str(row_data.get('nome_unidade', '')) == 'total':
                        continue
                    row_data['bloco_email'] = current_region
                    regions[current_region]['pre_venda_rows'].append(row_data)
                    continue

                if 'nome_digital' in row_data or 'sigla' in row_data:
                    # Ignora linhas de subtotal ("-" na sigla, ou nome "Total") ao fim de cada região
                    nome_para_checar = row_data.get('nome_digital') or row_data.get('nome_unidade', '')
                    if row_data.get('sigla', '').strip() == '-' or normalize_str(nome_para_checar) == 'total':
                        continue
                    row_text = " ".join(cell.get_text() for cell in row_cells if cell)
                    unidade_imatura = False
                    if '*' in row_text or '120 dias' in row_text or 'imatur' in row_text:
                        unidade_imatura = True

                    row_data['unidade_imatura'] = unidade_imatura
                    row_data['bloco_email'] = current_region

                    if table_type == 'main':
                        regions[current_region]['main_rows'].append(row_data)
                    else:
                        regions[current_region]['cancel_rows'].append(row_data)
                        
    return regions
