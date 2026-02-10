FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=True
ENV PYTHONPATH=/app/src
ENV UV_LINK_MODE=copy

# DuckDB保存先ディレクトリ
ENV STOCKDATA_CACHE_DIR=/cache

# 立花証券 e-支店 API
ENV eAPI_URL=
ENV eAPI_USER_ID=
ENV eAPI_PASSWORD=

# J-Quants API
ENV JQUANTS_API_KEY=


WORKDIR /app

# Layer 1: 依存関係のみインストール（キャッシュ効率化）
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --only-group cloud-job --no-install-project

# Layer 2: ソースコード
COPY src/BackcastPro/ /app/src/BackcastPro/
COPY src/trading_data/ /app/src/trading_data/
COPY cloud-job/update_stocks_price.py /app/update_stocks_price.py

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "/app/update_stocks_price.py"]
