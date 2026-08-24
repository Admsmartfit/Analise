FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema exigidas por lxml/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        libpq-dev \
        cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml.txt

COPY . .

# Usado só pelo serviço "web" (Flask). Outros serviços sobrescrevem o comando no docker-compose.
EXPOSE 5000
CMD ["python", "-m", "app.web.routes"]
