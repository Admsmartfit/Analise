import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import warnings
warnings.filterwarnings("ignore")
from sklearn.metrics import roc_curve
from sklearn.model_selection import train_test_split

from app.db.database import get_connection
from app.ml.model_utils import (
    load_model, get_model_metrics, build_training_dataset, preprocess_features,
    FEATURE_ORDER, CATEGORICAL_COLS,
)
from app.ml.data_utils import preprocess_input_data, validate_csv_data, FEATURE_DESCRIPTIONS
from app.ml.visualization_utils import (
    create_risco_distribution_plot,
    create_feature_importance_plot,
    create_confusion_matrix_plot,
    create_probability_distribution_plot,
    create_risk_level_distribution,
    risk_level_from_probability,
    risk_emoji,
)

st.set_page_config(
    page_title="Risco de Cancelamento — Smart Fit",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def load_app_resources():
    model_data = load_model()
    conn = get_connection()
    try:
        X_raw, y_sample, _ = build_training_dataset(conn)
    finally:
        conn.close()
    X_sample, _ = preprocess_features(X_raw, label_encoders=model_data["label_encoders"], fit=False)
    return model_data, X_sample, y_sample


try:
    model_data, X_sample, y_sample = load_app_resources()
    model = model_data["model"]
    label_encoders = model_data["label_encoders"]
    MODEL_LOADED = True
except Exception as e:
    MODEL_LOADED = False
    LOAD_ERROR = str(e)
    model = None
    label_encoders = {}
    X_sample = None
    y_sample = None


def main():
    st.title("📉 Previsão de Risco de Cancelamento — Smart Fit")
    st.caption("Prevê, por unidade, o risco de aumento de cancelamentos no mês seguinte, usando os dados já capturados pelo pipeline de ingestão.")
    st.markdown("---")

    st.sidebar.title("Navegação")
    page = st.sidebar.selectbox(
        "Escolha uma seção:",
        ["🏠 Início", "🔮 Predição Individual", "📁 Predição em Lote", "📈 Analytics do Modelo", "ℹ️ Sobre"],
    )

    if not MODEL_LOADED:
        st.error(f"Não foi possível carregar o modelo: {LOAD_ERROR}")
        st.info("Rode `python -m app.cli train-churn-model` no terminal antes de usar este app.")
        return

    if page == "🏠 Início":
        show_home_page()
    elif page == "🔮 Predição Individual":
        show_individual_prediction()
    elif page == "📁 Predição em Lote":
        show_batch_prediction()
    elif page == "📈 Analytics do Modelo":
        show_model_analytics()
    elif page == "ℹ️ Sobre":
        show_about_page()


def show_home_page():
    st.header("Bem-vindo à Previsão de Risco de Cancelamento")

    metrics = get_model_metrics(model, model_data["X_test"], model_data["y_test"])

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Acurácia do Modelo", f"{metrics['accuracy']:.3f}")
    with col2:
        st.metric("Precisão", f"{metrics['precision']:.3f}")
    with col3:
        st.metric("Recall", f"{metrics['recall']:.3f}")

    st.markdown("---")
    st.subheader("📋 Features do Modelo")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Cadastro da Unidade:**
        - Idade da unidade (meses)
        - Tipo de operação (Própria/Franquia)
        - País
        - Unidade imatura (< 120 dias)
        """)
    with col2:
        st.markdown("""
        **Operação do Mês:**
        - Ativos ao fim do mês / variação vs. mês anterior
        - Visitas e conversão
        - Vendas e transferências
        - Taxa de cancelamento do mês anterior
        """)

    st.subheader("📊 Distribuição de Risco (dataset de treino)")
    fig = create_risco_distribution_plot(y_sample)
    st.plotly_chart(fig, use_container_width=True)


def show_individual_prediction():
    st.header("🔮 Predição Individual por Unidade")
    st.markdown("Preencha os dados de uma unidade (real ou hipotética) para estimar o risco de cancelamento no mês seguinte.")

    with st.form("prediction_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Cadastro")
            idade_unidade_meses = st.slider("Idade da unidade (meses)", 0, 120, 24)
            tipo_operacao = st.selectbox("Tipo de Operação", ["Própria", "Franquia"])
            pais = st.text_input("País (código, ex: BR, MX, CL)", "BR").upper()
            unidade_imatura = st.selectbox("Unidade imatura (< 120 dias)?", ["Não", "Sim"])

        with col2:
            st.subheader("Operação do Mês")
            total_ativos_fim_mes = st.number_input("Ativos ao fim do mês", 0, 20000, 300)
            variacao_ativos_mes = st.slider("Variação de ativos vs. mês anterior (%)", -50.0, 50.0, 0.0) / 100.0
            visitas_mes = st.number_input("Visitas no mês", 0, 200000, 3000)
            conversao_mes = st.number_input("Conversão do mês (%)", 0.0, 100.0, 8.0)
            vendas_geral_mes = st.number_input("Vendas no mês", 0, 5000, 40)
            transferencias_liquida_mes = st.number_input("Transferências líquidas do mês", -500.0, 500.0, 0.0)
            taxa_cancelamento_mes_anterior = st.slider("Taxa de cancelamento do mês anterior (%)", 0.0, 100.0, 3.0) / 100.0

        submitted = st.form_submit_button("🔮 Prever Risco")

        if submitted:
            input_data = {
                "idade_unidade_meses": idade_unidade_meses,
                "tipo_operacao": tipo_operacao,
                "pais": pais,
                "total_ativos_fim_mes": total_ativos_fim_mes,
                "variacao_ativos_mes": variacao_ativos_mes,
                "visitas_mes": visitas_mes,
                "conversao_mes": conversao_mes,
                "vendas_geral_mes": vendas_geral_mes,
                "transferencias_liquida_mes": transferencias_liquida_mes,
                "unidade_imatura": 1 if unidade_imatura == "Sim" else 0,
                "taxa_cancelamento_mes_anterior": taxa_cancelamento_mes_anterior,
            }

            try:
                processed = preprocess_input_data(input_data, label_encoders)
                proba = model.predict_proba([processed])[0]
                pred = model.predict([processed])[0]

                st.markdown("---")
                st.subheader("🎯 Resultado da Previsão")

                col1, col2, col3 = st.columns(3)
                risco_prob = proba[1]
                nivel = risk_level_from_probability(risco_prob)

                with col1:
                    st.metric("Probabilidade de Alto Risco", f"{risco_prob:.1%}")
                with col2:
                    st.metric("Nível de Risco", f"{risk_emoji(nivel)} {nivel}")
                with col3:
                    resultado = "Alto Risco" if pred == 1 else "Risco Normal"
                    st.metric("Classificação", resultado)

                st.subheader("🔍 Importância das Features nesta Predição")
                fig_importance = create_feature_importance_plot(model.feature_importances_, FEATURE_ORDER)
                st.plotly_chart(fig_importance, use_container_width=True)

            except Exception as e:
                st.error(f"Erro ao gerar a predição: {e}")


def show_batch_prediction():
    st.header("📁 Predição em Lote")
    st.markdown("Envie um CSV com uma linha por unidade/mês para prever o risco de várias unidades de uma vez.")

    uploaded_file = st.file_uploader("Escolha um arquivo CSV", type="csv")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.subheader("📊 Prévia dos Dados")
            st.dataframe(df.head(), use_container_width=True)

            validation_result = validate_csv_data(df)

            if validation_result["valid"]:
                st.success(f"✅ Validação bem-sucedida! {len(df)} registros encontrados.")

                if st.button("🚀 Rodar Predição em Lote"):
                    with st.spinner("Processando..."):
                        predictions, probabilities = [], []
                        for idx, row in df.iterrows():
                            try:
                                processed = preprocess_input_data(row.to_dict(), label_encoders)
                                proba = model.predict_proba([processed])[0]
                                pred = model.predict([processed])[0]
                                predictions.append(pred)
                                probabilities.append(proba[1])
                            except Exception as e:
                                st.warning(f"Erro na linha {idx}: {e}")
                                predictions.append(None)
                                probabilities.append(None)

                        df["Predicao_Risco"] = predictions
                        df["Probabilidade_Risco"] = probabilities
                        df["Nivel_Risco"] = df["Probabilidade_Risco"].apply(
                            lambda x: risk_level_from_probability(x) if x is not None else "Erro"
                        )

                        st.subheader("🎯 Resultados")
                        st.dataframe(df[["Predicao_Risco", "Probabilidade_Risco", "Nivel_Risco"]], use_container_width=True)

                        col1, col2, col3 = st.columns(3)
                        validas = df["Predicao_Risco"].dropna()
                        alto_risco = sum(validas == 1)

                        with col1:
                            st.metric("Total de Predições", len(df))
                        with col2:
                            st.metric("Unidades em Alto Risco", int(alto_risco))
                        with col3:
                            taxa = alto_risco / len(validas) if len(validas) > 0 else 0
                            st.metric("Taxa de Alto Risco", f"{taxa:.1%}")

                        csv_buffer = io.StringIO()
                        df.to_csv(csv_buffer, index=False)
                        st.download_button(
                            label="📥 Baixar Resultados",
                            data=csv_buffer.getvalue(),
                            file_name="predicoes_risco_cancelamento.csv",
                            mime="text/csv",
                        )
            else:
                st.error("❌ Validação falhou!")
                for error in validation_result["errors"]:
                    st.error(f"• {error}")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")

    st.subheader("📋 Modelo de CSV")
    st.markdown("Seu CSV deve conter as seguintes colunas:")
    sample_df = pd.DataFrame({
        "idade_unidade_meses": [24, 6],
        "tipo_operacao": ["Própria", "Franquia"],
        "pais": ["BR", "MX"],
        "total_ativos_fim_mes": [300, 120],
        "variacao_ativos_mes": [0.02, -0.08],
        "visitas_mes": [3000, 900],
        "conversao_mes": [8.5, 5.2],
        "vendas_geral_mes": [40, 15],
        "transferencias_liquida_mes": [0.0, -2.0],
        "unidade_imatura": [0, 1],
        "taxa_cancelamento_mes_anterior": [0.03, 0.09],
    })
    st.dataframe(sample_df, use_container_width=True)

    csv_buffer = io.StringIO()
    sample_df.to_csv(csv_buffer, index=False)
    st.download_button(
        label="📥 Baixar Modelo de CSV",
        data=csv_buffer.getvalue(),
        file_name="modelo_predicao_lote.csv",
        mime="text/csv",
    )


def show_model_analytics():
    st.header("📈 Analytics do Modelo")

    X_train, X_test, y_train, y_test = train_test_split(
        X_sample, y_sample, test_size=0.3, random_state=42
    )
    metrics = get_model_metrics(model, model_data["X_test"], model_data["y_test"])
    y_pred = model.predict(model_data["X_test"])
    y_pred_proba = model.predict_proba(model_data["X_test"])[:, 1]

    st.subheader("🎯 Métricas de Performance")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Acurácia", f"{metrics['accuracy']:.3f}")
    with col2:
        st.metric("Precisão", f"{metrics['precision']:.3f}")
    with col3:
        st.metric("Recall", f"{metrics['recall']:.3f}")
    with col4:
        roc_auc = metrics["roc_auc"]
        st.metric("ROC AUC", f"{roc_auc:.3f}" if not np.isnan(roc_auc) else "N/A")

    st.subheader("📊 Matriz de Confusão")
    st.plotly_chart(create_confusion_matrix_plot(model_data["y_test"], y_pred), use_container_width=True)

    if len(set(model_data["y_test"])) > 1:
        st.subheader("📈 Curva ROC")
        fpr, tpr, _ = roc_curve(model_data["y_test"], y_pred_proba)
        fig_roc = go.Figure()
        fig_roc.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"Curva ROC (AUC = {metrics['roc_auc']:.3f})"))
        fig_roc.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Classificador Aleatório", line=dict(dash="dash")))
        fig_roc.update_layout(title="Curva ROC", xaxis_title="Taxa de Falsos Positivos", yaxis_title="Taxa de Verdadeiros Positivos", height=500)
        st.plotly_chart(fig_roc, use_container_width=True)

    st.subheader("🔍 Importância das Features")
    st.plotly_chart(create_feature_importance_plot(model.feature_importances_, FEATURE_ORDER), use_container_width=True)

    st.subheader("🎯 Insights dos Dados")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_probability_distribution_plot(y_pred_proba), use_container_width=True)
    with col2:
        st.plotly_chart(create_risk_level_distribution(y_pred_proba), use_container_width=True)


def show_about_page():
    st.header("ℹ️ Sobre este Módulo")
    st.markdown(f"""
    ## 🎯 Visão Geral

    Este módulo prevê, **por unidade Smart Fit**, o risco de aumento de cancelamentos no mês
    seguinte, usando exclusivamente dados já capturados pelo pipeline de ingestão de e-mails
    (sem depender de dado de aluno individual).

    Arquitetura adaptada do projeto open-source
    [Rinkyshu200/customer-churn-dashboard](https://github.com/Rinkyshu200/customer-churn-dashboard)
    (MIT License) — ver `PRD_SmartFit_Churn_Prediction.md` para o detalhamento completo.

    ## 🤖 Modelo

    - **Algoritmo:** Decision Tree Classifier
    - **Grão de treino:** unidade × mês
    - **Features:** {len(FEATURE_ORDER)} atributos (cadastro + operação do mês)
    - **Alvo:** unidade no top 25% de taxa de cancelamento do mês seguinte, comparada à rede toda

    ## ⚠️ Notas Importantes

    - O corte de "alto risco" (percentil 75 da rede) é um valor inicial — deve ser
      validado com quem entende o negócio.
    - Previsões devem ser usadas como apoio à decisão, não como verdade absoluta.
    - Retreinar o modelo periodicamente conforme novos meses de dado chegam
      (`python -m app.cli train-churn-model`).
    """)


if __name__ == "__main__":
    main()
