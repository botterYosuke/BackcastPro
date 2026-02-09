"""Google Drive download proxy for BackcastPro.

Streams .duckdb files from a shared Google Drive folder via HTTP.
Deployed on Cloud Run.
"""

import io
import json
import logging
import os
import re

from flask import Flask, Response
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Whitelist: only allow known file patterns
ALLOWED_PATHS = re.compile(
    r"^(stocks_daily/\d+\.duckdb|stocks_board/\d+\.duckdb|listed_info\.duckdb)$"
)


class GoogleDriveProxy:
    """Finds and streams files from a shared Google Drive folder."""

    def __init__(self, credentials, root_folder_id: str):
        self.service = build("drive", "v3", credentials=credentials)
        self.root_folder_id = root_folder_id
        self._folder_cache: dict[str, str] = {}  # name -> folder_id

    def find_subfolder(self, name: str) -> str | None:
        """Find a subfolder by name under the root folder (cached)."""
        if name in self._folder_cache:
            return self._folder_cache[name]

        query = (
            f"'{self.root_folder_id}' in parents"
            f" and name = '{name}'"
            f" and mimeType = 'application/vnd.google-apps.folder'"
            f" and trashed = false"
        )
        results = (
            self.service.files()
            .list(q=query, fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = results.get("files", [])
        if not files:
            return None

        folder_id = files[0]["id"]
        self._folder_cache[name] = folder_id
        return folder_id

    def find_file(self, folder_id: str, filename: str) -> str | None:
        """Find a file by name in a specific folder."""
        query = (
            f"'{folder_id}' in parents"
            f" and name = '{filename}'"
            f" and trashed = false"
        )
        results = (
            self.service.files()
            .list(q=query, fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = results.get("files", [])
        if not files:
            return None
        return files[0]["id"]

    def stream_file(self, file_id: str) -> Response:
        """Stream file content as a chunked HTTP response."""
        request = self.service.files().get_media(fileId=file_id)

        def generate():
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()
                fh.seek(0)
                yield fh.read()
                fh.seek(0)
                fh.truncate()

        return Response(
            generate(),
            content_type="application/octet-stream",
            headers={"Transfer-Encoding": "chunked"},
        )


def _build_credentials():
    """Build Google credentials from environment."""
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]

    if sa_json:
        info = json.loads(sa_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=scopes
        )

    # Fallback: Cloud Run default service account
    import google.auth

    credentials, _ = google.auth.default(scopes=scopes)
    return credentials


def _get_proxy() -> GoogleDriveProxy:
    """Get or create the GoogleDriveProxy singleton."""
    if not hasattr(app, "_drive_proxy"):
        credentials = _build_credentials()
        root_folder_id = os.environ.get(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID", "1LxXZ7dZv4oXlYyXH6OZtt_0yVbwtyiF4"
        )
        app._drive_proxy = GoogleDriveProxy(credentials, root_folder_id)
    return app._drive_proxy


@app.route("/")
def health():
    return "OK", 200


@app.route("/jp/<path:file_path>")
def download_file(file_path: str):
    # Validate path against whitelist
    if not ALLOWED_PATHS.match(file_path):
        return "Not Found", 404

    proxy = _get_proxy()

    # Parse path: "stocks_daily/1234.duckdb" or "listed_info.duckdb"
    parts = file_path.split("/")
    if len(parts) == 2:
        subfolder_name, filename = parts
    elif len(parts) == 1:
        subfolder_name, filename = None, parts[0]
    else:
        return "Not Found", 404

    if subfolder_name:
        folder_id = proxy.find_subfolder(subfolder_name)
        if not folder_id:
            logger.warning("Subfolder not found: %s", subfolder_name)
            return "Not Found", 404
    else:
        folder_id = proxy.root_folder_id

    file_id = proxy.find_file(folder_id, filename)
    if not file_id:
        logger.warning("File not found: %s/%s", subfolder_name or "", filename)
        return "Not Found", 404

    logger.info("Streaming: %s (file_id=%s)", file_path, file_id)
    return proxy.stream_file(file_id)


@app.errorhandler(HttpError)
def handle_google_error(e):
    if e.resp.status == 404:
        return "File not found", 404
    logger.error("Google Drive API error: %s", e)
    return "Google Drive API error", 503


@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Unexpected error: %s", e, exc_info=True)
    return "Internal error", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
