import os

HTML_CONTENT_1 = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Relatório Diário Smart Fit - 2026-08-20</title>
</head>
<body>
    <h1>Relatório Diário de Performance - 20/08/2026</h1>
    
    <h2>Brasil - SP</h2>
    <table class="report-table" border="1">
        <thead>
            <tr>
                <th rowspan="2">Sigla</th>
                <th rowspan="2">Nome Digital</th>
                <th rowspan="2">Inauguração</th>
                <th colspan="7">Ativos</th>
                <th colspan="2">Visitas</th>
                <th colspan="2">Conversão</th>
                <th colspan="2">Vendas Balcão Smart</th>
                <th colspan="2">Vendas Balcão Black</th>
                <th colspan="2">Vendas Balcão Fit</th>
                <th colspan="2">Vendas Balcão Black+</th>
                <th colspan="2">Vendas Balcão Studio</th>
                <th colspan="2">Vendas Web Smart</th>
                <th colspan="2">Vendas Web Black</th>
                <th colspan="2">Vendas Web Fit</th>
                <th colspan="2">Vendas Web Black+</th>
                <th colspan="2">Vendas Web Studio</th>
                <th colspan="2">Vendas Totem Smart</th>
                <th colspan="2">Vendas Totem Black</th>
                <th colspan="2">Vendas Totem Fit</th>
                <th colspan="2">Vendas Totem Black+</th>
                <th colspan="2">Vendas Totem Studio</th>
                <th colspan="2">Vendas Outros Smart</th>
                <th colspan="2">Vendas Outros Black</th>
                <th colspan="2">Vendas Outros Fit</th>
                <th colspan="2">Vendas Outros Black+</th>
                <th colspan="2">Vendas Outros Studio</th>
                <th colspan="2">Vendas Total</th>
            </tr>
            <tr>
                <th>Total</th>
                <th>Smart</th>
                <th>Black</th>
                <th>Fit</th>
                <th>Black+</th>
                <th>Studio</th>
                <th>Bloqueados</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
                <th>Dia</th>
                <th>Mês</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>SP01</td>
                <td>Paulista</td>
                <td>2015-03-20</td>
                <td>3500</td>
                <td>1000</td>
                <td>1500</td>
                <td>500</td>
                <td>300</td>
                <td>100</td>
                <td>100</td>
                <td>250</td>
                <td>6200</td>
                <td>8.5%</td>
                <td>9.2%</td>
                <!-- Vendas Balcao Smart -->
                <td>5</td><td>120</td>
                <!-- Vendas Balcao Black -->
                <td>10</td><td>250</td>
                <!-- Vendas Balcao Fit -->
                <td>2</td><td>50</td>
                <!-- Vendas Balcao Black+ -->
                <td>1</td><td>30</td>
                <!-- Vendas Balcao Studio -->
                <td>0</td><td>10</td>
                <!-- Vendas Web Smart -->
                <td>8</td><td>180</td>
                <!-- Vendas Web Black -->
                <td>12</td><td>300</td>
                <!-- Vendas Web Fit -->
                <td>3</td><td>70</td>
                <!-- Vendas Web Black+ -->
                <td>2</td><td>40</td>
                <!-- Vendas Web Studio -->
                <td>1</td><td>15</td>
                <!-- Vendas Totem Smart -->
                <td>1</td><td>20</td>
                <!-- Vendas Totem Black -->
                <td>2</td><td>40</td>
                <!-- Vendas Totem Fit -->
                <td>0</td><td>10</td>
                <!-- Vendas Totem Black+ -->
                <td>0</td><td>5</td>
                <!-- Vendas Totem Studio -->
                <td>0</td><td>2</td>
                <!-- Vendas Outros Smart -->
                <td>0</td><td>5</td>
                <!-- Vendas Outros Black -->
                <td>0</td><td>10</td>
                <!-- Vendas Outros Fit -->
                <td>0</td><td>2</td>
                <!-- Vendas Outros Black+ -->
                <td>0</td><td>1</td>
                <!-- Vendas Outros Studio -->
                <td>0</td><td>0</td>
                <!-- Vendas Total -->
                <td>47</td><td>1155</td>
            </tr>
            <tr>
                <td>SP02</td>
                <td>Berrini *</td>
                <td>2026-06-01</td>
                <td>800</td>
                <td>300</td>
                <td>400</td>
                <td>50</td>
                <td>20</td>
                <td>10</td>
                <td>20</td>
                <td>45</td>
                <td>1200</td>
                <td>-</td>
                <td>5.4%</td>
                <!-- Vendas Balcao Smart -->
                <td>1</td><td>20</td>
                <!-- Vendas Balcao Black -->
                <td>2</td><td>40</td>
                <!-- Vendas Balcao Fit -->
                <td>0</td><td>5</td>
                <!-- Vendas Balcao Black+ -->
                <td>0</td><td>2</td>
                <!-- Vendas Balcao Studio -->
                <td>0</td><td>1</td>
                <!-- Vendas Web Smart -->
                <td>3</td><td>60</td>
                <!-- Vendas Web Black -->
                <td>4</td><td>80</td>
                <!-- Vendas Web Fit -->
                <td>0</td><td>10</td>
                <!-- Vendas Web Black+ -->
                <td>0</td><td>4</td>
                <!-- Vendas Web Studio -->
                <td>0</td><td>2</td>
                <!-- Vendas Totem Smart -->
                <td>0</td><td>5</td>
                <!-- Vendas Totem Black -->
                <td>1</td><td>15</td>
                <!-- Vendas Totem Fit -->
                <td>0</td><td>1</td>
                <!-- Vendas Totem Black+ -->
                <td>0</td><td>0</td>
                <!-- Vendas Totem Studio -->
                <td>0</td><td>0</td>
                <!-- Vendas Outros Smart -->
                <td>0</td><td>1</td>
                <!-- Vendas Outros Black -->
                <td>0</td><td>2</td>
                <!-- Vendas Outros Fit -->
                <td>0</td><td>0</td>
                <!-- Vendas Outros Black+ -->
                <td>0</td><td>0</td>
                <!-- Vendas Outros Studio -->
                <td>0</td><td>0</td>
                <!-- Vendas Total -->
                <td>11</td><td>248</td>
            </tr>
        </tbody>
    </table>

    <h3>Transferências e Cancelamentos - Brasil - SP</h3>
    <table class="cancel-table" border="1">
        <thead>
            <tr>
                <th>Nome Digital</th>
                <th>Transferências Líquidas (Mês)</th>
                <th>Cancelados Smart</th>
                <th>Cancelados Black</th>
                <th>Cancelados Studio</th>
                <th>Cancelados Total</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Paulista</td>
                <td>-12.50</td>
                <td>15</td>
                <td>25</td>
                <td>2</td>
                <td>42</td>
            </tr>
            <tr>
                <td>Berrini *</td>
                <td>4.00</td>
                <td>5</td>
                <td>3</td>
                <td>0</td>
                <td>8</td>
            </tr>
        </tbody>
    </table>

    <p>* Unidade não atingiu o período de maturidade de 120 dias</p>
</body>
</html>
"""

def generate():
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    
    file_path = os.path.join(os.path.dirname(__file__), "smartfit_email_2026.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT_1)
    print(f"Fixture gerado em: {file_path}")

if __name__ == "__main__":
    generate()
