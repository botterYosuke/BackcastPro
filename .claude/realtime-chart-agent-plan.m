# リアルタイム1分足チャート — マルチエージェント実装計画

## ゴール

`C:\\Users\\sasai\\AppData\\Roaming\\marimo\\notebooks\\blacksheep.py` に、
kabuステーション REST API をポーリングしてリアルタイムで更新する
1分足ローソク足チャートを実装する。

---

## 前提知識（既調査済み）

| ファイル | 役割 |
|---|---|
| `BackcastPro/src/trading_data/lib/kabusap.py` | kabuステーション HTTP クライアント（シングルトン）。`/board/{code}@1` レスポンスに `CurrentPrice` 等が含まれるが `get_board()` では板データのみ返す |
| `marimo/notebooks/chart.py` | `LightweightChartWidget` — `last_bar`/`append_bars` をスレッドから直接更新可能 |
| `marimo/notebooks/blacksheep.py` | 現在はバックテスト用。今回上書き対象 |

---

## アーキテクチャ（確定）

kabu Station REST API の GET /board/{code}@1 を5秒ポーリング
→ get_current_price(code) ラッパー（blacksheep.py 内定義）
→ MinuteBarBuilder（分足境界検出・OHLCV 集計）
→ LightweightChartWidget（chart.py 既存・無変更）
→ mo.ui.anywidget() で marimo に表示

駆動: threading.Thread（5秒ごとポーリング）
制御 UI: 銘柄コード入力・ポーリング ON/OFF スイッチ

---

## エージェント全体構成

Orchestrator Agent（統括）
│
├── Phase 1（並列）
│   ├── Explorer A: kabusap レスポンス構造調査
│   └── Explorer B: LightweightChartWidget API 調査
│
├── Phase 2（順次）
│   └── Implementer: blacksheep.py 実装
│
├── Phase 3（並列）
│   ├── Tester A: 静的テスト（構文・import・単体）
│   ├── Tester B: kabuステーション疎通テスト
│   └── Tester C: marimo ヘッドレス起動テスト
│
└── Phase 4（FAIL 時のみ）
    └── Fixer: エラー修正 → 再テスト（最大3回）

---

## Orchestrator Agent（統括）

subagent_type: general-purpose

責務:
1. Phase 1 の Explorer を並列起動（同一メッセージに2つの Task 呼び出し）
2. 調査結果を統合して実装仕様を確定
3. Phase 2 の Implementer を起動
4. Phase 3 の Tester を並列起動（同一メッセージに3つの Task 呼び出し）
5. テスト結果を評価:
   - 全 PASS → 完了レポート出力
   - FAIL あり → Fixer を起動して再テスト（最大3回）
6. 最終結果を日本語でサマリー
7. 各エージェントの agent_id を保持し resume で追加調査可能に

判断基準:
- Tester A（静的テスト）が FAIL → 修正必須
- Tester B（API疎通）が SKIP  → 正常（kabuステーション未起動は許容）
- Tester C（marimo起動）が FAIL → 修正必須
- 3回修正後も FAIL → 人間にエスカレーション

---

## Phase 1: 調査（並列起動）

### Explorer A — kabusap レスポンス構造調査

subagent_type: Explore / thoroughness: medium

調査対象: C:\\Users\\sasai\\Documents\\BackcastPro\\src\\trading_data\\lib\\kabusap.py

調査内容:
1. /board/{code}@1 レスポンス JSON フィールド一覧
   （CurrentPrice, CurrentPriceTime, TradingVolume,
     OpeningPrice, HighPrice, LowPrice の有無とキー名）
2. 認証フロー（_set_token の仕組み）
3. 既存 get_board() が捨てているフィールド
4. api_key, API_URL, headers の参照方法

アウトプット: 「使えるフィールド一覧」と「ラッパー実装の注意点」

---

### Explorer B — LightweightChartWidget API 調査

subagent_type: Explore / thoroughness: medium

調査対象: C:\\Users\\sasai\\AppData\\Roaming\\marimo\\notebooks\\chart.py

調査内容:
1. LightweightChartWidget の全トレイト（型・用途）
2. update_bar_fast(), update_and_wait() の使い方
3. append_bars の使い方（新バー追加 vs last_bar の使い分け）
4. to_lwc_timestamp(idx, tz) の引数と戻り値
5. df_to_lwc_data() の期待する DataFrame 形式
6. スレッドからの安全な更新可否

アウトプット: 「blacksheep.py 実装者向けチートシート」

---

## Phase 2: 実装（順次）

subagent_type: general-purpose

変更禁止: kabusap.py / chart.py

blacksheep.py 構成仕様:

  スクリプトメタデータ:
    requires-python >= 3.13
    dependencies: marimo>=0.19.10, python-dotenv>=1.0.0

  with app.setup:
    sys.path に BackcastPro/src/trading_data/lib を追加
    from kabusap import kabusap
    from chart import LightweightChartWidget, to_lwc_timestamp

  ヘルパー関数・クラス（セル外）:

    def get_current_price(api, code) -> dict | None
      /board/{code}@1 から {price, volume, time} を返す
      エラー時は None（raise しない）
      CurrentPriceTime は datetime.fromisoformat() でパース

    class MinuteBarBuilder（threading.Lock でスレッドセーフ）
      push(price, volume, ts) -> dict | None
        分境界で確定バー(LWC形式)を返す、それ以外は None
      current_bar プロパティ: 進行中バー（LWC 形式）
      history プロパティ: 確定済みバー一覧

  セル構成:

    [cell: ui_controls]
      code_input    = mo.ui.text(value="8306", label="銘柄コード")
      interval_slider = mo.ui.slider(3, 30, value=5, label="更新間隔(秒)")
      polling_switch  = mo.ui.switch(label="ポーリング開始")
      mo.hstack([code_input, interval_slider, polling_switch])

    [cell: chart_display]
      widget = LightweightChartWidget()
      widget.options = height:500, showVolume:True, dark theme
      builder = MinuteBarBuilder()
      mo.ui.anywidget(widget)

    [cell: poller]
      ui_controls セルに依存
      stop_event で前回スレッドを安全に停止 → 新スレッド起動
      スレッド内: while ループで
        get_current_price → builder.push → widget.append_bars or update_bar_fast
      kabuステーション未起動時は mo.callout でエラー表示（クラッシュ禁止）
      mo.stop(not polling_switch.value) でスイッチ OFF 時は早期リターン

  注意: ポーリング切り替え時にチャートがリセットされてはならない

---

## Phase 3: テスト（並列起動 — 3エージェント）

### Tester A — 静的テスト（構文・import・単体）

subagent_type: Bash

テスト1: py_compile で構文チェック
テスト2: sys.path を設定して from kabusap / from chart が成功するか
テスト3: MinuteBarBuilder を exec してインスタンス化・push・分境界確定を確認
  - push() で open/high/low/close が更新されることを確認
  - 分境界（minute が変わった時）で confirmed が None でないことを確認

PASS/FAIL と詳細を報告。

---

### Tester B — kabuステーション疎通テスト

subagent_type: Bash

テスト1: curl --connect-timeout 3 http://localhost:18080/kabusapi/board/8306@1
テスト2: kabusap() を初期化して isEnable を確認
  True → /board/8306@1 を叩いて CurrentPrice を確認
  False → SKIP（kabuステーション未起動は許容）

判定: PASS / SKIP / FAIL を明確に報告

---

### Tester C — marimo ヘッドレス起動テスト

subagent_type: Bash

timeout 8秒で marimo run blacksheep.py --headless --port 2723 を実行
出力の先頭 40 行を確認

判定:
  "Uvicorn running" or "Application running" → PASS
  "Error" / "Traceback" / "ModuleNotFoundError" → FAIL（内容を報告）

---

## Phase 4: 修正（テスト FAIL 時のみ）

subagent_type: general-purpose

入力: Orchestrator が Phase 3 テスト結果を渡す

役割:
1. エラー内容を分析して原因を特定
2. blacksheep.py を修正（kabusap.py / chart.py は変更禁止）
3. Tester A（静的テスト）相当を自分で実行して PASS を確認
4. 修正内容と理由を Orchestrator に報告

繰り返し上限: 3回（それ以上は人間にエスカレーション）

---

## 成功条件チェックリスト

- py_compile エラーなし（Tester A）
- import が成功する（Tester A）
- MinuteBarBuilder の分足境界で確定バーが返る（Tester A）
- marimo headless 起動でクラッシュしない（Tester C）
- kabuステーション起動時: チャートにローソク足が表示（Tester B + 目視）
- kabuステーション未起動時: UI は動作しエラーメッセージが出る
- ポーリング OFF → ON 切り替えでチャートがリセットされない

---

## Claude Code での起動手順

Step 1: Orchestrator を起動
  Task(subagent_type="general-purpose", description="統括", prompt="Orchestratorのプロンプト")

Step 2: Orchestrator が内部で順に起動

  Phase 1（並列 — 同一メッセージに2つ）:
    Task(subagent_type="Explore", description="kabusap調査",  prompt="Explorer A")
    Task(subagent_type="Explore", description="chart.py調査", prompt="Explorer B")

  Phase 2（順次）:
    Task(subagent_type="general-purpose", description="実装", prompt="Implementer")

  Phase 3（並列 — 同一メッセージに3つ）:
    Task(subagent_type="Bash", description="静的テスト",       prompt="Tester A")
    Task(subagent_type="Bash", description="API疎通テスト",    prompt="Tester B")
    Task(subagent_type="Bash", description="marimo起動テスト", prompt="Tester C")

  Phase 4（FAIL 時のみ）:
    Task(subagent_type="general-purpose", description="修正", prompt="Fixer")

---

## 注意事項

- kabusap.py / chart.py は変更禁止
- blacksheep.py は上書き対象（バックテスト内容を削除してよい）
- .env に KABUSAP_API_PASSWORD が必要
- Orchestrator は各 agent_id を保持し resume で追加調査可能
