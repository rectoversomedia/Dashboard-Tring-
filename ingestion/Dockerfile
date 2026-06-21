FROM python:3.12-slim

WORKDIR /app

# Copy project metadata and source, then install from pyproject.toml.
# Dependencies come from [project].dependencies - no hardcoded versions here,
# so the image always matches what the project declares.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

RUN useradd -m appuser
USER appuser

ENTRYPOINT ["python", "-m", "tring_ingest"]
