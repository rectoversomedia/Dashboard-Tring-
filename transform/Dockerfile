FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir dbt-bigquery==1.8.2

COPY . .

RUN useradd -m dbtuser && chown -R dbtuser:dbtuser /app
USER dbtuser

RUN dbt deps --profiles-dir /app

ENTRYPOINT ["dbt", "build", "--profiles-dir", "/app", "--target", "prod"]
