"""FTPS proxy for BackcastPro.

Streams .duckdb files from a home NAS via FTPS, exposed as HTTP GET.
Deployed on Cloud Run.
"""

import ftplib
import logging
import os
import re
import ssl

from flask import Flask, Response

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Whitelist: only allow known file patterns
ALLOWED_PATHS = re.compile(
    r"^(stocks_daily/\d+\.duckdb|stocks_board/\d+\.duckdb|listed_info\.duckdb)$"
)


class _NatFriendlyFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS that works behind NAT.

    When the server returns a private IP in PASV response,
    replace it with the control connection host.
    """

    def makepasv(self):
        _host, port = super().makepasv()
        return self.host, port


class NASFtpsProxy:
    """Connects to a home NAS via FTPS and handles file operations."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        base_path: str = "/",
        connect_timeout: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_path = base_path.rstrip("/")
        self.connect_timeout = connect_timeout

    def _connect(self) -> _NatFriendlyFTP_TLS:
        """Establish a new FTPS connection (per-request)."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        ftp = _NatFriendlyFTP_TLS(context=context)
        ftp.connect(self.host, self.port, timeout=self.connect_timeout)
        ftp.login(self.username, self.password)
        ftp.prot_p()
        ftp.set_pasv(True)
        return ftp

    def _resolve_path(self, file_path: str) -> str:
        """Combine base_path with the relative file_path."""
        return f"{self.base_path}/jp/{file_path}"

    def stream_file(self, file_path: str) -> Response:
        """Stream file content as a chunked HTTP response via FTPS.

        Raises ftplib.error_perm if file not found.
        """
        remote_path = self._resolve_path(file_path)

        # Pre-check: verify file exists (raises error_perm if not found)
        ftp_check = self._connect()
        try:
            ftp_check.voidcmd("TYPE I")
            ftp_check.size(remote_path)
        finally:
            try:
                ftp_check.quit()
            except Exception:
                pass

        def generate():
            ftp = self._connect()
            try:
                ftp.voidcmd("TYPE I")
                conn = ftp.transfercmd(f"RETR {remote_path}")
                try:
                    while True:
                        chunk = conn.recv(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    conn.close()
                    ftp.voidresp()
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass

        return Response(
            generate(),
            content_type="application/octet-stream",
            headers={"Transfer-Encoding": "chunked"},
        )

def _get_proxy() -> NASFtpsProxy:
    """Get or create the NASFtpsProxy singleton."""
    if not hasattr(app, "_nas_proxy"):
        app._nas_proxy = NASFtpsProxy(
            host=os.environ.get("FTPS_HOST", "backcast.i234.me"),
            port=int(os.environ.get("FTPS_PORT", "21")),
            username=os.environ.get("FTPS_USERNAME", ""),
            password=os.environ.get("FTPS_PASSWORD", ""),
            base_path=os.environ.get("FTPS_BASE_PATH", "/StockData"),
            connect_timeout=float(os.environ.get("FTPS_CONNECT_TIMEOUT", "30")),
        )
        logger.info(
            "NAS FTPS proxy configured: %s:%s base=%s",
            app._nas_proxy.host,
            app._nas_proxy.port,
            app._nas_proxy.base_path,
        )
    return app._nas_proxy


@app.route("/")
def health():
    return "OK", 200


@app.route("/jp/<path:file_path>", methods=["GET"])
def download_file(file_path: str):
    if not ALLOWED_PATHS.match(file_path):
        return "Not Found", 404

    proxy = _get_proxy()
    try:
        logger.info("Streaming: %s", file_path)
        return proxy.stream_file(file_path)
    except ftplib.error_perm:
        logger.warning("File not found on NAS: %s", file_path)
        return "Not Found", 404


@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Unexpected error: %s", e, exc_info=True)
    if isinstance(e, (ftplib.error_perm, ftplib.error_temp)):
        return "NAS error", 503
    return "Internal error", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))