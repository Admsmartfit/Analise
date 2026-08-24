"""Automatiza a configuração inicial do Metabase para o Painel Analítico BI
(ver PRD_SmartFit_Dashboard_BI.md): cria o usuário admin, conecta o PostgreSQL,
e monta os 5 dashboards com os filtros interativos — sem precisar clicar em nada
na interface.

Seguro rodar mais de uma vez (idempotente: pula o que já existe).

Variáveis de ambiente esperadas:
    MB_URL              (padrão: http://localhost:3000)
    MB_ADMIN_EMAIL       (obrigatório)
    MB_ADMIN_PASSWORD    (obrigatório)
    MB_PG_HOST           (padrão: db)
    MB_PG_PORT           (padrão: 5432)
    MB_PG_DBNAME         (padrão: smartfit_db)
    MB_PG_USER           (padrão: metabase_reader)
    MB_PG_PASSWORD       (obrigatório)
"""
import os
import sys
import time
import requests

MB_URL = os.environ.get("MB_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.environ.get("MB_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("MB_ADMIN_PASSWORD")
DB_HOST = os.environ.get("MB_PG_HOST", "db")
DB_PORT = int(os.environ.get("MB_PG_PORT", "5432"))
DB_NAME = os.environ.get("MB_PG_DBNAME", "smartfit_db")
DB_USER = os.environ.get("MB_PG_USER", "metabase_reader")
DB_PASSWORD = os.environ.get("MB_PG_PASSWORD")
DB_DISPLAY_NAME = "Smart Fit DB"

if not ADMIN_EMAIL or not ADMIN_PASSWORD or not DB_PASSWORD:
    sys.exit("[ERRO] Defina MB_ADMIN_EMAIL, MB_ADMIN_PASSWORD e MB_PG_PASSWORD antes de rodar.")


def wait_health():
    print("[..] Aguardando o Metabase responder...")
    for _ in range(60):
        try:
            r = requests.get(f"{MB_URL}/api/health", timeout=5)
            if r.ok and r.json().get("status") == "ok":
                print("[OK] Metabase respondendo.")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    sys.exit("[ERRO] Metabase não respondeu em /api/health a tempo.")


def get_session():
    props = requests.get(f"{MB_URL}/api/session/properties").json()
    if not props.get("has-user-setup"):
        print("[..] Primeira execução: criando usuário admin...")
        r = requests.post(f"{MB_URL}/api/setup", json={
            "token": props["setup-token"],
            "user": {"first_name": "Smart", "last_name": "Fit", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            "prefs": {"site_name": "Smart Fit BI"},
        })
        r.raise_for_status()
        print(f"[OK] Admin criado: {ADMIN_EMAIL}")
        return r.json()["id"]

    print("[..] Instância já configurada, autenticando...")
    r = requests.post(f"{MB_URL}/api/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return r.json()["id"]


def hdrs(session):
    return {"X-Metabase-Session": session, "Content-Type": "application/json"}


def ensure_database(session):
    dbs = requests.get(f"{MB_URL}/api/database", headers=hdrs(session)).json()
    items = dbs.get("data", dbs) if isinstance(dbs, dict) else dbs
    for d in items:
        if d.get("name") == DB_DISPLAY_NAME:
            print(f"[OK] Banco '{DB_DISPLAY_NAME}' já conectado (id={d['id']}).")
            return d["id"]

    print(f"[..] Conectando ao PostgreSQL ({DB_HOST}:{DB_PORT}/{DB_NAME})...")
    r = requests.post(f"{MB_URL}/api/database", headers=hdrs(session), json={
        "engine": "postgres",
        "name": DB_DISPLAY_NAME,
        "details": {
            "host": DB_HOST, "port": DB_PORT, "dbname": DB_NAME,
            "user": DB_USER, "password": DB_PASSWORD, "ssl": False,
        },
        "is_full_sync": True,
    })
    r.raise_for_status()
    db_id = r.json()["id"]
    print(f"[OK] Conectado (id={db_id}). Aguardando sincronização de metadados...")
    for _ in range(30):
        info = requests.get(f"{MB_URL}/api/database/{db_id}", headers=hdrs(session)).json()
        if info.get("initial_sync_status") == "complete":
            print("[OK] Sincronizado.")
            break
        time.sleep(5)
    else:
        print("[ALERTA] Sincronização não confirmou 'complete' a tempo — seguindo mesmo assim.")
    return db_id


def get_field_map(session, db_id):
    meta = requests.get(f"{MB_URL}/api/database/{db_id}/metadata", headers=hdrs(session)).json()
    table_ids = {t["name"]: t["id"] for t in meta["tables"] if t["name"].startswith("vw_")}
    field_map = {}
    for name, tid in table_ids.items():
        tmeta = requests.get(f"{MB_URL}/api/table/{tid}/query_metadata", headers=hdrs(session)).json()
        for f in tmeta["fields"]:
            field_map[(name, f["name"])] = f["id"]
    return table_ids, field_map


def fld(field_map, table, col, base_type="type/Text"):
    return ["field", field_map[(table, col)], {"base-type": base_type}]


def find_card_by_name(session, name):
    cards = requests.get(f"{MB_URL}/api/card", headers=hdrs(session)).json()
    items = cards.get("data", cards) if isinstance(cards, dict) else cards
    for c in items:
        if c.get("name") == name and not c.get("archived"):
            return c["id"]
    return None


def find_dashboard_by_name(session, name):
    dashes = requests.get(f"{MB_URL}/api/dashboard", headers=hdrs(session)).json()
    items = dashes.get("data", dashes) if isinstance(dashes, dict) else dashes
    for d in items:
        if d.get("name") == name and not d.get("archived"):
            return d["id"]
    return None


def ensure_card(session, name, dataset_query, display="line"):
    existing = find_card_by_name(session, name)
    if existing:
        print(f"    [=] Card '{name}' já existe (id={existing}).")
        return existing
    r = requests.post(f"{MB_URL}/api/card", headers=hdrs(session), json={
        "name": name, "dataset_query": dataset_query, "display": display, "visualization_settings": {},
    })
    r.raise_for_status()
    cid = r.json()["id"]
    print(f"    [+] Card '{name}' criado (id={cid}).")
    return cid


def ensure_dashboard(session, name, parameters, dashcards):
    existing = find_dashboard_by_name(session, name)
    if existing:
        print(f"[=] Dashboard '{name}' já existe (id={existing}) — pulando.")
        return existing
    r = requests.post(f"{MB_URL}/api/dashboard", headers=hdrs(session), json={"name": name})
    r.raise_for_status()
    dash_id = r.json()["id"]
    r = requests.put(f"{MB_URL}/api/dashboard/{dash_id}", headers=hdrs(session), json={
        "parameters": parameters, "dashcards": dashcards,
    })
    r.raise_for_status()
    print(f"[+] Dashboard '{name}' criado (id={dash_id}).")
    return dash_id


def mbql_query(db_id, table_id, aggregation=None, breakout=None, order_by=None):
    q = {"source-table": table_id}
    if aggregation:
        q["aggregation"] = aggregation
    if breakout:
        q["breakout"] = breakout
    if order_by:
        q["order-by"] = order_by
    return {"type": "query", "database": db_id, "query": q}


def main():
    wait_health()
    session = get_session()
    db_id = ensure_database(session)
    table_ids, fm = get_field_map(session, db_id)

    T_UNIDADE = "vw_unidade_metrica_mensal"
    T_REGIAO = "vw_regiao_metrica_mensal"
    T_RISCO = "vw_risco_cancelamento"
    T_PREVENDA = "vw_pre_venda_mensal"

    # --- Dashboard 1: Comparação entre Unidades ---
    print("\n=== Dashboard: Comparação entre Unidades ===")
    c_ativos = ensure_card(session, "Tendencia de Ativos por Unidade", mbql_query(
        db_id, table_ids[T_UNIDADE],
        aggregation=[["sum", fld(fm, T_UNIDADE, "ativos", "type/Integer")]],
        breakout=[
            ["field", fm[(T_UNIDADE, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}],
            fld(fm, T_UNIDADE, "unidade"),
        ],
    ))
    c_cancel = ensure_card(session, "Taxa de Cancelamento por Unidade", mbql_query(
        db_id, table_ids[T_UNIDADE],
        aggregation=[["avg", fld(fm, T_UNIDADE, "taxa_cancelamento_pct", "type/Decimal")]],
        breakout=[
            ["field", fm[(T_UNIDADE, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}],
            fld(fm, T_UNIDADE, "unidade"),
        ],
    ))
    c_vendas = ensure_card(session, "Vendas por Unidade", mbql_query(
        db_id, table_ids[T_UNIDADE],
        aggregation=[["sum", fld(fm, T_UNIDADE, "vendas_mes", "type/Integer")]],
        breakout=[
            ["field", fm[(T_UNIDADE, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}],
            fld(fm, T_UNIDADE, "unidade"),
        ],
    ))
    c_tabela = ensure_card(session, "Detalhe Mensal por Unidade", mbql_query(
        db_id, table_ids[T_UNIDADE],
        order_by=[["desc", ["field", fm[(T_UNIDADE, "mes_referencia")], {"base-type": "type/Date"}]]],
    ), display="table")

    ensure_dashboard(session, "Comparacao entre Unidades",
        parameters=[{"id": "unidade_filter_1", "name": "Unidade", "slug": "unidade", "type": "string/=", "sectionId": "string"}],
        dashcards=[
            {"id": -1, "card_id": c_ativos, "row": 0, "col": 0, "size_x": 12, "size_y": 6,
             "parameter_mappings": [{"parameter_id": "unidade_filter_1", "card_id": c_ativos, "target": ["dimension", fld(fm, T_UNIDADE, "unidade")]}]},
            {"id": -2, "card_id": c_cancel, "row": 0, "col": 12, "size_x": 12, "size_y": 6,
             "parameter_mappings": [{"parameter_id": "unidade_filter_1", "card_id": c_cancel, "target": ["dimension", fld(fm, T_UNIDADE, "unidade")]}]},
            {"id": -3, "card_id": c_vendas, "row": 6, "col": 0, "size_x": 12, "size_y": 6,
             "parameter_mappings": [{"parameter_id": "unidade_filter_1", "card_id": c_vendas, "target": ["dimension", fld(fm, T_UNIDADE, "unidade")]}]},
            {"id": -4, "card_id": c_tabela, "row": 12, "col": 0, "size_x": 24, "size_y": 8,
             "parameter_mappings": [{"parameter_id": "unidade_filter_1", "card_id": c_tabela, "target": ["dimension", fld(fm, T_UNIDADE, "unidade")]}]},
        ])

    # --- Dashboard 2: Unidade vs Região ---
    print("\n=== Dashboard: Unidade vs Regiao ===")
    c_unidade_taxa = ensure_card(session, "Taxa de Cancelamento - Unidade Selecionada", mbql_query(
        db_id, table_ids[T_UNIDADE],
        aggregation=[["avg", fld(fm, T_UNIDADE, "taxa_cancelamento_pct", "type/Decimal")]],
        breakout=[["field", fm[(T_UNIDADE, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}]],
    ))
    c_regiao_taxa = ensure_card(session, "Taxa de Cancelamento - Media da Regiao", mbql_query(
        db_id, table_ids[T_REGIAO],
        aggregation=[["avg", fld(fm, T_REGIAO, "taxa_cancelamento_media_pct", "type/Decimal")]],
        breakout=[["field", fm[(T_REGIAO, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}]],
    ))
    ensure_dashboard(session, "Unidade vs Regiao",
        parameters=[
            {"id": "regiao_filter_1", "name": "Regiao", "slug": "regiao", "type": "string/=", "sectionId": "string"},
            {"id": "unidade_filter_2", "name": "Unidade", "slug": "unidade", "type": "string/=", "sectionId": "string", "filteringParameters": ["regiao_filter_1"]},
        ],
        dashcards=[
            {"id": -1, "card_id": c_unidade_taxa, "row": 0, "col": 0, "size_x": 12, "size_y": 8,
             "parameter_mappings": [{"parameter_id": "unidade_filter_2", "card_id": c_unidade_taxa, "target": ["dimension", fld(fm, T_UNIDADE, "unidade")]}]},
            {"id": -2, "card_id": c_regiao_taxa, "row": 0, "col": 12, "size_x": 12, "size_y": 8,
             "parameter_mappings": [{"parameter_id": "regiao_filter_1", "card_id": c_regiao_taxa, "target": ["dimension", fld(fm, T_REGIAO, "regiao")]}]},
        ])

    # --- Dashboard 3: Visão Geral da Rede ---
    print("\n=== Dashboard: Visao Geral da Rede ===")
    c_ativos_rede = ensure_card(session, "Total de Ativos na Rede (mes atual)", mbql_query(
        db_id, table_ids[T_REGIAO],
        aggregation=[["sum", fld(fm, T_REGIAO, "ativos_totais", "type/BigInteger")]],
        breakout=[["field", fm[(T_REGIAO, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}]],
    ))
    c_vendas_rede = ensure_card(session, "Vendas Totais na Rede por Mes", mbql_query(
        db_id, table_ids[T_REGIAO],
        aggregation=[["sum", fld(fm, T_REGIAO, "vendas_totais_mes", "type/BigInteger")]],
        breakout=[["field", fm[(T_REGIAO, "mes_referencia")], {"base-type": "type/Date", "temporal-unit": "month"}]],
    ))
    c_resumo_regiao = ensure_card(session, "Resumo por Regiao (mes mais recente)", mbql_query(
        db_id, table_ids[T_REGIAO],
        order_by=[["desc", ["field", fm[(T_REGIAO, "mes_referencia")], {"base-type": "type/Date"}]]],
    ), display="table")

    ensure_dashboard(session, "Visao Geral da Rede",
        parameters=[
            {"id": "pais_filter_geral", "name": "Pais", "slug": "pais", "type": "string/=", "sectionId": "string"},
            {"id": "regiao_filter_geral", "name": "Regiao", "slug": "regiao", "type": "string/=", "sectionId": "string", "filteringParameters": ["pais_filter_geral"]},
        ],
        dashcards=[
            {"id": -1, "card_id": c_ativos_rede, "row": 0, "col": 0, "size_x": 12, "size_y": 6,
             "parameter_mappings": [
                {"parameter_id": "pais_filter_geral", "card_id": c_ativos_rede, "target": ["dimension", fld(fm, T_REGIAO, "pais")]},
                {"parameter_id": "regiao_filter_geral", "card_id": c_ativos_rede, "target": ["dimension", fld(fm, T_REGIAO, "regiao")]},
             ]},
            {"id": -2, "card_id": c_vendas_rede, "row": 0, "col": 12, "size_x": 12, "size_y": 6,
             "parameter_mappings": [
                {"parameter_id": "pais_filter_geral", "card_id": c_vendas_rede, "target": ["dimension", fld(fm, T_REGIAO, "pais")]},
                {"parameter_id": "regiao_filter_geral", "card_id": c_vendas_rede, "target": ["dimension", fld(fm, T_REGIAO, "regiao")]},
             ]},
            {"id": -3, "card_id": c_resumo_regiao, "row": 6, "col": 0, "size_x": 24, "size_y": 8,
             "parameter_mappings": [
                {"parameter_id": "pais_filter_geral", "card_id": c_resumo_regiao, "target": ["dimension", fld(fm, T_REGIAO, "pais")]},
                {"parameter_id": "regiao_filter_geral", "card_id": c_resumo_regiao, "target": ["dimension", fld(fm, T_REGIAO, "regiao")]},
             ]},
        ])

    # --- Dashboard 4: Risco de Cancelamento ---
    print("\n=== Dashboard: Risco de Cancelamento ===")
    c_risco_nivel = ensure_card(session, "Unidades por Nivel de Risco", mbql_query(
        db_id, table_ids[T_RISCO],
        aggregation=[["count"]],
        breakout=[fld(fm, T_RISCO, "nivel_risco")],
    ), display="bar")
    c_risco_tabela = ensure_card(session, "Unidades por Risco de Cancelamento", mbql_query(
        db_id, table_ids[T_RISCO],
        order_by=[["desc", fld(fm, T_RISCO, "probabilidade_risco", "type/Decimal")]],
    ), display="table")

    ensure_dashboard(session, "Risco de Cancelamento",
        parameters=[
            {"id": "regiao_filter_risco", "name": "Regiao", "slug": "regiao", "type": "string/=", "sectionId": "string"},
            {"id": "mes_filter_risco", "name": "Mes", "slug": "mes", "type": "date/all-options", "sectionId": "date"},
        ],
        dashcards=[
            {"id": -1, "card_id": c_risco_nivel, "row": 0, "col": 0, "size_x": 24, "size_y": 6,
             "parameter_mappings": [
                {"parameter_id": "regiao_filter_risco", "card_id": c_risco_nivel, "target": ["dimension", fld(fm, T_RISCO, "regiao")]},
                {"parameter_id": "mes_filter_risco", "card_id": c_risco_nivel, "target": ["dimension", fld(fm, T_RISCO, "mes_referencia", "type/Date")]},
             ]},
            {"id": -2, "card_id": c_risco_tabela, "row": 6, "col": 0, "size_x": 24, "size_y": 10,
             "parameter_mappings": [
                {"parameter_id": "regiao_filter_risco", "card_id": c_risco_tabela, "target": ["dimension", fld(fm, T_RISCO, "regiao")]},
                {"parameter_id": "mes_filter_risco", "card_id": c_risco_tabela, "target": ["dimension", fld(fm, T_RISCO, "mes_referencia", "type/Date")]},
             ]},
        ])

    # --- Dashboard 5: Pré-vendas ---
    print("\n=== Dashboard: Pre-vendas ===")
    c_prevenda = ensure_card(session, "Pre-vendas - Detalhe por Unidade", mbql_query(
        db_id, table_ids[T_PREVENDA],
        order_by=[["desc", fld(fm, T_PREVENDA, "mes_referencia", "type/Date")]],
    ), display="table")

    ensure_dashboard(session, "Pre-vendas",
        parameters=[{"id": "regiao_filter_pv", "name": "Regiao", "slug": "regiao", "type": "string/=", "sectionId": "string"}],
        dashcards=[
            {"id": -1, "card_id": c_prevenda, "row": 0, "col": 0, "size_x": 24, "size_y": 10,
             "parameter_mappings": [{"parameter_id": "regiao_filter_pv", "card_id": c_prevenda, "target": ["dimension", fld(fm, T_PREVENDA, "regiao")]}]},
        ])

    print("\n[SUCESSO] Painel Analítico BI configurado. Acesse:", MB_URL)


if __name__ == "__main__":
    main()
