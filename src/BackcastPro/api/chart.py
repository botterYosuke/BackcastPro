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


def df_to_lwc_indicators(
    df: pd.DataFrame,
    indicator_columns: list[str],
    tz: str = "Asia/Tokyo",
) -> dict[str, list[dict]]:
    """
    DataFrameの指標列をLightweight Charts形式に変換

    Args:
        df: 指標列を含むDataFrame
        indicator_columns: 指標列名のリスト（例: ['SMA_20', 'SMA_50']）
        tz: 元データのタイムゾーン

    Returns:
        指標名をキーとし、Lightweight Charts形式のデータリストを値とする辞書
        NaN値は自動的にスキップされる
    """
    import warnings

    result = {}

    for col_name in indicator_columns:
        if col_name not in df.columns:
            warnings.warn(
                f"指標列 '{col_name}' が見つかりません。スキップします。",
                UserWarning,
                stacklevel=2
            )
            continue

        series_data = []
        for idx, row in df.iterrows():
            value = row[col_name]
            # NaN値はスキップ（SMAの初期値など）
            if pd.isna(value):
                continue

            series_data.append({
                "time": to_lwc_timestamp(idx, tz),
                "value": float(value),
            })

        if series_data:  # 空でない場合のみ追加
            result[col_name] = series_data
        else:
            warnings.warn(
                f"指標列 '{col_name}' にデータがありません（すべてNaN）。スキップします。",
                UserWarning,
                stacklevel=2
            )

    return result


def get_last_indicators(
    df: pd.DataFrame,
    indicator_columns: list[str],
    tz: str = "Asia/Tokyo",
) -> dict[str, dict]:
    """
    DataFrameの最後の指標値を取得

    Args:
        df: 指標列を含むDataFrame
        indicator_columns: 指標列名のリスト
        tz: 元データのタイムゾーン

    Returns:
        指標名をキーとし、最後の値を値とする辞書
        NaN値の場合は空辞書を返す
    """
    if len(df) == 0:
        return {}

    last_row = df.iloc[-1]
    idx = df.index[-1]
    time_value = to_lwc_timestamp(idx, tz)

    result = {}
    for col_name in indicator_columns:
        if col_name not in df.columns:
            continue

        value = last_row[col_name]
        if not pd.isna(value):
            result[col_name] = {
                "time": time_value,
                "value": float(value),
            }

    return result


def prepare_indicator_options(
    indicator_columns: list[str],
    user_options: dict = None,
) -> dict[str, dict]:
    """
    指標の表示オプションを準備

    Args:
        indicator_columns: 指標列名のリスト
        user_options: ユーザー指定のオプション辞書

    Returns:
        指標名をキーとし、オプション辞書を値とする辞書
    """
    DEFAULT_INDICATOR_COLORS = [
        "#2196F3",  # Blue
        "#FFC107",  # Amber
        "#9C27B0",  # Purple
        "#4CAF50",  # Green
        "#FF5722",  # Deep Orange
        "#00BCD4",  # Cyan
        "#E91E63",  # Pink
        "#8BC34A",  # Light Green
    ]

    result = {}
    user_options = user_options or {}

    for i, col_name in enumerate(indicator_columns):
        # デフォルトオプション
        default_opts = {
            "color": DEFAULT_INDICATOR_COLORS[i % len(DEFAULT_INDICATOR_COLORS)],
            "lineWidth": 2,
            "title": col_name,
        }

        # ユーザー指定のオプションでマージ
        if col_name in user_options:
            default_opts.update(user_options[col_name])

        result[col_name] = default_opts

    return result


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

    // msgpack ライブラリ読み込み（Phase 3: バイナリプロトコル）
    let msgpackDecode = null;
    let msgpackLoadPromise = null;
    async function loadMsgpack() {
        // ESM 互換の CDN URL のみ使用
        const CDN_URLS = [
            'https://cdn.jsdelivr.net/npm/msgpack-lite@0.1.26/+esm',
            'https://cdn.jsdelivr.net/npm/@msgpack/msgpack@3.0.0-beta2/+esm',
        ];
        for (const url of CDN_URLS) {
            try {
                const mod = await import(url);
                // msgpack-lite と @msgpack/msgpack の両方に対応
                return mod.default?.decode || mod.decode;
            } catch (e) {
                console.warn(`Failed to load msgpack from ${url}:`, e);
            }
        }
        console.warn('msgpack failed to load, falling back to JSON');
        return null;
    }

    // 遅延ロード用ヘルパー
    async function ensureMsgpack() {
        if (msgpackDecode) return msgpackDecode;
        if (!msgpackLoadPromise) {
            msgpackLoadPromise = loadMsgpack();
        }
        msgpackDecode = await msgpackLoadPromise;
        return msgpackDecode;
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

    // チャートインスタンスを保持するためのキー
    // 重要: el ではなく model に保存する
    // marimo の AnyWidgetPlugin は値が変わるたびに render() を呼び出し、
    // 毎回異なる el 要素が渡される可能性がある。
    // model オブジェクトは同一インスタンスが維持されるため、こちらに保存する。
    const MODEL_CHART_KEY = '__lwcChart';
    const MODEL_SERIES_KEY = '__lwcSeries';
    const MODEL_VOLUME_KEY = '__lwcVolume';
    const MODEL_OBSERVER_KEY = '__lwcObserver';
    const MODEL_EL_KEY = '__lwcElement';
    const MODEL_INDICATOR_SERIES_KEY = '__lwcIndicatorSeries';

    async function render({ model, el }) {
        // 既存のチャートがあるか確認（べき等性のため）
        // marimo は値が変わるたびに render() を呼び出すが、
        // change:* イベントリスナーが既にデータを更新しているため、
        // ここでは新規作成をスキップする
        if (model[MODEL_CHART_KEY]) {
            // 新しい el が渡された場合、チャートを新しい el に移動
            const oldEl = model[MODEL_EL_KEY];
            if (oldEl !== el && oldEl && model[MODEL_CHART_KEY]) {
                // 既存のチャートコンテナを新しい el に移動
                while (oldEl.firstChild) {
                    el.appendChild(oldEl.firstChild);
                }
                model[MODEL_EL_KEY] = el;
                // ResizeObserver を新しい el に付け替え
                if (model[MODEL_OBSERVER_KEY]) {
                    model[MODEL_OBSERVER_KEY].disconnect();
                    model[MODEL_OBSERVER_KEY].observe(el);
                }
            }
            return () => {};
        }

        // ライブラリ読み込み
        try {
            createChart = await loadLibrary();
            // msgpack は遅延ロード (ensureMsgpack() で初回使用時にロード)
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

        // チャートインスタンスを model に保存
        model[MODEL_CHART_KEY] = chart;
        model[MODEL_EL_KEY] = el;

        // 高頻度更新キーを設定（React 再レンダーをスキップ）
        // last_bar, last_bar_packed は model.on() で直接処理されるため、React の再レンダーは不要
        if (model.setDirectUpdateKeys) {
            model.setDirectUpdateKeys(['last_bar', 'last_bar_packed']);
        }

        // ローソク足シリーズ
        const candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderVisible: false,
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        });
        model[MODEL_SERIES_KEY] = candleSeries;

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
            model[MODEL_VOLUME_KEY] = volumeSeries;
        }

        // インジケーターライン系列（Map で管理）
        model[MODEL_INDICATOR_SERIES_KEY] = new Map();

        // 初期データ設定
        const data = model.get("data") || [];
        if (data.length > 0) {
            candleSeries.setData(data);

            // 表示範囲を直近N本に制限（デフォルト60本≒約2か月）
            const visibleBars = options.visibleBars || 60;
            if (data.length > visibleBars) {
                chart.timeScale().setVisibleLogicalRange({
                    from: data.length - visibleBars,
                    to: data.length - 1,
                });
            } else {
                chart.timeScale().fitContent();
            }
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

        // インジケーターライン系列の初期化
        const indicatorOptions = model.get("indicator_options") || {};
        const indicatorData = model.get("indicator_series") || {};

        for (const [name, options] of Object.entries(indicatorOptions)) {
            const lineSeries = chart.addLineSeries({
                color: options.color || '#2196F3',
                lineWidth: options.lineWidth || 2,
                title: options.title || name,
                lastValueVisible: true,
                priceLineVisible: false,
            });

            model[MODEL_INDICATOR_SERIES_KEY].set(name, lineSeries);

            // 初期データがあれば設定
            if (indicatorData[name] && indicatorData[name].length > 0) {
                lineSeries.setData(indicatorData[name]);
            }
        }

        // データ全体が変更された時
        model.on("change:data", () => {
            const newData = model.get("data") || [];
            if (newData.length > 0) {
                candleSeries.setData(newData);

                // 表示範囲を直近N本に制限
                const visibleBars = options.visibleBars || 60;
                if (newData.length > visibleBars) {
                    chart.timeScale().setVisibleLogicalRange({
                        from: newData.length - visibleBars,
                        to: newData.length - 1,
                    });
                } else {
                    chart.timeScale().fitContent();
                }
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

        // インジケーターデータ変更時（全データ更新）
        model.on("change:indicator_series", () => {
            const newIndicatorData = model.get("indicator_series") || {};
            const indicatorSeriesMap = model[MODEL_INDICATOR_SERIES_KEY];

            if (!indicatorSeriesMap) return;

            for (const [name, series] of indicatorSeriesMap.entries()) {
                if (newIndicatorData[name] && newIndicatorData[name].length > 0) {
                    series.setData(newIndicatorData[name]);
                }
            }
        });

        // インジケーターオプション変更時（系列再作成）
        model.on("change:indicator_options", () => {
            const newOptions = model.get("indicator_options") || {};
            const indicatorSeriesMap = model[MODEL_INDICATOR_SERIES_KEY];

            if (!indicatorSeriesMap) return;

            // 古い系列を削除
            for (const [name, series] of indicatorSeriesMap.entries()) {
                if (!newOptions[name]) {
                    chart.removeSeries(series);
                    indicatorSeriesMap.delete(name);
                }
            }

            // 新しい系列を追加
            const indicatorData = model.get("indicator_series") || {};
            for (const [name, options] of Object.entries(newOptions)) {
                if (!indicatorSeriesMap.has(name)) {
                    const lineSeries = chart.addLineSeries({
                        color: options.color || '#2196F3',
                        lineWidth: options.lineWidth || 2,
                        title: options.title || name,
                        lastValueVisible: true,
                        priceLineVisible: false,
                    });

                    indicatorSeriesMap.set(name, lineSeries);

                    if (indicatorData[name] && indicatorData[name].length > 0) {
                        lineSeries.setData(indicatorData[name]);
                    }
                }
            }
        });

        // 最後のバーのみ更新（差分更新）
        // RAF ベースのバッチ更新: ブラウザの描画サイクルに同期して更新
        // 100ms間隔の更新でも最大60fpsに制限し、CPU負荷を軽減
        let pendingBar = null;
        let rafId = null;
        let isDisposed = false;

        const flushPendingBar = () => {
            // Guard: チャートが破棄されていたらスキップ
            if (isDisposed || !model[MODEL_CHART_KEY]) {
                pendingBar = null;
                rafId = null;
                return;
            }
            try {
                if (pendingBar && isValidBar(pendingBar)) {
                    candleSeries.update(pendingBar);
                }
            } catch (e) {
                // チャートがRAF待機中に破棄された場合のエラーを抑制
                console.debug('Chart update skipped (disposed):', e);
            } finally {
                pendingBar = null;
                rafId = null;
            }
        };

        model.on("change:last_bar", () => {
            // チャートが破棄されていたら新規更新をスキップ
            if (isDisposed) return;

            const bar = model.get("last_bar");
            if (!isValidBar(bar)) return;

            // 複数の更新が同フレーム内に発生した場合、最新の値のみ使用
            pendingBar = bar;

            // 次の描画フレームでまとめて更新
            if (rafId === null) {
                rafId = requestAnimationFrame(flushPendingBar);
            }
        });

        // バイナリプロトコル用ハンドラ (Phase 3: INP改善)
        // msgpack でペイロードを削減し、パース時間を短縮
        // ハンドラは常に登録し、msgpack は遅延ロード
        model.on("change:last_bar_packed", async () => {
            if (isDisposed) return;

            const packed = model.get("last_bar_packed");
            if (!packed || packed.byteLength === 0) return;

            // 遅延ロード: 初回使用時に msgpack をロード
            const decode = await ensureMsgpack();
            if (!decode) {
                console.warn('msgpack unavailable, ignoring packed data');
                return;
            }

            try {
                const decoded = decode(new Uint8Array(packed));
                if (!Array.isArray(decoded) || decoded.length !== 5) {
                    console.warn('Invalid packed bar format');
                    return;
                }
                const [time, open, high, low, close] = decoded;
                if (!isValidBar({ time, open, high, low, close })) {
                    console.warn('Invalid bar values after decode');
                    return;
                }
                pendingBar = { time, open, high, low, close };

                if (rafId === null) {
                    rafId = requestAnimationFrame(flushPendingBar);
                }
            } catch (e) {
                console.warn('msgpack decode failed:', e);
            }
        });

        // インジケーターの差分更新（RAFバッチング）
        let pendingIndicators = {};
        let indicatorRafId = null;

        const flushPendingIndicators = () => {
            if (isDisposed || !model[MODEL_CHART_KEY]) {
                pendingIndicators = {};
                indicatorRafId = null;
                return;
            }

            try {
                const indicatorSeriesMap = model[MODEL_INDICATOR_SERIES_KEY];
                if (!indicatorSeriesMap) return;

                for (const [name, data] of Object.entries(pendingIndicators)) {
                    const series = indicatorSeriesMap.get(name);
                    if (series && data && typeof data.time === 'number' && typeof data.value === 'number') {
                        series.update(data);
                    }
                }
            } catch (e) {
                console.debug('Indicator update skipped (disposed):', e);
            } finally {
                pendingIndicators = {};
                indicatorRafId = null;
            }
        };

        model.on("change:last_indicators", () => {
            if (isDisposed) return;

            const newIndicators = model.get("last_indicators");
            if (!newIndicators || Object.keys(newIndicators).length === 0) return;

            pendingIndicators = { ...pendingIndicators, ...newIndicators };

            if (indicatorRafId === null) {
                indicatorRafId = requestAnimationFrame(flushPendingIndicators);
            }
        });

        // リスナー設定前に発生した last_bar の変更を適用
        // （チャート作成中にイベントが発火した場合への対処）
        const currentLastBar = model.get("last_bar");
        if (isValidBar(currentLastBar)) {
            candleSeries.update(currentLastBar);
        }

        // リサイズ対応
        const resizeObserver = new ResizeObserver(entries => {
            const { width } = entries[0].contentRect;
            if (width > 0) {
                chart.applyOptions({ width });
            }
        });
        resizeObserver.observe(el);
        model[MODEL_OBSERVER_KEY] = resizeObserver;

        // クリーンアップ関数を作成
        // 注: model に保存しているため、cleanup は最終的な破棄時のみ呼ばれる想定
        // marimo が毎回 cleanup を呼んでも、model にチャートが残っている限り再利用される
        const cleanup = () => {
            // 破棄フラグを設定（RAF コールバックでの更新を防止）
            isDisposed = true;

            // RAF をキャンセル（メモリリーク防止）
            if (rafId !== null) {
                cancelAnimationFrame(rafId);
                rafId = null;
            }
            pendingBar = null;

            // インジケーター RAF をキャンセル
            if (indicatorRafId !== null) {
                cancelAnimationFrame(indicatorRafId);
                indicatorRafId = null;
            }
            pendingIndicators = {};

            // model にチャートが存在しない場合はスキップ
            if (!model[MODEL_CHART_KEY]) {
                return;
            }

            // 現在の el が DOM に接続されている場合は削除しない
            // （ウィジェットがまだ表示されている可能性がある）
            const currentEl = model[MODEL_EL_KEY];
            if (currentEl && currentEl.isConnected) {
                return;
            }
            if (model[MODEL_OBSERVER_KEY]) {
                model[MODEL_OBSERVER_KEY].disconnect();
            }
            if (model[MODEL_CHART_KEY]) {
                model[MODEL_CHART_KEY].remove();
            }
            // チャート参照をクリア
            delete model[MODEL_CHART_KEY];
            delete model[MODEL_SERIES_KEY];
            delete model[MODEL_VOLUME_KEY];
            delete model[MODEL_OBSERVER_KEY];
            delete model[MODEL_EL_KEY];
            delete model[MODEL_INDICATOR_SERIES_KEY];
        };

        return cleanup;
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
    last_bar_packed = traitlets.Bytes(b"").tag(sync=True)  # バイナリプロトコル用
    options = traitlets.Dict({}).tag(sync=True)
    indicator_series = traitlets.Dict({}).tag(sync=True)  # 指標データ
    indicator_options = traitlets.Dict({}).tag(sync=True)  # 指標表示オプション
    last_indicators = traitlets.Dict({}).tag(sync=True)  # 差分更新用

    def update_bar_fast(self, bar: dict) -> None:
        """バイナリプロトコルで高速更新 (INP改善用)

        msgpack でシリアライズしてペイロードを削減し、
        JavaScript 側のパース時間を短縮する。
        msgpack が利用できない場合は JSON ベースの last_bar にフォールバック。

        Args:
            bar: ローソク足バーデータ（time, open, high, low, close）
        """
        required_keys = ("time", "open", "high", "low", "close")

        # 必要なキーが存在するか検証
        if not all(k in bar for k in required_keys):
            self.last_bar = bar
            return

        try:
            import msgpack

            self.last_bar_packed = msgpack.packb(
                [bar[k] for k in required_keys]
            )
        except (ImportError, Exception):
            # msgpack が利用できない場合は JSON にフォールバック
            self.last_bar = bar


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
    visible_bars: int = 60,
    indicators: list[str] = None,
    indicator_options: dict = None,
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
        visible_bars: 初期表示するバー数（デフォルト: 60本≒約2か月）
        indicators: 表示する指標列名のリスト（例: ['SMA_20', 'SMA_50']）
        indicator_options: 指標の表示オプション辞書

    Returns:
        LightweightChartWidget: anywidget ベースのチャートウィジェット
    """
    # データを整形（indicators用に元のdfを保持）
    original_df = df.copy()
    df = _prepare_chart_df(df)

    # ウィジェット作成
    widget = LightweightChartWidget()
    widget.options = {
        "height": height,
        "showVolume": show_volume,
        "visibleBars": visible_bars,
    }

    # ローソク足データ設定
    widget.data = df_to_lwc_data(df, tz)

    # 出来高データ設定
    if show_volume:
        widget.volume_data = df_to_lwc_volume(df, tz)

    # 売買マーカー設定
    if trades:
        widget.markers = trades_to_markers(trades, code, show_tags, tz)

    # 指標データ設定
    if indicators:
        widget.indicator_options = prepare_indicator_options(indicators, indicator_options)
        widget.indicator_series = df_to_lwc_indicators(original_df, indicators, tz)

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
