FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
# Pango and a font: required by WeasyPrint for PDF reports
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY suites/ /app/suites/
RUN useradd -r -u 10001 medguard && chown -R medguard /app
USER medguard
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp/cache
EXPOSE 8000
CMD ["uvicorn", "medguard_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
