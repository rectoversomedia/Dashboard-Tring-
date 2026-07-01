FROM python:3.12-slim

WORKDIR /app

# install ingestion package from pyproject.toml (all deps declared there)
COPY ingestion/pyproject.toml ./ingestion/
COPY ingestion/src/ ./ingestion/src/
RUN pip install --no-cache-dir ./ingestion

# install dbt
RUN pip install --no-cache-dir dbt-bigquery==1.8.2

# copy dbt project
COPY transform/ ./transform/

# non-root user cannot write to /app/transform/target; redirect to /tmp
ENV DBT_TARGET_PATH=/tmp/dbt-target

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# pre-fetch dbt packages so the image is self-contained
RUN dbt deps --project-dir /app/transform --profiles-dir /app/transform

# Default CMD: minimal HTTP server so Cloud Run Service health check passes (Jenkins CI/CD uses gcloud run deploy).
# Cloud Run Jobs override this via --command/--args (extract: python -m tring_ingest --source <src>; dbt: dbt build ...).
CMD ["python", "-c", "import http.server, os; http.server.HTTPServer(('', int(os.environ.get('PORT', 8080))), http.server.BaseHTTPRequestHandler).serve_forever()"]
