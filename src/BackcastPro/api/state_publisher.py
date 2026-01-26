# -*- coding: utf-8 -*-
"""
バックテスト状態をBroadcastChannelで公開するウィジェット

marimoセル内のバックテスト情報を、別のiframe（three.js等）で
リアルタイム表示するためのブリッジウィジェット。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..backtest import Backtest


class BacktestStatePublisher(anywidget.AnyWidget):
    """バックテスト状態をBroadcastChannelで公開するウィジェット

    AnyWidgetとしてmarimoセルに配置すると、Pythonから更新された
    状態がBroadcastChannel経由で同一オリジン内の全リスナーに配信される。

    Example:
        # Python側
        publisher = BacktestStatePublisher()
        publisher.update_state(bt, code="7203")

        # JavaScript側（iframe内など）
        const channel = new BroadcastChannel('backtest_channel');
        channel.onmessage = (e) => console.log(e.data);
    """

    _esm = """
    function render({ model, el }) {
        const CHANNEL_NAME = 'backtest_channel';
        const channel = new BroadcastChannel(CHANNEL_NAME);

        function publishState() {
            const state = model.get('state') || {};
            channel.postMessage({
                type: 'backtest_update',
                data: {
                    ...state,
                    _timestamp: Date.now()
                }
            });
        }

        model.on('change:state', publishState);
        publishState(); // 初回公開

        // ステータスインジケーター
        el.innerHTML = `
            <div style="
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: 11px;
                color: #00ff88;
                background: rgba(0, 40, 20, 0.8);
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid #00ff8844;
            ">
                <span style="
                    width: 6px;
                    height: 6px;
                    background: #00ff88;
                    border-radius: 50%;
                    animation: pulse 1s infinite;
                "></span>
                <span>Broadcasting</span>
            </div>
            <style>
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.4; }
                }
            </style>
        `;

        // クリーンアップ
        return () => {
            model.off('change:state', publishState);
            channel.close();
        };
    }
    export default { render };
    """

    _css = """
    :host {
        display: inline-block;
    }
    """

    state = traitlets.Dict({}).tag(sync=True)

    def update_state(self, bt: "Backtest", code: str | None = None) -> None:
        """Backtestオブジェクトから状態を更新

        Args:
            bt: Backtestインスタンス
            code: 銘柄コード（ポジション取得用）
        """
        # パブリックAPIを使用してステップインデックスを取得
        step_index = getattr(bt, "step_index", getattr(bt, "_step_index", 0))
        total_steps = len(bt.index) if hasattr(bt, "index") else 0

        self.state = {
            "current_time": str(bt.current_time) if bt.current_time else "-",
            "progress": float(bt.progress),
            "equity": float(bt.equity),
            "cash": float(bt.cash),
            "position": bt.position_of(code) if code else 0,
            "closed_trades": len(bt.closed_trades),
            "step_index": step_index,
            "total_steps": total_steps,
        }
