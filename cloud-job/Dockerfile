# python: パッチバージョンまで固定して再現性を確保（更新時は都度変更）
FROM python:3.11.11-slim

# uv: パッチバージョンまで固定して再現性を確保（最新パッチに更新する場合は都度変更）
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# uv設定: コンテナ向け最適化
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# 仮想環境パスを明示（ツール・デバッグ時に venv 場所を認識させるため）
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# DuckDB保存先ディレクトリ
ENV STOCKDATA_CACHE_DIR=/cache

# 立花証券 e-支店 API（実行時に --env で上書き）
ENV eAPI_URL=
ENV eAPI_USER_ID=
ENV eAPI_PASSWORD=

# J-Quants API（実行時に --env で上書き）
ENV JQUANTS_API_KEY=

WORKDIR /app

# 非rootユーザーとキャッシュディレクトリを事前作成
RUN adduser --disabled-password --gecos '' appuser \
    && mkdir -p /cache \
    && chown appuser:appuser /cache

# Layer 1: 依存関係のみインストール（キャッシュ効率化）
# sharing=locked: 並列ビルド時のキャッシュ競合を防止
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --only-group cloud-job --no-install-project

# Layer 2: ソースコード
COPY src/BackcastPro/ /app/src/BackcastPro/
COPY src/trading_data/ /app/src/trading_data/
COPY cloud-job/update_stocks_price.py /app/update_stocks_price.py
COPY cloud-job/split_only.py /app/split_only.py
COPY cloud-job/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

# update が部分失敗でも split を必ず実行する（entrypoint.sh で両方の終了コードを評価）
ENTRYPOINT ["/app/entrypoint.sh"]
CMD []
