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

        # チャートウィジェットキャッシュ（パフォーマンス最適化）
        self._chart_widgets: dict = {}
        self._chart_last_index: dict[str, int] = {}
        self._chart_indicators: dict[str, tuple] = {}  # (indicators, indicator_options)

        # 戦略関数
        self._strategy: Optional[Callable[['Backtest'], None]] = None

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

        # 取引イベントパブリッシャーが既に設定されている場合、コールバックを登録
        if hasattr(self, "_trade_event_publisher") and self._trade_event_publisher:
            def on_trade(event_type: str, trade):
                self._trade_event_publisher.emit_from_trade(trade, is_opening=True)
            self._broker_instance.set_on_trade_event(on_trade)

        # ヘッドレス取引イベントが有効な場合、コールバックを設定
        if getattr(self, '_headless_trade_events_enabled', False):
            self._setup_headless_trade_callback()

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

        # チャート自動更新
        self._update_all_charts()

        if self._step_index >= len(self.index):
            self._is_finished = True

        return not self._is_finished

    def _update_all_charts(self) -> None:
        """保持している全チャートウィジェットを更新"""
        for code, widget in self._chart_widgets.items():
            try:
                self.update_chart(widget, code)
            except Exception:
                pass  # ウィジェット破棄時のエラーを無視

    def reset(self, *, clear_chart_cache: bool = False) -> 'Backtest':
        """
        バックテストをリセットして最初から

        Args:
            clear_chart_cache: チャートウィジェットキャッシュをクリアするか
                              （デフォルト: False でウィジェットは再利用）
        """
        self._broker_instance = self._broker_factory(data=self._data)
        self._step_index = 0
        self._is_finished = False
        self._results = None
        # インデックスをリセット（次回chart()で全データ更新）
        self._chart_last_index = {}
        # 明示的に指定された場合のみウィジェットをクリア
        if clear_chart_cache:
            self._chart_widgets = {}
            self._chart_indicators = {}
        # 初期データ（最初の1行）でチャートをリセット
        self._current_data = {}
        if self._data:
            for code, df in self._data.items():
                if len(df) > 0:
                    self._current_data[code] = df.iloc[:1]
        self._update_all_charts()
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
    # 可視化
    # =========================================================================

    def chart(
        self,
        code: str = None,
        height: int = 500,
        show_tags: bool = True,
        visible_bars: int = 60,
        indicators: list[str] = None,
        indicator_options: dict = None,
    ):
        """
        現在時点までのローソク足チャートを生成（売買マーカー付き）

        差分更新対応:
        - 初回呼び出し: 全データでウィジェット作成
        - 2回目以降: 既存ウィジェットを再利用し差分更新

        Args:
            code: 銘柄コード
            height: チャートの高さ
            show_tags: 売買理由（tag）をチャートに表示するか
            visible_bars: 初期表示するバー数（デフォルト: 60本≒約2か月）
            indicators: 表示する指標列名のリスト（例: ['SMA_20', 'SMA_50']）
            indicator_options: 指標の表示オプション辞書

        Returns:
            LightweightChartWidget
        """
        if code is None:
            if len(self._data) == 1:
                code = list(self._data.keys())[0]
            else:
                raise ValueError("複数銘柄がある場合はcodeを指定してください")

        # indicators をキャッシュに保存（早期リターン前に）
        if indicators:
            self._chart_indicators[code] = (indicators, indicator_options)

        if not self._is_started or self._broker_instance is None:
            from .api.chart import LightweightChartWidget
            # キャッシュに登録して後から更新できるようにする
            if code not in self._chart_widgets:
                self._chart_widgets[code] = LightweightChartWidget()
            return self._chart_widgets[code]

        if code not in self._current_data or len(self._current_data[code]) == 0:
            from .api.chart import LightweightChartWidget
            # キャッシュに登録して後から更新できるようにする
            if code not in self._chart_widgets:
                self._chart_widgets[code] = LightweightChartWidget()
            return self._chart_widgets[code]

        df = self._current_data[code]
        current_idx = len(df)

        # 全取引（アクティブ + 決済済み）を取得
        all_trades = list(self._broker_instance.closed_trades) + list(self._broker_instance.trades)

        # キャッシュ確認
        if code in self._chart_widgets:
            widget = self._chart_widgets[code]
            last_idx = self._chart_last_index.get(code, 0)

            # 巻き戻しまたは大きなジャンプの場合は全データ更新
            needs_full_update = (
                last_idx == 0 or
                current_idx < last_idx or
                current_idx - last_idx > 1
            )

            if needs_full_update:
                # 全データ更新
                from .api.chart import df_to_lwc_data, trades_to_markers, df_to_lwc_indicators, prepare_indicator_options
                widget.data = df_to_lwc_data(df)
                widget.markers = trades_to_markers(all_trades, code, show_tags)

                # 指標データ全更新（キャッシュからも取得を試みる）
                effective_indicators = indicators or (self._chart_indicators.get(code, (None, None))[0])
                effective_options = indicator_options or (self._chart_indicators.get(code, (None, None))[1])
                if effective_indicators:
                    widget.indicator_options = prepare_indicator_options(effective_indicators, effective_options)
                    widget.indicator_series = df_to_lwc_indicators(df, effective_indicators)
            else:
                # 差分更新: last_bar_packed (バイナリ) と data の両方を更新
                # last_bar_packed: JS側でリアルタイム更新用（change:last_bar_packedイベント）
                # data: 同期が失われた場合のフォールバック用
                from .api.chart import df_to_lwc_data, get_last_bar, trades_to_markers, get_last_indicators
                bar = get_last_bar(df)
                # バイナリプロトコルで高速更新 (INP改善)
                if hasattr(widget, "update_bar_fast"):
                    widget.update_bar_fast(bar)
                else:
                    widget.last_bar = bar
                widget.data = df_to_lwc_data(df)  # フォールバック用に全データも更新
                widget.markers = trades_to_markers(all_trades, code, show_tags)

                # 指標データ差分更新（キャッシュからも取得を試みる）
                effective_indicators = indicators or (self._chart_indicators.get(code, (None, None))[0])
                if effective_indicators:
                    last_ind = get_last_indicators(df, effective_indicators)
                    if last_ind:
                        widget.last_indicators = last_ind

            self._chart_last_index[code] = current_idx
            # indicators 設定をキャッシュ（update_chart用）
            if indicators:
                self._chart_indicators[code] = (indicators, indicator_options)
            return widget

        # 初回: 新規ウィジェット作成
        from .api.chart import chart_by_df
        widget = chart_by_df(
            df,
            trades=all_trades,
            height=height,
            show_tags=show_tags,
            show_volume=False,
            title=f"{code} - {self.current_time}",
            code=code,
            visible_bars=visible_bars,
            indicators=indicators,
            indicator_options=indicator_options,
        )

        self._chart_widgets[code] = widget
        self._chart_last_index[code] = current_idx
        self._chart_indicators[code] = (indicators, indicator_options)

        return widget

    def update_chart(self, widget, code: str = None) -> None:
        """
        既存チャートウィジェットを差分更新（軽量）

        chart()と異なり、ウィジェット作成やキャッシュ管理をスキップし、
        データとマーカーの更新のみを行う。高頻度更新に最適。

        Args:
            widget: chart()で作成したLightweightChartWidget
            code: 銘柄コード（省略時は最初のデータを使用）

        Example:
            # セル1: チャート作成（一度だけ）
            chart_widget = bt.chart(code=code)

            # セル2: 差分更新（AutoRefreshで繰り返し）
            bt.update_chart(chart_widget, code)
        """
        if code is None:
            code = next(iter(self._data.keys()), None)
        if code is None:
            return

        if code not in self._current_data or len(self._current_data[code]) == 0:
            return

        df = self._current_data[code]

        # 全データ更新（新しいバーを追加するため）
        from .api.chart import df_to_lwc_data, get_last_bar
        widget.data = df_to_lwc_data(df)

        # last_bar も更新（リアルタイム描画用）
        bar = get_last_bar(df)
        if hasattr(widget, "update_bar_fast"):
            widget.update_bar_fast(bar)
        else:
            widget.last_bar = bar

        # マーカー更新
        if self._broker_instance:
            from .api.chart import trades_to_markers
            all_trades = list(self._broker_instance.closed_trades) + list(self._broker_instance.trades)
            widget.markers = trades_to_markers(all_trades, code, show_tags=True)

        # インジケーター更新（キャッシュから設定を取得）
        if code in self._chart_indicators:
            indicators, indicator_options = self._chart_indicators[code]
            if indicators:
                from .api.chart import df_to_lwc_indicators, prepare_indicator_options
                widget.indicator_series = df_to_lwc_indicators(df, indicators)
                # オプションが未設定の場合のみ設定
                if not widget.indicator_options:
                    widget.indicator_options = prepare_indicator_options(indicators, indicator_options)

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

    # =========================================================================
    # ヘッドレスパブリッシャーAPI（app.setup内でも動作可能）
    # =========================================================================

    def publish_state_headless(
        self,
        status_label: str = "Backtest",
        status_variant: str = "secondary",
    ):
        """
        バックテスト状態をBroadcastChannelで公開（ヘッドレス版）

        AnyWidgetのレンダリングが不要。app.setup内や_game_loop内から
        直接呼び出してBroadcastChannelにメッセージを送信できる。
        data属性を持つdiv要素を出力し、フロントエンドのMutationObserverで
        検出してBroadcastChannelに送信する。

        Args:
            status_label: HUDに表示するステータスラベル（例: "実行中", "停止中"）
            status_variant: Badgeの色 ("default", "secondary", "destructive", "success", "outline")

        Example:
            # _game_loop内で使用可能
            def _game_loop():
                while bt.is_finished == False:
                    bt.step()
                    bt.publish_state_headless(status_label="実行中", status_variant="success")
        """
        import json
        import base64
        import time
        import marimo as mo
        from marimo._output.hypertext import Html

        # 状態データを準備
        positions: dict[str, int] = {}
        if self._broker_instance and self._broker_instance.trades:
            for trade in self._broker_instance.trades:
                code = trade.code
                positions[code] = positions.get(code, 0) + trade.size

        state = {
            "current_time": str(self.current_time) if self.current_time else "-",
            "progress": float(self.progress),
            "equity": float(self.equity),
            "cash": float(self.cash),
            "position": self.position,
            "positions": positions,
            "closed_trades": len(self.closed_trades),
            "step_index": self._step_index,
            "total_steps": len(self.index) if hasattr(self, "index") else 0,
            "status_label": status_label,
            "status_variant": status_variant,
        }

        state_json = json.dumps(state)
        state_b64 = base64.b64encode(state_json.encode()).decode()

        unique_id = f"marimo-bc-{self._step_index}-{int(time.time() * 1000)}"

        html = (
            f'<marimo-broadcast '
            f'id="{unique_id}" '
            f'channel="backtest_channel" '
            f'type="backtest_update" '
            f'payload="{state_b64}" '
            f'style="display:none;"></marimo-broadcast>'
        )

        mo.output.replace(Html(html))

    def publish_trade_event_headless(
        self,
        event_type: str,
        code: str,
        size: int,
        price: float,
        tag: Optional[str] = None
    ):
        """
        取引イベントをBroadcastChannelで公開（ヘッドレス版）

        Args:
            event_type: 'BUY' または 'SELL'
            code: 銘柄コード
            size: 取引数量（正の値）
            price: 約定価格
            tag: 取引タグ（オプション）
        """
        import json
        import base64
        import marimo as mo
        from marimo._output.hypertext import Html

        event = {
            "event_type": event_type,
            "code": code,
            "size": abs(size),
            "price": float(price),
            "tag": str(tag) if tag else None,
        }

        event_json = json.dumps(event)
        event_b64 = base64.b64encode(event_json.encode()).decode()

        # data属性を持つdiv要素を出力（MutationObserverで検出される）
        html = (
            f'<div data-marimo-broadcast="trade_event_channel" '
            f'data-marimo-type="trade_event" '
            f'data-marimo-payload="{event_b64}" '
            f'style="display:none;"></div>'
        )
        mo.output.append(Html(html))

    def enable_headless_trade_events(self):
        """
        取引イベントをヘッドレスモードで自動発行するよう設定

        bt.buy() / bt.sell() が成立した際に自動的に
        publish_trade_event_headless() が呼び出される。
        ウィジェットのレンダリングが不要。app.setup内や_game_loop内から使用可能。

        Example:
            # _game_loop内で使用可能
            def _game_loop():
                bt.enable_headless_trade_events()  # 最初に1回呼び出し
                while bt.is_finished == False:
                    bt.step()
                    bt.publish_state_headless()
        """
        self._headless_trade_events_enabled = True

        # ブローカーが既に存在する場合はコールバックを設定
        if self._broker_instance:
            self._setup_headless_trade_callback()

    def _setup_headless_trade_callback(self):
        """ヘッドレス取引イベント用のコールバックを設定"""
        if not getattr(self, '_headless_trade_events_enabled', False):
            return

        def on_trade(event_type: str, trade):
            self.publish_trade_event_headless(
                event_type=event_type,
                code=trade.code,
                size=trade.size,
                price=trade.entry_price,
                tag=getattr(trade, 'tag', None)
            )
        self._broker_instance.set_on_trade_event(on_trade)
