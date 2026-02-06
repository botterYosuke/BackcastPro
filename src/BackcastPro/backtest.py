"""
バックテスト管理モジュール。
"""

import sys
import warnings
from functools import partial
from numbers import Number
from typing import Callable, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ._broker import _Broker
from ._stats import compute_stats


class Backtest:
    """
    特定のデータに対してバックテストを実行します。

    バックテストを初期化します。
    初期化後、`Backtest.runy`メソッドを呼び出して実行します。

    `data`は以下の列を持つ`pd.DataFrame`です：
    `Open`, `High`, `Low`, `Close`, および（オプションで）`Volume`。
    列が不足している場合は、利用可能なものに設定してください。
    例：

        df['Open'] = df['High'] = df['Low'] = df['Close']

    渡されたデータフレームには、戦略で使用できる追加の列
    （例：センチメント情報）を含めることができます。
    DataFrameのインデックスは、datetimeインデックス（タイムスタンプ）または
    単調増加の範囲インデックス（期間のシーケンス）のいずれかです。

    `cash`は開始時の初期現金です。

    `spread`は一定のビッドアスクスプレッド率（価格に対する相対値）です。
    例：平均スプレッドがアスク価格の約0.2‰である手数料なしの
    外国為替取引では`0.0002`に設定してください。

    `commission`は手数料率です。例：ブローカーの手数料が
    注文価値の1%の場合、commissionを`0.01`に設定してください。
    手数料は2回適用されます：取引開始時と取引終了時です。
    単一の浮動小数点値に加えて、`commission`は浮動小数点値の
    タプル`(fixed, relative)`にすることもできます。例：ブローカーが
    最低$100 + 1%を請求する場合は`(100, .01)`に設定してください。
    さらに、`commission`は呼び出し可能な
    `func(order_size: int, price: float) -> float`
    （注：ショート注文では注文サイズは負の値）にすることもでき、
    より複雑な手数料構造をモデル化するために使用できます。
    負の手数料値はマーケットメーカーのリベートとして解釈されます。

    `margin`はレバレッジアカウントの必要証拠金（比率）です。
    初期証拠金と維持証拠金の区別はありません。
    ブローカーが許可する50:1レバレッジなどでバックテストを実行するには、
    marginを`0.02`（1 / レバレッジ）に設定してください。

    `trade_on_close`が`True`の場合、成行注文は
    次のバーの始値ではなく、現在のバーの終値で約定されます。

    `exclusive_orders`が`True`の場合、各新しい注文は前の
    取引/ポジションを自動クローズし、各時点で最大1つの取引
    （ロングまたはショート）のみが有効になります。

    `finalize_trades`が`True`の場合、バックテスト終了時に
    まだ[アクティブで継続中]の取引は最後のバーでクローズされ、
    計算されたバックテスト統計に貢献します。
    """

    def __init__(self,
                data: dict[str, pd.DataFrame] = None,
                *,
                cash: float = 10_000,
                spread: float = .0,
                commission: Union[float, Tuple[float, float]] = .0,
                margin: float = 1.,
                trade_on_close=False,
                exclusive_orders=False,
                finalize_trades=False,
                ):

        if not isinstance(spread, Number):
            raise TypeError('`spread` must be a float value, percent of '
                            'entry order price')
        if not isinstance(commission, (Number, tuple)) and not callable(commission):
            raise TypeError('`commission` must be a float percent of order value, '
                            'a tuple of `(fixed, relative)` commission, '
                            'or a function that takes `(order_size, price)`'
                            'and returns commission dollar value')

        # partialとは、関数の一部の引数を事前に固定して、新しい関数を作成します。
        # これにより、後で残りの引数だけを渡せば関数を実行できるようになります。
        # 1. _Brokerクラスのコンストラクタの引数の一部（cash, spread, commissionなど）を事前に固定
        # 2. 新しい関数（実際には呼び出し可能オブジェクト）を作成
        # 3. 後で残りの引数（おそらくdataなど）を渡すだけで_Brokerのインスタンスを作成できるようにする
        self._broker_factory = partial[_Broker](
            _Broker, cash=cash, spread=spread, commission=commission, margin=margin,
            trade_on_close=trade_on_close, exclusive_orders=exclusive_orders
        )

        self._results: Optional[pd.Series] = None
        self._finalize_trades = bool(finalize_trades)

        # ステップ実行用の状態管理
        self._broker_instance: Optional[_Broker] = None
        self._step_index = 0
        self._is_started = False
        self._is_finished = False
        self._current_data: dict[str, pd.DataFrame] = {}

        # パフォーマンス最適化: 各銘柄の index position マッピング
        self._index_positions: dict[str, dict] = {}

        # 戦略関数
        self._strategy: Optional[Callable[['Backtest'], None]] = None

        # 取引コールバックリスト（複数登録可能）
        self._trade_callbacks: list[Callable[[str, 'Trade'], None]] = []

        # データを設定（set_data内でstart()が自動的に呼ばれる）
        self.set_data(data)

    def _validate_and_prepare_df(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """
        単一のDataFrameをバリデーションし、準備します。
        
        Args:
            df: バリデーションするDataFrame
            code: データの識別子（エラーメッセージ用）
        
        Returns:
            バリデーション済みのDataFrame（コピー）
        
        Raises:
            TypeError: DataFrameでない場合
            ValueError: 必要な列がない場合、またはNaN値が含まれる場合
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"`data[{code}]` must be a pandas.DataFrame with columns")
        
        # データフレームのコピーを作成
        df = df.copy()
        
        # インデックスをdatetimeインデックスに変換
        if (not isinstance(df.index, pd.DatetimeIndex) and
            not isinstance(df.index, pd.RangeIndex) and
            # 大部分が大きな数値の数値インデックス
            (df.index.is_numeric() and
            (df.index > pd.Timestamp('1975').timestamp()).mean() > .8)):
            try:
                df.index = pd.to_datetime(df.index, infer_datetime_format=True)
            except ValueError:
                pass
        
        # Volume列がない場合は追加
        if 'Volume' not in df:
            df['Volume'] = np.nan
        
        # 空のDataFrameチェック
        if len(df) == 0:
            raise ValueError(f'OHLC `data[{code}]` is empty')
        
        # 必要な列の確認
        if len(df.columns.intersection({'Open', 'High', 'Low', 'Close', 'Volume'})) != 5:
            raise ValueError(f"`data[{code}]` must be a pandas.DataFrame with columns "
                            "'Open', 'High', 'Low', 'Close', and (optionally) 'Volume'")
        
        # NaN値の確認
        if df[['Open', 'High', 'Low', 'Close']].isnull().values.any():
            raise ValueError('Some OHLC values are missing (NaN). '
                            'Please strip those lines with `df.dropna()` or '
                            'fill them in with `df.interpolate()` or whatever.')
        
        # インデックスのソート確認
        if not df.index.is_monotonic_increasing:
            warnings.warn(f'data[{code}] index is not sorted in ascending order. Sorting.',
                        stacklevel=3)
            df = df.sort_index()
        
        # インデックスの型警告
        if not isinstance(df.index, pd.DatetimeIndex):
            warnings.warn(f'data[{code}] index is not datetime. Assuming simple periods, '
                        'but `pd.DateTimeIndex` is advised.',
                        stacklevel=3)
        
        return df


    def set_data(self, data):
        self._data = None
        if data is None:
            return

        data = data.copy()

        # 各DataFrameをバリデーションして準備
        for code, df in data.items():
            data[code] = self._validate_and_prepare_df(df, code)

        # 辞書dataに含まれる全てのdf.index一覧を作成
        # df.indexが不一致の場合のために、どれかに固有値があれば抽出しておくため
        self.index: pd.DatetimeIndex = pd.DatetimeIndex(sorted({idx for df in data.values() for idx in df.index}))

        self._data: dict[str, pd.DataFrame] = data

        # データ設定後、自動的にバックテストを開始
        self.start()

    def set_cash(self, cash):
        self._broker_factory.keywords['cash'] = cash

    def set_strategy(self, strategy: Callable[['Backtest'], None]) -> 'Backtest':
        """
        戦略関数を設定する。

        設定された戦略は step() の最初に自動的に呼び出される。
        これは run() や goto() と同じタイミング。

        Args:
            strategy: 各ステップで呼び出す戦略関数 (bt) -> None

        Returns:
            self (メソッドチェーン用)
        """
        self._strategy = strategy
        return self

    # =========================================================================
    # ステップ実行 API
    # =========================================================================

    def start(self) -> 'Backtest':
        """バックテストを開始準備する"""
        if self._data is None:
            raise ValueError("data が設定されていません")

        self._broker_instance = self._broker_factory(data=self._data)
        self._step_index = 0
        self._is_started = True
        self._is_finished = False
        self._current_data = {}
        self._results = None

        # パフォーマンス最適化: 各銘柄の index → position マッピングを事前計算
        self._index_positions = {}
        for code, df in self._data.items():
            self._index_positions[code] = {
                ts: i for i, ts in enumerate(df.index)
            }

        # 取引イベントパブリッシャーをコールバックリストに追加（重複防止）
        if hasattr(self, "_trade_event_publisher") and self._trade_event_publisher:
            def on_trade_publish(event_type: str, trade):
                self._trade_event_publisher.emit_from_trade(trade, is_opening=True)
            # 関数オブジェクトの同一性比較はできないので、フラグで重複チェック
            if not getattr(self, "_trade_event_publisher_registered", False):
                self._trade_callbacks.append(on_trade_publish)
                self._trade_event_publisher_registered = True

        # 全コールバックをブローカーに設定
        self._setup_trade_callbacks()

        return self

    def step(self) -> bool:
        """
        1ステップ（1バー）進める。

        【タイミング】
        - step(t) 実行時、data[:t] が見える状態になる
        - 注文は broker.next(t) 内で処理される

        Returns:
            bool: まだ続行可能なら True、終了なら False
        """
        if not self._is_started:
            raise RuntimeError("start() を呼び出してください")

        if self._is_finished:
            return False

        if self._step_index >= len(self.index):
            self._is_finished = True
            return False

        current_time = self.index[self._step_index]

        with np.errstate(invalid='ignore'):
            # パフォーマンス最適化: iloc ベースで slicing
            for code, df in self._data.items():
                if current_time in self._index_positions[code]:
                    pos = self._index_positions[code][current_time]
                    self._current_data[code] = df.iloc[:pos + 1]
                # current_time がこの銘柄に存在しない場合は前の状態を維持

            # 戦略を呼び出し（_current_data 設定後に呼ぶ）
            if self._strategy is not None:
                self._strategy(self)

            # ブローカー処理（注文の約定）
            try:
                self._broker_instance._data = self._current_data
                self._broker_instance.next(current_time)
            except Exception:
                self._is_finished = True
                return False

        self._step_index += 1

        if self._step_index >= len(self.index):
            self._is_finished = True

        return not self._is_finished

    def reset(self) -> 'Backtest':
        """バックテストをリセットして最初から"""
        self._broker_instance = self._broker_factory(data=self._data)
        self._step_index = 0
        self._is_finished = False
        self._results = None
        # 初期データ（最初の1行）でリセット
        self._current_data = {}
        if self._data:
            for code, df in self._data.items():
                if len(df) > 0:
                    self._current_data[code] = df.iloc[:1]

        # 取引コールバックを新しいブローカーに再登録
        self._setup_trade_callbacks()

        return self

    def goto(self, step: int, strategy: Callable[['Backtest'], None] = None) -> 'Backtest':
        """
        指定ステップまで進める（スライダー連携用）

        Args:
            step: 目標のステップ番号（1-indexed、0以下は1に丸められる）
            strategy: 各ステップで呼び出す戦略関数（省略可）
                      ※ strategy は step() の **前** に呼ばれます

        Note:
            step < 現在位置 の場合、reset() してから再実行します。
        """
        step = max(1, min(step, len(self.index)))

        # 現在より前に戻る場合はリセット
        if step < self._step_index:
            self.reset()

        # 目標まで進める（戦略を適用しながら）
        # 引数の strategy が渡された場合は一時的に上書き
        original_strategy = self._strategy
        if strategy is not None:
            self._strategy = strategy

        try:
            while self._step_index < step and not self._is_finished:
                self.step()
        finally:
            self._strategy = original_strategy

        return self

    # =========================================================================
    # 売買 API
    # =========================================================================

    def buy(self, *,
            code: str = None,
            size: float = None,
            limit: Optional[float] = None,
            stop: Optional[float] = None,
            sl: Optional[float] = None,
            tp: Optional[float] = None,
            tag: object = None):
        """
        買い注文を発注する。

        Args:
            code: 銘柄コード（1銘柄のみの場合は省略可）
            size: 注文数量（省略時は利用可能資金の99.99%）
            limit: 指値価格
            stop: 逆指値価格
            sl: ストップロス価格
            tp: テイクプロフィット価格
            tag: 注文理由（例: "dip_buy", "breakout"）→ チャートに表示可能
        """
        if not self._is_started:
            raise RuntimeError("start() を呼び出してください")

        if code is None:
            if len(self._data) == 1:
                code = list(self._data.keys())[0]
            else:
                raise ValueError("複数銘柄がある場合はcodeを指定してください")

        if size is None:
            size = 1 - sys.float_info.epsilon

        return self._broker_instance.new_order(code, size, limit, stop, sl, tp, tag)

    def sell(self, *,
             code: str = None,
             size: float = None,
             limit: Optional[float] = None,
             stop: Optional[float] = None,
             sl: Optional[float] = None,
             tp: Optional[float] = None,
             tag: object = None):
        """
        売り注文を発注する。

        Args:
            code: 銘柄コード（1銘柄のみの場合は省略可）
            size: 注文数量（省略時は利用可能資金の99.99%）
            limit: 指値価格
            stop: 逆指値価格
            sl: ストップロス価格
            tp: テイクプロフィット価格
            tag: 注文理由（例: "profit_take", "stop_loss"）→ チャートに表示可能
        """
        if not self._is_started:
            raise RuntimeError("start() を呼び出してください")

        if code is None:
            if len(self._data) == 1:
                code = list(self._data.keys())[0]
            else:
                raise ValueError("複数銘柄がある場合はcodeを指定してください")

        if size is None:
            size = 1 - sys.float_info.epsilon

        return self._broker_instance.new_order(code, -size, limit, stop, sl, tp, tag)

    # =========================================================================
    # ステップ実行用プロパティ
    # =========================================================================

    @property
    def data(self) -> dict[str, pd.DataFrame]:
        """現在時点までのデータ"""
        if len(self._current_data) == 0:
            return self._data
        return self._current_data

    @property
    def position(self) -> int:
        """
        現在のポジションサイズ（全銘柄合計）

        ⚠️ 注意: 複数銘柄を扱う場合は position_of(code) を使用してください。
        このプロパティは後方互換性のために残されています。
        """
        if not self._is_started or self._broker_instance is None:
            return 0
        return self._broker_instance.position.size

    def position_of(self, code: str) -> int:
        """
        指定銘柄のポジションサイズ（推奨）

        Args:
            code: 銘柄コード

        Returns:
            int: ポジションサイズ（正: ロング、負: ショート、0: ノーポジ）
        """
        if not self._is_started or self._broker_instance is None:
            return 0
        return sum(t.size for t in self._broker_instance.trades if t.code == code)

    @property
    def equity(self) -> float:
        """現在の資産"""
        if not self._is_started or self._broker_instance is None:
            return self._broker_factory.keywords.get('cash', 0)
        return self._broker_instance.equity

    @property
    def is_finished(self) -> bool:
        """完了したかどうか"""
        return self._is_finished

    @property
    def current_time(self) -> Optional[pd.Timestamp]:
        """現在の日時"""
        if self._step_index == 0 or not hasattr(self, 'index'):
            return None
        return self.index[self._step_index - 1]

    @property
    def progress(self) -> float:
        """進捗率（0.0〜1.0）"""
        if not hasattr(self, 'index') or len(self.index) == 0:
            return 0.0
        return self._step_index / len(self.index)

    @property
    def step_index(self) -> int:
        """現在のステップインデックス（read-only）"""
        return self._step_index

    @property
    def trades(self) -> List:
        """アクティブな取引リスト"""
        if not self._is_started or self._broker_instance is None:
            return []
        return list(self._broker_instance.trades)

    @property
    def closed_trades(self) -> List:
        """決済済み取引リスト"""
        if not self._is_started or self._broker_instance is None:
            return []
        return list(self._broker_instance.closed_trades)

    @property
    def orders(self) -> List:
        """未約定の注文リスト"""
        if not self._is_started or self._broker_instance is None:
            return []
        return list(self._broker_instance.orders)

    # =========================================================================
    # 状態スナップショット / コールバック API
    # =========================================================================

    def get_state_snapshot(self) -> dict:
        """現在の状態を辞書で返す（marimo非依存）

        Returns:
            dict: current_time, progress, equity, cash, position, positions,
                  closed_trades, step_index, total_steps を含む辞書
        """
        positions: dict[str, int] = {}
        for trade in self.trades:
            code = trade.code
            positions[code] = positions.get(code, 0) + trade.size

        return {
            "current_time": str(self.current_time) if self.current_time else "-",
            "progress": float(self.progress),
            "equity": float(self.equity),
            "cash": float(self.cash),
            "position": self.position,
            "positions": positions,
            "closed_trades": len(self.closed_trades),
            "step_index": self.step_index,
            "total_steps": len(self.index) if hasattr(self, "index") else 0,
        }

    def add_trade_callback(
        self, callback: Callable[[str, 'Trade'], None]
    ) -> None:
        """取引発生時のコールバックを追加（複数登録可能）

        Args:
            callback: (event_type: 'BUY'|'SELL', trade) を受け取る関数
        """
        self._trade_callbacks.append(callback)
        # 既にブローカーが存在する場合は即座に反映
        if self._broker_instance:
            self._setup_trade_callbacks()

    def _setup_trade_callbacks(self) -> None:
        """全コールバックをブローカーに設定"""
        if not self._trade_callbacks:
            return

        def emit_all(event_type: str, trade):
            for cb in self._trade_callbacks:
                cb(event_type, trade)

        self._broker_instance.set_on_trade_event(emit_all)

    # =========================================================================
    # finalize / run
    # =========================================================================

    def finalize(self) -> pd.Series:
        """統計を計算して結果を返す"""
        if self._results is not None:
            return self._results

        if not self._is_started:
            raise RuntimeError("バックテストが開始されていません")

        broker = self._broker_instance

        if self._finalize_trades:
            for trade in reversed(broker.trades):
                trade.close()
            if self._step_index > 0:
                broker.next(self.index[self._step_index - 1])
        elif len(broker.trades):
            warnings.warn(
                'バックテスト終了時に一部の取引がオープンのままです。'
                '`Backtest(..., finalize_trades=True)`を使用してクローズし、'
                '統計に含めてください。', stacklevel=2)

        # インデックスが空の場合のガード
        result_index = self.index[:self._step_index] if self._step_index > 0 else self.index[:1]

        equity = pd.Series(broker._equity).bfill().fillna(broker._cash).values
        self._results = compute_stats(
            trades=broker.closed_trades,
            equity=np.array(equity),
            index=result_index,
            strategy_instance=None,
            risk_free_rate=0.0,
        )

        return self._results

    def run(self) -> pd.Series:
        """
        バックテストを最後まで実行（ステップ実行API版）
        """
        if not self._is_started:
            self.start()

        while not self._is_finished:
            self.step()

        return self.finalize()

    @property
    def cash(self):
        """現在の現金残高"""
        if self._is_started and self._broker_instance is not None:
            return self._broker_instance.cash
        # partialで初期化されている場合、初期化時のcash値を返す
        return self._broker_factory.keywords.get('cash', 0)

    @property
    def commission(self):
        # partialで初期化されている場合、初期化時のcommission値を返す
        return self._broker_factory.keywords.get('commission', 0)

