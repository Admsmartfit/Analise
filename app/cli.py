import os
import sys
import argparse
from app.db.database import get_connection, init_db
from app.auth.setup_gmail import setup_gmail_flow
from app.auth.gmail_client import GmailClient
from app.etl.discovery import discover_new_emails
from app.etl.backfill import run_backfill, process_single_email, COVERAGE_PASSED_PATH
from app.etl.raw_headers_scanner import run_coverage_report
from app.etl.exporter import export_to_xlsx

def cmd_setup_gmail(args):
    print("[IMAP] Iniciando assistente de configuração do e-mail...")
    success = setup_gmail_flow(interactive=True)
    if success:
        print("[SUCESSO] Configuração concluída!")
    else:
        print("[ERRO] Configuração falhou. Verifique os passos listados.")
        sys.exit(1)

def cmd_test_coverage(args):
    html_content = None
    source_name = ""
    
    if args.file:
        if not os.path.exists(args.file):
            print(f"[ERRO] Arquivo {args.file} não encontrado.")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            html_content = f.read()
        source_name = f"arquivo local '{os.path.basename(args.file)}'"
    elif args.message_id:
        try:
            client = GmailClient()
            msg = client.get_message(args.message_id)
            html_content = client.extract_html_payload(msg)
            source_name = f"Gmail ID '{args.message_id}'"
        except Exception as e:
            print(f"[ERRO] Erro ao buscar mensagem {args.message_id} do Gmail: {e}")
            sys.exit(1)
    else:
        # Se nenhum argumento for passado, tenta usar o fixture padrão se existir para facilitar testes
        default_fixture = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                       "tests", "fixtures", "smartfit_email_2026.html")
        if os.path.exists(default_fixture):
            print(f"[INFO] Nenhum e-mail ou arquivo especificado. Usando fixture padrão para teste: {default_fixture}")
            with open(default_fixture, "r", encoding="utf-8") as f:
                html_content = f.read()
            source_name = "Fixture padrão"
        else:
            print("[ERRO] Especifique um arquivo local (--file) ou ID de e-mail (--message-id) para rodar o teste de cobertura.")
            sys.exit(1)
            
    if not html_content:
        print("[ERRO] Não foi possível obter o conteúdo HTML.")
        sys.exit(1)
        
    print(f"[COBERTURA] Executando teste de cobertura de campos para: {source_name}...")
    try:
        report = run_coverage_report(html_content)
        
        print("\n========================================================================")
        print(f"RELATÓRIO DE COBERTURA DE CAMPOS")
        print("========================================================================")
        print(f"Regiões encontradas no HTML bruto: {len(report['regions_raw'])}")
        print(f"Regiões mapeadas pelo parser:     {len(report['regions_parsed'])}")
        print(f"Unidades no HTML bruto:          {report['units_raw']}")
        print(f"Unidades mapeadas pelo parser:    {report['units_parsed']}")
        print(f"Pré-vendas no HTML bruto:        {report['pre_venda_raw']}")
        print(f"Pré-vendas mapeadas pelo parser:  {report['pre_venda_parsed']}")
        print(f"Checksum de vendas (HTML bruto):  {report['checksum_raw']}")
        print(f"Checksum de vendas (Mapeado):     {report['checksum_parsed']}")
        print(f"Campos Mapeados com sucesso:      {len(report['captured_fields'])}")
        print(f"Campos órfãos (NÃO mapeados):     {len(report['unmapped_fields'])}")
        print(f"Índice de cobertura de campos:    {report['coverage_pct']:.1f}%")
        print("========================================================================")
        
        if report['unmapped_fields']:
            print("\n[ALERTA] Campos encontrados no HTML e NÃO mapeados (ajuste o parser.py):")
            for col in report['unmapped_fields']:
                print(f"   - {col}")
                
        # Validação do teste de cobertura
        is_success = (
            report['coverage_pct'] == 100.0 and
            report['units_raw'] == report['units_parsed'] and
            report['pre_venda_raw'] == report['pre_venda_parsed'] and
            report['checksum_raw'] == report['checksum_parsed'] and
            len(report['unmapped_fields']) == 0
        )

        if is_success:
            print("\n[SUCESSO] TESTE PASSOU COM 100% DE COBERTURA E INTEGRIDADE!")
            # Salva o carimbo de aprovação do teste
            os.makedirs(os.path.dirname(COVERAGE_PASSED_PATH), exist_ok=True)
            with open(COVERAGE_PASSED_PATH, "w") as f:
                f.write(f"PASSED AT {os.path.getmtime(args.file) if args.file else 'NOW'}")
            print(f"[OK] Carimbo gerado em {COVERAGE_PASSED_PATH}.")
        else:
            print("\n[ERRO] TESTE FALHOU!")
            if report['units_raw'] != report['units_parsed']:
                print(f"   - Divergência no número de unidades: Bruto({report['units_raw']}) vs Mapeado({report['units_parsed']})")
            if report['pre_venda_raw'] != report['pre_venda_parsed']:
                print(f"   - Divergência no número de unidades em pré-venda: Bruto({report['pre_venda_raw']}) vs Mapeado({report['pre_venda_parsed']})")
            if report['checksum_raw'] != report['checksum_parsed']:
                print(f"   - Divergência no checksum de vendas: Bruto({report['checksum_raw']}) vs Mapeado({report['checksum_parsed']})")
            if report['unmapped_fields']:
                print(f"   - Existem {len(report['unmapped_fields'])} colunas órfãs não mapeadas.")
                
            # Remove o carimbo se existir
            if os.path.exists(COVERAGE_PASSED_PATH):
                os.remove(COVERAGE_PASSED_PATH)
            sys.exit(1)
            
    except Exception as e:
        print(f"[ERRO] Erro durante a geração do relatório de cobertura: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def cmd_backfill(args):
    print("[INFO] Inicializando conexões...")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao banco de dados: {e}")
        sys.exit(1)
        
    try:
        client = GmailClient()
    except Exception as e:
        print(f"[ERRO] Não foi possível carregar o cliente Gmail: {e}")
        conn.close()
        sys.exit(1)
        
    if args.discover:
        # Executa a descoberta primeiro
        discover_new_emails(conn, client)
        
    # Executa o backfill
    success, fail = run_backfill(conn, client, limit=args.limit)
    conn.close()
    print(f"[OK] Backfill concluído. Processados com sucesso: {success} | Erros: {fail}.")

def cmd_run_daily(args):
    print("[INFO] Iniciando execução diária incremental...")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao banco de dados: {e}")
        sys.exit(1)
        
    try:
        client = GmailClient()
    except Exception as e:
        print(f"[ERRO] Não foi possível carregar o cliente Gmail: {e}")
        conn.close()
        sys.exit(1)
        
    # 1. Varre novos e-mails (Descoberta)
    new_discovered, total = discover_new_emails(conn, client)
    
    # 2. Processa os pendentes
    success, fail = run_backfill(conn, client, limit=None)
    conn.close()
    print(f"[OK] Execução diária concluída. Sucessos: {success} | Erros: {fail}.")

def cmd_init_db(args):
    print("[BD] Inicializando Tabelas do Banco de Dados...")
    init_db()

def cmd_train_churn_model(args):
    print("[ML] Treinando modelo de risco de cancelamento...")
    from app.ml.model_utils import train_model, InsufficientDataError

    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao banco de dados: {e}")
        sys.exit(1)

    try:
        model, metrics, model_data = train_model(conn)
        print(f"[OK] Modelo treinado com {model_data['n_amostras_treino']} amostras de treino "
              f"e {model_data['n_amostras_teste']} de teste.")
        print(f"     Acurácia:  {metrics['accuracy']:.3f}")
        print(f"     Precisão:  {metrics['precision']:.3f}")
        print(f"     Recall:    {metrics['recall']:.3f}")
        roc_auc = metrics['roc_auc']
        print(f"     ROC AUC:   {roc_auc:.3f}" if roc_auc == roc_auc else "     ROC AUC:   N/A")
        print(f"     Corte de alto risco (percentil {75}): {model_data['risk_threshold']:.4f}")
        print(f"     Versão do modelo: {model_data['versao_modelo']}")
    except InsufficientDataError as e:
        print(f"[ERRO] Dado insuficiente para treinar: {e}")
        sys.exit(1)
    finally:
        conn.close()

def cmd_predict_churn(args):
    print(f"[ML] Gerando predições de risco de cancelamento para {args.month}...")
    from app.ml.model_utils import load_model, predict_for_month, InsufficientDataError

    try:
        model_data = load_model()
    except FileNotFoundError as e:
        print(f"[ERRO] {e}")
        sys.exit(1)

    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao banco de dados: {e}")
        sys.exit(1)

    try:
        result = predict_for_month(conn, model_data, args.month)

        with conn.cursor() as cur:
            for _, row in result.iterrows():
                cur.execute("""
                    INSERT INTO churn_predicoes (unidade_id, mes_referencia, probabilidade_risco, nivel_risco, versao_modelo)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (unidade_id, mes_referencia, versao_modelo) DO UPDATE SET
                        probabilidade_risco = EXCLUDED.probabilidade_risco,
                        nivel_risco = EXCLUDED.nivel_risco,
                        gerado_em = CURRENT_TIMESTAMP;
                """, (
                    int(row["unidade_id"]), row["mes_referencia"],
                    float(row["probabilidade_risco"]), row["nivel_risco"],
                    model_data["versao_modelo"],
                ))
        conn.commit()

        alto_risco = (result["nivel_risco"] == "Alto").sum()
        print(f"[OK] {len(result)} predições gravadas em churn_predicoes.")
        print(f"     Unidades em risco Alto: {alto_risco}")
    except InsufficientDataError as e:
        print(f"[ERRO] {e}")
        sys.exit(1)
    finally:
        conn.close()

def cmd_export_xlsx(args):
    print("[EXPORT] Gerando planilha com os dados capturados...")
    try:
        conn = get_connection()
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao banco de dados: {e}")
        sys.exit(1)

    try:
        output_path = args.output or os.path.join("exports", "dados_capturados.xlsx")
        path, main_count, pv_count = export_to_xlsx(conn, output_path, data_referencia=args.date)
        print(f"[OK] Planilha gerada em: {os.path.abspath(path)}")
        print(f"     Unidades (formato padrão): {main_count}")
        print(f"     Unidades (pré-venda):      {pv_count}")
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Pipeline de Ingestão Smart Fit - CLI")
    parser.add_argument('--version', action='version', version='SmartFit ETL v1.0')
    subparsers = parser.add_subparsers(dest='command', help='Sub-comandos')
    
    # setup-gmail
    subparsers.add_parser('setup-gmail', help='Assistente de configuração do e-mail via IMAP (Senha de App)')
    
    # init-db
    subparsers.add_parser('init-db', help='Cria/verifica tabelas no banco de dados')
    
    # test-coverage
    p_coverage = subparsers.add_parser('test-coverage', help='Valida cobertura de campos do parser')
    group = p_coverage.add_mutually_exclusive_group()
    group.add_argument('--file', type=str, help='Caminho para arquivo HTML local')
    group.add_argument('--message-id', type=str, help='ID do e-mail do Gmail')
    
    # backfill
    p_backfill = subparsers.add_parser('backfill', help='Processa mensagens históricas pendentes')
    p_backfill.add_argument('--limit', type=int, help='Limite de e-mails para processar neste lote')
    p_backfill.add_argument('--discover', action='store_true', help='Executa descoberta de novos e-mails antes de rodar o backfill')
    
    # run-daily
    subparsers.add_parser('run-daily', help='Varre novos e-mails e executa ingestão diária')

    # export-xlsx
    p_export = subparsers.add_parser('export-xlsx', help='Exporta os dados capturados no banco para uma planilha Excel')
    p_export.add_argument('--date', type=str, help='Filtra por uma data de referência específica (YYYY-MM-DD). Se omitido, exporta tudo.')
    p_export.add_argument('--output', type=str, help='Caminho do arquivo .xlsx de saída (padrão: exports/dados_capturados.xlsx)')

    # train-churn-model
    subparsers.add_parser('train-churn-model', help='Treina o modelo de risco de cancelamento com dados reais do banco')

    # predict-churn
    p_predict_churn = subparsers.add_parser('predict-churn', help='Gera predições de risco de cancelamento para um mês e grava no banco')
    p_predict_churn.add_argument('--month', type=str, required=True, help='Mês de referência no formato YYYY-MM')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'setup-gmail': cmd_setup_gmail,
        'init-db': cmd_init_db,
        'test-coverage': cmd_test_coverage,
        'backfill': cmd_backfill,
        'run-daily': cmd_run_daily,
        'export-xlsx': cmd_export_xlsx,
        'train-churn-model': cmd_train_churn_model,
        'predict-churn': cmd_predict_churn
    }
    
    commands[args.command](args)

if __name__ == '__main__':
    main()
