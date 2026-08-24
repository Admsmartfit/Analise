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
]

TARGET_COL = "alto_risco_cancelamento"


class InsufficientDataError(Exception):
    """Levantado quando não há histórico suficiente para treinar o modelo (FR-CH-03)."""


def _fetch_monthly_raw(conn):
    """Busca os dados diários brutos necessários para a agregação mensal por unidade."""
    query = """
        SELECT
            u.id AS unidade_id,
            u.tipo_operacao,
            u.pais,
            u.data_inauguracao,
            f.data_referencia,
            f.total_ativos,
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
        ORDER BY u.id, f.data_referencia;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

    return pd.DataFrame(rows, columns=columns)


def compute_monthly_features(conn):
    """Monta a matriz de features unidade x mês, com engenharia de atributos aplicada.

    Reaproveitada tanto pelo treino (build_training_dataset) quanto pela predição em lote
    (predict_for_month), para nunca haver divergência entre a feature vista no treino e a
    feature vista na hora de prever.
    """
    raw = _fetch_monthly_raw(conn)
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
        tipo_operacao=("tipo_operacao", "last"),
        pais=("pais", "last"),
        data_inauguracao=("data_inauguracao", "last"),
        total_ativos_fim_mes=("total_ativos", "last"),
        visitas_mes=("visitas_mes", "mean"),
        conversao_mes=("conversao_mes", "mean"),
        vendas_geral_mes=("vendas_geral_mes", "last"),
        transferencias_liquida_mes=("transferencias_liquida_mes", "last"),
        unidade_imatura=("unidade_imatura", "max"),
        cancelados_total_mes=("cancelados_total_mes", "last"),
    ).reset_index()

    df = last_per_month.sort_values(["unidade_id", "mes_referencia"]).reset_index(drop=True)

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


def predict_for_month(conn, model_data, mes_referencia):
    """Roda o modelo já treinado sobre todas as unidades disponíveis num mês específico.

    `mes_referencia` é uma string 'YYYY-MM'. Retorna um DataFrame com unidade_id,
    probabilidade_risco e nivel_risco — pronto para persistir em `churn_predicoes`.
    """
    from app.ml.visualization_utils import risk_level_from_probability

    df = compute_monthly_features(conn)
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
    }

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    return model, metrics, model_data


def load_model():
    """Carrega o modelo treinado do disco. Levanta FileNotFoundError se ainda não existir."""
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Modelo não encontrado em {MODEL_PATH}. Rode 'python -m app.cli train-churn-model' primeiro."
        )

    with open(MODEL_PATH, "rb") as f:
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
