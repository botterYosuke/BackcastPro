import pandas as pd


# 東証の値幅制限テーブル: (基準価格の上限, 値幅)
PRICE_LIMIT_TABLE = [
    (100, 30),
    (200, 50),
    (500, 80),
    (700, 100),
    (1000, 150),
    (1500, 300),
    (2000, 400),
    (3000, 500),
    (5000, 700),
    (7000, 1000),
    (10000, 1500),
    (15000, 3000),
    (20000, 4000),
    (30000, 5000),
    (float('inf'), 10000),
]


def _Timestamp(value):
    """
    from_/to に与えられる日付入力（str, datetime.date, datetime, pd.Timestamp, None）
    を pandas.Timestamp（もしくは None）に正規化する。

    不正な文字列などは ValueError とする。
    """
    if value is None:
        return None
    try:
        ts = pd.to_datetime(value, errors='raise')
        # pandas.Timestamp は strftime を持つため、そのまま返す
        return ts
    except Exception:
        raise ValueError(f"日付パラメータの形式が不正です: {value}")
