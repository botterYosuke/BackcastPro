"""
Cloud Run APIクライアント

Cloud Run上のプロキシAPIを通じて、
Google Drive共有フォルダからDuckDBファイルをダウンロード/アップロードするモジュール。
"""
import os
import logging
import requests
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CloudRunConfig:
    """Cloud Run API接続設定"""
    api_base_url: str

    @classmethod
    def from_environment(cls) -> "CloudRunConfig":
        """環境変数から設定を読み込み"""
        return cls(
            api_base_url=os.environ.get("BACKCASTPRO_GDRIVE_API_URL", ""),
        )

    def is_configured(self) -> bool:
        """API URLが設定されているか確認"""
        return bool(self.api_base_url)


class CloudRunClient:
    """BackcastPro用Cloud Run APIクライアント"""

    def __init__(self, config: Optional[CloudRunConfig] = None):
        self.config = config or CloudRunConfig.from_environment()

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """
        Cloud Run APIからファイルをストリームダウンロード

        Args:
            remote_path: 論理パス (例: "stocks_daily/1234.duckdb")
            local_path: ローカル保存先パス

        Returns:
            成功時True、失敗時False
        """
        url = f"{self.config.api_base_url.rstrip('/')}/jp/{remote_path}"

        try:
            logger.info(f"ダウンロード開始: {remote_path} -> {local_path}")

            resp = requests.get(url, stream=True, timeout=(10, 300))

            if resp.status_code == 404:
                logger.debug(f"ファイルが見つかりません: {remote_path}")
                return False

            resp.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"ダウンロード完了: {local_path}")
            return True

        except Exception as e:
            logger.warning(f"ダウンロード失敗: {e}")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
            return False

    def upload_file(self, remote_path: str, local_path: str) -> bool:
        """
        Cloud Run API経由でファイルをアップロード

        Args:
            remote_path: 論理パス (例: "stocks_daily/1234.duckdb")
            local_path: ローカルファイルパス

        Returns:
            成功時True、失敗時False
        """
        url = f"{self.config.api_base_url.rstrip('/')}/jp/{remote_path}"
        api_key = os.environ.get("UPLOAD_API_KEY", "")

        try:
            logger.info(f"アップロード開始: {local_path} -> {remote_path}")
            with open(local_path, 'rb') as f:
                resp = requests.post(
                    url, data=f,
                    headers={"X-API-Key": api_key},
                    timeout=(10, 300),
                )
            resp.raise_for_status()
            logger.info(f"アップロード完了: {remote_path}")
            return True
        except Exception as e:
            logger.warning(f"アップロード失敗: {e}")
            return False

    def upload_stocks_daily(self, code: str, local_path: str) -> bool:
        """stocks_daily DuckDBファイルをアップロード"""
        return self.upload_file(f"stocks_daily/{code}.duckdb", local_path)

    def download_stocks_daily(self, code: str, local_path: str) -> bool:
        """stocks_daily DuckDBファイルをダウンロード"""
        return self.download_file(f"stocks_daily/{code}.duckdb", local_path)

    def download_stocks_board(self, code: str, local_path: str) -> bool:
        """stocks_board DuckDBファイルをダウンロード"""
        return self.download_file(f"stocks_board/{code}.duckdb", local_path)

    def download_listed_info(self, local_path: str) -> bool:
        """listed_info.duckdb ファイルをダウンロード"""
        return self.download_file("listed_info.duckdb", local_path)
