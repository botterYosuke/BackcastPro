"""Local file server for BackcastPro.

Serves .duckdb files from a local directory, exposed as HTTP GET.
Deployed on Cloud Run.
"""

import logging
import os
import re
from typing import List, Optional

import duckdb as _duckdb
import strawberry
from dotenv import load_dotenv
from flask import Flask, send_from_directory
from strawberry.flask.views import GraphQLView
from werkzeug.exceptions import HTTPException, NotFound

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("STOCKDATA_CACHE_DIR", "/cache")

# Whitelist: only allow known file patterns
ALLOWED_PATHS = re.compile(
    r"^jp/(stocks_daily/(?:\d+|mother)\.duckdb|stocks_board/\d+\.duckdb|stocks_minute/\d+\.duckdb|listed_info\.duckdb)$"
)


@app.route("/")
def health():
    return "OK", 200


@app.route("/<path:file_path>", methods=["GET"])
def download_file(file_path: str):
    if not ALLOWED_PATHS.match(file_path):
        return "Not Found", 404

    directory = DATA_DIR
    logger.info("Serving: %s", file_path)
    try:
        return send_from_directory(
            directory, file_path, mimetype="application/octet-stream"
        )
    except NotFound:
        logger.warning("File not found: %s", file_path)
        return "Not Found", 404


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return e
    logger.error("Unexpected error: %s", e, exc_info=True)
    return "Internal error", 500


MOTHER_DB_PATH = os.path.join(DATA_DIR, "jp", "stocks_daily", "mother.duckdb")

# SQL injection 対策ホワイトリスト
_ORDER_MAP = {"desc": "DESC", "asc": "ASC"}


@strawberry.type
class StockRankingItem:
    code: str
    close: float
    prev_close: Optional[float]
    gain_rate: Optional[float]
    volume: Optional[float]
    rank: int


def _fetch_gain_ranking(
    order_key: str, date: str, limit: int
) -> List[StockRankingItem]:
    """mother.duckdb から値上がり/値下がり率ランキングを取得"""
    order = _ORDER_MAP[order_key]
    sql = f"""
    WITH target AS (
        SELECT "Code", "Close", "Volume"
        FROM stocks_daily WHERE "Date" = ?
    ),
    prev AS (
        SELECT s."Code", s."Close" AS PrevClose
        FROM stocks_daily s
        INNER JOIN (
            SELECT "Code", MAX("Date") AS PrevDate
            FROM stocks_daily WHERE "Date" < ?
            GROUP BY "Code"
        ) p ON s."Code" = p."Code" AND s."Date" = p.PrevDate
    )
    SELECT
        t."Code",
        t."Close",
        pr.PrevClose,
        (t."Close" - pr.PrevClose) / pr.PrevClose * 100 AS GainRate,
        t."Volume",
        ROW_NUMBER() OVER (ORDER BY GainRate {order}) AS Rank
    FROM target t
    JOIN prev pr ON t."Code" = pr."Code"
    WHERE pr.PrevClose > 0
    ORDER BY GainRate {order}
    LIMIT ?
    """
    with _duckdb.connect(MOTHER_DB_PATH, read_only=True) as con:
        rows = con.execute(sql, [date, date, limit]).fetchall()
    return [
        StockRankingItem(
            code=r[0],
            close=r[1],
            prev_close=r[2],
            gain_rate=round(r[3], 4),
            volume=r[4],
            rank=r[5],
        )
        for r in rows
    ]


@strawberry.type
class Query:
    @strawberry.field
    def gain_ranking(self, date: str, limit: int = 20) -> List[StockRankingItem]:
        """値上がり率ランキング"""
        return _fetch_gain_ranking("desc", date, limit)

    @strawberry.field
    def decline_ranking(self, date: str, limit: int = 20) -> List[StockRankingItem]:
        """値下がり率ランキング"""
        return _fetch_gain_ranking("asc", date, limit)

    @strawberry.field
    def volume_ranking(self, date: str, limit: int = 20) -> List[StockRankingItem]:
        """出来高ランキング"""
        sql = """
        SELECT "Code", "Close", "Volume",
               ROW_NUMBER() OVER (ORDER BY "Volume" DESC) AS Rank
        FROM stocks_daily WHERE "Date" = ?
        ORDER BY "Volume" DESC LIMIT ?
        """
        with _duckdb.connect(MOTHER_DB_PATH, read_only=True) as con:
            rows = con.execute(sql, [date, limit]).fetchall()
        return [
            StockRankingItem(
                code=r[0],
                close=r[1],
                prev_close=None,
                gain_rate=None,
                volume=r[2],
                rank=r[3],
            )
            for r in rows
        ]


gql_schema = strawberry.Schema(query=Query)
app.add_url_rule(
    "/graphql",
    view_func=GraphQLView.as_view("graphql_view", schema=gql_schema),
)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
