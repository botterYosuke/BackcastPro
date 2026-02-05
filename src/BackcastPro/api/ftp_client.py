"""
FTPクライアントユーティリティ

BackcastProのFTP操作を一元管理するモジュール。
ダウンロード・アップロード機能を提供する。
"""
import ftplib
import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FTPConfig:
    """FTP接続設定"""
    host: str
    port: int
    username: str
    password: str

    @classmethod
    def from_environment(cls) -> "FTPConfig":
        """環境変数から設定を読み込み"""
        return cls(
            host=os.environ.get("BACKCASTPRO_FTP_HOST", "backcast.i234.me"),
            port=int(os.environ.get("BACKCASTPRO_FTP_PORT", "21")),
            username=os.environ.get("BACKCASTPRO_FTP_USER", "sasaco_worker"),
            password=os.environ.get("BACKCASTPRO_FTP_PASSWORD", "S#1y9c%7o9"),
        )

    def is_configured(self) -> bool:
        """認証情報が設定されているか確認"""
        return bool(self.username and self.password)


class FTPClient:
    """BackcastPro用FTPクライアント"""

    REMOTE_BASE = "/StockData/jp"
    STOCKS_DAILY_DIR = f"{REMOTE_BASE}/stocks_daily"
    STOCKS_BOARD_DIR = f"{REMOTE_BASE}/stocks_board"

    def __init__(self, config: Optional[FTPConfig] = None):
        self.config = config or FTPConfig.from_environment()

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """
        FTPサーバーからファイルをダウンロード

        Args:
            remote_path: リモートファイルのフルパス
            local_path: ローカル保存先パス

        Returns:
            成功時True、失敗時False
        """
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.config.host, self.config.port)
                ftp.login(self.config.username, self.config.password)

                # ファイル存在確認
                try:
                    ftp.voidcmd("TYPE I")
                    ftp.size(remote_path)
                except Exception:
                    logger.debug(f"FTPサーバーにファイルが見つかりません: {remote_path}")
                    return False

                logger.info(f"FTPダウンロード開始: {remote_path} -> {local_path}")

                with open(local_path, 'wb') as f:
                    ftp.retrbinary(f"RETR {remote_path}", f.write)

                logger.info(f"FTPダウンロード完了: {local_path}")
                return True

        except Exception as e:
            logger.warning(f"FTPダウンロード失敗: {e}")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
            return False

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        create_dirs: bool = True
    ) -> bool:
        """
        FTPサーバーにファイルをアップロード

        Args:
            local_path: ローカルファイルパス
            remote_path: リモート保存先パス
            create_dirs: ディレクトリが存在しない場合に作成するか

        Returns:
            成功時True、失敗時False
        """
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.config.host, self.config.port, timeout=60)
                ftp.login(self.config.username, self.config.password)
                ftp.set_pasv(True)

                # ディレクトリに移動（必要なら作成）
                remote_dir = os.path.dirname(remote_path)
                remote_filename = os.path.basename(remote_path)

                if remote_dir:
                    if create_dirs:
                        try:
                            ftp.cwd(remote_dir)
                        except ftplib.error_perm:
                            logger.info(f"リモートディレクトリ作成: {remote_dir}")
                            ftp.mkd(remote_dir)
                            ftp.cwd(remote_dir)
                    else:
                        ftp.cwd(remote_dir)

                with open(local_path, 'rb') as f:
                    ftp.storbinary(f"STOR {remote_filename}", f)

                logger.debug(f"アップロード完了: {local_path} -> {remote_path}")
                return True

        except Exception as e:
            logger.error(f"FTPアップロード失敗: {e}")
            return False

    def download_stocks_daily(self, code: str, local_path: str) -> bool:
        """stocks_daily DuckDBファイルをダウンロード"""
        remote_path = f"{self.STOCKS_DAILY_DIR}/{code}.duckdb"
        return self.download_file(remote_path, local_path)

    def download_stocks_board(self, code: str, local_path: str) -> bool:
        """stocks_board DuckDBファイルをダウンロード"""
        remote_path = f"{self.STOCKS_BOARD_DIR}/{code}.duckdb"
        return self.download_file(remote_path, local_path)

    def download_listed_info(self, local_path: str) -> bool:
        """listed_info.duckdb ファイルをダウンロード"""
        remote_path = f"{self.REMOTE_BASE}/listed_info.duckdb"
        return self.download_file(remote_path, local_path)

    def upload_stocks_daily(self, code: str, local_path: str) -> bool:
        """stocks_daily DuckDBファイルをアップロード"""
        remote_path = f"{self.STOCKS_DAILY_DIR}/{code}.duckdb"
        return self.upload_file(local_path, remote_path)

    def upload_multiple(
        self,
        files: list[tuple[str, str]],
    ) -> dict[str, list]:
        """
        複数ファイルをアップロード

        Args:
            files: (local_path, remote_path) のタプルリスト

        Returns:
            {'success': [...], 'failed': [...]}
        """
        results: dict[str, list] = {'success': [], 'failed': []}

        try:
            with ftplib.FTP() as ftp:
                ftp.connect(self.config.host, self.config.port, timeout=60)
                ftp.login(self.config.username, self.config.password)
                ftp.set_pasv(True)

                for local_path, remote_path in files:
                    if not os.path.exists(local_path):
                        logger.warning(f"ローカルファイルなし: {local_path}")
                        results['failed'].append((local_path, "File not found"))
                        continue

                    try:
                        remote_dir = os.path.dirname(remote_path)
                        remote_filename = os.path.basename(remote_path)

                        if remote_dir:
                            try:
                                ftp.cwd(remote_dir)
                            except ftplib.error_perm:
                                logger.info(f"リモートディレクトリ作成: {remote_dir}")
                                ftp.mkd(remote_dir)
                                ftp.cwd(remote_dir)

                        with open(local_path, 'rb') as f:
                            ftp.storbinary(f"STOR {remote_filename}", f)

                        results['success'].append(local_path)
                        logger.debug(f"アップロード完了: {remote_filename}")

                    except Exception as e:
                        logger.error(f"アップロード失敗 {local_path}: {e}")
                        results['failed'].append((local_path, str(e)))

        except ftplib.all_errors as e:
            logger.error(f"FTP接続エラー: {e}")
            for local_path, _ in files:
                if local_path not in results['success']:
                    results['failed'].append((local_path, f"Connection error: {e}"))

        return results
