import plotly.graph_objects as go
import pandas as pd
from sklearn.metrics import confusion_matrix


def create_risco_distribution_plot(y_data):
    """Distribuição de unidades entre Risco Normal e Alto Risco (dataset de treino/teste)."""
    counts = pd.Series(y_data).value_counts()
    labels = ["Risco Normal", "Alto Risco"]

    fig = go.Figure(data=[
        go.Bar(
            x=labels,
            y=[counts.get(0, 0), counts.get(1, 0)],
            text=[counts.get(0, 0), counts.get(1, 0)],
            textposition="auto",
            marker_color=["#2E8B57", "#DC143C"],
        )
    ])

    fig.update_layout(
        title="Distribuição de Risco de Cancelamento",
        xaxis_title="Classe",
        yaxis_title="Número de Unidades",
        showlegend=False,
        height=400,
    )
    return fig


def create_feature_importance_plot(feature_importances, feature_names):
    """Importância de cada feature nas predições do modelo."""
    importance_df = pd.DataFrame({
        "Feature": feature_names,
        "Importância": feature_importances,
    }).sort_values("Importância", ascending=True)

    fig = go.Figure(go.Bar(
        x=importance_df["Importância"],
        y=importance_df["Feature"],
        orientation="h",
        marker_color="#1f77b4",
        text=[f"{val:.3f}" for val in importance_df["Importância"]],
        textposition="auto",
    ))

    fig.update_layout(
        title="Importância das Features nas Predições",
        xaxis_title="Importância",
        yaxis_title="Feature",
        height=500,
    )
    return fig


def create_confusion_matrix_plot(y_true, y_pred):
    """Matriz de confusão do modelo."""
    cm = confusion_matrix(y_true, y_pred)
    labels = ["Risco Normal", "Alto Risco"]

    fig = go.Figure(data=go.Heatmap(
        z=cm,
        x=labels,
        y=labels,
        colorscale="Blues",
        text=cm,
        texttemplate="%{text}",
        textfont={"size": 16},
    ))

    fig.update_layout(
        title="Matriz de Confusão",
        xaxis_title="Previsto",
        yaxis_title="Real",
        height=400,
        width=400,
    )
    return fig


def create_probability_distribution_plot(probabilities):
    """Distribuição das probabilidades de risco previstas."""
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=probabilities,
        nbinsx=20,
        name="Distribuição de Probabilidade de Risco",
        marker_color="skyblue",
        opacity=0.7,
    ))

    fig.update_layout(
        title="Distribuição das Probabilidades de Risco",
        xaxis_title="Probabilidade de Alto Risco",
        yaxis_title="Número de Unidades",
        showlegend=False,
        height=400,
    )
    return fig


def create_risk_level_distribution(probabilities):
    """Distribuição das unidades por nível de risco (Baixo/Médio/Alto)."""
    risk_levels = []
    for prob in probabilities:
        if prob > 0.7:
            risk_levels.append("Alto")
        elif prob > 0.3:
            risk_levels.append("Médio")
        else:
            risk_levels.append("Baixo")

    risk_counts = pd.Series(risk_levels).value_counts()
    colors = {"Alto": "#DC143C", "Médio": "#FF8C00", "Baixo": "#2E8B57"}
    bar_colors = [colors[level] for level in risk_counts.index]

    fig = go.Figure(data=[
        go.Bar(
            x=risk_counts.index,
            y=risk_counts.values,
            text=risk_counts.values,
            textposition="auto",
            marker_color=bar_colors,
        )
    ])

    fig.update_layout(
        title="Distribuição de Unidades por Nível de Risco",
        xaxis_title="Nível de Risco",
        yaxis_title="Número de Unidades",
        showlegend=False,
        height=400,
    )
    return fig


def risk_level_from_probability(prob):
    if prob > 0.7:
        return "Alto"
    if prob > 0.3:
        return "Médio"
    return "Baixo"


def risk_emoji(level):
    return {"Alto": "🔴", "Médio": "🟡", "Baixo": "🟢"}.get(level, "")
