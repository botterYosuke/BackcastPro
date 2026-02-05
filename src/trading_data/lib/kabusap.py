import json
import urllib.request
import urllib.error
import os
import logging
import threading
from typing import Optional
from datetime import datetime, timedelta
import pandas as pd

# 環境変数を読み込み
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class kabusap:
    """
    kabuステーションAPI Client (Singleton)
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(kabusap, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 既に初期化済みの場合はスキップ
        if hasattr(self, '_initialized'):
            return
            
        self.API_URL = os.getenv('KABUSAP_API_PASSWORD',"http://localhost:18080/kabusapi")
        self.api_key = ""
        self.headers = {}  # 初期化を確実にする
        self._initialized = True
        self.isEnable = self._set_token()
        if self.isEnable:
            self.headers = {
                'Content-Type': 'application/json',
                'X-API-KEY': self.api_key
            }

    def _set_token(self) -> bool:
        """
        APIトークンを取得
        
        正しく設定ファイルが作成されていれば、本コードを実行することで、APIトークンを取得することができます。
        「APIを使用する準備が完了しました。」と出力されれば、kabuステーションAPIをコールすることができるようになります！
        """
        api_password = os.getenv('KABUSAP_API_PASSWORD')
        
        # 環境変数が設定されていない場合はAPI呼び出しを行わない
        if not api_password:
            logger.warning("kabuステーションAPIの認証情報（KABUSAP_API_PASSWORD）が設定されていません。")
            return False
        
        # トークン取得
        try:
            obj = {'APIPassword': api_password}
            json_data = json.dumps(obj).encode('utf8')
            
            url = f'{self.API_URL}/token'
            req = urllib.request.Request(url, json_data, method='POST')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req) as res:
                content = json.loads(res.read())
                # レスポンスからトークンを取得
                # レスポンス形式は {'ResultCode': 0, 'Token': '...'} の形式を想定
                if 'Token' in content:
                    self.api_key = content['Token']
                    logger.info("API使用の準備が完了しました。")
                    return True
                else:
                    logger.error(f"トークンの取得に失敗しました。レスポンス: {content}")
                    return False
        except urllib.error.HTTPError as e:
            error_content = json.loads(e.read().decode('utf-8'))
            logger.error(f"HTTPエラー: {e.code} - {error_content}")
            return False
        except Exception as e:
            logger.error(f"トークンの取得に失敗しました: {e}")
            return False

    def _refresh_token_if_needed(self) -> bool:
        """
        トークンが期限切れの場合は再取得する
        kabuステーションAPIのトークンは有効期限があるため、必要に応じて再取得する
        """
        # 現在の実装では、トークンが無効になった場合に再取得する
        # 必要に応じて、トークンの有効期限をチェックするロジックを追加可能
        if not self.api_key:
            logger.info("トークンが無効のため、再取得します。")
            return self._set_token()
        return True

    def get_board(self, code: str) -> pd.DataFrame:
        """
        板情報を取得する

        Args:
            code (str): 銘柄コード

        Returns:
            pd.DataFrame: 板情報
        """
        # APIが有効でない場合は空のDataFrameを返す
        if not self.isEnable:
            logger.warning("kabuステーションAPIが有効ではありません。")
            return pd.DataFrame()

        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()

        # 銘柄コードの検証
        if not code or not isinstance(code, str) or not code.strip():
            logger.error("銘柄コードが指定されていません。")
            return pd.DataFrame()

        # 板情報取得のURLを構築（銘柄コード@市場コードの形式）
        # 市場コード1は東証を表す
        url = f'{self.API_URL}/board/{code}@1'
        
        try:
            # GETリクエストを送信
            req = urllib.request.Request(url, method='GET')
            req.add_header('Content-Type', 'application/json')
            req.add_header('X-API-KEY', self.api_key)
            
            with urllib.request.urlopen(req) as res:
                content = json.loads(res.read())
                
                # エラーチェック
                if 'ResultCode' in content and content['ResultCode'] != 0:
                    logger.error(f"API Error: {content.get('ResultCode')} - {content.get('Message', '')}")
                    return pd.DataFrame()
                
                # 板情報をDataFrameに変換
                # APIレスポンスの構造に応じてデータを抽出
                board_data = []
                
                # パターン1: Bid/Askキーが存在する場合（JSON配列形式）
                if 'Bid' in content and isinstance(content['Bid'], list):
                    for bid in content['Bid']:
                        board_data.append({
                            'Price': bid.get('Price', 0),
                            'Qty': bid.get('Qty', 0),
                            'Type': 'Bid'
                        })
                
                if 'Ask' in content and isinstance(content['Ask'], list):
                    for ask in content['Ask']:
                        board_data.append({
                            'Price': ask.get('Price', 0),
                            'Qty': ask.get('Qty', 0),
                            'Type': 'Ask'
                        })
                
                # パターン2: Sell1.Price, Buy1.Price形式の場合（json_normalize後の形式）
                if not board_data:
                    normalized_df = pd.json_normalize(content)
                    
                    # 買い板（Buy1～Buy10）の処理
                    for i in range(1, 11):
                        price_col = f'Buy{i}.Price'
                        qty_col = f'Buy{i}.Qty'
                        if price_col in normalized_df.columns and qty_col in normalized_df.columns:
                            price = normalized_df[price_col].iloc[0] if len(normalized_df) > 0 else 0
                            qty = normalized_df[qty_col].iloc[0] if len(normalized_df) > 0 else 0
                            if pd.notna(price) and pd.notna(qty) and price > 0 and qty > 0:
                                board_data.append({
                                    'Price': float(price),
                                    'Qty': int(qty),
                                    'Type': 'Bid'
                                })
                    
                    # 売り板（Sell1～Sell10）の処理
                    for i in range(1, 11):
                        price_col = f'Sell{i}.Price'
                        qty_col = f'Sell{i}.Qty'
                        if price_col in normalized_df.columns and qty_col in normalized_df.columns:
                            price = normalized_df[price_col].iloc[0] if len(normalized_df) > 0 else 0
                            qty = normalized_df[qty_col].iloc[0] if len(normalized_df) > 0 else 0
                            if pd.notna(price) and pd.notna(qty) and price > 0 and qty > 0:
                                board_data.append({
                                    'Price': float(price),
                                    'Qty': int(qty),
                                    'Type': 'Ask'
                                })
                
                # DataFrameに変換
                if board_data:
                    df = pd.DataFrame(board_data)
                    # ソース情報を追加
                    df['source'] = 'kabu-station'
                    df['code'] = code
                    return df
                else:
                    # 板情報が取得できなかった場合
                    logger.warning(f"板情報が取得できませんでした: {code}")
                    return pd.DataFrame()
                
        except urllib.error.HTTPError as e:
            error_content = json.loads(e.read().decode('utf-8'))
            logger.error(f"HTTPエラー: {e.code} - {error_content}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"板情報の取得に失敗しました: {e}")
            return pd.DataFrame()



if __name__ == '__main__':
    kabusap = kabusap()
    df = kabusap.get_board('8306')
    print(df)
