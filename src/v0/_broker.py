"""
ブローカー管理モジュール。
"""

import warnings
from math import copysign
from typing import List, Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

from .order import Order
from .position import Position
from .trade import Trade

if TYPE_CHECKING:
    pass


class _Broker:
    """
    バックテストにおける証券取引の実行、注文管理、ポジション管理、損益計算を担当します。
    実際の証券会社のブローカー機能をシミュレートし、リアルな取引環境を提供します。
    
    Parameters
    ----------
    data : pd.DataFrame
        取引対象の価格データ。Open, High, Low, Closeの列を持つ必要があります。
    cash : float
        初期現金残高。正の値である必要があります。
    spread : float
        ビッドアスクスプレッド（買値と売値の差）。取引コストとして使用されます。
    commission : float or tuple or callable
        手数料の設定方法：
        - float: 相対手数料（例: 0.001 = 0.1%）
        - tuple: (固定手数料, 相対手数料) の組み合わせ
        - callable: カスタム手数料計算関数 (size, price) -> 手数料
    margin : float
        必要証拠金率（0 < margin <= 1）。レバレッジ = 1/margin として計算されます。
    trade_on_close : bool
        取引を終値で実行するかどうか。Trueの場合、次の始値ではなく現在の終値で取引します。
    hedging : bool
        ヘッジングモードの有効化。Trueの場合、反対方向のポジションを同時に保有できます。
    exclusive_orders : bool
        排他的注文モード。Trueの場合、新しい注文が前のポジションを自動的にクローズします。
    """

    # ヒント:
    # 関数定義における`*`の意味
    # - `*`以降の引数は、必ずキーワード引数として渡す必要がある
    # - 位置引数として渡すことはできない
    # なぜキーワード専用引数を使うのか？
    # 1. APIの明確性: 引数の意味が明確になる
    # 2. 保守性: 引数の順序を変更しても既存のコードが壊れない
    # 3. 可読性: 関数呼び出し時に何を渡しているかが分かりやすい
    def __init__(self, *, data, cash, spread, commission, margin,
                 trade_on_close, hedging, exclusive_orders):
        assert cash > 0, f"cash should be > 0, is {cash}"
        assert 0 < margin <= 1, f"margin should be between 0 and 1, is {margin}"
        self._data: dict[str, pd.DataFrame] = data
        self._cash = cash

        # 手数料の登録
        if callable(commission):
            # 関数`commission`が呼び出し可能な場合
            self._commission = commission
        else:
            try:
                self._commission_fixed, self._commission_relative = commission
            except TypeError:
                self._commission_fixed, self._commission_relative = 0, commission
            assert self._commission_fixed >= 0, 'Need fixed cash commission in $ >= 0'
            assert -.1 <= self._commission_relative < .1, \
                ("commission should be between -10% "
                 f"(e.g. market-maker's rebates) and 10% (fees), is {self._commission_relative}")
            self._commission = self._commission_func


        self._spread = spread
        self._leverage = 1 / margin
        self._trade_on_close = trade_on_close
        self._hedging = hedging
        self._exclusive_orders = exclusive_orders

        self._equity = []
        self._current_time = None
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.position = Position(self)
        self.closed_trades: List[Trade] = []

    def _commission_func(self, order_size, price):
        return self._commission_fixed + abs(order_size) * price * self._commission_relative

    def new_order(self,
                  code: str,
                  size: float,
                  limit: Optional[float] = None,
                  stop: Optional[float] = None,
                  sl: Optional[float] = None,
                  tp: Optional[float] = None,
                  tag: object = None,
                  *,
                  trade: Optional[Trade] = None) -> Order:
        """
        Argument size indicates whether the order is long or short
        """
        size = float(size)
        stop = stop and float(stop)
        limit = limit and float(limit)
        sl = sl and float(sl)
        tp = tp and float(tp)

        is_long = size > 0
        assert size != 0, size
        adjusted_price = self._adjusted_price(code, size)

        if is_long:
            if not (sl or -np.inf) < (limit or stop or adjusted_price) < (tp or np.inf):
                raise ValueError(
                    "Long orders require: "
                    f"SL ({sl}) < LIMIT ({limit or stop or adjusted_price}) < TP ({tp})")
        else:
            if not (tp or -np.inf) < (limit or stop or adjusted_price) < (sl or np.inf):
                raise ValueError(
                    "Short orders require: "
                    f"TP ({tp}) < LIMIT ({limit or stop or adjusted_price}) < SL ({sl})")

        order = Order(self, code, size, limit, stop, sl, tp, trade, tag)

        if not trade:
            # 排他的注文（各新しい注文が前の注文/ポジションを自動クローズ）の場合、
            # 事前にすべての非条件付き注文をキャンセルし、すべてのオープン取引をクローズ
            if self._exclusive_orders:
                for o in self.orders:
                    if not o.is_contingent:
                        o.cancel()
                for t in self.trades:
                    t.close()

        # 新しい注文を注文キューに配置、SL注文が最初に処理されるようにする
        self.orders.insert(0 if trade and stop else len(self.orders), order)

        return order

    def last_price(self, code: str) -> float:
        """ Price at the last (current) close. """
        return self._data[code].Close.iloc[-1]

    def _adjusted_price(self, code: str, size=None, price=None) -> float:
        """
        Long/short `price`, adjusted for spread.
        In long positions, the adjusted price is a fraction higher, and vice versa.
        """
        return (price or self.last_price(code)) * (1 + copysign(self._spread, size))

    @property
    def equity(self) -> float:
        return self._cash + sum(trade.pl for trade in self.trades)

    @property
    def margin_available(self) -> float:
        # https://github.com/QuantConnect/Lean/pull/3768 から
        margin_used = sum(trade.value / self._leverage for trade in self.trades)
        return max(0, self.equity - margin_used)

    @property
    def cash(self):
        return self._cash

    @property
    def commission(self):
        return self._commission

    def next(self, current_time: pd.Timestamp):
        self._current_time = current_time
        self._process_orders()

        # エクイティカーブ用にアカウントエクイティを記録
        equity = self.equity
        self._equity.append(equity)

        # エクイティが負の場合、すべてを0に設定してシミュレーションを停止
        if equity <= 0:
            assert self.margin_available <= 0
            for trade in self.trades:
                price = self._data[trade.code].Close.iloc[-1]
                self._close_trade(trade, price, self._current_time)
            self._cash = 0
            raise Exception

    def _process_orders(self):
        data = self._data
        reprocess_orders = False

        # 注文を処理
        for order in list(self.orders):  # 型: Order

            # 関連するSL/TP注文は既に削除されている
            if order not in self.orders:
                continue

            # 注文の銘柄データを取得
            if order.code not in data:
                continue
            df = data[order.code]
            
            # データの存在確認
            if len(df) == 0 or df.index[-1] != self._current_time:
                continue
                
            open, high, low = df.Open.iloc[-1], df.High.iloc[-1], df.Low.iloc[-1]

            # ストップ条件が満たされたかチェック
            stop_price = order.stop
            if stop_price:
                is_stop_hit = ((high >= stop_price) if order.is_long else (low <= stop_price))
                if not is_stop_hit:
                    continue

                # ストップ価格に達すると、ストップ注文は成行/指値注文になる
                # https://www.sec.gov/fast-answers/answersstopordhtm.html
                order._replace(stop_price=None)

            # 購入価格を決定
            # 指値注文が約定可能かチェック
            if order.limit:
                is_limit_hit = low <= order.limit if order.is_long else high >= order.limit
                # ストップとリミットが同じバー内で満たされた場合、悲観的に
                # リミットがストップより先に満たされたと仮定する（つまり「カウントされる前に」）
                is_limit_hit_before_stop = (is_limit_hit and
                                            (order.limit <= (stop_price or -np.inf)
                                            if order.is_long
                                            else order.limit >= (stop_price or np.inf)))
                if not is_limit_hit or is_limit_hit_before_stop:
                    continue

                # stop_priceが設定されている場合、このバー内で満たされた
                price = (min(stop_price or open, order.limit)
                        if order.is_long else
                        max(stop_price or open, order.limit))
            else:
                # 成行注文（Market-if-touched / market order）
                # 条件付き注文は常に次の始値で
                prev_close = df.Close.iloc[-2]
                price = prev_close if self._trade_on_close and not order.is_contingent else open
                if stop_price:
                    price = max(price, stop_price) if order.is_long else min(price, stop_price)

                # エントリー/エグジットバーのインデックスを決定
                is_market_order = not order.limit and not stop_price

                # 注文がSL/TP注文の場合、それが依存していた既存の取引をクローズする必要がある
                if order.parent_trade:
                    trade = order.parent_trade
                    _prev_size = trade.size
                    # order.sizeがtrade.sizeより「大きい」場合、この注文はtrade.close()注文で
                    # 取引の一部は事前にクローズされている
                    size = copysign(min(abs(_prev_size), abs(order.size)), order.size)
                    # この取引がまだクローズされていない場合（例：複数の`trade.close(.5)`呼び出し）
                    if trade in self.trades:
                        self._reduce_trade(trade, price, size, self._current_time)
                        assert order.size != -_prev_size or trade not in self.trades
                        if price == stop_price:
                            # 統計用にSLを注文に戻す
                            trade._sl_order._replace(stop_price=stop_price)
                    if order in (trade._sl_order,
                                trade._tp_order):
                        assert order.size == -trade.size
                        assert order not in self.orders  # 取引がクローズされたときに削除される
                    else:
                        # trade.close()注文で、完了
                        assert abs(_prev_size) >= abs(size) >= 1
                        self.orders.remove(order)
                    continue

                # そうでなければ、これは独立した取引

                # 手数料（またはビッドアスクスプレッド）を含むように価格を調整
                # ロングポジションでは調整価格が少し高くなり、その逆も同様
                adjusted_price = self._adjusted_price(code=order.code, size=order.size, price=price)
                adjusted_price_plus_commission = \
                    adjusted_price + self._commission(order.size, price) / abs(order.size)

                # 注文サイズが比例的に指定された場合、
                # マージンとスプレッド/手数料を考慮して、単位での真のサイズを事前計算
                size = order.size
                if -1 < size < 1:
                    size = copysign(int((self.margin_available * self._leverage * abs(size))
                                        // adjusted_price_plus_commission), size)
                    # 単一ユニットでも十分な現金/マージンがない
                    if not size:
                        warnings.warn(
                            f'{self._current_time}: ブローカーは相対サイズの注文を'
                            f'不十分なマージンのためキャンセルしました。', category=UserWarning)
                        # XXX: 注文はブローカーによってキャンセルされる？
                        self.orders.remove(order)
                        continue
                assert size == round(size)
                need_size = int(size)

                if not self._hedging:
                    # 既存の反対方向の取引をFIFOでクローズ/削減してポジションを埋める
                    # 既存の取引は調整価格でクローズされる（調整は購入時に既に行われているため）
                    for trade in list(self.trades):
                        if trade.is_long == order.is_long:
                            continue
                        assert trade.size * order.size < 0

                        # 注文サイズがこの反対方向の既存取引より大きい場合、
                        # 完全にクローズされる
                        if abs(need_size) >= abs(trade.size):
                            self._close_trade(trade, price, self._current_time)
                            need_size += trade.size
                        else:
                            # 既存の取引が新しい注文より大きい場合、
                            # 部分的にのみクローズされる
                            self._reduce_trade(trade, price, need_size, self._current_time)
                            need_size = 0

                        if not need_size:
                            break

                # 注文をカバーするのに十分な流動性がない場合、ブローカーはそれをキャンセルする
                if abs(need_size) * adjusted_price_plus_commission > \
                        self.margin_available * self._leverage:
                    self.orders.remove(order)
                    continue

                # 新しい取引を開始
                if need_size:
                    self._open_trade(order.code,
                                    adjusted_price,
                                    need_size,
                                    order.sl,
                                    order.tp,
                                    self._current_time,
                                    order.tag)

                    # 新しくキューに追加されたSL/TP注文を再処理する必要がある
                    # これにより、注文が開かれた同じバーでSLがヒットすることを可能にする
                    # https://github.com/kernc/backtesting.py/issues/119 を参照
                    if order.sl or order.tp:
                        if is_market_order:
                            reprocess_orders = True
                        # Order.stopとTPが同じバー内でヒットしたが、SLはヒットしなかった。この場合
                        # ストップとTPが同じ価格方向に進むため、曖昧ではない
                        elif stop_price and not order.limit and order.tp and (
                                (order.is_long and order.tp <= high and (order.sl or -np.inf) < low) or
                                (order.is_short and order.tp >= low and (order.sl or np.inf) > high)):
                            reprocess_orders = True
                        elif (low <= (order.sl or -np.inf) <= high or
                            low <= (order.tp or -np.inf) <= high):
                            warnings.warn(
                                f"({df.index[-1]}) 条件付きSL/TP注文が、その親ストップ/リミット注文が取引に"
                                "変換された同じバーで実行されることになります。"
                                "正確なローソク足内価格変動を断言できないため、"
                                "影響を受けるSL/TP注文は代わりに次の（マッチングする）価格/バーで"
                                "実行され、結果（この取引の）が幾分疑わしいものになります。"
                                "https://github.com/kernc/backtesting.py/issues/119 を参照",
                                UserWarning)

                # 注文処理完了
                self.orders.remove(order)

        if reprocess_orders:
            self._process_orders()

    def _reduce_trade(self, trade: Trade, price: float, size: float, current_time: pd.Timestamp):
        assert trade.size * size < 0
        assert abs(trade.size) >= abs(size)

        size_left = trade.size + size
        assert size_left * trade.size >= 0
        if not size_left:
            close_trade = trade
        else:
            # 既存の取引を削減...
            trade._replace(size=size_left)
            if trade._sl_order:
                trade._sl_order._replace(size=-trade.size)
            if trade._tp_order:
                trade._tp_order._replace(size=-trade.size)

            # ... その削減コピーをクローズすることによって
            close_trade = trade._copy(size=-size, sl_order=None, tp_order=None)
            self.trades.append(close_trade)

        self._close_trade(close_trade, price, current_time)

    def _close_trade(self, trade: Trade, price: float, current_time: pd.Timestamp):
        self.trades.remove(trade)
        if trade._sl_order:
            self.orders.remove(trade._sl_order)
        if trade._tp_order:
            self.orders.remove(trade._tp_order)

        closed_trade = trade._replace(exit_price=price, exit_time=current_time)
        self.closed_trades.append(closed_trade)
        # 取引終了時に手数料を再度適用
        commission = self._commission(trade.size, price)
        self._cash += trade.pl - commission
        # 統計用にTradeインスタンスに手数料を保存
        trade_open_commission = self._commission(closed_trade.size, closed_trade.entry_price)
        # サイズが_reduce_trade()によって変更された可能性があるため、
        # Trade開始時ではなくここで適用
        closed_trade._commissions = commission + trade_open_commission

    def _open_trade(self, code: str, price: float, size: int,
                    sl: Optional[float], tp: Optional[float], current_time: pd.Timestamp, tag):
        trade = Trade(self, code, size, price, current_time, tag)
        self.trades.append(trade)
        # 取引開始時にブローカー手数料を適用
        self._cash -= self._commission(size, price)
        # SL/TP（ブラケット）注文を作成。
        if tp:
            trade.tp = tp
        if sl:
            trade.sl = sl
