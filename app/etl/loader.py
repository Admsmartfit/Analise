import json
import psycopg2
from psycopg2.extras import Json
from app.etl.normalizer import normalize_unit_data, normalize_cancel_data, normalize_pre_venda_data

def load_parsed_data(conn, parsed_data, data_referencia, gmail_message_id):
    """Realiza a carga idempotente dos dados parseados e normalizados no banco de dados.

    Toda a execução é envolvida em uma única transação do PostgreSQL.
    """
    # 1. Agrupa e une dados da main table e cancel table por Nome Digital e Região
    unified_data = {}
    
    for region, data in parsed_data.items():
        # Processa dados principais
        for row in data.get('main_rows', []):
            norm = normalize_unit_data(row)
            nome_digital = norm['nome_digital']
            if not nome_digital:
                continue
                
            key = (region, nome_digital)
            if key not in unified_data:
                unified_data[key] = {
                    'main': norm,
                    'cancel': None
                }
            else:
                unified_data[key]['main'] = norm
                
        # Processa cancelamentos
        for row in data.get('cancel_rows', []):
            norm = normalize_cancel_data(row)
            nome_digital = norm['nome_digital']
            if not nome_digital:
                continue
                
            key = (region, nome_digital)
            if key not in unified_data:
                unified_data[key] = {
                    'main': None,
                    'cancel': norm
                }
            else:
                unified_data[key]['cancel'] = norm

    # 2. Executa a carga no banco
    with conn.cursor() as cur:
        for (region, nome_digital), item in unified_data.items():
            main = item['main']
            cancel = item['cancel']
            
            # Decide tipo de operação
            tipo_operacao = 'Franquia' if 'franquia' in region.lower() else 'Própria'
            
            # Extrai valores cadastrais
            sigla = main['sigla'] if main else (cancel['nome_digital'][:10] if cancel else '')
            pais = main['pais'] if main else ''
            data_inauguracao = main['data_inauguracao'] if main else None

            # --- TABELA 1: dim_unidade (Upsert) ---
            # Chave composta (nome, país, região): o nome sozinho colide entre
            # países/regiões diferentes (ex: várias unidades "Santa Cruz").
            cur.execute("""
                INSERT INTO dim_unidade (nome_digital, pais, sigla_atual, regiao_uf, tipo_operacao, data_inauguracao)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (nome_digital, pais, regiao_uf) DO UPDATE SET
                    sigla_atual = EXCLUDED.sigla_atual,
                    tipo_operacao = EXCLUDED.tipo_operacao,
                    data_inauguracao = COALESCE(dim_unidade.data_inauguracao, EXCLUDED.data_inauguracao)
                RETURNING id;
            """, (nome_digital, pais, sigla, region, tipo_operacao, data_inauguracao))
            
            unidade_id = cur.fetchone()[0]
            
            # Prepara métricas para fato_metricas_diarias
            unidade_imatura = main['unidade_imatura'] if main else False
            total_ativos = main['total_ativos'] if main else 0
            ativos_smart = main['ativos_smart'] if main else 0
            ativos_black = main['ativos_black'] if main else 0
            ativos_fit = main['ativos_fit'] if main else 0
            ativos_black_plus = main['ativos_black_plus'] if main else 0
            ativos_studio = main['ativos_studio'] if main else 0
            bloqueados = main['bloqueados'] if main else 0
            
            visitas_dia = main['visitas_dia'] if main else 0
            visitas_mes = main['visitas_mes'] if main else 0
            conversao_dia = main['conversao_dia'] if main else None
            conversao_mes = main['conversao_mes'] if main else None
            
            vendas_geral_dia = main['vendas_geral_dia'] if main else 0
            vendas_geral_mes = main['vendas_geral_mes'] if main else 0
            
            # No layout real do e-mail, Transferências/Cancelamentos vêm dentro da própria
            # linha "main" (mesma tabela das unidades). Mantemos "cancel" como respaldo
            # para o caso (previsto no PRD original) de um layout com tabela separada.
            transferencias_liquida_mes = main['transferencias_liquida_mes'] if main else (cancel['transferencias_liquida_mes'] if cancel else 0.0)
            cancelamentos_detalhe = (main['cancelamentos_detalhe'] if main else None) or (cancel['cancelamentos_detalhe'] if cancel else {})

            # Payloads brutos para rede de segurança
            detalhe_vendas_json = Json(main['vendas_detalhe']) if main else Json({})
            detalhe_movimentacoes_json = Json({
                'transferencias_liquida_mes': transferencias_liquida_mes,
                'cancelamentos': cancelamentos_detalhe
            })
            
            # --- TABELA 2: fato_metricas_diarias (Upsert) ---
            cur.execute("""
                INSERT INTO fato_metricas_diarias (
                    data_referencia, unidade_id, sigla_no_dia, bloco_email, tendencia, unidade_imatura,
                    total_ativos, ativos_smart, ativos_black, ativos_fit, ativos_black_plus, ativos_studio, bloqueados,
                    visitas_dia, visitas_mes, conversao_dia, conversao_mes,
                    transferencias_liquida_mes, vendas_geral_dia, vendas_geral_mes,
                    detalhe_vendas_json, detalhe_movimentacoes_json, gmail_message_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (data_referencia, unidade_id) DO UPDATE SET
                    sigla_no_dia = EXCLUDED.sigla_no_dia,
                    bloco_email = EXCLUDED.bloco_email,
                    tendencia = EXCLUDED.tendencia,
                    unidade_imatura = EXCLUDED.unidade_imatura,
                    total_ativos = EXCLUDED.total_ativos,
                    ativos_smart = EXCLUDED.ativos_smart,
                    ativos_black = EXCLUDED.ativos_black,
                    ativos_fit = EXCLUDED.ativos_fit,
                    ativos_black_plus = EXCLUDED.ativos_black_plus,
                    ativos_studio = EXCLUDED.ativos_studio,
                    bloqueados = EXCLUDED.bloqueados,
                    visitas_dia = EXCLUDED.visitas_dia,
                    visitas_mes = EXCLUDED.visitas_mes,
                    conversao_dia = EXCLUDED.conversao_dia,
                    conversao_mes = EXCLUDED.conversao_mes,
                    transferencias_liquida_mes = EXCLUDED.transferencias_liquida_mes,
                    vendas_geral_dia = EXCLUDED.vendas_geral_dia,
                    vendas_geral_mes = EXCLUDED.vendas_geral_mes,
                    detalhe_vendas_json = EXCLUDED.detalhe_vendas_json,
                    detalhe_movimentacoes_json = EXCLUDED.detalhe_movimentacoes_json,
                    gmail_message_id = EXCLUDED.gmail_message_id,
                    processado_em = CURRENT_TIMESTAMP
                RETURNING id;
            """, (
                data_referencia, unidade_id, sigla, region, None, unidade_imatura,
                total_ativos, ativos_smart, ativos_black, ativos_fit, ativos_black_plus, ativos_studio, bloqueados,
                visitas_dia, visitas_mes, conversao_dia, conversao_mes,
                transferencias_liquida_mes, vendas_geral_dia, vendas_geral_mes,
                detalhe_vendas_json, detalhe_movimentacoes_json, gmail_message_id
            ))
            
            fato_diaria_id = cur.fetchone()[0]
            
            # --- TABELA 3: fato_vendas_detalhada (Upsert) ---
            if main and main['vendas_detalhe']:
                # Agrupa chaves venda_detalhe|{canal}|{plano}|{periodo} por (canal, plano)
                vendas_agrupadas = {}
                for key, val in main['vendas_detalhe'].items():
                    parts = key.split('|')
                    if len(parts) == 4:
                        _, canal, plano, periodo = parts
                        combo = (canal, plano)
                        if combo not in vendas_agrupadas:
                            vendas_agrupadas[combo] = {'dia': 0, 'mes': 0}
                        vendas_agrupadas[combo][periodo] = val
                        
                for (canal, plano), qtds in vendas_agrupadas.items():
                    cur.execute("""
                        INSERT INTO fato_vendas_detalhada (fato_diaria_id, canal_venda, plano, qtd_dia, qtd_mes)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (fato_diaria_id, canal_venda, plano) DO UPDATE SET
                            qtd_dia = EXCLUDED.qtd_dia,
                            qtd_mes = EXCLUDED.qtd_mes;
                    """, (fato_diaria_id, canal, plano, qtds['dia'], qtds['mes']))
            
            # --- TABELA 4: fato_cancelamentos_detalhada (Upsert) ---
            if cancelamentos_detalhe:
                for key, val in cancelamentos_detalhe.items():
                    parts = key.split('|')
                    if len(parts) == 2:
                        _, plano = parts
                        cur.execute("""
                            INSERT INTO fato_cancelamentos_detalhada (fato_diaria_id, plano, qtd_mes)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (fato_diaria_id, plano) DO UPDATE SET
                                qtd_mes = EXCLUDED.qtd_mes;
                        """, (fato_diaria_id, plano, val))

        # --- Pré-vendas: unidades ainda não inauguradas (fora do fluxo de dim_unidade) ---
        for region, data in parsed_data.items():
            for row in data.get('pre_venda_rows', []):
                norm = normalize_pre_venda_data(row)
                codigo_unidade = norm['codigo_unidade']
                if not codigo_unidade:
                    continue

                cur.execute("""
                    INSERT INTO dim_unidade_pre_venda (codigo_unidade, nome_unidade, pais_regiao)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (codigo_unidade) DO UPDATE SET
                        nome_unidade = EXCLUDED.nome_unidade,
                        pais_regiao = COALESCE(dim_unidade_pre_venda.pais_regiao, EXCLUDED.pais_regiao)
                    RETURNING id;
                """, (codigo_unidade, norm['nome_unidade'], region))
                unidade_pv_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO fato_pre_venda_diaria (data_referencia, unidade_pre_venda_id, vendas_total, detalhe_vendas_json, gmail_message_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (data_referencia, unidade_pre_venda_id) DO UPDATE SET
                        vendas_total = EXCLUDED.vendas_total,
                        detalhe_vendas_json = EXCLUDED.detalhe_vendas_json,
                        gmail_message_id = EXCLUDED.gmail_message_id,
                        processado_em = CURRENT_TIMESTAMP;
                """, (data_referencia, unidade_pv_id, norm['vendas_total'], Json(norm['vendas_detalhe']), gmail_message_id))

    conn.commit()
