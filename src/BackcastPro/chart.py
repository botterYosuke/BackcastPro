"""
chart関数: バックエンドAPIから株価データを取得してDataFrameを返す
"""

import os
import pandas as pd
import requests
from typing import Optional


def _get_api_base_url() -> str:
    """
    環境変数からAPIのベースURLを取得
    
    Returns:
        str: APIのベースURL
    """
    # 環境変数 BACKCAST_API_URL が設定されている場合はそれを使用
    api_url = os.getenv('BACKCAST_API_URL')
    if api_url:
        return api_url.rstrip('/')
    
    # 環境変数 BACKCAST_ENV が production の場合は本番環境を使用
    env = os.getenv('BACKCAST_ENV', '').lower()
    if env == 'production':
        return 'http://backcast.i234.me'
    
    # デフォルトは開発環境
    return 'http://localhost:8000'


def chart(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    指定された銘柄の株価データを取得してDataFrameを返す
    
    Args:
        code (str): 銘柄コード（例: '2371'）
        start_date (str): 開始日（例: '2025-01-01'）
        end_date (str): 終了日（例: '2025-01-31'）
    
    Returns:
        pd.DataFrame: 株価データのDataFrame
    
    Raises:
        ValueError: APIからエラーレスポンスが返された場合
        requests.exceptions.RequestException: ネットワークエラーやタイムアウトが発生した場合
    """
    # APIのベースURLを取得
    base_url = _get_api_base_url()
    endpoint = f"{base_url}/jp/stocks/daily"
    
    # クエリパラメータを設定
    params = {
        'code': code,
        'start_date': start_date,
        'end_date': end_date
    }
    
    try:
        # APIを呼び出し
        response = requests.get(endpoint, params=params, timeout=30)
        response.raise_for_status()  # HTTPエラーの場合は例外を発生
        
        # JSONレスポンスを取得
        result = response.json()
        
        # APIエラーの場合は例外を発生
        if not result.get('success', False):
            error_message = result.get('error', 'APIエラーが発生しました')
            raise ValueError(f"APIエラー: {error_message}")
        
        # データを取得
        data = result.get('data', [])
        
        # データが空の場合は空のDataFrameを返す
        if not data:
            return pd.DataFrame()
        
        # 辞書のリストをDataFrameに変換
        df = pd.DataFrame(data)
        
        return df
        
    except requests.exceptions.RequestException as e:
        # ネットワークエラーやタイムアウトはそのまま伝播
        raise
    except ValueError:
        # ValueErrorはそのまま伝播
        raise
    except Exception as e:
        # その他の予期しないエラー
        raise ValueError(f"データの取得に失敗しました: {str(e)}")

