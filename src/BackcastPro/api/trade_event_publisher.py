# -*- coding: utf-8 -*-
"""
取引イベントをBroadcastChannelで公開するウィジェット

bt.buy() / bt.sell() が成立した際にイベントを配信し、
Three.jsのエフェクト（マネーミサイル）をトリガーする。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

import anywidget
import traitlets

if TYPE_CHECKING:
    from ..trade import Trade


class TradeEventPublisher(anywidget.AnyWidget):
    """取引イベントをBroadcastChannelで公開するウィジェット

    AnyWidgetとしてmarimoセルに配置すると、Pythonから更新された
    イベントがBroadcastChannel経由で同一オリジン内の全リスナーに配信される。

    Example:
        # Python側
        publisher = TradeEventPublisher()
        publisher.emit_trade_event('BUY', 'AAPL', 100, 150.0, 'dip_buy')

        # JavaScript側（Three.jsシーン内など）
        const channel = new BroadcastChannel('trade_event_channel');
        channel.onmessage = (e) => {
            if (e.data.type === 'trade_event') {
                const { event_type, code, size, price, tag } = e.data.data;
                // BUY: ドローンにお金が飛んでくる
                // SELL: ドローンからお金が発射される
            }
        };
    """

    _esm = """
    function render({ model, el }) {
        const CHANNEL_NAME = 'trade_event_channel';
        const channel = new BroadcastChannel(CHANNEL_NAME);

        function publishEvent() {
            const event = model.get('trade_event') || {};
            if (!event.event_type) return;

            channel.postMessage({
                type: 'trade_event',
                data: {
                    ...event,
                    _timestamp: Date.now()
                }
            });
        }

        model.on('change:trade_event', publishEvent);

        // 初回は配信しない（イベント駆動のため）

        // ステータスインジケーター
        el.innerHTML = `
            <div style="
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: 11px;
                color: #ffaa00;
                background: rgba(40, 30, 0, 0.8);
                padding: 4px 8px;
                border-radius: 4px;
                border: 1px solid #ffaa0044;
            ">
                <span style="
                    width: 6px;
                    height: 6px;
                    background: #ffaa00;
                    border-radius: 50%;
                "></span>
                <span>Trade Events</span>
                <span id="event-counter" style="
                    background: rgba(255,170,0,0.3);
                    padding: 1px 5px;
                    border-radius: 3px;
                    font-weight: bold;
                ">0</span>
            </div>
        `;

        let eventCount = 0;
        model.on('change:trade_event', () => {
            eventCount++;
            const counter = el.querySelector('#event-counter');
            if (counter) {
                counter.textContent = eventCount;
                // 一瞬光らせる
                counter.style.background = 'rgba(255,170,0,0.8)';
                setTimeout(() => {
                    counter.style.background = 'rgba(255,170,0,0.3)';
                }, 200);
            }
        });

        // クリーンアップ
        return () => {
            model.off('change:trade_event', publishEvent);
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

    trade_event = traitlets.Dict({}).tag(sync=True)
    _event_counter = traitlets.Int(0).tag(sync=True)

    def emit_trade_event(
        self,
        event_type: str,
        code: str,
        size: int,
        price: float,
        tag: Optional[str] = None,
    ) -> None:
        """取引イベントを配信

        Args:
            event_type: 'BUY' または 'SELL'
            code: 銘柄コード
            size: 取引数量（正の値）
            price: 約定価格
            tag: 取引タグ（オプション）
        """
        self._event_counter += 1
        self.trade_event = {
            "event_type": event_type,
            "code": code,
            "size": abs(size),
            "price": price,
            "tag": str(tag) if tag else None,
            "_event_id": self._event_counter,
        }

    def emit_from_trade(self, trade: "Trade", is_opening: bool = True) -> None:
        """Tradeオブジェクトからイベントを配信

        Args:
            trade: Tradeインスタンス
            is_opening: True=新規取引、False=決済
        """
        event_type = "BUY" if trade.size > 0 else "SELL"
        price = trade.entry_price if is_opening else (trade.exit_price or trade.entry_price)

        self.emit_trade_event(
            event_type=event_type,
            code=trade.code,
            size=trade.size,
            price=price,
            tag=trade.tag,
        )
