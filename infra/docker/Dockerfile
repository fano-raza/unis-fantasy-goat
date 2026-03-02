FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY infra/docker/requirements-deploy.txt /tmp/requirements-deploy.txt
RUN pip install --no-cache-dir -r /tmp/requirements-deploy.txt

COPY . /app

# Default command can be overridden per-service in compose.
CMD ["python", "-m", "services.gdoc_updater.entrypoint"]
