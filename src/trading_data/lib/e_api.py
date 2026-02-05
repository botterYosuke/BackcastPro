import json
from typing import Tuple
from requests import Response
import requests
import os
from datetime import datetime, timedelta
import pandas as pd
import logging
import threading
from pathlib import Path
import tempfile

# 環境変数を読み込み
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class e_api:
    """
    立花証券-e支店 API Client (Singleton)
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(e_api, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 既に初期化済みの場合はスキップ
        if hasattr(self, '_initialized'):
            return

        self.API_URL = os.getenv('eAPI_URL')
        self.p_no = 1
        self.sUrlRequest = ""
        self.sUrlMaster = ""
        self.sUrlPrice = ""
        self.sUrlEvent = ""
        self.sUrlEventWebSocket = ""
        
        self.token_expires_at = None
        
        # キャッシュファイルのパス設定
        env_cache_dir = os.environ.get('BACKCASTPRO_CACHE_DIR', tempfile.mkdtemp())
        self.cache_dir = Path(os.path.abspath(env_cache_dir))
        os.environ['BACKCASTPRO_CACHE_DIR'] = str(self.cache_dir)
        self.cache_file = self.cache_dir / "e_api_login_cache.json"
        self.failure_cache_file = self.cache_dir / "e_api_login_failures.json"
        
        # ログイン失敗管理
        self.login_failures = []
        self.login_blocked_until = None
        self.max_login_failures = int(os.getenv('eAPI_MAX_LOGIN_FAILURES', '3'))
        
        self._initialized = True
        
        # キャッシュから情報を読み込み
        if self._load_from_cache():
            self.isEnable = True
            logger.info("キャッシュからログイン情報を読み込みました。")
        else:
            self.isEnable = self._set_token()


    def _load_from_cache(self) -> bool:
        """
        キャッシュファイルからログイン情報を読み込む
        
        Returns:
            bool: 有効なキャッシュが読み込めた場合はTrue
        """
        try:
            if not self.cache_file.exists():
                return False
            
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 有効期限をチェック
            token_expires_at = datetime.fromisoformat(cache_data.get('token_expires_at'))
            if datetime.now() >= token_expires_at:
                logger.info("キャッシュのトークンが期限切れです。")
                return False
            
            # ログイン情報を復元
            self.sUrlRequest = cache_data.get('sUrlRequest', '')
            self.sUrlMaster = cache_data.get('sUrlMaster', '')
            self.sUrlPrice = cache_data.get('sUrlPrice', '')
            self.sUrlEvent = cache_data.get('sUrlEvent', '')
            self.sUrlEventWebSocket = cache_data.get('sUrlEventWebSocket', '')
            self.p_no = cache_data.get('p_no', 1)
            self.token_expires_at = token_expires_at
            
            return True
            
        except Exception as e:
            logger.warning(f"キャッシュの読み込みに失敗しました: {e}")
            return False
    
    def _save_to_cache(self) -> None:
        """
        ログイン情報をキャッシュファイルに保存
        """
        try:
            if self.token_expires_at is None:
                logger.warning("token_expires_atがNullのため、キャッシュに保存できません。")
                return
            
            # キャッシュディレクトリが存在しない場合は作成
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                'sUrlRequest': self.sUrlRequest,
                'sUrlMaster': self.sUrlMaster,
                'sUrlPrice': self.sUrlPrice,
                'sUrlEvent': self.sUrlEvent,
                'sUrlEventWebSocket': self.sUrlEventWebSocket,
                'p_no': self.p_no,
                'token_expires_at': self.token_expires_at.isoformat(),
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"ログイン情報をキャッシュに保存しました: {self.cache_file}")
            
        except Exception as e:
            logger.error(f"キャッシュの保存に失敗しました: {e}")
    
    def _load_login_failures(self) -> None:
        """
        ログイン失敗履歴を読み込む
        """
        try:
            if not self.failure_cache_file.exists():
                return
            
            with open(self.failure_cache_file, 'r', encoding='utf-8') as f:
                failure_data = json.load(f)
            
            self.login_failures = [datetime.fromisoformat(dt) for dt in failure_data.get('failures', [])]
            if failure_data.get('blocked_until'):
                self.login_blocked_until = datetime.fromisoformat(failure_data.get('blocked_until'))
            
        except Exception as e:
            logger.warning(f"ログイン失敗履歴の読み込みに失敗しました: {e}")
    
    def _save_login_failures(self) -> None:
        """
        ログイン失敗履歴を保存
        """
        try:
            # キャッシュディレクトリが存在しない場合は作成
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            failure_data = {
                'failures': [dt.isoformat() for dt in self.login_failures],
                'blocked_until': self.login_blocked_until.isoformat() if self.login_blocked_until else None
            }
            
            with open(self.failure_cache_file, 'w', encoding='utf-8') as f:
                json.dump(failure_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"ログイン失敗履歴の保存に失敗しました: {e}")
    
    def _record_login_failure(self) -> None:
        """
        ログイン失敗を記録し、必要に応じてブロックを設定
        """
        now = datetime.now()
        
        # 24時間以内の失敗のみを保持
        twenty_four_hours_ago = now - timedelta(hours=24)
        self.login_failures = [dt for dt in self.login_failures if dt > twenty_four_hours_ago]
        
        # 新しい失敗を記録
        self.login_failures.append(now)
        
        # 24時間以内に指定回数失敗した場合、24時間ブロック
        if len(self.login_failures) >= self.max_login_failures:
            self.login_blocked_until = now + timedelta(hours=24)
            logger.warning(f"24時間以内に{self.max_login_failures}回ログインに失敗しました。{self.login_blocked_until}までログインをブロックします。")
        
        self._save_login_failures()
    
    def _is_login_blocked(self) -> bool:
        """
        ログインがブロックされているかチェック
        
        Returns:
            bool: ブロックされている場合はTrue
        """
        self._load_login_failures()
        
        if self.login_blocked_until:
            if datetime.now() < self.login_blocked_until:
                logger.warning(f"ログインがブロックされています。ブロック解除: {self.login_blocked_until}")
                return True
            else:
                # ブロック期間が過ぎたらリセット
                self.login_blocked_until = None
                self.login_failures = []
                self._save_login_failures()
        
        return False

    def _set_token(self) -> bool:
        """
        仮想URLを取得
        
        正しく設定ファイルが作成されていれば、本コードを実行することで、仮想URLを取得することができます。
        「APIを使用する準備が完了しました。」と出力されれば、立花証券 APIをコールすることができるようになります！
        """
        # ログインがブロックされているかチェック
        if self._is_login_blocked():
            return False
        
        # 仮想URLを取得
        USER_DATA = {
            "sCLMID":"CLMAuthLoginRequest",
            "p_no" : str(self.p_no),
            "p_sd_date": datetime.now().strftime('%Y.%m.%d-%H:%M:%S.%f')[:-3],
            "sPassword":os.getenv('eAPI_PASSWORD'),
            "sUserId":os.getenv('eAPI_USER_ID'),
            "sJsonOfmt": "5"
        }

        # 環境変数が設定されていない場合はAPI呼び出しを行わない
        if not USER_DATA["sUserId"] or not USER_DATA["sPassword"]:
            logger.warning("立花証券-e支店の認証情報が設定されていません。")
            return False
        # refresh token取得
        try:
            url = f"{self.API_URL.rstrip('/')}/auth/?{json.dumps(USER_DATA)}"
            req = requests.get(url)
            str_api_response = req.content.decode(req.apparent_encoding, errors="ignore")
            dic_return = json.loads(str_api_response)
        except Exception as e:
            logger.error(f"立花証券-e支店のlogin用のAPI問合せに失敗しました: {e}")
            self._record_login_failure()
        else:
            # ログインの判定とログイン情報の保存
            try:
                int_p_errno = int(dic_return.get('p_errno', 0))
                int_sResultCode = int(dic_return.get('sResultCode', 0))

                if int_p_errno ==  0 and int_sResultCode == 0:    # ログインエラーでない場合
                    # 仮想URLを保存する。
                    self.sUrlRequest = dic_return.get('sUrlRequest')
                    self.sUrlMaster = dic_return.get('sUrlMaster')
                    self.sUrlPrice = dic_return.get('sUrlPrice')
                    self.sUrlEvent = dic_return.get('sUrlEvent')
                    self.sUrlEventWebSocket = dic_return.get('sUrlEventWebSocket')

                    # "p_no"を保存する。
                    self.p_no = int(dic_return.get('p_no'))

                    # トークンの有効期限を設定（24時間後）
                    p_sd_date = dic_return.get('p_sd_date')
                    ## p_sd_dateを文字列からdatetime型に変換（フォーマット: "2025.10.09-07:32:59.888"）
                    token_datetime = datetime.strptime(p_sd_date, "%Y.%m.%d-%H:%M:%S.%f")
                    self.token_expires_at = token_datetime + timedelta(hours=24)
                    
                    # ログイン情報をキャッシュに保存
                    self._save_to_cache()
                    
                    # ログイン失敗履歴をリセット
                    self.login_failures = []
                    self.login_blocked_until = None
                    if self.failure_cache_file.exists():
                        self.failure_cache_file.unlink()
                    
                    logger.info("立花証券-e支店のAPI使用の準備が完了しました。")
                    return True
                else :
                    logger.error(f"{int_sResultCode}: \n {dic_return.get('689')}")
                    self._record_login_failure()
            except Exception as e:
                logger.error(f"立花証券-e支店のログイン情報の保存の取得に失敗しました: {e}")
                self._record_login_failure()
        return False

    def _refresh_token_if_needed(self) -> bool:
        """
        トークンが期限切れの場合はリフレッシュする
        """
        if self.token_expires_at:
            # token_expires_atがfloatの場合はdatetimeに変換
            if isinstance(self.token_expires_at, (int, float)):
                self.token_expires_at = datetime.fromtimestamp(self.token_expires_at)
            if datetime.now() >= self.token_expires_at:
                logger.info("トークンの期限が切れているため、リフレッシュします。")
                try:
                    # キャッシュを削除
                    if self.cache_file.exists():
                        self.cache_file.unlink()
                    
                    self.isEnable = self._set_token()
                    if self.isEnable:
                        logger.info("トークンのリフレッシュが完了しました。")
                    return self.isEnable
                except Exception as e:
                    logger.error(f"トークンのリフレッシュに失敗しました: {e}")
                    return False
        return True


    def get_daily_quotes(self, code: str, from_: datetime = None, to: datetime = None) -> pd.DataFrame:
        """
        株価四本値（/price-kabuka.e-shiten.jp/e_api_v4r8/price/）

        備考: 
            銘柄コードは、通常銘柄、4桁。優先株等、5桁。
            例、伊藤園'2593'、伊藤園優先株'25935'
        """

        # from_が20年より前の場合はスキップ（立花証券APIは最大約20年分のデータを保持）
        if from_ is not None:
            twenty_years_ago = datetime.now() - timedelta(days=365*20)
            if from_ < twenty_years_ago:
                logger.info(f"from_パラメータ({from_})が20年より前のため、スキップします。")
                return pd.DataFrame()
        
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()

        params = {
            "p_no" : str(self.p_no + 1),
            "p_sd_date": datetime.now().strftime('%Y.%m.%d-%H:%M:%S.%f')[:-3],
            "sCLMID":"CLMMfdsGetMarketPriceHistory",
            "sIssueCode":str(code),
            "sSizyouC":"00",  # 市場（現在、東証'00'のみ）
            "sJsonOfmt":"5"   # 返り値の表示形式指定
        }

        res = requests.get(f"{self.sUrlPrice.rstrip('/')}/?{json.dumps(params)}")
        if res.status_code == 200:
            dic_return = res.json()

            # エラーコードを取得
            p_errno = int(dic_return.get('p_errno', 0))
            # エラーが有っても無くても p_noを更新
            self.p_no = int(dic_return.get('p_no', self.p_no))
            self._save_to_cache()

            if p_errno == 6:
                logger.error(f"API Error: {dic_return.get('p_err')}")
                # キャッシュに新しいp_noを保存
                # retry with new p_no
                return self.get_daily_quotes(code, from_, to) 

            if p_errno != 0:
                logger.error(f"API Error: {p_errno} - {dic_return.get('p_err')}")
                return pd.DataFrame()

            if 'aCLMMfdsMarketPriceHistory' not in dic_return:
                if len(code) > 4:
                    ## codeが存在しないことが多い
                    code = code[:-1]
                    return self.get_daily_quotes(code, from_, to) 
                logger.error(f"API Error: {p_errno} - {dic_return.get('p_err')}")
                return pd.DataFrame()

            data = dic_return['aCLMMfdsMarketPriceHistory']

            df = pd.DataFrame(data)

            # カラム名を統一（J-Quants APIと合わせる）
            df = _e_normalize_columns(code, df)
            
            # from_とtoの期間でフィルタリング
            # Dateはインデックスとして設定されているため、インデックスでフィルタリング
            if from_ is not None:
                if isinstance(df.index, pd.DatetimeIndex):
                    df = df[df.index >= from_]
                elif 'Date' in df.columns:
                    df = df[df['Date'] >= from_]
            if to is not None:
                if isinstance(df.index, pd.DatetimeIndex):
                    df = df[df.index <= to]
                elif 'Date' in df.columns:
                    df = df[df['Date'] <= to]
            
            df['source'] = 'e-shiten'

            return df

        logger.error(f"API Error: {res.status_code} - {res.json()}")
        return pd.DataFrame()

    def get_board(self, code: str) -> pd.DataFrame:
        """
        板情報を取得する

        Args:
            code (str): 銘柄コード

        Returns:
            pd.DataFrame: 板情報
        """
        # トークンリフレッシュが必要かチェック
        self._refresh_token_if_needed()

        # 銘柄コードの検証
        if not code or not isinstance(code, str):
            logger.error("銘柄コードが指定されていません。")
            return pd.DataFrame()
        code = str(code).strip()
        if not code:
            logger.error("銘柄コードが空です。")
            return pd.DataFrame()

        # 板情報コードを構築
        board_columns = []
        # 買い板（1-10段）
        for i in range(1, 11):
            board_columns.extend([f'pGBP{i}', f'pGBV{i}'])
        board_columns.append('pQUV')  # 買-UNDER
        # 売り板（1-10段）
        for i in range(1, 11):
            board_columns.extend([f'pGAP{i}', f'pGAV{i}'])
        board_columns.append('pQOV')  # 売-OVER
        sTargetColumn = ','.join(board_columns)

        # APIパラメータの構築
        params = {
            "p_no": str(self.p_no + 1),
            "p_sd_date": datetime.now().strftime('%Y.%m.%d-%H:%M:%S.%f')[:-3],
            "sCLMID": "CLMMfdsGetMarketPrice",
            "sTargetIssueCode": code,
            "sTargetColumn": sTargetColumn,
            "sJsonOfmt": "5"
        }

        # API呼び出し
        res = requests.get(f"{self.sUrlPrice.rstrip('/')}/?{json.dumps(params)}")
        if res.status_code == 200:
            dic_return = res.json()

            # エラーチェック
            p_errno = int(dic_return.get('p_errno', 0))
            # エラーが有っても無くても p_noを更新
            self.p_no = int(dic_return.get('p_no', self.p_no))
            self._save_to_cache()

            if p_errno == 6:
                logger.error(f"API Error: {dic_return.get('p_err')}")
                # リトライ
                return self.get_board(code)

            if p_errno != 0:
                logger.error(f"API Error: {p_errno} - {dic_return.get('p_err')}")
                return pd.DataFrame()

            if 'aCLMMfdsMarketPrice' not in dic_return:
                logger.error(f"API Error: aCLMMfdsMarketPrice not found in response")
                return pd.DataFrame()

            # レスポンスから板情報を抽出
            board_data = []
            response_data = dic_return.get('aCLMMfdsMarketPrice', [])

            if response_data:
                item = response_data[0]  # 1銘柄のみ取得する想定
                
                # 買い板（1-10段）
                for i in range(1, 11):
                    price_key = f'pGBP{i}'
                    qty_key = f'pGBV{i}'
                    if price_key in item and qty_key in item:
                        price = item.get(price_key)
                        qty = item.get(qty_key)
                        if price and qty:  # 値が存在する場合のみ追加
                            try:
                                board_data.append({
                                    'Price': float(price) if price else 0,
                                    'Qty': int(qty) if qty else 0,
                                    'Type': 'Bid'
                                })
                            except (ValueError, TypeError):
                                # 数値変換エラーはスキップ
                                continue
                
                # 買-UNDER
                if 'pQUV' in item and item.get('pQUV'):
                    try:
                        board_data.append({
                            'Price': 0,  # UNDERは値段なし
                            'Qty': int(item.get('pQUV')),
                            'Type': 'Bid'
                        })
                    except (ValueError, TypeError):
                        pass
                
                # 売り板（1-10段）
                for i in range(1, 11):
                    price_key = f'pGAP{i}'
                    qty_key = f'pGAV{i}'
                    if price_key in item and qty_key in item:
                        price = item.get(price_key)
                        qty = item.get(qty_key)
                        if price and qty:
                            try:
                                board_data.append({
                                    'Price': float(price) if price else 0,
                                    'Qty': int(qty) if qty else 0,
                                    'Type': 'Ask'
                                })
                            except (ValueError, TypeError):
                                # 数値変換エラーはスキップ
                                continue
                
                # 売-OVER
                if 'pQOV' in item and item.get('pQOV'):
                    try:
                        board_data.append({
                            'Price': 0,  # OVERは値段なし
                            'Qty': int(item.get('pQOV')),
                            'Type': 'Ask'
                        })
                    except (ValueError, TypeError):
                        pass

            # DataFrame変換
            if board_data:
                df = pd.DataFrame(board_data)
                df['source'] = 'e-shiten'
                df['code'] = code
                return df
            else:
                return pd.DataFrame()

        logger.error(f"API Error: {res.status_code} - {res.text}")
        return pd.DataFrame()
        

def _e_normalize_columns(code: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    カラム名をJ-Quants APIの形式に統一する

    Args:
        df (pd.DataFrame): 元のDataFrame

    Returns:
        pd.DataFrame: カラム名を統一したDataFrame
    """
    # 立花証券 apiのカラム名をJ-Quantsの形式にマッピング
    names_mapping = {
        'pDOP': 'Open',
        'pDHP': 'High', 
        'pDLP': 'Low',
        'pDPP': 'Close',
        'pDV': 'Volume',
        "pDOPxK": "AdjustmentOpen",
        "pDHPxK": "AdjustmentHigh",
        "pDLPxK": "AdjustmentLow",
        "pDPPxK": "AdjustmentClose",
        "pDVxK": "AdjustmentVolume",
        "pSPUK": "AdjustmentFactor"
    }

    df['Date'] = pd.to_datetime(df['sDate'], format='%Y%m%d')
    
    # Dateをインデックスに設定
    df = df.set_index('Date')

    from .stooq import _common_normalize_columns

    return _common_normalize_columns(code, df, names_mapping)



if __name__ == '__main__':
    """
    テスト用のメイン関数。このファイルを直接実行した場合に実行される。
    """
    e_api = e_api()
    df = e_api.get_board('8306')
    print(df)
