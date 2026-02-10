"""Local file server for BackcastPro.

Serves .duckdb files from a local directory, exposed as HTTP GET.
Deployed on Cloud Run.
"""

import logging
import os
import re

from dotenv import load_dotenv
from flask import Flask, send_from_directory
from werkzeug.exceptions import HTTPException, NotFound

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("STOCKDATA_CACHE_DIR", "/cache")

# Whitelist: only allow known file patterns
ALLOWED_PATHS = re.compile(
    r"^(stocks_daily/\d+\.duckdb|stocks_board/\d+\.duckdb|listed_info\.duckdb)$"
)


@app.route("/")
def health():
    return "OK", 200


@app.route("/jp/<path:file_path>", methods=["GET"])
def download_file(file_path: str):
    if not ALLOWED_PATHS.match(file_path):
        return "Not Found", 404

    directory = os.path.join(DATA_DIR, "jp")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
