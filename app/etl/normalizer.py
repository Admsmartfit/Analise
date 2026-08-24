import re
from datetime import datetime
from email.utils import parsedate_to_datetime

def clean_name(name):
    """Remove asteriscos e espaços extras de nomes digitais e siglas."""
    if not name:
        return ""
    # Remove asteriscos
    name = name.replace("*", "")
    # Remove espaços duplos e nas pontas
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def parse_int(val):
    """Converte valores do e-mail para inteiros, tratando '-' ou vazios como 0."""
    if not val:
        return 0
    val_str = str(val).strip()
    if val_str == "-" or val_str == "":
        return 0
    # Remove pontos de milhares (ex: 3.500) e espaços
    val_str = val_str.replace(".", "").replace(",", "").replace(" ", "")
    try:
        return int(val_str)
    except ValueError:
        return 0

def parse_float_percent(val):
    """Converte valores de conversão/porcentagem para float (ex: '8.5%' -> 8.5, '-' -> None)."""
    if not val:
        return None
    val_str = str(val).strip()
    if val_str == "-" or val_str == "" or val_str == "NULL":
        return None
    # Remove o símbolo de porcentagem e espaços
    val_str = val_str.replace("%", "").strip()
    # Corrige vírgula decimal brasileira para ponto (ex: 9,2 -> 9.2)
    val_str = val_str.replace(",", ".")
    try:
        return float(val_str)
    except ValueError:
        return None

def parse_float_currency(val):
    """Converte valores monetários/saldos (como transferências) para float (ex: '-12.50' -> -12.50)."""
    if not val:
        return 0.0
    val_str = str(val).strip()
    if val_str == "-" or val_str == "":
        return 0.0
    # Corrige vírgula decimal para ponto se houver, removendo pontos de milhar
    # Exemplo: -1.250,50 -> -1250.50 ou -12,50 -> -12.50
    if "," in val_str and "." in val_str:
        if val_str.index(".") < val_str.index(","):
            # Ponto é milhar, vírgula é decimal
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            # Vírgula é milhar, ponto é decimal
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        # Se só tem vírgula, assume que é decimal (ex: -12,50)
        val_str = val_str.replace(",", ".")
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def extract_pais_from_sigla(sigla):
    """Extrai o código de país embutido na sigla (ex: 'SBRSPCSTZ01' -> 'BR').

    NÃO USE para popular dim_unidade.pais — o formato da sigla mudou ao longo do
    histórico (siglas de meses mais antigos não seguem o padrão "S" + país), o que
    fazia essa função devolver valores diferentes para a MESMA unidade física em
    meses diferentes, fragmentando-a em várias linhas de dim_unidade. Mantida só
    como utilitário auxiliar; a extração usada de fato é extract_pais_from_regiao.
    """
    if not sigla:
        return ''
    match = re.match(r'^S([A-Z]{2})', sigla.strip().upper())
    return match.group(1) if match else sigla.strip().upper()

def extract_pais_from_regiao(regiao_uf):
    """Extrai o país a partir do texto do bloco de região do e-mail
    (ex: 'Chile - Región Metropolitana' -> 'Chile').

    Preferido sobre extrair da sigla: o texto da região é estável (o mesmo texto
    de cabeçalho sempre gera o mesmo "país"), diferente da sigla, que mudou de
    formato ao longo do tempo. Blocos sem país explícito (ex: "Franquia",
    "Digital") viram seu próprio "país" — não são um código ISO real, mas
    permanecem estáveis, o que é o que importa para não fragmentar a unidade.
    """
    if not regiao_uf:
        return ''
    return regiao_uf.split(' - ')[0].strip()

def parse_date(date_str):
    """Tenta converter a string de data em um objeto date do Python (YYYY-MM-DD)."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Cabeçalho "Date" de e-mail (RFC 2822), ex: "Sun, 23 Aug 2026 10:17:12 +0000 (UTC)"
    try:
        return parsedate_to_datetime(date_str).date()
    except (TypeError, ValueError):
        return None

def normalize_unit_data(raw_row):
    """Aplica as regras de normalização para uma linha da tabela principal de métricas."""
    normalized = {}

    # 1. Identificação Cadastral (Dimensão Unidade)
    # "Nome Digital" é a chave mestra estável (siglas são reaproveitadas em reorganizações).
    # Alguns layouts de e-mail chamam essa coluna apenas de "Nome" — tratamos como sinônimos.
    normalized['sigla'] = clean_name(raw_row.get('sigla', ''))
    normalized['nome_digital'] = clean_name(raw_row.get('nome_digital') or raw_row.get('nome_unidade', ''))
    normalized['data_inauguracao'] = parse_date(raw_row.get('data_inauguracao', ''))
    normalized['unidade_imatura'] = raw_row.get('unidade_imatura', False)
    normalized['bloco_email'] = raw_row.get('bloco_email', '')
    normalized['pais'] = extract_pais_from_regiao(normalized['bloco_email'])
    
    # 2. Ativos
    normalized['total_ativos'] = parse_int(raw_row.get('total_ativos', 0))
    normalized['ativos_smart'] = parse_int(raw_row.get('ativos_smart', 0))
    normalized['ativos_black'] = parse_int(raw_row.get('ativos_black', 0))
    normalized['ativos_fit'] = parse_int(raw_row.get('ativos_fit', 0))
    normalized['ativos_black_plus'] = parse_int(raw_row.get('ativos_black_plus', 0))
    normalized['ativos_studio'] = parse_int(raw_row.get('ativos_studio', 0))
    normalized['bloqueados'] = parse_int(raw_row.get('bloqueados', 0))
    
    # 3. Visitas e Conversão
    normalized['visitas_dia'] = parse_int(raw_row.get('visitas_dia', 0))
    normalized['visitas_mes'] = parse_int(raw_row.get('visitas_mes', 0))
    normalized['conversao_dia'] = parse_float_percent(raw_row.get('conversao_dia', None))
    normalized['conversao_mes'] = parse_float_percent(raw_row.get('conversao_mes', None))
    
    # 4. Totais de Vendas
    normalized['vendas_geral_dia'] = parse_int(raw_row.get('vendas_geral_dia', 0))
    normalized['vendas_geral_mes'] = parse_int(raw_row.get('vendas_geral_mes', 0))
    
    # 5. Detalhes de Vendas Granulares (Canal x Plano x Período)
    # Copia todos os campos venda_detalhe|... mantendo o nome
    vendas_detalhe = {}
    for key, value in raw_row.items():
        if key.startswith('venda_detalhe|'):
            vendas_detalhe[key] = parse_int(value)
    normalized['vendas_detalhe'] = vendas_detalhe

    # 6. Transferências e Cancelamentos
    # No layout real do e-mail, essas colunas vêm na MESMA tabela das unidades
    # (não numa tabela "cancel" separada) — por isso são extraídas aqui também.
    normalized['transferencias_liquida_mes'] = parse_float_currency(raw_row.get('transferencias_liquida_mes', 0.0))
    cancelamentos_detalhe = {}
    for key, value in raw_row.items():
        if key.startswith('cancelamento_detalhe|'):
            cancelamentos_detalhe[key] = parse_int(value)
    normalized['cancelamentos_detalhe'] = cancelamentos_detalhe

    return normalized

def normalize_pre_venda_data(raw_row):
    """Aplica as regras de normalização para uma linha da tabela de pré-vendas (unidades ainda não inauguradas)."""
    normalized = {}

    normalized['codigo_unidade'] = clean_name(raw_row.get('codigo_unidade', ''))
    normalized['nome_unidade'] = clean_name(raw_row.get('nome_unidade', ''))
    normalized['bloco_email'] = raw_row.get('bloco_email', '')
    normalized['vendas_total'] = parse_int(raw_row.get('pre_venda_total', 0))

    vendas_detalhe = {}
    for key, value in raw_row.items():
        if key.startswith('pre_venda_detalhe|'):
            vendas_detalhe[key] = parse_int(value)
    normalized['vendas_detalhe'] = vendas_detalhe

    return normalized

def normalize_cancel_data(raw_row):
    """Aplica as regras de normalização para uma linha da tabela de transferências e cancelamentos."""
    normalized = {}

    normalized['nome_digital'] = clean_name(raw_row.get('nome_digital') or raw_row.get('nome_unidade', ''))
    normalized['transferencias_liquida_mes'] = parse_float_currency(raw_row.get('transferencias_liquida_mes', 0.0))
    
    cancelamentos_detalhe = {}
    for key, value in raw_row.items():
        if key.startswith('cancelamento_detalhe|'):
            cancelamentos_detalhe[key] = parse_int(value)
    normalized['cancelamentos_detalhe'] = cancelamentos_detalhe
    
    return normalized
