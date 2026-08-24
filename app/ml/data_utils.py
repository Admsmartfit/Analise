import pandas as pd

from app.ml.model_utils import FEATURE_ORDER, CATEGORICAL_COLS, preprocess_features


def preprocess_input_data(input_data, label_encoders):
    """Transforma um dicionário de entrada (formulário individual) num vetor de features
    na mesma ordem/codificação usada no treino.
    """
    row = {feat: input_data.get(feat, 0) for feat in FEATURE_ORDER}
    df = pd.DataFrame([row])
    X, _ = preprocess_features(df, label_encoders=label_encoders, fit=False)
    return X[0]


def validate_csv_data(df):
    """Valida um CSV de entrada para predição em lote."""
    validation_result = {"valid": True, "errors": []}

    if df.empty:
        validation_result["valid"] = False
        validation_result["errors"].append("O arquivo enviado está vazio.")
        return validation_result

    numeric_cols = [c for c in FEATURE_ORDER if c not in CATEGORICAL_COLS]
    missing_columns = [col for col in FEATURE_ORDER if col not in df.columns]
    if missing_columns:
        validation_result["valid"] = False
        validation_result["errors"].append(
            f"Colunas obrigatórias ausentes: {', '.join(missing_columns)}"
        )
        return validation_result

    for col in numeric_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.isna().any():
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"A coluna '{col}' deve conter apenas valores numéricos."
                )

    valid_tipo_operacao = ["Própria", "Franquia"]
    if "tipo_operacao" in df.columns:
        invalid = [v for v in df["tipo_operacao"].dropna().unique() if v not in valid_tipo_operacao]
        if invalid:
            validation_result["errors"].append(
                f"Valores inesperados em 'tipo_operacao': {invalid}. Esperado: {valid_tipo_operacao}"
            )

    return validation_result


def prepare_batch_data(df, label_encoders):
    """Prepara um DataFrame inteiro (linha a linha) para predição em lote."""
    processed_rows = []
    for _, row in df.iterrows():
        try:
            processed_rows.append(preprocess_input_data(row.to_dict(), label_encoders))
        except Exception:
            processed_rows.append(None)
    return processed_rows


FEATURE_DESCRIPTIONS = {
    "idade_unidade_meses": "Meses desde a inauguração da unidade até o mês de referência",
    "tipo_operacao": "Própria ou Franquia",
    "pais": "Código de país da unidade (ex: BR, MX, CL)",
    "total_ativos_fim_mes": "Total de alunos ativos ao final do mês",
    "variacao_ativos_mes": "Variação percentual de ativos vs. o mês anterior",
    "visitas_mes": "Total de visitas no mês",
    "conversao_mes": "Taxa de conversão do mês (%)",
    "vendas_geral_mes": "Total de vendas no mês",
    "transferencias_liquida_mes": "Saldo líquido de transferências de/para outras unidades no mês",
    "unidade_imatura": "Se a unidade ainda não atingiu 120 dias de operação (0/1)",
    "taxa_cancelamento_mes_anterior": "Taxa de cancelamento (cancelados / ativos) do mês anterior",
}
