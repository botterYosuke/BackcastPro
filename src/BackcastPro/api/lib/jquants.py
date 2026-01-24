import requests
import os
from datetime import datetime
import pandas as pd
import logging
import threading

# 環境変数を読み込み
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_TIMEOUT_SECONDS = 10


class jquants:
    """
    J-Quants API Client (Singleton)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(jquants, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 既に初期化済みの場合はスキップ
        if hasattr(self, "_initialized"):
            return

        self.API_URL = "https://api.jquants.com"
        self.api_key = os.getenv("JQUANTS_API_KEY")
        self.headers = {}
        self._initialized = True
        self.isEnable = self._set_api_key()
        if self.isEnable:
            self.headers = {"x-api-key": self.api_key}

    def _set_api_key(self) -> bool:
        """
        APIキーを設定
        """
        if not self.api_key:
            logger.warning("J-QuantsのAPIキーが設定されていません。")
            return False
        logger.info("API使用の準備が完了しました。")
        return True

    def _ensure_api_key(self) -> bool:
        """
        APIキーが利用可能かを確認する
        """
        if self.isEnable:
            return True
        self.api_key = os.getenv("JQUANTS_API_KEY")
        if not self.api_key:
            return False
        self.headers = {"x-api-key": self.api_key}
        self.isEnable = True
        return True

    def _handle_auth_error(self, res: requests.Response) -> None:
        if res.status_code in (401, 403):
            logger.error(f"API認証エラー: {res.status_code}")
            self.isEnable = False

    def _get_all_pages(self, endpoint: str, params: dict) -> list:
        if not self._ensure_api_key():
            return []

        data: list = []
        page_params = dict(params)
        while True:
            res = requests.get(
                f"{self.API_URL}{endpoint}",
                params=page_params,
                headers=self.headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if res.status_code in (401, 403):
                self._handle_auth_error(res)
                break
            if res.status_code != 200:
                try:
                    logger.error(f"API Error: {res.status_code} - {res.json()}")
                except Exception:
                    logger.error(f"API Error: {res.status_code} - {res.text}")
                break

            d = res.json()
            data += d.get("data", [])
            pagination_key = d.get("pagination_key")
            if pagination_key:
                page_params["pagination_key"] = pagination_key
                continue
            break

        return data

    def get_listed_info(self, code="", date="") -> pd.DataFrame:
        """
        上場銘柄一覧（/v2/equities/master）

        - 過去時点での銘柄情報、当日の銘柄情報および翌営業日時点の銘柄情報が取得可能です。
        - データの取得では、銘柄コード（code）または日付（date）の指定が可能です。

        （データ更新時刻）
        - 毎営業日の24:00頃

        """
        if isinstance(date, datetime):
            date = date.strftime("%Y-%m-%d")

        params = {}
        if code != "":
            # codeが4文字だったら末尾に0を付けて
            if len(code) == 4:
                code = code + "0"
            params["code"] = code
        if date != "":
            params["date"] = date

        data = self._get_all_pages("/v2/equities/master", params)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if "Code" not in df.columns and "code" in df.columns:
            df = df.rename(columns={"code": "Code"})
        if "CompanyName" not in df.columns and "Name" in df.columns:
            df = df.rename(columns={"Name": "CompanyName"})
        df["source"] = "j-quants"

        return df

    def get_daily_quotes(
        self, code: str, from_: datetime = None, to: datetime = None
    ) -> pd.DataFrame:
        """
        株価四本値（/v2/equities/bars/daily）

        - 株価は分割・併合を考慮した調整済み株価（小数点第２位四捨五入）と調整前の株価を取得することができます。
        - データの取得では、銘柄コード（code）または日付（date）の指定が必須となります。

        （データ更新時刻）
        - 毎営業日の17:00頃

        - Premiumプランの方には、日通しに加え、前場(Morning)及び後場(Afternoon)の四本値及び取引高（調整前・後両方）・取引代金が取得可能です。
        - データの取得では、日付（date）を指定して全銘柄取得するモードがあるが、非対応となっています。
        """
        # V2では code または date が必須のため code を要求する
        if not code or not str(code).strip():
            raise ValueError("銘柄コードが指定されていません")

        # codeが4文字だったら末尾に0を付けて
        if len(code) == 4:
            code = code + "0"

        params = {}
        if code != "":
            params["code"] = code
        if from_ is not None:
            # 文字列形式の日付も対応
            if isinstance(from_, str):
                from_ = datetime.strptime(from_, "%Y-%m-%d")
            params["from"] = from_.strftime("%Y-%m-%d")
        if to is not None:
            # 文字列形式の日付も対応
            if isinstance(to, str):
                to = datetime.strptime(to, "%Y-%m-%d")
            params["to"] = to.strftime("%Y-%m-%d")

        data = self._get_all_pages("/v2/equities/bars/daily", params)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df = _rename_daily_quote_columns(df)
        # 型変換（日次株価フィールド定義に基づく）
        df = _normalize_columns(df)
        df["source"] = "j-quants"

        return df

    def get_fins_statements(self, code="", date="", from_="", to="") -> pd.DataFrame:
        """
        財務情報（/v2/fins/summary）

        - 財務情報APIでは、上場企業がTDnetへ提出する決算短信Summary等を基に作成された、四半期毎の財務情報を取得することができます。
        - データの取得では、銘柄コード（code）または開示日（date）の指定が必須です。

        （データ更新時刻）
        - 速報18:00頃、確報24:30頃
        """
        params = {}
        if code != "":
            # codeが4文字だったら末尾に0を付けて
            if len(code) == 4:
                code = code + "0"
            params["code"] = code
        if date != "":
            params["date"] = date
        if from_ != "":
            params["from"] = from_
        if to != "":
            params["to"] = to

        data = self._get_all_pages("/v2/fins/summary", params)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["source"] = "j-quants"

        return df

    def get_fins_announcement(self) -> pd.DataFrame:
        """
        決算発表予定日（/v2/equities/earnings-calendar）

        （データ更新時刻）
        - 不定期（更新がある日は）19:00頃

        - [当該ページ](https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html)で、3月期・９月期決算会社分に更新があった場合のみ19時ごろに更新されます。
        """
        params = {}
        data = self._get_all_pages("/v2/equities/earnings-calendar", params)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["source"] = "j-quants"

        return df

    def get_market_trading_calendar(
        self, holidaydivision="", from_="", to=""
    ) -> pd.DataFrame:
        """
        取引カレンダー（/v2/markets/calendar）

        - 東証およびOSEにおける営業日、休業日、ならびにOSEにおける祝日取引の有無の情報を取得できます。
        - データの取得では、休日区分（holidaydivision）または日付（from/to）の指定が可能です。

        （データ更新日）
        - 不定期（原則として、毎年2月頃をめどに翌年1年間の営業日および祝日取引実施日（予定）を更新します。）
        """
        params = {}
        if holidaydivision != "":
            params["hol_div"] = holidaydivision
        if from_ != "":
            params["from"] = from_
        if to != "":
            params["to"] = to

        data = self._get_all_pages("/v2/markets/calendar", params)
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["source"] = "j-quants"

        return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    カラム名をJ-Quants APIの形式に統一し、型変換を行う

    日次株価のフィールド定義に基づいた型変換:
    - Date: string (YYYY-MM-DD) → DatetimeIndex
    - Code: string → string
    - 数値フィールド: number → float
      (Open, High, Low, Close, Volume, TurnoverValue,
       UpperLimit, LowerLimit, AdjustmentFactor,
       AdjustmentOpen, AdjustmentHigh, AdjustmentLow,
       AdjustmentClose, AdjustmentVolume)
    """
    # 既にDatetimeIndexの場合はそのまま処理を続行
    if isinstance(df.index, pd.DatetimeIndex):
        pass
    # Date列をdatetime型に変換してindexに設定
    elif "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    else:
        # インデックスが日付でない場合は、警告を出す
        logger.warning("Dateカラムが存在せず、インデックスも日付型ではありません")

    # Code列はstring型として保持（明示的に変換）
    if "Code" in df.columns:
        df["Code"] = df["Code"].astype(str)

    # 数値フィールドの定義
    numeric_fields = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "TurnoverValue",
        "UpperLimit",
        "LowerLimit",
        "AdjustmentFactor",
        "AdjustmentOpen",
        "AdjustmentHigh",
        "AdjustmentLow",
        "AdjustmentClose",
        "AdjustmentVolume",
    ]

    # DataFrameに存在する数値フィールドのみ変換
    for field in numeric_fields:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce")

    # カラムの順序を統一（Dateはindexなので含めない）
    column_order = [
        "Code",
        "Open",
        "High",
        "Low",
        "Close",
        "UpperLimit",
        "LowerLimit",
        "Volume",
        "TurnoverValue",
        "AdjustmentFactor",
        "AdjustmentOpen",
        "AdjustmentHigh",
        "AdjustmentLow",
        "AdjustmentClose",
        "AdjustmentVolume",
    ]
    # 存在するカラムのみを選択
    available_columns = [col for col in column_order if col in df.columns]
    # 存在しないカラムも含める（順序は保持）
    all_columns = available_columns + [
        col for col in df.columns if col not in column_order
    ]
    df = df[all_columns].copy()

    return df


def _rename_daily_quote_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    V2日次株価の短縮カラムを既存の列名へ変換
    """
    rename_map = {
        "O": "Open",
        "H": "High",
        "L": "Low",
        "C": "Close",
        "Vo": "Volume",
        "V": "Volume",
        "Va": "TurnoverValue",
        "TV": "TurnoverValue",
        "UL": "UpperLimit",
        "LL": "LowerLimit",
        "AdjFactor": "AdjustmentFactor",
        "AdjO": "AdjustmentOpen",
        "AdjH": "AdjustmentHigh",
        "AdjL": "AdjustmentLow",
        "AdjC": "AdjustmentClose",
        "AdjVo": "AdjustmentVolume",
        "AdjV": "AdjustmentVolume",
    }
    columns = {k: v for k, v in rename_map.items() if k in df.columns}
    if columns:
        df = df.rename(columns=columns)
    if "Code" not in df.columns and "code" in df.columns:
        df = df.rename(columns={"code": "Code"})
    if "Date" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "Date"})
    return df
