# -*- coding: utf-8 -*-
"""
Lightweight Charts ベースの株価チャートモジュール

anywidget を使用してリアルタイム更新可能な金融チャートを提供する。
Plotly から移行し、Canvas 差分更新によりパフォーマンスを大幅に改善。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import anywidget
import traitlets

import datetime

import pandas as pd


if TYPE_CHECKING:
    import pandas as pd


class CandleBar(TypedDict):
    """ローソク足バーの型定義"""

    time: int  # UNIXタイムスタンプ（UTC）
    open: float
    high: float
    low: float
    close: float


class VolumeBar(TypedDict):
    """出来高バーの型定義"""

    time: int
    value: float
    color: str


class MarkerData(TypedDict):
    """マーカーの型定義"""

    time: int
    position: str  # "aboveBar" or "belowBar"
    color: str
    shape: str  # "arrowUp", "arrowDown", "circle", "square"
    text: str


def to_lwc_timestamp(idx, tz: str = "Asia/Tokyo") -> int:
    """
    インデックスをLightweight Charts用UTCタイムスタンプに変換

    Args:
        idx: DatetimeIndex, Timestamp, or date string
        tz: 元データのタイムゾーン（日本株はAsia/Tokyo）

    Returns:
        UTCベースのUNIXタイムスタンプ
    """
    import pandas as pd

    ts = pd.Timestamp(idx)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz)
    return int(ts.tz_convert("UTC").timestamp())


def df_to_lwc_data(df: pd.DataFrame, tz: str = "Asia/Tokyo") -> list[dict]:
    """
    DataFrameをLightweight Charts形式に変換

    Args:
        df: OHLC データを含むDataFrame（Open, High, Low, Close列が必要）
        tz: 元データのタイムゾーン

    Returns:
        Lightweight Charts形式のローソク足データリスト
    """
    if len(df) == 0:
        return []

    records = []
    for idx, row in df.iterrows():
        records.append(
            {
                "time": to_lwc_timestamp(idx, tz),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        )
    return records


def get_last_bar(df: pd.DataFrame, tz: str = "Asia/Tokyo") -> dict:
    """
    DataFrameの最後のバーを取得

    Args:
        df: OHLC データを含むDataFrame
        tz: 元データのタイムゾーン

    Returns:
        最後のバーデータ（空DataFrameの場合は空辞書）
    """
    if len(df) == 0:
        return {}

    last_row = df.iloc[-1]
    idx = df.index[-1]

    return {
        "time": to_lwc_timestamp(idx, tz),
        "open": float(last_row["Open"]),
        "high": float(last_row["High"]),
        "low": float(last_row["Low"]),
        "close": float(last_row["Close"]),
    }


def df_to_lwc_volume(df: pd.DataFrame, tz: str = "Asia/Tokyo") -> list[dict]:
    """
    DataFrameの出来高をLightweight Charts形式に変換

    Args:
        df: Volume列を含むDataFrame
        tz: 元データのタイムゾーン

    Returns:
        Lightweight Charts形式の出来高データリスト
    """
    if "Volume" not in df.columns:
        return []

    records = []
    for idx, row in df.iterrows():
        # 陽線/陰線で色を変える
        is_up = row["Close"] >= row["Open"]
        records.append({
            "time": to_lwc_timestamp(idx, tz),
            "value": float(row["Volume"]),
            "color": "rgba(38, 166, 154, 0.5)" if is_up else "rgba(239, 83, 80, 0.5)",
        })
    return records


class LightweightChartWidget(anywidget.AnyWidget):
    """
    Lightweight Charts ローソク足チャートウィジェット

    marimo の mo.ui.anywidget() でラップして使用する。
    差分更新に対応し、高速なリアルタイム更新が可能。

    Attributes:
        data: 全ローソク足データ（初回設定用）
        volume_data: 出来高データ
        markers: 売買マーカー
        last_bar: 最新バー（差分更新用）
        options: チャートオプション（height, showVolumeなど）

    Example:
        widget = LightweightChartWidget()
        widget.options = {"height": 500, "showVolume": True}
        widget.data = df_to_lwc_data(df)

        # 差分更新
        widget.last_bar = get_last_bar(df)
    """

    _esm = """
    // CDNフォールバック付きのインポート
    let createChart;

    async function loadLibrary() {
        const CDN_URLS = [
            'https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.mjs',
            'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.mjs',
        ];

        for (const url of CDN_URLS) {
            try {
                const mod = await import(url);
                return mod.createChart;
            } catch (e) {
                console.warn(`Failed to load from ${url}:`, e);
            }
        }
        throw new Error('All CDN sources failed');
    }

    // バーデータの検証
    function isValidBar(bar) {
        return bar &&
            typeof bar.time === 'number' &&
            typeof bar.open === 'number' &&
            typeof bar.high === 'number' &&
            typeof bar.low === 'number' &&
            typeof bar.close === 'number';
    }

    async function render({ model, el }) {
        // ライブラリ読み込み
        try {
            createChart = await loadLibrary();
        } catch (e) {
            el.innerHTML = '<p style="color:#ef5350;padding:20px;">Chart library failed to load. Check network connection.</p>';
            console.error(e);
            return;
        }

        // チャート作成
        const options = model.get("options") || {};
        const chart = createChart(el, {
            width: el.clientWidth || 800,
            height: options.height || 400,
            layout: {
                background: { color: options.backgroundColor || '#1e1e1e' },
                textColor: options.textColor || '#d1d4dc',
            },
            grid: {
                vertLines: { color: '#2B2B43' },
                horzLines: { color: '#2B2B43' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
            crosshair: {
                mode: 1,
            },
        });

        // ローソク足シリーズ
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });

        // 出来高シリーズ（オプション）
        let volumeSeries = null;
        const showVolume = options.showVolume !== false;
        if (showVolume) {
            volumeSeries = chart.addHistogramSeries({
                color: '#26a69a',
                priceFormat: { type: 'volume' },
                priceScaleId: 'volume',
            });
            chart.priceScale('volume').applyOptions({
                scaleMargins: { top: 0.8, bottom: 0 },
            });
        }

        // 初期データ設定
        const data = model.get("data") || [];
        if (data.length > 0) {
            candleSeries.setData(data);
            chart.timeScale().fitContent();
        }

        // 出来高データ設定
        const volumeData = model.get("volume_data") || [];
        if (volumeSeries && volumeData.length > 0) {
            volumeSeries.setData(volumeData);
        }

        // マーカー設定
        const markers = model.get("markers") || [];
        if (markers.length > 0) {
            candleSeries.setMarkers(markers);
        }

        // データ全体が変更された時
        model.on("change:data", () => {
            const newData = model.get("data") || [];
            if (newData.length > 0) {
                candleSeries.setData(newData);
                chart.timeScale().fitContent();
            }
        });

        // 出来高データ変更時
        model.on("change:volume_data", () => {
            if (!volumeSeries) return;
            const newVolumeData = model.get("volume_data") || [];
            if (newVolumeData.length > 0) {
                volumeSeries.setData(newVolumeData);
            }
        });

        // マーカー変更時
        model.on("change:markers", () => {
            const newMarkers = model.get("markers") || [];
            candleSeries.setMarkers(newMarkers);
        });

        // 最後のバーのみ更新（差分更新）
        model.on("change:last_bar", () => {
            const bar = model.get("last_bar");
            if (isValidBar(bar)) {
                candleSeries.update(bar);
            } else if (bar && Object.keys(bar).length > 0) {
                console.warn('Invalid bar format:', bar);
            }
            // 空オブジェクトの場合は無視（クリア時）
        });

        // リサイズ対応
        const resizeObserver = new ResizeObserver(entries => {
            const { width } = entries[0].contentRect;
            if (width > 0) {
                chart.applyOptions({ width });
            }
        });
        resizeObserver.observe(el);

        // クリーンアップ
        return () => {
            resizeObserver.disconnect();
            chart.remove();
        };
    }

    export default { render };
    """

    _css = """
    :host {
        display: block;
        width: 100%;
    }
    """

    # 同期するトレイト
    data = traitlets.List([]).tag(sync=True)
    volume_data = traitlets.List([]).tag(sync=True)
    markers = traitlets.List([]).tag(sync=True)
    last_bar = traitlets.Dict({}).tag(sync=True)
    options = traitlets.Dict({}).tag(sync=True)


def _prepare_chart_df(df: pd.DataFrame) -> pd.DataFrame:
    """チャート表示用データを準備"""
    df = df.copy()

    # DatetimeIndexの場合はそのまま使用
    if isinstance(df.index, pd.DatetimeIndex):
        df.index.name = "Date"
    elif "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df.index.name = "Date"
    else:
        try:
            df.index = pd.to_datetime(df.index)
            df.index.name = "Date"
        except (ValueError, TypeError):
            pass

    # カラム名を大文字に統一
    column_mapping = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    for lower, upper in column_mapping.items():
        if lower in df.columns and upper not in df.columns:
            df.rename(columns={lower: upper}, inplace=True)

    # 必要なカラムを抽出して数値変換
    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    available_cols = [col for col in required_cols if col in df.columns]
    df = df[available_cols].copy()

    # 数値カラムを数値型に変換
    for col in available_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna()


def trades_to_markers(
    trades: list,
    code: str = None,
    show_tags: bool = True,
    tz: str = "Asia/Tokyo",
) -> list[dict]:
    """
    TradeオブジェクトをLightweight Chartsマーカー形式に変換

    Args:
        trades: Trade オブジェクトのリスト
        code: 銘柄コード（フィルタリング用）
        show_tags: 売買理由（tag）を表示するか
        tz: 元データのタイムゾーン

    Returns:
        Lightweight Charts形式のマーカーリスト
    """
    markers = []

    for trade in trades:
        # codeが指定されている場合はフィルタリング
        if code is not None and hasattr(trade, "code") and trade.code != code:
            continue

        is_long = trade.size > 0
        tag = getattr(trade, "tag", None)

        # エントリーマーカー
        entry_text = "BUY" if is_long else "SELL"
        if show_tags and tag:
            entry_text = f"{entry_text}: {tag}"

        markers.append({
            "time": to_lwc_timestamp(trade.entry_time, tz),
            "position": "belowBar" if is_long else "aboveBar",
            "color": "#26a69a" if is_long else "#ef5350",
            "shape": "arrowUp" if is_long else "arrowDown",
            "text": entry_text,
        })

        # イグジットマーカー（決済済みの場合）
        exit_time = getattr(trade, "exit_time", None)
        exit_price = getattr(trade, "exit_price", None)
        if exit_time is not None and exit_price is not None:
            pnl = (exit_price - trade.entry_price) * trade.size
            markers.append({
                "time": to_lwc_timestamp(exit_time, tz),
                "position": "aboveBar" if is_long else "belowBar",
                "color": "#2196F3",
                "shape": "circle",
                "text": f"EXIT ({pnl:+.0f})",
            })

    # 時間順にソート（Lightweight Chartsの要件）
    markers.sort(key=lambda x: x["time"])
    return markers


def chart_by_df(
    df: pd.DataFrame,
    *,
    trades: list = None,
    height: int = 500,
    show_tags: bool = True,
    show_volume: bool = True,
    title: str = None,
    code: str = None,
    tz: str = "Asia/Tokyo",
) -> LightweightChartWidget:
    """
    株価データからLightweight Chartsチャートを作成

    Args:
        df: 株価データ（pandas DataFrame）
        trades: 取引リスト（Trade オブジェクトのリスト）
        height: チャートの高さ（ピクセル）
        show_tags: 売買理由（tag）をチャートに表示するか
        show_volume: 出来高を表示するか
        title: チャートのタイトル（現在は未使用）
        code: 銘柄コード（trades のフィルタリング用）
        tz: タイムゾーン（デフォルト: Asia/Tokyo）

    Returns:
        LightweightChartWidget: anywidget ベースのチャートウィジェット
    """
    # データを整形
    df = _prepare_chart_df(df)

    # ウィジェット作成
    widget = LightweightChartWidget()
    widget.options = {
        "height": height,
        "showVolume": show_volume,
    }

    # ローソク足データ設定
    widget.data = df_to_lwc_data(df, tz)

    # 出来高データ設定
    if show_volume:
        widget.volume_data = df_to_lwc_volume(df, tz)

    # 売買マーカー設定
    if trades:
        widget.markers = trades_to_markers(trades, code, show_tags, tz)

    return widget


def chart(
    code: str = "",
    from_: datetime.datetime = None,
    to: datetime.datetime = None,
    df: pd.DataFrame = None,
):
    """
    株価データを指定して株価チャートを表示する

    Args:
        code: 銘柄コード（例: "6723"）
        from_: 開始日（datetime, オプション）
        to: 終了日（datetime, オプション）
        df: 株価データ（pandas DataFrame）
    """
    if df is None:
        from .stocks_daily import stocks_price

        __sp__ = stocks_price()
        df = __sp__.get_japanese_stock_price_data(code, from_=from_, to=to)

    if df.empty:
        raise ValueError(f"銘柄コード '{code}' の株価が取得できませんでした。")

    return chart_by_df(df)
