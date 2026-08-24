import os
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "app", "ml", "models", "churn_model.pkl")

# Ponto em aberto documentado no PRD (Seção 5): corte de "alto risco" = top 25% da rede.
# Ajustar aqui não exige mudança de arquitetura.
RISK_THRESHOLD_PERCENTILE = 0.75

# Mínimo de meses de histórico consolidado exigido antes de permitir o treino (FR-CH-03).
MIN_MONTHS_REQUIRED = 3

CATEGORICAL_COLS = ["tipo_operacao", "pais"]

# Mix de planos (% dos ativos em cada plano) — captura o "tipo de público" de cada
# unidade (ex: Black tem acesso à rede toda + fidelidade; SmartAcesso não tem
# fidelidade; FitAcesso é restrito à unidade + fidelidade), sem precisar de um
# modelo separado por unidade.
PLAN_MIX_COLS = [
    "pct_ativos_smart",
    "pct_ativos_black",
    "pct_ativos_fit",
    "pct_ativos_black_plus",
    "pct_ativos_studio",
]

FEATURE_ORDER = [
    "idade_unidade_meses",
    "tipo_operacao",
    "pais",
    "total_ativos_fim_mes",
    "variacao_ativos_mes",
    "visitas_mes",
    "conversao_mes",
    "vendas_geral_mes",
    "transferencias_liquida_mes",
    "unidade_imatura",
    "taxa_cancelamento_mes_anterior",
] + PLAN_MIX_COLS

TARGET_COL = "alto_risco_cancelamento"

# Nº de unidades "pares" (mesma região + perfil de planos parecido) usadas para
# treinar um modelo local com dado suficiente quando se pede retreino por unidade.
DEFAULT_N_PEERS = 40
MIN_PEER_ROWS_REQUIRED = 60


class InsufficientDataError(Exception):
    """Levantado quando não há histórico suficiente para treinar o modelo (FR-CH-03)."""


def _fetch_monthly_raw(conn, unidade_ids=None):
    """Busca os dados diários brutos necessários para a agregação mensal por unidade.

    Se `unidade_ids` for informado, restringe a busca a essas unidades (usado no
    retreino local por unidade, para não carregar a rede inteira à toa).
    """
    query = """
        SELECT
            u.id AS unidade_id,
            u.nome_digital,
            u.regiao_uf,
            u.tipo_operacao,
            u.pais,
            u.data_inauguracao,
            f.data_referencia,
            f.total_ativos,
            f.ativos_smart,
            f.ativos_black,
            f.ativos_fit,
            f.ativos_black_plus,
            f.ativos_studio,
            f.visitas_mes,
            f.conversao_mes,
            f.vendas_geral_mes,
            f.transferencias_liquida_mes,
            f.unidade_imatura,
            COALESCE(c.qtd_mes, 0) AS cancelados_total_mes
        FROM fato_metricas_diarias f
        JOIN dim_unidade u ON u.id = f.unidade_id
        LEFT JOIN fato_cancelamentos_detalhada c
            ON c.fato_diaria_id = f.id AND c.plano = 'total'
        {where_clause}
        ORDER BY u.id, f.data_referencia;
    """
    params = None
    where_clause = ""
    if unidade_ids:
        where_clause = "WHERE u.id = ANY(%s)"
        params = (list(unidade_ids),)

    with conn.cursor() as cur:
        cur.execute(query.format(where_clause=where_clause), params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return pd.DataFrame(rows, columns=columns)


def compute_monthly_features(conn, unidade_ids=None):
    """Monta a matriz de features unidade x mês, com engenharia de atributos aplicada.

    Reaproveitada pelo treino global (build_training_dataset), pela predição em lote
    (predict_for_month) e pelo treino local por unidade (train_local_model_for_unit),
    para nunca haver divergência entre a feature vista no treino e a vista na hora de prever.
    """
    raw = _fetch_monthly_raw(conn, unidade_ids=unidade_ids)
    if raw.empty:
        raise InsufficientDataError(
            "Nenhum dado encontrado em fato_metricas_diarias. Rode o backfill de e-mails antes de treinar."
        )

    raw["data_referencia"] = pd.to_datetime(raw["data_referencia"])
    raw["mes_referencia"] = raw["data_referencia"].dt.to_period("M")

    # Dentro de cada unidade/mês, os campos "...mes" (total_ativos, vendas_geral_mes,
    # transferencias_liquida_mes, cancelados_total_mes) são acumulados crescentes ao longo
    # do mês no próprio e-mail — o valor do ÚLTIMO dia disponível no mês é o total do mês.
    raw_sorted = raw.sort_values(["unidade_id", "mes_referencia", "data_referencia"])
    last_per_month = raw_sorted.groupby(["unidade_id", "mes_referencia"]).agg(
        nome_digital=("nome_digital", "last"),
        regiao_uf=("regiao_uf", "last"),
        tipo_operacao=("tipo_operacao", "last"),
        pais=("pais", "last"),
        data_inauguracao=("data_inauguracao", "last"),
        total_ativos_fim_mes=("total_ativos", "last"),
        ativos_smart=("ativos_smart", "last"),
        ativos_black=("ativos_black", "last"),
        ativos_fit=("ativos_fit", "last"),
        ativos_black_plus=("ativos_black_plus", "last"),
        ativos_studio=("ativos_studio", "last"),
        visitas_mes=("visitas_mes", "mean"),
        conversao_mes=("conversao_mes", "mean"),
        vendas_geral_mes=("vendas_geral_mes", "last"),
        transferencias_liquida_mes=("transferencias_liquida_mes", "last"),
        unidade_imatura=("unidade_imatura", "max"),
        cancelados_total_mes=("cancelados_total_mes", "last"),
    ).reset_index()

    df = last_per_month.sort_values(["unidade_id", "mes_referencia"]).reset_index(drop=True)

    # Mix de planos: % dos ativos da unidade em cada plano naquele mês.
    for plano_col, pct_col in zip(
        ["ativos_smart", "ativos_black", "ativos_fit", "ativos_black_plus", "ativos_studio"],
        PLAN_MIX_COLS,
    ):
        df[pct_col] = np.where(
            df["total_ativos_fim_mes"] > 0,
            df[plano_col] / df["total_ativos_fim_mes"],
            0.0,
        )

    # Taxa de cancelamento do próprio mês (base para as features de mês anterior/seguinte)
    df["taxa_cancelamento_mes"] = np.where(
        df["total_ativos_fim_mes"] > 0,
        df["cancelados_total_mes"] / df["total_ativos_fim_mes"],
        0.0,
    )

    # Features/alvo que dependem de meses vizinhos, calculadas por unidade
    df["mes_ordinal"] = df["mes_referencia"].apply(lambda p: p.ordinal)
    df = df.sort_values(["unidade_id", "mes_ordinal"])

    grouped = df.groupby("unidade_id")
    df["total_ativos_mes_anterior"] = grouped["total_ativos_fim_mes"].shift(1)
    df["taxa_cancelamento_mes_anterior"] = grouped["taxa_cancelamento_mes"].shift(1)
    df["taxa_cancelamento_mes_seguinte"] = grouped["taxa_cancelamento_mes"].shift(-1)

    df["variacao_ativos_mes"] = np.where(
        (df["total_ativos_mes_anterior"].notna()) & (df["total_ativos_mes_anterior"] > 0),
        (df["total_ativos_fim_mes"] - df["total_ativos_mes_anterior"]) / df["total_ativos_mes_anterior"],
        0.0,
    )

    df["idade_unidade_meses"] = (
        (df["mes_referencia"].dt.year - pd.to_datetime(df["data_inauguracao"]).dt.year) * 12
        + (df["mes_referencia"].dt.month - pd.to_datetime(df["data_inauguracao"]).dt.month)
    ).clip(lower=0)

    df["taxa_cancelamento_mes_anterior"] = df["taxa_cancelamento_mes_anterior"].fillna(0.0)
    df["unidade_imatura"] = df["unidade_imatura"].astype(int)

    return df


def list_units_with_data(conn):
    """Lista as unidades com histórico suficiente para retreino local, para preencher
    um seletor de unidade na interface (ordenado por nome).
    """
    df = compute_monthly_features(conn)
    resumo = df.groupby("unidade_id").agg(
        nome_digital=("nome_digital", "last"),
        regiao_uf=("regiao_uf", "last"),
        pais=("pais", "last"),
        n_meses=("mes_referencia", "nunique"),
    ).reset_index()
    return resumo.sort_values(["nome_digital", "regiao_uf"])


def find_peer_units(conn, unidade_id, n_peers=DEFAULT_N_PEERS):
    """Encontra as unidades mais parecidas com `unidade_id` para servir de grupo de
    comparação num treino local: prioriza a mesma região e, dentro dela, o perfil de
    planos (mix % Smart/Black/Fit/Black+/Studio) mais próximo. Se a região não tiver
    unidades suficientes, expande para o mesmo país e, por último, para a rede toda.

    Retorna (peer_ids, info_da_unidade_alvo). peer_ids NÃO inclui a própria unidade.
    """
    df = compute_monthly_features(conn)

    if unidade_id not in df["unidade_id"].values:
        raise InsufficientDataError(
            f"Unidade {unidade_id} não tem histórico em fato_metricas_diarias."
        )

    perfil = df.groupby("unidade_id").agg(
        nome_digital=("nome_digital", "last"),
        regiao_uf=("regiao_uf", "last"),
        pais=("pais", "last"),
        n_meses=("mes_referencia", "nunique"),
        **{col: (col, "mean") for col in PLAN_MIX_COLS},
    )

    alvo = perfil.loc[unidade_id]

    mesma_regiao = perfil[(perfil["regiao_uf"] == alvo["regiao_uf"]) & (perfil.index != unidade_id)]
    candidatos = mesma_regiao
    if len(candidatos) < n_peers:
        mesmo_pais = perfil[
            (perfil["pais"] == alvo["pais"])
            & (perfil.index != unidade_id)
            & (~perfil.index.isin(candidatos.index))
        ]
        candidatos = pd.concat([candidatos, mesmo_pais])
    if len(candidatos) < n_peers:
        resto = perfil[(perfil.index != unidade_id) & (~perfil.index.isin(candidatos.index))]
        candidatos = pd.concat([candidatos, resto])

    diffs = candidatos[PLAN_MIX_COLS].astype(float) - alvo[PLAN_MIX_COLS].astype(float)
    candidatos = candidatos.copy()
    candidatos["distancia_perfil"] = np.sqrt((diffs ** 2).sum(axis=1))
    candidatos = candidatos.sort_values("distancia_perfil")

    peer_ids = candidatos.index[:n_peers].tolist()

    return peer_ids, {
        "nome_digital": alvo["nome_digital"],
        "regiao_uf": alvo["regiao_uf"],
        "pais": alvo["pais"],
        "n_meses": int(alvo["n_meses"]),
    }


def train_local_model_for_unit(conn, unidade_id, n_peers=DEFAULT_N_PEERS):
    """Treina um modelo LOCAL para uma unidade específica, usando o histórico dela +
    o de unidades parecidas (mesma região/país + perfil de planos similar) como grupo
    de comparação. Uma unidade sozinha (~24 meses) não tem dado suficiente para um
    modelo confiável isolado — juntar pares reais e comparáveis resolve isso sem
    "misturar" unidades muito diferentes.
    """
    peer_ids, unidade_info = find_peer_units(conn, unidade_id, n_peers=n_peers)
    grupo_ids = [unidade_id] + peer_ids

    df = compute_monthly_features(conn, unidade_ids=grupo_ids)
    trainable = df.dropna(subset=["taxa_cancelamento_mes_seguinte"]).copy()

    if len(trainable) < MIN_PEER_ROWS_REQUIRED:
        raise InsufficientDataError(
            f"Mesmo somando a unidade e {len(peer_ids)} unidades parecidas, só há "
            f"{len(trainable)} linhas de treino disponíveis (mínimo recomendado: "
            f"{MIN_PEER_ROWS_REQUIRED}). Rode mais backfill histórico antes de tentar de novo."
        )

    threshold = trainable["taxa_cancelamento_mes_seguinte"].quantile(RISK_THRESHOLD_PERCENTILE)
    trainable[TARGET_COL] = (trainable["taxa_cancelamento_mes_seguinte"] > threshold).astype(int)

    if trainable[TARGET_COL].nunique() < 2:
        raise InsufficientDataError(
            "As unidades desse grupo de comparação ficaram todas na mesma classe de risco "
            "— tente novamente com mais unidades pares (aumente n_peers) ou mais histórico."
        )

    X_raw = trainable[FEATURE_ORDER].copy()
    y = trainable[TARGET_COL].values

    X, label_encoders = preprocess_features(X_raw, fit=True)

    test_size = 0.2 if len(X) >= 50 else 0.3
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
    except ValueError:
        # Classe minoritária pequena demais para estratificar num grupo pequeno
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

    # Árvore mais rasa que o modelo global: menos dado disponível, mais risco de overfit.
    model = DecisionTreeClassifier(
        max_depth=6,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_pred_proba) if len(set(y_test)) > 1 else float("nan"),
    }

    versao_modelo = f"local_u{unidade_id}_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    model_data = {
        "model": model,
        "feature_names": FEATURE_ORDER,
        "label_encoders": label_encoders,
        "risk_threshold": threshold,
        "X_test": X_test,
        "y_test": y_test,
        "versao_modelo": versao_modelo,
        "treinado_em": datetime.now().isoformat(),
        "n_amostras_treino": len(X_train),
        "n_amostras_teste": len(X_test),
        "escopo": "local",
        "unidade_id": unidade_id,
        "unidade_nome": unidade_info["nome_digital"],
        "unidade_regiao": unidade_info["regiao_uf"],
        "peer_ids": peer_ids,
        "n_peers": len(peer_ids),
    }

    path = get_model_path(unidade_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model_data, f)

    return model, metrics, model_data


def get_model_path(unidade_id=None):
    """Caminho do arquivo do modelo: global (padrão) ou local de uma unidade específica."""
    if unidade_id is None:
        return MODEL_PATH
    return os.path.join(BASE_DIR, "app", "ml", "models", f"churn_model_unidade_{unidade_id}.pkl")


def build_training_dataset(conn):
    """Monta o dataset de treino real (unidade x mês) a partir do banco Smart Fit.

    Substitui create_telco_dataset() do repositório de referência, que gerava dado sintético.
    """
    df = compute_monthly_features(conn)

    n_months = df["mes_referencia"].nunique()
    if n_months < MIN_MONTHS_REQUIRED:
        raise InsufficientDataError(
            f"Apenas {n_months} mês(es) de histórico consolidado disponível(is). "
            f"São necessários pelo menos {MIN_MONTHS_REQUIRED} meses consecutivos para treinar com confiabilidade. "
            "Rode mais backfill de e-mails históricos antes de treinar o modelo."
        )

    # Só linhas com "mês seguinte" conhecido servem para treino (o alvo depende dele)
    trainable = df.dropna(subset=["taxa_cancelamento_mes_seguinte"]).copy()
    if trainable.empty:
        raise InsufficientDataError(
            "Nenhuma unidade tem um mês seguinte completo no histórico ainda — "
            "impossível calcular o alvo de treino."
        )

    threshold = trainable["taxa_cancelamento_mes_seguinte"].quantile(RISK_THRESHOLD_PERCENTILE)
    trainable[TARGET_COL] = (trainable["taxa_cancelamento_mes_seguinte"] > threshold).astype(int)

    if trainable[TARGET_COL].nunique() < 2:
        raise InsufficientDataError(
            "Todas as unidades ficaram na mesma classe de risco com o histórico atual "
            "(dado insuficiente para separar 'alto risco' de 'risco normal'). "
            "Rode mais backfill antes de treinar."
        )

    X = trainable[FEATURE_ORDER].copy()
    y = trainable[TARGET_COL].values

    return X, y, threshold


def predict_for_month(conn, model_data, mes_referencia, unidade_id=None):
    """Roda o modelo já treinado sobre as unidades disponíveis num mês específico.

    `mes_referencia` é uma string 'YYYY-MM'. Se `unidade_id` for informado, restringe
    a predição a essa unidade só (uso esperado ao usar um modelo local por unidade —
    aplicar um modelo local a outras unidades fora do seu grupo de treino não é
    válido). Retorna um DataFrame com unidade_id, probabilidade_risco e nivel_risco —
    pronto para persistir em `churn_predicoes`.
    """
    from app.ml.visualization_utils import risk_level_from_probability

    df = compute_monthly_features(conn, unidade_ids=[unidade_id] if unidade_id else None)
    periodo = pd.Period(mes_referencia, freq="M")
    month_df = df[df["mes_referencia"] == periodo].copy()

    if month_df.empty:
        raise InsufficientDataError(f"Nenhum dado encontrado para o mês {mes_referencia}.")

    X_raw = month_df[FEATURE_ORDER]
    X, _ = preprocess_features(X_raw, label_encoders=model_data["label_encoders"], fit=False)

    probabilidades = model_data["model"].predict_proba(X)[:, 1]

    result = month_df[["unidade_id"]].copy()
    result["mes_referencia"] = periodo.to_timestamp().date()
    result["probabilidade_risco"] = probabilidades
    result["nivel_risco"] = [risk_level_from_probability(p) for p in probabilidades]

    return result


def preprocess_features(X, label_encoders=None, fit=False):
    """Codifica as colunas categóricas em X. Se fit=True, cria e retorna novos encoders."""
    X = X.copy()
    if fit:
        label_encoders = {}
        for col in CATEGORICAL_COLS:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            label_encoders[col] = le
    else:
        for col in CATEGORICAL_COLS:
            le = label_encoders[col]
            X[col] = X[col].astype(str).map(
                lambda v: le.transform([v])[0] if v in le.classes_ else 0
            )

    return X[FEATURE_ORDER].astype(float).values, label_encoders


def train_model(conn):
    """Treina e salva o modelo de risco de cancelamento a partir do banco real."""
    X_raw, y, threshold = build_training_dataset(conn)

    X, label_encoders = preprocess_features(X_raw, fit=True)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = DecisionTreeClassifier(
        max_depth=10,
        min_samples_split=20,
        min_samples_leaf=10,
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_pred_proba) if len(set(y_test)) > 1 else float("nan"),
    }

    versao_modelo = datetime.now().strftime("%Y%m%d_%H%M%S")

    model_data = {
        "model": model,
        "feature_names": FEATURE_ORDER,
        "label_encoders": label_encoders,
        "risk_threshold": threshold,
        "X_test": X_test,
        "y_test": y_test,
        "versao_modelo": versao_modelo,
        "treinado_em": datetime.now().isoformat(),
        "n_amostras_treino": len(X_train),
        "n_amostras_teste": len(X_test),
        "escopo": "global",
    }

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    return model, metrics, model_data


def load_model(unidade_id=None):
    """Carrega o modelo treinado do disco: global (padrão) ou local de uma unidade.

    Levanta FileNotFoundError se ainda não existir.
    """
    path = get_model_path(unidade_id)
    if not os.path.exists(path):
        if unidade_id is None:
            raise FileNotFoundError(
                f"Modelo não encontrado em {path}. Rode 'python -m app.cli train-churn-model' primeiro."
            )
        raise FileNotFoundError(
            f"Ainda não existe um modelo local para a unidade {unidade_id}. "
            f"Rode 'python -m app.cli train-churn-model --unit-id {unidade_id}' primeiro."
        )

    with open(path, "rb") as f:
        model_data = pickle.load(f)

    return model_data


def get_model_metrics(model, X_test, y_test):
    """Calcula métricas de performance do modelo sobre um conjunto de teste."""
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_pred_proba) if len(set(y_test)) > 1 else float("nan"),
    }
