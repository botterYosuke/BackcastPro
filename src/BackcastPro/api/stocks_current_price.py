from datetime import datetime
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_stock_current_price(code: str) -> dict | None:
    """
    kabuステーションAPIから現在値・出来高・時刻を取得する

    Args:
        code (str): 銘柄コード（例: "8306"）

    Returns:
        dict | None: {"price": float, "volume": float, "time": datetime} or None
    """
    from trading_data.lib.kabusap import kabusap

    api = kabusap()
    return api.get_current_price(code=code)
