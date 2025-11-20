# <img src="img/logo.drawio.svg" alt="BackcastPro Logo" width="40" height="24"> 開発者向けガイド

BackcastProの開発に参加するためのガイドです。

## 目次

- [開発環境のセットアップ](#開発環境のセットアップ)
- [プロジェクト構造](#プロジェクト構造)
- [アーキテクチャ](#アーキテクチャ)
- [コーディング規約](#コーディング規約)
- [テスト](#テスト)
- [コントリビューション](#コントリビューション)
- [リリースプロセス](#リリースプロセス)

## 開発環境のセットアップ

### 必要なツール

- Python 3.9+
- Git
- pip
- テキストエディタ（VS Code推奨）

### セットアップ手順

1. **リポジトリをクローン**
```powershell
git clone https://github.com/BackcastPro/BackcastPro.git
cd BackcastPro
```

2. **仮想環境を作成**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. **依存関係をインストール**
```powershell
python -m pip install -e .
python -m pip install -r requirements.txt
```

4. **開発用依存関係をインストール**
```powershell
python -m pip install pytest pytest-cov black flake8 mypy
```

### VS Code設定

`.vscode/settings.json`を作成：

```json
{
    "python.defaultInterpreterPath": ".\\.venv\\Scripts\\python.exe",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"]
}
```

## プロジェクト構造

```
BackcastPro/
├── src/
│   └── BackcastPro/
│       ├── __init__.py          # メインパッケージ
│       ├── backtest.py          # バックテストエンジン
│       ├── strategy.py          # 戦略基底クラス
│       ├── _broker.py           # ブローカー実装
│       ├── _stats.py            # 統計計算
│       ├── order.py             # 注文クラス
│       ├── position.py          # ポジションクラス
│       ├── trade.py             # トレードクラス
│       └── data/
│           ├── __init__.py
│           └── JapanStock.py    # データ取得
├── tests/                       # テストファイル
├── docs/                        # ドキュメント
├── examples/                    # サンプルコード
├── pyproject.toml              # プロジェクト設定
├── requirements.txt            # 依存関係
└── README.md                   # プロジェクト説明
```

## アーキテクチャ

### 主要コンポーネント

#### 1. Backtestクラス
- バックテストの実行を管理
- データと戦略を統合
- 結果の計算と返却

#### 2. Strategyクラス
- トレーディング戦略の基底クラス
- ユーザーが戦略を実装するためのインターフェース

#### 3. _Brokerクラス
- 注文の実行と管理
- ポジションとトレードの追跡
- 手数料とスプレッドの計算

#### 4. データモジュール
- 外部APIからのデータ取得
- データの前処理と変換

### データフロー

```
1. データ取得
   ↓
2. 戦略初期化 (Strategy.init)
   ↓
3. バックテスト実行 (Backtest.run)
   ↓
4. 各タイムスタンプで戦略実行 (Strategy.next(current_time))
   ↓
5. 注文処理 (_Broker.next(current_time))
   ↓
6. 統計計算 (_stats.compute_stats)
   ↓
7. 結果返却
```

### クラス図

```mermaid
classDiagram
    class Backtest {
        +data: dict[str, DataFrame]
        +strategy: Strategy
        +run() Series
    }
    
    class Strategy {
        +init()
        +next(current_time)
        +buy() Order
        +sell() Order
    }
    
    class _Broker {
        +equity: float
        +position: Position
        +trades: List[Trade]
        +next(current_time)
        +new_order() Order
    }
    
    class Order {
        +size: float
        +limit: float
        +stop: float
        +sl: float
        +tp: float
    }
    
    class Position {
        +size: float
        +is_long: bool
        +is_short: bool
        +close()
    }
    
    class Trade {
        +entry_price: float
        +exit_price: float
        +pl: float
        +close()
    }
    
    Backtest --> Strategy
    Backtest --> _Broker
    Strategy --> _Broker
    _Broker --> Order
    _Broker --> Position
    _Broker --> Trade
```

## コーディング規約

### Pythonスタイル

- **PEP 8**に準拠
- **Black**でフォーマット
- **flake8**でリント
- **mypy**で型チェック

### 命名規則

- **クラス名**: PascalCase (例: `Backtest`, `Strategy`)
- **関数名**: snake_case (例: `run`, `calculate_stats`)
- **変数名**: snake_case (例: `data`, `strategy`)
- **定数名**: UPPER_SNAKE_CASE (例: `DEFAULT_CASH`)

### ドキュメント

- **docstring**はGoogle形式を使用
- **型ヒント**を必須とする
- **コメント**は日本語で記述

### 例

```python
def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    RSI（相対力指数）を計算します。
    
    Args:
        data: OHLCVデータを含むDataFrame
        period: RSIの計算期間（デフォルト: 14）
    
    Returns:
        RSI値を含むSeries
    
    Raises:
        ValueError: データが空の場合
    """
    if data.empty:
        raise ValueError("データが空です")
    
    # RSI計算ロジック
    delta = data['Close'].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    
    rs = avg_gain / (avg_loss.replace(0, pd.NA))
    return 100 - (100 / (1 + rs))
```

## テスト

### テスト構造

```
tests/
├── test_backtest.py      # バックテストのテスト
├── test_strategy.py      # 戦略のテスト
├── test_broker.py        # ブローカーのテスト
├── test_data.py          # データ取得のテスト
└── fixtures/             # テストデータ
    ├── sample_data.csv
    └── test_strategies.py
```

### テストの実行

```powershell
# 全テストを実行
python -m pytest

# カバレッジ付きで実行
python -m pytest --cov=BackcastPro

# 特定のテストを実行
python -m pytest tests/test_backtest.py

# 詳細な出力で実行
python -m pytest -v
```

### テストの書き方

```python
import pytest
import pandas as pd
from BackcastPro import Backtest, Strategy

class TestStrategy(Strategy):
    def init(self):
        pass
    
    def next(self, current_time):
        for code, df in self.data.items():
            if len(df) == 1:
                self.buy(code=code)

def test_backtest_basic():
    """基本的なバックテストのテスト"""
    # テストデータを作成
    data = pd.DataFrame({
        'Open': [100, 101, 102],
        'High': [105, 106, 107],
        'Low': [99, 100, 101],
        'Close': [104, 105, 106],
        'Volume': [1000, 1100, 1200]
    }, index=pd.date_range('2023-01-01', periods=3))
    
    # バックテストを実行
    bt = Backtest({'TEST': data}, TestStrategy, cash=10000)
    results = bt.run()
    
    # 結果を検証
    assert results['Return [%]'] > 0
    assert results['# Trades'] > 0
    assert results['_strategy'] == 'TestStrategy'

def test_strategy_buy_sell():
    """戦略の買い売りロジックのテスト"""
    strategy = TestStrategy(None, None)
    
    # モックデータでテスト
    mock_data = pd.DataFrame({
        'Close': [100, 101, 102]
    })
    strategy._data = mock_data
    
    # 戦略を実行
    strategy.next(pd.Timestamp('2023-01-01'))
    
    # 結果を検証
    assert strategy.position.size > 0
```

### フィクスチャの使用

```python
@pytest.fixture
def sample_data():
    """サンプルデータのフィクスチャ"""
    return pd.DataFrame({
        'Open': [100, 101, 102, 103, 104],
        'High': [105, 106, 107, 108, 109],
        'Low': [99, 100, 101, 102, 103],
        'Close': [104, 105, 106, 107, 108],
        'Volume': [1000, 1100, 1200, 1300, 1400]
    }, index=pd.date_range('2023-01-01', periods=5))

@pytest.fixture
def simple_strategy():
    """シンプルな戦略のフィクスチャ"""
    class SimpleStrategy(Strategy):
        def init(self):
            pass
        def next(self, current_time):
            if len(self.data) == 1:
                self.buy()
    return SimpleStrategy

def test_with_fixtures(sample_data, simple_strategy):
    """フィクスチャを使用したテスト"""
    bt = Backtest(sample_data, simple_strategy)
    results = bt.run()
    assert results['Return [%]'] > 0
```

## コントリビューション

### コントリビューションの流れ

1. **Issueを作成** - バグ報告や機能要求
2. **Fork** - リポジトリをフォーク
3. **ブランチ作成** - 機能ブランチを作成
4. **開発** - コードを実装
5. **テスト** - テストを実行
6. **Pull Request** - PRを作成
7. **レビュー** - コードレビューを受ける
8. **マージ** - メインブランチにマージ

### ブランチ命名規則

- `feature/機能名` - 新機能
- `bugfix/バグ名` - バグ修正
- `docs/ドキュメント名` - ドキュメント更新
- `refactor/リファクタリング名` - リファクタリング

### コミットメッセージ

```
<type>(<scope>): <subject>

<body>

<footer>
```

**例:**
```
feat(backtest): プログレスバーを追加

バックテスト実行中にプログレスバーを表示する機能を追加。
tqdmライブラリを使用して実装。

Closes #123
```

### Pull Request

PRを作成する際は以下を含めてください：

1. **変更内容の説明**
2. **テスト結果**
3. **スクリーンショット**（UI変更の場合）
4. **関連Issue**へのリンク

### コードレビュー

レビュー時は以下を確認：

1. **コード品質** - 可読性、保守性
2. **テスト** - テストカバレッジ
3. **ドキュメント** - 更新の必要性
4. **パフォーマンス** - 性能への影響

## リリースプロセス

### バージョン管理

- **セマンティックバージョニング**を使用
- **MAJOR.MINOR.PATCH**形式
- **MAJOR**: 破壊的変更
- **MINOR**: 新機能追加
- **PATCH**: バグ修正

### リリース手順

1. **バージョン更新**
```toml
# pyproject.toml の version を更新
version = "0.1.0"
```

2. **CHANGELOG更新**
```markdown
## [0.1.0] - 2023-01-01

### Added
- 新機能A
- 新機能B

### Changed
- 既存機能の改善

### Fixed
- バグ修正A
- バグ修正B
```

3. **テスト実行**
```powershell
python -m pytest
python -m pytest --cov=BackcastPro
```

4. **ビルド**
```powershell
python -m build
```

5. **PyPIにアップロード**
```powershell
python -m twine upload dist/*
```

6. **Gitタグ作成**
```powershell
git tag v0.1.0
git push origin v0.1.0
```

### 自動化

GitHub Actionsを使用して以下を自動化：

- **テスト実行** - PR作成時
- **コード品質チェック** - リント、フォーマット
- **ビルド** - リリース時
- **PyPIアップロード** - タグ作成時

## パフォーマンス最適化

### プロファイリング

```python
import cProfile
import pstats
from BackcastPro import Backtest

def profile_backtest():
    """バックテストのプロファイリング"""
    # プロファイリングを開始
    profiler = cProfile.Profile()
    profiler.enable()
    
    # バックテストを実行
    bt = Backtest(data, MyStrategy)
    results = bt.run()
    
    # プロファイリングを停止
    profiler.disable()
    
    # 結果を表示
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)

if __name__ == "__main__":
    profile_backtest()
```

### メモリ使用量の監視

```python
import psutil
import os

def monitor_memory():
    """メモリ使用量を監視"""
    process = psutil.Process(os.getpid())
    
    # バックテスト前
    memory_before = process.memory_info().rss / 1024 / 1024  # MB
    
    # バックテスト実行
    bt = Backtest(data, MyStrategy)
    results = bt.run()
    
    # バックテスト後
    memory_after = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"メモリ使用量: {memory_after - memory_before:.2f} MB")
```

## まとめ

この開発者向けガイドでは、BackcastProの開発に参加するための情報を提供しました：

1. **開発環境のセットアップ** - 必要なツールと手順
2. **プロジェクト構造** - コードの組織
3. **アーキテクチャ** - システムの設計
4. **コーディング規約** - コードスタイルと品質
5. **テスト** - テストの書き方と実行
6. **コントリビューション** - 貢献の方法
7. **リリースプロセス** - リリースの手順

これらの情報を参考に、BackcastProの開発に参加してください。
